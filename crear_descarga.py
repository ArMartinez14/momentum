import streamlit as st
from firebase_admin import credentials, firestore
from datetime import datetime
import firebase_admin
import json
import copy
import re

# === INICIALIZAR FIREBASE ===
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# ========= Utilidades tomadas del estilo de ver_rutinas =========

def normalizar_correo(correo: str) -> str:
    return (correo or "").strip().lower().replace("@", "_").replace(".", "_")

def solo_dias_keys(rutina_dict: dict) -> list[str]:
    """Devuelve SOLO claves de días que son numéricas ('1','2',...)."""
    if not isinstance(rutina_dict, dict):
        return []
    return sorted([k for k in rutina_dict.keys() if str(k).isdigit()], key=lambda x: int(x))

def _to_ej_dict(x):
    """Normaliza un 'ejercicio' a dict si viene como string/otros."""
    if isinstance(x, dict):
        return x
    if isinstance(x, str):
        return {
            "bloque": "",
            "seccion": "",
            "circuito": "",
            "ejercicio": x,
            "detalle": "",
            "series": "",
            "repeticiones": "",
            "reps_min": "",
            "reps_max": "",
            "peso": "",
            "tiempo": "",
            "velocidad": "",
            "rir": "",
            "tipo": "",
            "video": "",
        }
    return {}

def obtener_lista_ejercicios(data_dia):
    """
    Devuelve SIEMPRE una lista de dicts (ejercicios).
    Soporta:
      - {"ejercicios": {"0": {...}, "1": {...}}}
      - {"0": {...}, "1": {...}}
      - [ {...}, {...} ]
    """
    if data_dia is None:
        return []

    if isinstance(data_dia, dict):
        # 1) Rama con 'ejercicios'
        if "ejercicios" in data_dia:
            ejercicios = data_dia["ejercicios"]
            if isinstance(ejercicios, dict):
                try:
                    pares = sorted(ejercicios.items(), key=lambda kv: int(kv[0]))
                    return [_to_ej_dict(v) for _, v in pares if isinstance(v, dict) or isinstance(v, str)]
                except Exception:
                    return [_to_ej_dict(v) for v in ejercicios.values() if isinstance(v, (dict, str))]
            elif isinstance(ejercicios, list):
                return [_to_ej_dict(e) for e in ejercicios if isinstance(e, (dict, str))]
            else:
                return []

        # 2) Mapa indexado {"0": {...}}
        claves_num = [k for k in data_dia.keys() if str(k).isdigit()]
        if claves_num:
            try:
                pares = sorted(((k, data_dia[k]) for k in claves_num), key=lambda kv: int(kv[0]))
                return [_to_ej_dict(v) for _, v in pares if isinstance(v, (dict, str))]
            except Exception:
                return [_to_ej_dict(data_dia[k]) for k in data_dia if isinstance(data_dia[k], (dict, str))]

        # 3) Fallback: tomar values dict
        return [_to_ej_dict(v) for v in data_dia.values() if isinstance(v, (dict, str))]

    if isinstance(data_dia, list):
        # si es lista con un dict que trae 'ejercicios'
        if len(data_dia) == 1 and isinstance(data_dia[0], dict) and "ejercicios" in data_dia[0]:
            return obtener_lista_ejercicios(data_dia[0])
        return [_to_ej_dict(e) for e in data_dia if isinstance(e, (dict, str))]

    return []

# ================================================================

