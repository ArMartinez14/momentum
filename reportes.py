# reportes.py — Reportes + Resumen "Semana X de Y" por bloque
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, date
import json, re
import pandas as pd
from collections import defaultdict

DIAS_VALIDOS = {"1","2","3","4","5"}

def _doc_id_from_mail(mail: str) -> str:
    return mail.replace('@','_').replace('.','_')

def _comentarios_ack_map(_db, correo_entrenador: str) -> dict[str, str]:
    try:
        doc_id = _doc_id_from_mail(correo_entrenador)
        snap = _db.collection("comentarios_ack").document(doc_id).get()
        data = snap.to_dict() if snap.exists else {}
        if not isinstance(data, dict):
            return {}
        return {str(k).strip().lower(): str(v) for k, v in data.items() if isinstance(k, str) and v}
    except Exception:
        return {}

# ---------- Utils ----------
def init_firebase():
    if not firebase_admin._apps:
        cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)

def lunes_actual() -> date:
    hoy = datetime.now().date()
    return hoy - timedelta(days=hoy.weekday())

def es_no_vacio(v):
    if v is None: return False
    if isinstance(v, str): return v.strip() != ""
    return True

def parse_fecha_de_id(doc_id: str) -> str | None:
    m = re.search(r"_(\d{4})_(\d{2})_(\d{2})$", doc_id)
    if not m: return None
    yyyy, mm, dd = m.groups()
    try:
        return date(int(yyyy), int(mm), int(dd)).isoformat()
    except Exception:
        return None

def filas_series_data(cliente, dia_label, ejercicio_nombre, series_data, comentario=""):
    filas = []
    comentario = (comentario or "").strip()
    tiene_series = False
    if not isinstance(series_data, list): return filas
    for idx, s in enumerate(series_data):
        if isinstance(s, dict) and any(es_no_vacio(v) for v in s.values()):
            fila = {"cliente": cliente, "día": dia_label, "ejercicio": ejercicio_nombre, "serie": idx + 1}
            for k, v in s.items():
                fila[str(k)] = v
            if comentario:
                fila["comentario"] = comentario
            filas.append(fila)
            tiene_series = True
    if comentario and not tiene_series:
        filas.append({
            "cliente": cliente,
            "día": dia_label,
            "ejercicio": ejercicio_nombre,
            "serie": "-",
            "comentario": comentario,
        })
    return filas

