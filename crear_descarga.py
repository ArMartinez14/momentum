# crear_descarga.py — Descarga con preview tipo editor + edición manual en grilla (igual a editar_rutinas)
import streamlit as st
from firebase_admin import credentials, firestore
from datetime import datetime
import firebase_admin
import json
import copy

from app_core.utils import (
    empresa_de_usuario,
    EMPRESA_MOTION,
    EMPRESA_ASESORIA,
    EMPRESA_DESCONOCIDA,
    correo_a_doc_id,
)

# =============== 🔐 FIREBASE ===============
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# =============== 🧰 UTILIDADES COMUNES ===============
def normalizar_correo(correo: str) -> str:
    return (correo or "").strip().lower().replace("@", "_").replace(".", "_")

def solo_dias_keys(rutina_dict: dict) -> list[str]:
    if not isinstance(rutina_dict, dict):
        return []
    return sorted([k for k in rutina_dict.keys() if str(k).isdigit()], key=lambda x: int(x))

def _to_ej_dict(x):
    if isinstance(x, dict):
        return x
    if isinstance(x, str):
        return {
            "bloque": "", "seccion": "", "circuito": "", "ejercicio": x,
            "detalle": "", "series": "", "repeticiones": "",
            "reps_min": "", "reps_max": "", "peso": "", "tiempo": "",
            "velocidad": "", "rir": "", "tipo": "", "video": "",
        }
    return {}

def obtener_lista_ejercicios(data_dia):
    if data_dia is None:
        return []
    if isinstance(data_dia, dict):
        if "ejercicios" in data_dia:
            ejercicios = data_dia["ejercicios"]
            if isinstance(ejercicios, dict):
                try:
                    pares = sorted(ejercicios.items(), key=lambda kv: int(kv[0]))
                    return [_to_ej_dict(v) for _, v in pares if isinstance(v, (dict, str))]
                except Exception:
                    return [_to_ej_dict(v) for v in ejercicios.values() if isinstance(v, (dict, str))]
            elif isinstance(ejercicios, list):
                return [_to_ej_dict(e) for e in ejercicios if isinstance(e, (dict, str))]
            return []
        claves_num = [k for k in data_dia.keys() if str(k).isdigit()]
        if claves_num:
            try:
                pares = sorted(((k, data_dia[k]) for k in claves_num), key=lambda kv: int(kv[0]))
                return [_to_ej_dict(v) for _, v in pares if isinstance(v, (dict, str))]
            except Exception:
                return [_to_ej_dict(data_dia[k]) for k in data_dia if isinstance(data_dia[k], (dict, str))]
        return [_to_ej_dict(v) for v in data_dia.values() if isinstance(v, (dict, str))]
    if isinstance(data_dia, list):
        if len(data_dia) == 1 and isinstance(data_dia[0], dict) and "ejercicios" in data_dia[0]:
            return obtener_lista_ejercicios(data_dia[0])
        return [_to_ej_dict(e) for e in data_dia if isinstance(e, (dict, str))]
    return []

# =============== 📦 CARGAS (igual filosofía editor) ===============
@st.cache_data(show_spinner=False)
def cargar_ejercicios():
    docs = db.collection("ejercicios").stream()
    return { (d.to_dict() or {}).get("nombre",""): (d.to_dict() or {}) for d in docs if d.exists }

@st.cache_data(show_spinner=False)
def cargar_usuarios():
    docs = db.collection("usuarios").stream()
    return [doc.to_dict() for doc in docs if doc.exists]

@st.cache_data(show_spinner=False)
def cargar_implementos():
    impl = {}
    for doc in db.collection("implementos").stream():
        di = doc.to_dict() or {}
        di["pesos"] = di.get("pesos", [])
        impl[str(doc.id)] = di
    return impl

EJERCICIOS  = cargar_ejercicios()
USUARIOS    = cargar_usuarios()
IMPLEMENTOS = cargar_implementos()

# =============== 🔁 MAPEO (igual a editar_rutinas) ===============
COLUMNAS_TABLA = [
    "Circuito", "Sección", "Ejercicio", "Detalle",
    "Series", "RepsMin", "RepsMax", "Peso", "RIR",
    "Tiempo", "Velocidad", "Tipo", "Video",
    "Variable_1", "Cantidad_1", "Operacion_1", "Semanas_1",
    "Variable_2", "Cantidad_2", "Operacion_2", "Semanas_2",
    "Variable_3", "Cantidad_3", "Operacion_3", "Semanas_3",
    "BuscarEjercicio"
]

