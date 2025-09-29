# reportes.py — Reportes + Resumen "Semana X de Y" por bloque
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, date
import json, re
import pandas as pd
from collections import defaultdict

DIAS_VALIDOS = {"1","2","3","4","5"}

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

def filas_series_data(cliente, dia_label, ejercicio_nombre, series_data):
    filas = []
    if not isinstance(series_data, list): return filas
    for idx, s in enumerate(series_data):
        if isinstance(s, dict) and any(es_no_vacio(v) for v in s.values()):
            fila = {"cliente": cliente, "día": dia_label, "ejercicio": ejercicio_nombre, "serie": idx + 1}
            for k, v in s.items():
                fila[str(k)] = v
            filas.append(fila)
    return filas
        })
    return filas
def normalizar_ejercicios(node):
    if node is None:
        return []
    if isinstance(node, list):
        if len(node) == 1 and isinstance(node[0], dict) and "ejercicios" in node[0]:
            return normalizar_ejercicios(node[0]["ejercicios"])
        return [e for e in node if isinstance(e, dict)]
    if isinstance(node, dict):
        if "ejercicios" in node:
            return normalizar_ejercicios(node.get("ejercicios"))
        claves_numericas = [k for k in node.keys() if str(k).isdigit()]
        if claves_numericas:
            try:
                claves_numericas.sort(key=lambda x: int(x))
                return [node[k] for k in claves_numericas if isinstance(node[k], dict)]
            except Exception:
                return [node[k] for k in node if isinstance(node[k], dict)]
        return [v for v in node.values() if isinstance(v, dict)]
    return []
# ---------- Vista ----------
def ver_reportes():
    st.title("📊 Reportes de Sesión (agrupados)")
                if "rpe" in dia_node and es_no_vacio(dia_node.get("rpe")):
                    filas_rpe.append({"cliente": cliente, "día": dia_label, "rpe": dia_node.get("rpe")})
                ejercicios = normalizar_ejercicios(dia_node)
                for ej in ejercicios:
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
                for rk in (f"rpe_{dia_key}", f"rpe{dia_key}"):
                    if rk in rutina and es_no_vacio(rutina.get(rk)):
                        filas_rpe.append({"cliente": cliente, "día": dia_label, "rpe": rutina.get(rk)})
                        break
                ejercicios = normalizar_ejercicios(dia_node)
                for ej in ejercicios:
                    nombre_ej = ej.get("ejercicio") or ej.get("nombre") or ej.get("id_ejercicio") or "(sin nombre)"
                    if filtro_ejercicio and filtro_ejercicio.lower() not in str(nombre_ej).lower():
                        continue
                    series_data = ej.get("series_data", [])
                    if solo_con_datos:
                        tiene_datos = any(isinstance(s, dict) and any(es_no_vacio(v) for v in s.values()) for s in series_data)
                        if not tiene_datos:
                            continue
                    filas_series.extend(filas_series_data(cliente, dia_label, nombre_ej, series_data))

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