# ---------- Vista ----------
def ver_reportes():
    st.title("📊 Reportes de Sesión (agrupados)")

    init_firebase()
    db = firestore.client()

    correo_entrenador = st.session_state.get("correo", "").strip().lower()
    if not correo_entrenador:
        st.warning("Debes iniciar sesión para ver los reportes.")
        return

    # Filtros
    fecha_lunes = st.date_input("Semana (selecciona el lunes)", value=lunes_actual())
    c1, c2, c3 = st.columns(3)
    with c1: filtro_cliente = st.text_input("Filtrar por cliente (opcional)")
    with c2: filtro_ejercicio = st.text_input("Filtrar por ejercicio (opcional)")
    with c3: solo_con_datos = st.checkbox("Solo ejercicios con datos en series", value=True)

    st.caption("Cargando datos…")

    col = db.collection("rutinas_semanales")
    try:
        docs = list(
            col.where("entrenador", "==", correo_entrenador)
               .where("fecha_lunes", "==", fecha_lunes.isoformat())
               .stream()
        )
    except Exception:
        try:
            docs = list(col.where("fecha_lunes", "==", fecha_lunes.isoformat()).stream())
        except Exception:
            docs = list(col.limit(300).stream())

    ack_map = _comentarios_ack_map(db, correo_entrenador)

    # =========================
    # 1) RESUMEN: "Semana X de Y" por bloque (para esta semana)
    # =========================
    avances = []  # [(cliente, semana_idx, total, bloque_id)]
    # preparar pares únicos (correo_cliente, bloque_id) para minimizar lecturas
    pares = []  # [(correo_cliente, bloque_id, cliente_nombre)]
    for d in docs:
        if not d.exists: continue
        doc = d.to_dict() or {}
        if (doc.get("entrenador","").strip().lower() != correo_entrenador): 
            continue
        cliente_nombre = doc.get("cliente") or doc.get("nombre") or "(sin nombre)"
        correo_cliente = doc.get("correo") or ""  # correo del deportista
        bloque_id = doc.get("bloque_rutina")
        if not correo_cliente or not bloque_id: 
            continue
        pares.append((correo_cliente, str(bloque_id), cliente_nombre))

    # quitar duplicados
    pares_unicos = {}
    for c_mail, b_id, c_nombre in pares:
        pares_unicos[(c_mail, b_id)] = c_nombre  # conserva último nombre

    # cache de fechas por (correo_cliente, bloque_id)
    fechas_por_bloque = {}
    for (c_mail, b_id), c_nombre in pares_unicos.items():
        q = (
            col.where("correo", "==", c_mail)
               .where("bloque_rutina", "==", b_id)
        )
        semanas_bloque = list(q.stream())
        fechas = []
        for r in semanas_bloque:
            dct = r.to_dict() or {}
            f = dct.get("fecha_lunes") or parse_fecha_de_id(r.id)
            if f: fechas.append(f)
        fechas = sorted(set(fechas))
        fechas_por_bloque[(c_mail, b_id)] = fechas

    # construir avance por cada doc de esta semana
    for d in docs:
        if not d.exists: continue
        doc = d.to_dict() or {}
        if (doc.get("entrenador","").strip().lower() != correo_entrenador): 
            continue
        cliente_nombre = doc.get("cliente") or doc.get("nombre") or "(sin nombre)"
        correo_cliente = doc.get("correo") or ""
        bloque_id = doc.get("bloque_rutina")
        if not correo_cliente or not bloque_id:
            continue
        fechas = fechas_por_bloque.get((correo_cliente, str(bloque_id)), [])
        try:
            semana_idx = fechas.index(fecha_lunes.isoformat()) + 1
            total = len(fechas)
            avances.append((cliente_nombre, semana_idx, total, str(bloque_id)))
        except ValueError:
            # semana no encontrada en ese bloque (puede ser otra semana cargada manualmente)
            avances.append((cliente_nombre, None, len(fechas), str(bloque_id)))

    if avances:
        st.subheader("🧭 Resumen de avance de bloque (semana seleccionada)")
        # ordenar por nombre
        avances = sorted(avances, key=lambda x: x[0].lower())
        for nombre, idx, total, b in avances:
            if idx is None or total == 0:
                st.markdown(f"- **{nombre}** — bloque `{b}` (sin posición para esta semana)")
            else:
                st.markdown(f"- **{nombre}** — Semana **{idx}** de **{total}** (bloque `{b}`)")
        st.divider()

    # =========================
    # 2) REPORTE AGRUPADO Cliente -> Día (series_data + RPE)
    # =========================
    filas_series, filas_rpe = [], []

    comentarios_vistos = dict(ack_map)

    for d in docs:
        if not d.exists: continue
        doc = d.to_dict() or {}

        # seguridad por si el query no filtró
        if (doc.get("entrenador","").strip().lower() != correo_entrenador):
            continue
        if (doc.get("fecha_lunes") or parse_fecha_de_id(d.id)) != fecha_lunes.isoformat():
            continue

        cliente = doc.get("cliente") or doc.get("nombre") or "(sin nombre)"
        rutina = doc.get("rutina", {}) or {}
        correo_cliente = (doc.get("correo") or "").strip().lower()
        fecha_iso = fecha_lunes.isoformat()

        for dia_key, dia_node in rutina.items():
            if str(dia_key) not in DIAS_VALIDOS:
                continue
            dia_label = f"Día {dia_key}"

            # A) día = objeto {ejercicios:[...], rpe: X}
            if isinstance(dia_node, dict):
                if "rpe" in dia_node and es_no_vacio(dia_node.get("rpe")):
                    filas_rpe.append({"cliente": cliente, "día": dia_label, "rpe": dia_node.get("rpe")})

                ejercicios = dia_node.get("ejercicios", [])
                if isinstance(ejercicios, list):
                    for ej in ejercicios:
                        if not isinstance(ej, dict): 
                            continue
                        nombre_ej = ej.get("ejercicio") or ej.get("nombre") or ej.get("id_ejercicio") or "(sin nombre)"
                        if filtro_ejercicio and filtro_ejercicio.lower() not in str(nombre_ej).lower():
                            continue
                        series_data = ej.get("series_data", [])
                        comentario = (ej.get("comentario") or "").strip()
                        if comentario and correo_cliente:
                            prev = comentarios_vistos.get(correo_cliente)
                            if prev is None or fecha_iso > prev:
                                comentarios_vistos[correo_cliente] = fecha_iso
                        if solo_con_datos:
                            tiene_datos = any(isinstance(s, dict) and any(es_no_vacio(v) for v in s.values()) for s in series_data)
                            if not tiene_datos and not comentario:
                                continue
                        filas_series.extend(filas_series_data(cliente, dia_label, nombre_ej, series_data, comentario=comentario))

            # B) día = lista de ejercicios
            elif isinstance(dia_node, list):
                # rpe como rpe_1 / rpe1 a nivel de rutina
                for rk in (f"rpe_{dia_key}", f"rpe{dia_key}"):
                    if rk in rutina and es_no_vacio(rutina.get(rk)):
                        filas_rpe.append({"cliente": cliente, "día": dia_label, "rpe": rutina.get(rk)})
                        break

                for ej in dia_node:
                    if not isinstance(ej, dict): 
                        continue
                    nombre_ej = ej.get("ejercicio") or ej.get("nombre") or ej.get("id_ejercicio") or "(sin nombre)"
                    if filtro_ejercicio and filtro_ejercicio.lower() not in str(nombre_ej).lower():
                        continue
                    series_data = ej.get("series_data", [])
                    comentario = (ej.get("comentario") or "").strip()
                    if comentario and correo_cliente:
                        prev = comentarios_vistos.get(correo_cliente)
                        if prev is None or fecha_iso > prev:
                            comentarios_vistos[correo_cliente] = fecha_iso
                    if solo_con_datos:
                        tiene_datos = any(isinstance(s, dict) and any(es_no_vacio(v) for v in s.values()) for s in series_data)
                        if not tiene_datos and not comentario:
                            continue
                    filas_series.extend(filas_series_data(cliente, dia_label, nombre_ej, series_data, comentario=comentario))

    if comentarios_vistos:
        try:
            ack_doc = db.collection("comentarios_ack").document(_doc_id_from_mail(correo_entrenador))
            ack_doc.set(comentarios_vistos, merge=True)
        except Exception:
            pass

    if filtro_cliente:
        f = filtro_cliente.strip().lower()
        filas_series = [x for x in filas_series if f in str(x.get("cliente","")).lower()]
        filas_rpe    = [x for x in filas_rpe    if f in str(x.get("cliente","")).lower()]

    # ------- Vista agrupada Cliente -> Día -------
    st.subheader("🧩 Reporte agrupado por Cliente y Día")

    if not filas_series and not filas_rpe:
        st.info("No hay registros para los filtros seleccionados.")
        return

    rpe_map = {(row["cliente"], row["día"]): row["rpe"] for row in filas_rpe}

    grupos = defaultdict(lambda: defaultdict(list))
    all_cols_dyn = set()
    for row in filas_series:
        cliente = row["cliente"]; dia = row["día"]
        grupos[cliente][dia].append(row)
        for k in row.keys():
            if k not in {"cliente","día","ejercicio","serie"}:
                all_cols_dyn.add(k)

    clientes_orden = sorted(grupos.keys())
    base_cols = ["ejercicio","serie"] + sorted(all_cols_dyn)

    for cliente in clientes_orden:
        st.markdown(f"### 👤 {cliente}")
        dias_orden = sorted(grupos[cliente].keys(), key=lambda x: int(x.split()[-1]))
        for dia in dias_orden:
            st.markdown(f"**{dia}**")
            rows = grupos[cliente][dia]
            df = pd.DataFrame(rows)
            cols_presentes = [c for c in base_cols if c in df.columns]
            df_show = df[["ejercicio","serie"] + [c for c in cols_presentes if c not in {"ejercicio","serie"}]]
            df_show = df_show.sort_values(["ejercicio","serie"], kind="stable")
            st.dataframe(df_show, use_container_width=True)

            rpe_val = rpe_map.get((cliente, dia))
            if rpe_val is not None and es_no_vacio(rpe_val):
                st.markdown(f"**RPE de la sesión:** `{rpe_val}`")
            st.divider()

    # Descarga CSV plano
    if filas_series:
        st.download_button(
            "⬇️ Descargar CSV (series_data plano)",
            data=pd.DataFrame(filas_series).to_csv(index=False).encode("utf-8"),
            file_name=f"reportes_series_{fecha_lunes.isoformat()}.csv",
            mime="text/csv",
        )