def _ejercicio_firestore_a_fila_ui(ej: dict) -> dict:
    fila = {k: "" for k in COLUMNAS_TABLA}
    seccion = ej.get("Sección") or ej.get("bloque") or ej.get("seccion") or ""
    if seccion not in ["Warm Up", "Work Out"]:
        seccion = "Warm Up" if (ej.get("circuito","") in ["A","B","C"]) else (seccion or "Work Out")
    fila["Sección"]   = seccion
    fila["Circuito"]  = ej.get("Circuito") or ej.get("circuito") or ""
    fila["Ejercicio"] = ej.get("Ejercicio") or ej.get("ejercicio") or ""
    if fila["Sección"] == "Work Out":
        fila["BuscarEjercicio"] = fila["Ejercicio"]
    fila["Detalle"]   = ej.get("Detalle")   or ej.get("detalle")   or ""
    fila["Series"]    = ej.get("Series")    or ej.get("series")    or ""
    fila["RIR"]       = ej.get("RIR")       or ej.get("rir")       or ""
    fila["Peso"]      = ej.get("Peso")      or ej.get("peso")      or ""
    fila["Tiempo"]    = ej.get("Tiempo")    or ej.get("tiempo")    or ""
    fila["Velocidad"] = ej.get("Velocidad") or ej.get("velocidad") or ""
    fila["Tipo"]      = ej.get("Tipo")      or ej.get("tipo")      or ""
    fila["Video"]     = ej.get("Video")     or ej.get("video")     or ""
    if "reps_min" in ej or "reps_max" in ej:
        fila["RepsMin"] = ej.get("reps_min","")
        fila["RepsMax"] = ej.get("reps_max","")
    elif "RepsMin" in ej or "RepsMax" in ej:
        fila["RepsMin"] = ej.get("RepsMin","")
        fila["RepsMax"] = ej.get("RepsMax","")
    else:
        rep = str(ej.get("repeticiones","")).strip()
        if "-" in rep:
            mn, mx = rep.split("-", 1)
            fila["RepsMin"], fila["RepsMax"] = mn.strip(), mx.strip()
        else:
            fila["RepsMin"], fila["RepsMax"] = rep, ""
    for p in (1,2,3):
        fila[f"Variable_{p}"]  = ej.get(f"Variable_{p}","")
        fila[f"Cantidad_{p}"]  = ej.get(f"Cantidad_{p}","")
        fila[f"Operacion_{p}"] = ej.get(f"Operacion_{p}","")
        fila[f"Semanas_{p}"]   = ej.get(f"Semanas_{p}","")
    return fila

def _f(v):
    try:
        s = str(v).strip().replace(",", ".")
        if s == "":
            return None
        if "-" in s:
            s = s.split("-", 1)[0].strip()
        return float(s)
    except:
        return None

def _fila_ui_a_ejercicio_firestore_legacy(fila: dict) -> dict:
    seccion = fila.get("Sección", "")
    if seccion not in ["Warm Up", "Work Out"]:
        seccion = "Warm Up" if (fila.get("Circuito","") in ["A","B","C"]) else "Work Out"
    series   = _f(fila.get("Series",""))
    reps_min = _f(fila.get("RepsMin",""))
    reps_max = _f(fila.get("RepsMax",""))
    peso     = _f(fila.get("Peso",""))
    rir      = _f(fila.get("RIR",""))
    return {
        "bloque":    seccion,
        "circuito":  fila.get("Circuito",""),
        "ejercicio": fila.get("Ejercicio",""),
        "detalle":   fila.get("Detalle",""),
        "series":    series,
        "reps_min":  reps_min,
        "reps_max":  reps_max,
        "peso":      peso,
        "tiempo":    fila.get("Tiempo",""),
        "velocidad": fila.get("Velocidad",""),
        "rir":       rir,
        "tipo":      fila.get("Tipo",""),
        "video":     fila.get("Video",""),
    }

# =============== 🎨 LAYOUT (headers & helpers) ===============
COL_SIZES = [0.9, 2.0, 3.0, 2.0, 0.8, 1.6, 1.0, 0.8, 1.2, 0.8]
HEADERS   = ["Circuito", "Buscar Ejercicio", "Ejercicio", "Detalle",
             "Series", "Repeticiones", "Peso", "RIR", "Progresión", "Copiar"]