def descarga_rutina():
    st.title("📉 Crear Rutina de Descarga")

    # === Buscar clientes (nombre -> correo) ===
    docs = db.collection("rutinas_semanales").stream()
    clientes_dict = {}
    for doc in docs:
        data = doc.to_dict() or {}
        nombre = data.get("cliente")
        correo = data.get("correo")
        if nombre and correo:
            clientes_dict[nombre] = correo

    if not clientes_dict:
        st.warning("❌ No hay clientes con rutinas.")
        return

    nombres_clientes = sorted(clientes_dict.keys())
    nombre_sel = st.selectbox("Selecciona el cliente:", nombres_clientes)
    if not nombre_sel:
        return

    correo = clientes_dict[nombre_sel]

    # === Obtener última semana del cliente ===
    docs = db.collection("rutinas_semanales").where("correo", "==", correo).stream()
    semanas_dict = {}
    for doc in docs:
        data = doc.to_dict() or {}
        fecha_lunes = data.get("fecha_lunes")
        if fecha_lunes:
            semanas_dict[fecha_lunes] = doc.id

    if not semanas_dict:
        st.warning("❌ No hay rutinas para este cliente.")
        return

    ultima_semana = max(semanas_dict.keys())
    doc_id_semana = semanas_dict[ultima_semana]
    st.info(f"Última semana encontrada: **{ultima_semana}**")

    # === Obtener rutina base ===
    doc_data = db.collection("rutinas_semanales").document(doc_id_semana).get().to_dict() or {}
    rutina_original = doc_data.get("rutina", {}) or {}
    rutina_modificada = copy.deepcopy(rutina_original)

    modalidad = st.selectbox(
        "Selecciona modalidad de descarga:",
        [
            "Mantener series/reps y bajar 20% peso",
            "Mantener pesos y bajar 1 serie y 3 reps (min y max)",
            "Elección manual",
        ],
    )

    # === APLICAR AJUSTES AUTOMÁTICOS (solo días numéricos) ===
    if modalidad == "Mantener series/reps y bajar 20% peso":
        for dia in solo_dias_keys(rutina_modificada):
            ejercicios = obtener_lista_ejercicios(rutina_modificada.get(dia, []))
            for ej in ejercicios:
                try:
                    peso_txt = str(ej.get("peso", "")).strip().replace(",", ".")
                    if peso_txt != "":
                        ej["peso"] = str(round(float(peso_txt) * 0.8, 1))
                except:
                    pass
            rutina_modificada[dia] = ejercicios  # normaliza formato

    elif modalidad == "Mantener pesos y bajar 1 serie y 3 reps (min y max)":
        for dia in solo_dias_keys(rutina_modificada):
            ejercicios = obtener_lista_ejercicios(rutina_modificada.get(dia, []))
            for ej in ejercicios:
                # series
                try:
                    series_txt = str(ej.get("series", "")).strip()
                    if series_txt.isdigit():
                        ej["series"] = str(max(1, int(series_txt) - 1))
                except:
                    pass
                # reps
                try:
                    reps_min = str(ej.get("reps_min", "")).strip()
                    reps_max = str(ej.get("reps_max", "")).strip()
                    reps_simple = str(ej.get("repeticiones", "")).strip()

                    if reps_min.isdigit() or reps_max.isdigit():
                        min_r = str(max(0, int(reps_min) - 3)) if reps_min.isdigit() else ""
                        max_r = str(max(0, int(reps_max) - 3)) if reps_max.isdigit() else ""
                        ej["reps_min"] = min_r
                        ej["reps_max"] = max_r
                        if not (min_r or max_r):
                            ej["repeticiones"] = ""
                    elif reps_simple.isdigit():
                        ej["repeticiones"] = str(max(0, int(reps_simple) - 3))
                except:
                    pass
            rutina_modificada[dia] = ejercicios  # normaliza

    elif modalidad == "Elección manual":
        dias_disponibles = solo_dias_keys(rutina_modificada)
        if not dias_disponibles:
            st.warning("Esta rutina no tiene días numéricos para editar.")
            return

        dia_sel = st.selectbox("Selecciona el día a editar:", dias_disponibles, format_func=lambda x: f"Día {x}")

        ejercicios_dia = obtener_lista_ejercicios(rutina_modificada.get(dia_sel, []))
        bloques = sorted(list({str(ej.get("bloque", "") or "") for ej in ejercicios_dia}))
        if not bloques:
            bloques = [""]

        bloque_sel = st.selectbox("Selecciona el bloque:", bloques)

        ejercicios_editados = []
        for idx, ej in enumerate(ejercicios_dia):
            if str(ej.get("bloque", "") or "") != bloque_sel:
                continue
            st.markdown(f"**Ejercicio {idx + 1}**")
            c1, c2, c3, c4, c5 = st.columns([4, 1, 2, 2, 1])
            nuevo = ej.copy()
            nuevo["ejercicio"] = c1.text_input("Ejercicio", value=str(ej.get("ejercicio", "")), key=f"ej_{idx}_nombre")
            nuevo["series"] = c2.text_input("Series", value=str(ej.get("series", "")), key=f"ej_{idx}_series")
            # admite reps_min/max o repeticiones simple
            rep_min = str(ej.get("reps_min", "") or ej.get("repeticiones", "")).strip()
            rep_max = str(ej.get("reps_max", "")).strip()
            reps_input = rep_min if rep_max == "" else f"{rep_min}-{rep_max}"
            reps_txt = c3.text_input("Reps (min o min-max)", value=reps_input, key=f"ej_{idx}_reps")
            # guardar coherente
            if "-" in reps_txt:
                p = [t.strip() for t in reps_txt.split("-", 1)]
                nuevo["reps_min"] = p[0]
                nuevo["reps_max"] = p[1] if len(p) > 1 else ""
                nuevo["repeticiones"] = ""
            else:
                nuevo["reps_min"] = reps_txt
                nuevo["reps_max"] = ""
                nuevo["repeticiones"] = reps_txt

            nuevo["peso"] = c4.text_input("Peso", value=str(ej.get("peso", "")), key=f"ej_{idx}_peso")
            nuevo["rir"] = c5.text_input("RIR", value=str(ej.get("rir", "")), key=f"ej_{idx}_rir")
            ejercicios_editados.append((idx, nuevo))

        # ✅ Guardar el dict (no tupla)
        for idx, ej_dict in ejercicios_editados:
            if 0 <= idx < len(ejercicios_dia):
                ejercicios_dia[idx] = ej_dict

        rutina_modificada[dia_sel] = ejercicios_dia

    # === Previsualización (solo días numéricos) ===
    st.subheader("👀 Previsualización de la rutina de descarga")
    for dia in solo_dias_keys(rutina_modificada):
        st.markdown(f"**📅 Día {dia}**")
        for ej in obtener_lista_ejercicios(rutina_modificada.get(dia, [])):
            reps_min = ej.get("reps_min", "")
            reps_max = ej.get("reps_max", "")
            rep_simple = ej.get("repeticiones", "")
            if reps_min and reps_max:
                rep_str = f"{reps_min}-{reps_max}"
            else:
                rep_str = rep_simple or reps_min or reps_max or ""
            st.write(
                f"{ej.get('ejercicio','')} | Series: {ej.get('series','')} | "
                f"Reps: {rep_str} | Peso: {ej.get('peso','')} | RIR: {ej.get('rir','')}"
            )

    # === Guardar ===
    nueva_fecha = st.date_input("Fecha de inicio de rutina de descarga", datetime.now()).strftime("%Y-%m-%d")
    if st.button("💾 Guardar rutina de descarga"):
        nuevo_doc = (doc_data or {}).copy()
        nuevo_doc["fecha_lunes"] = nueva_fecha
        nuevo_doc["rutina"] = rutina_modificada  # mantiene también claves no numéricas como '2_rpe'
        nuevo_doc["tipo"] = "descarga"

        nuevo_doc_id = f"{normalizar_correo(correo)}_{nueva_fecha.replace('-', '_')}"
        db.collection("rutinas_semanales").document(nuevo_doc_id).set(nuevo_doc)
        st.success(f"✅ Rutina de descarga creada para la semana {nueva_fecha}")