def _render_headers():
    header_cols = st.columns(COL_SIZES)
    for c, title in zip(header_cols, HEADERS):
        c.markdown(
            f"<div style='text-align:center; white-space:nowrap'><b>{title}</b></div>",
            unsafe_allow_html=True
        )

def _reps_str(fila: dict) -> str:
    rmin = str(fila.get("RepsMin") or "").strip()
    rmax = str(fila.get("RepsMax") or "").strip()
    return f"{rmin}-{rmax}" if (rmin and rmax) else (rmin or rmax or "")

def _ordenar_por_circuito(lista_ui: list[dict]) -> list[dict]:
    orden = {c:i for i,c in enumerate(list("ABCDEFGHIJKL"))}
    return sorted(lista_ui, key=lambda f: orden.get((f.get("Circuito") or "").upper(), 999))

# =============== 👀 PREVIEW READ-ONLY (idéntico al editor) ===============
def _render_row_readonly(fila: dict):
    cols = st.columns(COL_SIZES)
    cols[0].markdown(f"<div style='text-align:center'>{fila.get('Circuito','')}</div>", unsafe_allow_html=True)
    cols[1].markdown(f"<div style='text-align:center'>{fila.get('BuscarEjercicio','')}</div>", unsafe_allow_html=True)
    cols[2].markdown(f"{fila.get('Ejercicio','')}")
    cols[3].markdown(f"{fila.get('Detalle','')}")
    cols[4].markdown(f"<div style='text-align:center'>{fila.get('Series','')}</div>", unsafe_allow_html=True)
    cols[5].markdown(f"<div style='text-align:center'>{_reps_str(fila)}</div>", unsafe_allow_html=True)
    cols[6].markdown(f"<div style='text-align:center'>{fila.get('Peso','')}</div>", unsafe_allow_html=True)
    cols[7].markdown(f"<div style='text-align:center'>{fila.get('RIR','')}</div>", unsafe_allow_html=True)
    cols[8].markdown("<div style='text-align:center'>—</div>", unsafe_allow_html=True)
    cols[9].markdown("<div style='text-align:center'>—</div>", unsafe_allow_html=True)

def _split_por_seccion(lista_ui: list[dict]):
    wu, wo = [], []
    for f in lista_ui:
        (wu if (f.get("Sección","") == "Warm Up") else wo).append(f)
    return wu, wo

def _render_tabla_preview(dia_label: str, ejercicios_raw):
    st.markdown(f"### 📅 {dia_label}")
    filas_ui = [_ejercicio_firestore_a_fila_ui(e) for e in ejercicios_raw]
    wu, wo = _split_por_seccion(filas_ui)
    wu = _ordenar_por_circuito(wu); wo = _ordenar_por_circuito(wo)

    st.subheader("Warm Up")
    _render_headers()
    if not wu: st.caption("No hay ejercicios en Warm Up para este día.")
    for fila in wu: _render_row_readonly(fila)

    st.markdown("---")
    st.subheader("Work Out")
    _render_headers()
    if not wo: st.caption("No hay ejercicios en Work Out para este día.")
    for fila in wo: _render_row_readonly(fila)

# =============== ✏️ EDICIÓN MANUAL EN GRILLA (igual al editor) ===============
def _asegurar_lista_session(key: str):
    if key not in st.session_state:
        st.session_state[key] = []

def _fila_vacia(seccion: str) -> dict:
    base = {k: "" for k in COLUMNAS_TABLA}
    base["Sección"] = seccion
    base["Circuito"] = "A"
    return base

def _render_tabla_manual(dia_sel: str, bloque_sel: str, ejercicios_dia: list[dict], rutina_modificada_ref: dict):
    """
    Muestra y edita el bloque seleccionado con el mismo layout que 'editar_rutinas.py'.
    Al enviar, reemplaza SOLO ese bloque dentro de rutina_modificada_ref[dia_sel].
    """
    key_seccion = f"descarga_dia_{dia_sel}_{bloque_sel.replace(' ','_')}"
    _asegurar_lista_session(key_seccion)

    # Cargar una sola vez desde Firestore a UI (si vacío)
    if not st.session_state[key_seccion]:
        # Normalizar a filas UI y filtrar por bloque
        filas_ui = [_ejercicio_firestore_a_fila_ui(e) for e in ejercicios_dia if (e.get("bloque","") == bloque_sel or e.get("Sección","") == bloque_sel)]
        # Ordenar por circuito
        filas_ui = _ordenar_por_circuito(filas_ui)
        st.session_state[key_seccion] = filas_ui

    st.subheader(bloque_sel)

    # Controles de filas
    ctrl_cols = st.columns([1.4, 1.4, 1.6, 5.6])
    add_n = ctrl_cols[2].number_input("N", min_value=1, max_value=10, value=1, key=f"addn_{key_seccion}", label_visibility="collapsed")
    if ctrl_cols[0].button("➕ Agregar fila", key=f"add_{key_seccion}"):
        st.session_state[key_seccion].extend([_fila_vacia(bloque_sel) for _ in range(int(add_n))])
        st.rerun()
    if ctrl_cols[1].button("➖ Quitar última", key=f"del_{key_seccion}"):
        if st.session_state[key_seccion]:
            st.session_state[key_seccion].pop()
            st.rerun()

    # Encabezados
    _render_headers()

    # === FORM ===
    with st.form(f"form_{key_seccion}", clear_on_submit=False):
        for idx, fila in enumerate(st.session_state[key_seccion]):
            # Asegurar que la fila siga marcada con el bloque actual
            fila["Sección"] = bloque_sel
            key_ent = f"{dia_sel}_{bloque_sel.replace(' ','_')}_{idx}"
            cols = st.columns(COL_SIZES)

            # 0) Circuito
            opciones_circuito = list("ABCDEFGHIJKL")
            fila["Circuito"] = cols[0].selectbox(
                "", opciones_circuito,
                index=(opciones_circuito.index(fila.get("Circuito")) if fila.get("Circuito") in opciones_circuito else 0),
                key=f"circ_{key_ent}", label_visibility="collapsed"
            )

            # 1) Buscar (solo para Work Out) + 2) Ejercicio
            if bloque_sel == "Work Out":
                palabra = cols[1].text_input("", value=fila.get("BuscarEjercicio",""), key=f"buscar_{key_ent}", label_visibility="collapsed")
                fila["BuscarEjercicio"] = palabra
                try:
                    encontrados = [n for n in EJERCICIOS.keys() if all(p in n.lower() for p in palabra.lower().split())] if palabra.strip() else []
                except Exception:
                    encontrados = []
                seleccionado = cols[2].selectbox("", encontrados if encontrados else ["(sin resultados)"], key=f"select_{key_ent}", label_visibility="collapsed")
                if seleccionado != "(sin resultados)":
                    fila["Ejercicio"] = seleccionado
                    fila["Video"] = (EJERCICIOS.get(seleccionado, {}) or {}).get("video","").strip()
            else:
                cols[1].markdown("&nbsp;", unsafe_allow_html=True)
                fila["Ejercicio"] = cols[2].text_input("", value=fila.get("Ejercicio",""), key=f"ej_{key_ent}", label_visibility="collapsed")

            # 3) Detalle
            fila["Detalle"] = cols[3].text_input("", value=fila.get("Detalle",""), key=f"det_{key_ent}", label_visibility="collapsed")
            # 4) Series
            fila["Series"] = cols[4].text_input("", value=str(fila.get("Series","")), key=f"ser_{key_ent}", label_visibility="collapsed")
            # 5) Reps min/max
            cmin, cmax = cols[5].columns(2)
            fila["RepsMin"] = cmin.text_input("", value=str(fila.get("RepsMin","")), key=f"rmin_{key_ent}", label_visibility="collapsed")
            fila["RepsMax"] = cmax.text_input("", value=str(fila.get("RepsMax","")), key=f"rmax_{key_ent}", label_visibility="collapsed")

            # 6) Peso (select por implemento si aplica)
            peso_widget_key = f"peso_{key_ent}"
            peso_value = fila.get("Peso","")
            usar_text_input = True
            pesos_disponibles = []
            try:
                nombre_ej = fila.get("Ejercicio","")
                ej_doc = EJERCICIOS.get(nombre_ej, {}) or {}
                id_impl = str(ej_doc.get("id_implemento","") or "")
                if id_impl and id_impl != "1" and id_impl in IMPLEMENTOS:
                    pesos_disponibles = IMPLEMENTOS[id_impl].get("pesos",[]) or []
                    usar_text_input = not bool(pesos_disponibles)
            except Exception:
                usar_text_input = True

            if not usar_text_input:
                opciones_peso = [str(p) for p in pesos_disponibles]
                if str(peso_value) not in opciones_peso and opciones_peso:
                    peso_value = opciones_peso[0]
                fila["Peso"] = cols[6].selectbox("", options=opciones_peso,
                                                 index=(opciones_peso.index(str(peso_value)) if str(peso_value) in opciones_peso else 0),
                                                 key=peso_widget_key, label_visibility="collapsed")
            else:
                fila["Peso"] = cols[6].text_input("", value=str(peso_value), key=peso_widget_key,
                                                  label_visibility="collapsed", placeholder="Kg")

            # 7) RIR
            fila["RIR"] = cols[7].text_input("", value=fila.get("RIR",""), key=f"rir_{key_ent}", label_visibility="collapsed")
            # 8) Progresión (placeholder)
            cols[8].markdown("<div style='text-align:center'>—</div>", unsafe_allow_html=True)
            # 9) Copiar (placeholder)
            cols[9].markdown("<div style='text-align:center'>—</div>", unsafe_allow_html=True)

        submitted = st.form_submit_button("Aplicar cambios en este bloque")
        if submitted:
            # 1) Convertir filas UI -> formato Firestore (legacy)
            nuevos = [_fila_ui_a_ejercicio_firestore_legacy(f) for f in st.session_state[key_seccion]]

            # 2) Volcar en rutina_modificada SOLO este bloque
            ejercicios_dia_full = obtener_lista_ejercicios(rutina_modificada_ref.get(dia_sel, []))
            otros = [e for e in ejercicios_dia_full if (e.get("bloque","") != bloque_sel and e.get("Sección","") != bloque_sel)]
            rutina_modificada_ref[dia_sel] = otros + nuevos
            st.success("✅ Bloque actualizado en la rutina de descarga")

# =============== 🎯 PÁGINA PRINCIPAL ===============
def descarga_rutina():
    st.title("📉 Crear Rutina de Descarga")

    # Mapear usuarios y filtrarlos según empresa
    usuarios_map: dict[str, dict] = {}
    for u in USUARIOS:
        correo_u = (u.get("correo") or "").strip().lower()
        if correo_u:
            usuarios_map[correo_u] = u
            usuarios_map[correo_a_doc_id(correo_u)] = u

    correo_login = (st.session_state.get("correo") or "").strip().lower()
    rol_login = (st.session_state.get("rol") or "").strip().lower()
    empresa_login = empresa_de_usuario(correo_login, usuarios_map) if correo_login else EMPRESA_DESCONOCIDA

    clientes_dict = {}
    for doc in db.collection("rutinas_semanales").stream():
        data = doc.to_dict() or {}
        nombre = data.get("cliente")
        correo_cli = (data.get("correo") or "").strip().lower()
        if not nombre or not correo_cli:
            continue

        empresa_cli = empresa_de_usuario(correo_cli, usuarios_map)
        coach_cli = ((usuarios_map.get(correo_cli) or {}).get("coach_responsable") or "").strip().lower()

        permitido = True
        if rol_login in ("entrenador",):
            if empresa_login == EMPRESA_ASESORIA:
                permitido = coach_cli == correo_login
            elif empresa_login == EMPRESA_MOTION:
                if empresa_cli == EMPRESA_MOTION:
                    permitido = True
                elif empresa_cli == EMPRESA_DESCONOCIDA:
                    permitido = coach_cli == correo_login
                else:
                    permitido = False
            else:
                permitido = coach_cli == correo_login
        elif rol_login not in ("admin", "administrador"):
            permitido = coach_cli == correo_login

        if permitido:
            clientes_dict[nombre] = correo_cli

    if not clientes_dict:
        st.warning("❌ No hay clientes con rutinas.")
        return

    nombre_sel = st.selectbox("Selecciona el cliente:", sorted(clientes_dict.keys()))
    if not nombre_sel: return
    correo = clientes_dict[nombre_sel]

    # Semanas del cliente
    semanas_dict = {}
    for doc in db.collection("rutinas_semanales").where("correo","==",correo).stream():
        data = doc.to_dict() or {}
        f = data.get("fecha_lunes")
        if f: semanas_dict[f] = doc.id

    if not semanas_dict:
        st.warning("❌ No hay rutinas para este cliente.")
        return

    ultima_semana = max(semanas_dict.keys())
    doc_id_semana = semanas_dict[ultima_semana]
    st.info(f"Última semana encontrada: **{ultima_semana}**")

    # Rutina base
    doc_data = db.collection("rutinas_semanales").document(doc_id_semana).get().to_dict() or {}
    rutina_original = doc_data.get("rutina", {}) or {}
    rutina_modificada = copy.deepcopy(rutina_original)

    modalidad = st.selectbox(
        "Selecciona modalidad de descarga:",
        ["Mantener series/reps y bajar 20% peso",
         "Mantener pesos y bajar 1 serie y 3 reps (min y max)",
         "Elección manual"]
    )

    # === Automáticas ===
    if modalidad == "Mantener series/reps y bajar 20% peso":
        for dia in solo_dias_keys(rutina_modificada):
            ejercicios = obtener_lista_ejercicios(rutina_modificada.get(dia, []))
            for ej in ejercicios:
                try:
                    peso_txt = str(ej.get("peso","")).strip().replace(",", ".")
                    if peso_txt != "":
                        ej["peso"] = str(round(float(peso_txt) * 0.8, 1))
                except: pass
            rutina_modificada[dia] = ejercicios

    elif modalidad == "Mantener pesos y bajar 1 serie y 3 reps (min y max)":
        for dia in solo_dias_keys(rutina_modificada):
            ejercicios = obtener_lista_ejercicios(rutina_modificada.get(dia, []))
            for ej in ejercicios:
                # series
                try:
                    s = str(ej.get("series","")).strip()
                    if s.isdigit():
                        ej["series"] = str(max(1, int(s)-1))
                except: pass
                # reps
                try:
                    rmin = str(ej.get("reps_min","")).strip()
                    rmax = str(ej.get("reps_max","")).strip()
                    rs   = str(ej.get("repeticiones","")).strip()
                    if rmin.isdigit() or rmax.isdigit():
                        ej["reps_min"] = str(max(0, int(rmin)-3)) if rmin.isdigit() else ""
                        ej["reps_max"] = str(max(0, int(rmax)-3)) if rmax.isdigit() else ""
                        if not (ej["reps_min"] or ej["reps_max"]):
                            ej["repeticiones"] = ""
                    elif rs.isdigit():
                        ej["repeticiones"] = str(max(0, int(rs)-3))
                except: pass
            rutina_modificada[dia] = ejercicios

    # === Edición manual con grilla igual al editor ===
    elif modalidad == "Elección manual":
        dias_disponibles = solo_dias_keys(rutina_modificada)
        if not dias_disponibles:
            st.warning("Esta rutina no tiene días numéricos para editar.")
            return

        dia_sel = st.selectbox("Selecciona el día a editar:", dias_disponibles, format_func=lambda x: f"Día {x}")
        ejercicios_dia = obtener_lista_ejercicios(rutina_modificada.get(dia_sel, []))
        # Detectar bloques presentes (si vacío, ofrecer ambos)
        bloques_presentes = sorted(list({(e.get("bloque") or e.get("Sección") or "") for e in ejercicios_dia if (e.get("bloque") or e.get("Sección"))}))
        if not bloques_presentes:
            bloques_presentes = ["Warm Up", "Work Out"]
        bloque_sel = st.selectbox("Selecciona el bloque:", bloques_presentes)

        # Grilla editable para el bloque elegido
        _render_tabla_manual(dia_sel, bloque_sel, ejercicios_dia, rutina_modificada)

    # =============== 👀 PREVISUALIZACIÓN (idéntico editor) ===============
    st.subheader("👀 Previsualización de la rutina de descarga (formato filas)")
    for dia in solo_dias_keys(rutina_modificada):
        ejercicios_raw = obtener_lista_ejercicios(rutina_modificada.get(dia, []))
        _render_tabla_preview(f"Día {dia}", ejercicios_raw)
        st.markdown("---")

    # =============== 💾 GUARDAR ===============
    nueva_fecha = st.date_input("Fecha de inicio de rutina de descarga", datetime.now()).strftime("%Y-%m-%d")
    if st.button("💾 Guardar rutina de descarga"):
        nuevo_doc = (doc_data or {}).copy()
        nuevo_doc["fecha_lunes"] = nueva_fecha
        nuevo_doc["rutina"] = rutina_modificada
        nuevo_doc["tipo"] = "descarga"
        nuevo_doc_id = f"{normalizar_correo(correo)}_{nueva_fecha.replace('-', '_')}"
        db.collection("rutinas_semanales").document(nuevo_doc_id).set(nuevo_doc)
        st.success(f"✅ Rutina de descarga creada para la semana {nueva_fecha}")

# Multipage
if __name__ == "__main__":
    descarga_rutina()
