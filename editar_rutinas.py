# editar_rutinas.py — Mismo estilo que ver/crear (solo UI/colores)
import json
import unicodedata
from datetime import datetime
import streamlit as st
import pandas as pd

import firebase_admin
from firebase_admin import credentials, firestore

# ===================== 🎨 PALETA / ESTILOS =====================
PRIMARY   = "#00C2FF"
SUCCESS   = "#22C55E"
WARNING   = "#F59E0B"
DANGER    = "#EF4444"
BG_DARK   = "#0B0F14"
SURFACE   = "#121821"
TEXT_MAIN = "#FFFFFF"
TEXT_MUTED= "#94A3B8"
STROKE    = "rgba(255,255,255,.08)"

st.markdown(f"""
<style>
:root {{
  --primary:{PRIMARY}; --success:{SUCCESS}; --warning:{WARNING}; --danger:{DANGER};
  --bg:{BG_DARK}; --surface:{SURFACE}; --muted:{TEXT_MUTED}; --stroke:{STROKE};
}}
html,body,[data-testid="stAppViewContainer"]{{ background:var(--bg)!important; }}
h1,h2,h3,h4,h5 {{ color:{TEXT_MAIN}; }}
p, label, span, div {{ color:{TEXT_MAIN}; }}
small, .muted {{ color:var(--muted)!important; }}
.hr-light {{ border-bottom:1px solid var(--stroke); margin:12px 0; }}
.h-accent {{ position:relative; padding-left:10px; margin:8px 0 6px; font-weight:700; color:{TEXT_MAIN}; }}
.h-accent:before {{ content:""; position:absolute; left:0; top:2px; bottom:2px; width:4px; border-radius:3px; background:var(--primary); }}
.card {{
  background:var(--surface); border:1px solid var(--stroke);
  border-radius:12px; padding:12px 14px; margin:8px 0;
}}
.badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:700; }}
.badge--warn {{ background:rgba(245,158,11,.15); border:1px solid rgba(245,158,11,.25); color:#FFCF7A; }}
/* Botones */
div.stButton > button[kind="primary"], .stDownloadButton button {{
  background: var(--primary) !important; color:#001018 !important; border:none !important;
  font-weight:700 !important; border-radius:10px !important;
}}
div.stButton > button[kind="secondary"] {{
  background:#1A2431 !important; color:#E0E0E0 !important; border:1px solid var(--stroke) !important;
  border-radius:10px !important;
}}
div.stButton > button:hover {{ filter:brightness(0.93); }}
/* Inputs */
.stTextInput > div > div > input,
.stNumberInput input, .stTextArea textarea, .stSelectbox > div > div {{
  background:#101722 !important; color:{TEXT_MAIN} !important; border:1px solid var(--stroke) !important;
}}
/* Tabs */
.stTabs [data-baseweb="tab-list"] button span {{ color:{TEXT_MAIN}; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:var(--primary)!important; }}
/* Encabezados de tabla */
.header-center {{ text-align:center; white-space:nowrap; font-weight:700; }}
</style>
""", unsafe_allow_html=True)

# ===================== ⚙️ CONFIGURACIÓN RÁPIDA =====================
DEFAULT_WU_ROWS_NEW_DAY = 0
DEFAULT_WO_ROWS_NEW_DAY = 0

# ===================== 🔧 UTILIDADES BÁSICAS =====================
def normalizar_texto(txt: str) -> str:
    txt = (txt or "").strip().lower()
    txt = unicodedata.normalize("NFD", txt).encode("ascii", "ignore").decode("utf-8")
    return txt

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

# ===================== 🔥 FIREBASE (init perezoso + cacheado) =====================
@st.cache_resource(show_spinner=False)
def get_db():
    if not firebase_admin._apps:
        cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# ===================== 📦 CARGAS CACHEADAS =====================
@st.cache_data(show_spinner=False)
def cargar_ejercicios():
    db = get_db()
    docs = db.collection("ejercicios").stream()
    return {doc.to_dict().get("nombre", ""): (doc.to_dict() or {}) for doc in docs if doc.exists}

@st.cache_data(show_spinner=False)
def cargar_usuarios():
    db = get_db()
    docs = db.collection("usuarios").stream()
    return [doc.to_dict() for doc in docs if doc.exists]

@st.cache_data(show_spinner=False)
def cargar_implementos():
    db = get_db()
    impl = {}
    for doc in db.collection("implementos").stream():
        d = doc.to_dict() or {}
        d["pesos"] = d.get("pesos", [])
        impl[str(doc.id)] = d
    return impl

EJERCICIOS  = cargar_ejercicios()
USUARIOS    = cargar_usuarios()
IMPLEMENTOS = cargar_implementos()

# ===================== 🎛️ DEFINICIÓN DE COLUMNAS UI =====================
COLUMNAS_TABLA = [
    "Circuito", "Sección", "Ejercicio", "Detalle",
    "Series", "RepsMin", "RepsMax", "Peso", "RIR",
    "Tiempo", "Velocidad", "Tipo", "Video",
    "Variable_1", "Cantidad_1", "Operacion_1", "Semanas_1",
    "Variable_2", "Cantidad_2", "Operacion_2", "Semanas_2",
    "Variable_3", "Cantidad_3", "Operacion_3", "Semanas_3",
    "BuscarEjercicio"
]

CIRCUITOS = ["A","B","C","D","E","F","G","H","I","J","K","L"]
COL_SIZES = [0.9, 2.0, 3.0, 2.0, 0.8, 1.6, 1.0, 0.8, 1.2, 0.8]
HEADERS   = ["Circuito", "Buscar Ejercicio", "Ejercicio", "Detalle",
             "Series", "Repeticiones", "Peso", "RIR", "Progresión", "Copiar"]

# ===================== 🔄 DÍAS =====================
def claves_dias(rutina_dict: dict) -> list[str]:
    if not rutina_dict:
        return []
    solo_dias = [str(k) for k in rutina_dict.keys() if str(k).isdigit()]
    return sorted(solo_dias, key=lambda x: int(x))

# ===================== 🔁 MAPEO UI <-> FIRESTORE =====================
def _ejercicio_firestore_a_fila_ui(ej: dict) -> dict:
    fila = {k: "" for k in COLUMNAS_TABLA}
    seccion = ej.get("Sección") or ej.get("bloque") or ""
    if seccion not in ["Warm Up", "Work Out"]:
        seccion = "Warm Up" if (ej.get("circuito","") in ["A","B","C"]) else (seccion or "Work Out")
    fila["Sección"] = seccion
    fila["Circuito"] = ej.get("Circuito") or ej.get("circuito") or ""
    fila["Ejercicio"] = ej.get("Ejercicio") or ej.get("ejercicio") or ""
    if fila["Sección"] == "Work Out":
        fila["BuscarEjercicio"] = fila["Ejercicio"]
        fila["_exact_on_load"] = True  # 🔧 cambio clave: forzar match exacto solo al cargar
    fila["Detalle"]   = ej.get("Detalle")    or ej.get("detalle")    or ""
    fila["Series"]    = ej.get("Series")     or ej.get("series")     or ""
    fila["RIR"]       = ej.get("RIR")        or ej.get("rir")        or ""
    fila["Peso"]      = ej.get("Peso")       or ej.get("peso")       or ""
    fila["Tiempo"]    = ej.get("Tiempo")     or ej.get("tiempo")     or ""
    fila["Velocidad"] = ej.get("Velocidad")  or ej.get("velocidad")  or ""
    fila["Tipo"]      = ej.get("Tipo")       or ej.get("tipo")       or ""
    fila["Video"]     = ej.get("Video")      or ej.get("video")      or ""
    if "reps_min" in ej or "reps_max" in ej:
        fila["RepsMin"] = ej.get("reps_min", "")
        fila["RepsMax"] = ej.get("reps_max", "")
    elif "RepsMin" in ej or "RepsMax" in ej:
        fila["RepsMin"] = ej.get("RepsMin", "")
        fila["RepsMax"] = ej.get("RepsMax", "")
    else:
        rep = str(ej.get("repeticiones", "")).strip()
        if "-" in rep:
            mn, mx = rep.split("-", 1)
            fila["RepsMin"], fila["RepsMax"] = mn.strip(), mx.strip()
        else:
            fila["RepsMin"], fila["RepsMax"] = rep, ""
    for p in (1,2,3):
        fila[f"Variable_{p}"]  = ej.get(f"Variable_{p}",  "")
        fila[f"Cantidad_{p}"]  = ej.get(f"Cantidad_{p}",  "")
        fila[f"Operacion_{p}"] = ej.get(f"Operacion_{p}", "")
        fila[f"Semanas_{p}"]   = ej.get(f"Semanas_{p}",   "")
    return fila

def _fila_ui_a_ejercicio_firestore_legacy(fila: dict) -> dict:
    seccion = fila.get("Sección", "")
    if seccion not in ["Warm Up", "Work Out"]:
        seccion = "Warm Up" if (fila.get("Circuito","") in ["A","B","C"]) else "Work Out"
    series   = _f(fila.get("Series",""))
    reps_min = _f(fila.get("RepsMin",""))
    reps_max = _f(fila.get("RepsMax",""))
    peso     = _f(fila.get("Peso",""))
    rir      = _f(fila.get("RIR",""))
    tiempo   = fila.get("Tiempo","")
    velocidad= fila.get("Velocidad","")
    return {
        "bloque":     seccion,
        "circuito":   fila.get("Circuito",""),
        "ejercicio":  fila.get("Ejercicio",""),
        "detalle":    fila.get("Detalle",""),
        "series":     series,
        "reps_min":   reps_min,
        "reps_max":   reps_max,
        "peso":       peso,
        "tiempo":     tiempo,
        "velocidad":  velocidad,
        "rir":        rir,
        "tipo":       fila.get("Tipo",""),
        "video":      fila.get("Video",""),
    }

# ===================== 🧱 FILAS / DÍAS (session_state) =====================
def _fila_vacia(seccion: str) -> dict:
    base = {k: "" for k in COLUMNAS_TABLA}
    base["Sección"] = seccion
    return base

def _asegurar_dia_en_session(idx_dia: int):
    wu_key = f"rutina_dia_{idx_dia}_Warm_Up"
    wo_key = f"rutina_dia_{idx_dia}_Work_Out"
    if wu_key not in st.session_state:
        st.session_state[wu_key] = []
        if DEFAULT_WU_ROWS_NEW_DAY > 0:
            st.session_state[wu_key] = [_fila_vacia("Warm Up") for _ in range(DEFAULT_WU_ROWS_NEW_DAY)]
    if wo_key not in st.session_state:
        st.session_state[wo_key] = []
        if DEFAULT_WO_ROWS_NEW_DAY > 0:
            st.session_state[wo_key] = [_fila_vacia("Work Out") for _ in range(DEFAULT_WO_ROWS_NEW_DAY)]

def _agregar_dia():
    dias = st.session_state.get("dias_editables", [])
    nuevo_idx = (max([int(d) for d in dias]) + 1) if dias else 1
    dias.append(str(nuevo_idx))
    st.session_state["dias_editables"] = dias
    _asegurar_dia_en_session(nuevo_idx)
    try: st.rerun()
    except AttributeError: st.experimental_rerun()

def limpiar_dia(idx_dia: int):
    for seccion in ["Warm Up", "Work Out"]:
        key = f"rutina_dia_{idx_dia}_{seccion.replace(' ', '_')}"
        st.session_state[key] = []
    i0 = idx_dia - 1
    patrones = [f"_{i0}_Warm_Up_", f"_{i0}_Work_Out_"]
    claves_borrar = []
    for k in list(st.session_state.keys()):
        if any(p in k for p in patrones) or k.startswith(f"multiselect_{i0}_") or k.startswith(f"do_copy_{i0}_"):
            claves_borrar.append(k)
    for k in claves_borrar:
        st.session_state.pop(k, None)
    try: st.rerun()
    except AttributeError: st.experimental_rerun()

# ===================== 🧩 RENDER DE TABLA POR DÍA/SECCIÓN =====================
def render_tabla_dia(i: int, seccion: str, progresion_activa: str, dias_labels: list[str]):
    key_seccion = f"rutina_dia_{i+1}_{seccion.replace(' ', '_')}"
    if key_seccion not in st.session_state:
        st.session_state[key_seccion] = []

    st.markdown(f"<h4 class='h-accent' style='margin-top:2px'>{seccion}</h4>", unsafe_allow_html=True)

    ctrl_cols = st.columns([1.4, 1.4, 1.6, 5.6])
    add_n = ctrl_cols[2].number_input("N", min_value=1, max_value=10, value=1,
                                      key=f"addn_{key_seccion}", label_visibility="collapsed")
    if ctrl_cols[0].button("➕ Agregar fila", key=f"add_{key_seccion}", type="secondary"):
        st.session_state[key_seccion].extend([_fila_vacia(seccion) for _ in range(int(add_n))])
        st.rerun()
    if ctrl_cols[1].button("➖ Quitar última", key=f"del_{key_seccion}", type="secondary"):
        if st.session_state[key_seccion]:
            st.session_state[key_seccion].pop()
            st.rerun()

    header_cols = st.columns(COL_SIZES)
    for c, title in zip(header_cols, HEADERS):
        c.markdown(f"<div class='header-center'>{title}</div>", unsafe_allow_html=True)

    col_sizes = COL_SIZES
    ejercicios_dict = EJERCICIOS

    def _buscar_fuzzy(palabra: str) -> list[str]:
        if not palabra.strip():
            return []
        tokens = normalizar_texto(palabra).split()
        res = []
        for n in ejercicios_dict.keys():
            nn = normalizar_texto(n)
            if all(t in nn for t in tokens):
                res.append(n)
        return res

    with st.form(f"form_{key_seccion}", clear_on_submit=False):
        for idx, fila in enumerate(st.session_state[key_seccion]):
            key_entrenamiento = f"{i}_{seccion.replace(' ','_')}_{idx}"
            cols = st.columns(col_sizes)

            # Circuito
            opciones_circuito = CIRCUITOS
            fila["Circuito"] = cols[0].selectbox(
                "", opciones_circuito,
                index=(opciones_circuito.index(fila.get("Circuito")) if fila.get("Circuito") in opciones_circuito else 0),
                key=f"circ_{key_entrenamiento}", label_visibility="collapsed"
            )

            # Buscar + Ejercicio
            if seccion == "Work Out":
                palabra = cols[1].text_input(
                    "", value=fila.get("BuscarEjercicio", ""),
                    key=f"buscar_{key_entrenamiento}", label_visibility="collapsed", placeholder="Buscar…"
                )
                fila["BuscarEjercicio"] = palabra

                nombre_original = (fila.get("Ejercicio","") or "").strip()
                exact_on_load = bool(fila.get("_exact_on_load", False))  # 🔧 cambio clave

                # Lógica: si estamos en modo exacto y el usuario no cambió la búsqueda, lista = [nombre_original]
                # Si el usuario escribe algo distinto al original, migramos a fuzzy y apagamos el modo exacto.
                ejercicios_encontrados = []
                if exact_on_load:
                    if (not palabra.strip()) or (normalizar_texto(palabra) == normalizar_texto(nombre_original)):
                        if nombre_original:
                            ejercicios_encontrados = [nombre_original]
                        else:
                            ejercicios_encontrados = []
                    else:
                        ejercicios_encontrados = _buscar_fuzzy(palabra)
                        fila["_exact_on_load"] = False  # 🔧 ya se salió del modo exacto
                else:
                    ejercicios_encontrados = _buscar_fuzzy(palabra)

                # Resguardo: si no hay resultados, mantenemos el original como única opción
                if not ejercicios_encontrados and nombre_original:
                    ejercicios_encontrados = [nombre_original]

                # Remover duplicados preservando orden
                vistos = set()
                ejercicios_encontrados = [e for e in ejercicios_encontrados if not (e in vistos or vistos.add(e))]

                seleccionado = cols[2].selectbox(
                    "", ejercicios_encontrados if ejercicios_encontrados else ["(sin resultados)"],
                    key=f"select_{key_entrenamiento}", label_visibility="collapsed"
                )
                if seleccionado != "(sin resultados)":
                    fila["Ejercicio"] = seleccionado
                    fila["Video"] = (ejercicios_dict.get(seleccionado, {}) or {}).get("video", "").strip()
            else:
                cols[1].markdown("&nbsp;", unsafe_allow_html=True)
                fila["Ejercicio"] = cols[2].text_input(
                    "", value=fila.get("Ejercicio",""),
                    key=f"ej_{key_entrenamiento}", label_visibility="collapsed", placeholder="Nombre del ejercicio"
                )

            # Detalle
            fila["Detalle"] = cols[3].text_input(
                "", value=fila.get("Detalle",""),
                key=f"det_{key_entrenamiento}", label_visibility="collapsed", placeholder="Notas (opcional)"
            )
            # Series
            fila["Series"] = cols[4].text_input(
                "", value=fila.get("Series",""),
                key=f"ser_{key_entrenamiento}", label_visibility="collapsed", placeholder="N°"
            )
            # Reps min/max
            cmin, cmax = cols[5].columns(2)
            try:
                fila["RepsMin"] = cmin.text_input("", value=str(fila.get("RepsMin","")),
                                                  key=f"rmin_{key_entrenamiento}", label_visibility="collapsed", placeholder="Min")
            except:
                fila["RepsMin"] = ""
            try:
                fila["RepsMax"] = cmax.text_input("", value=str(fila.get("RepsMax","")),
                                                  key=f"rmax_{key_entrenamiento}", label_visibility="collapsed", placeholder="Max")
            except:
                fila["RepsMax"] = ""

            # Peso (implementos)
            peso_widget_key = f"peso_{key_entrenamiento}"
            peso_value = fila.get("Peso","")
            pesos_disponibles, usar_text_input = [], True
            try:
                nombre_ej = fila.get("Ejercicio","")
                ej_doc = EJERCICIOS.get(nombre_ej, {}) or {}
                id_impl = str(ej_doc.get("id_implemento","") or "")
                if id_impl and id_impl != "1" and id_impl in IMPLEMENTOS:
                    pesos_disponibles = IMPLEMENTOS[id_impl].get("pesos", []) or []
                    usar_text_input = not bool(pesos_disponibles)
            except Exception:
                usar_text_input = True

            if not usar_text_input:
                opciones_peso = [str(p) for p in pesos_disponibles]
                if str(peso_value) not in opciones_peso and opciones_peso:
                    peso_value = opciones_peso[0]
                fila["Peso"] = cols[6].selectbox(
                    "", options=opciones_peso,
                    index=(opciones_peso.index(str(peso_value)) if str(peso_value) in opciones_peso else 0),
                    key=peso_widget_key, label_visibility="collapsed"
                )
            else:
                fila["Peso"] = cols[6].text_input(
                    "", value=str(peso_value),
                    key=peso_widget_key, label_visibility="collapsed", placeholder="Kg"
                )

            # RIR
            fila["RIR"] = cols[7].text_input(
                "", value=fila.get("RIR",""),
                key=f"rir_{key_entrenamiento}", label_visibility="collapsed", placeholder="RIR"
            )

            # Progresión (checkbox centrado)
            prog_cell = cols[8].columns([1,1,1])
            mostrar_progresion = prog_cell[1].checkbox("", key=f"prog_check_{key_entrenamiento}_{idx}")

            # Copiar (checkbox centrado)
            copy_cell = cols[9].columns([1,1,1])
            mostrar_copia = copy_cell[1].checkbox("", key=f"copy_check_{key_entrenamiento}_{idx}")

            # === PROGRESIONES ===
            if mostrar_progresion:
                st.markdown("<div class='hr-light'></div>", unsafe_allow_html=True)
                st.markdown("<div class='h-accent'>Progresiones activas</div>", unsafe_allow_html=True)
                p = int(progresion_activa.split()[-1])  # 1..3
                pcols = st.columns(4)
                opciones_var = ["", "peso", "velocidad", "tiempo", "rir", "series", "repeticiones"]
                opciones_ope = ["", "multiplicacion", "division", "suma", "resta"]

                fila[f"Variable_{p}"] = pcols[0].selectbox(
                    f"Variable {p}", opciones_var,
                    index=(opciones_var.index(fila.get(f"Variable_{p}", "")) if fila.get(f"Variable_{p}","") in opciones_var else 0),
                    key=f"var{p}_{key_entrenamiento}_{idx}"
                )
                fila[f"Cantidad_{p}"] = pcols[1].text_input(
                    f"Cantidad {p}", value=fila.get(f"Cantidad_{p}", ""), key=f"cant{p}_{key_entrenamiento}_{idx}"
                )
                fila[f"Operacion_{p}"] = pcols[2].selectbox(
                    f"Operación {p}", opciones_ope,
                    index=(opciones_ope.index(fila.get(f"Operacion_{p}", "")) if fila.get(f"Operacion_{p}","") in opciones_ope else 0),
                    key=f"ope{p}_{key_entrenamiento}_{idx}"
                )
                fila[f"Semanas_{p}"] = pcols[3].text_input(
                    f"Semanas {p}", value=fila.get(f"Semanas_{p}", ""), key=f"sem{p}_{key_entrenamiento}_{idx}"
                )

            # === Copia a otros días ===
            if mostrar_copia:
                st.caption("Selecciona día(s) y presiona **Actualizar sección** para copiar.")
                dias_copia = st.multiselect(
                    "Días destino", dias_labels,
                    key=f"multiselect_{key_entrenamiento}_{idx}"
                )
                st.session_state[f"do_copy_{key_entrenamiento}_{idx}"] = True
            else:
                st.session_state.pop(f"multiselect_{key_entrenamiento}_{idx}", None)
                st.session_state.pop(f"do_copy_{key_entrenamiento}_{idx}", None)

        submitted = st.form_submit_button("Actualizar sección", type="primary")
        if submitted:
            for idx, fila in enumerate(st.session_state[key_seccion]):
                key_entrenamiento = f"{i}_{seccion.replace(' ','_')}_{idx}"
                do_copy_key = f"do_copy_{key_entrenamiento}_{idx}"
                multisel_key = f"multiselect_{key_entrenamiento}_{idx}"
                if st.session_state.get(do_copy_key):
                    dias_copia = st.session_state.get(multisel_key, [])
                    for dia_destino in dias_copia:
                        idx_dia = dias_labels.index(dia_destino)
                        key_destino = f"rutina_dia_{idx_dia + 1}_{seccion.replace(' ', '_')}"
                        if key_destino not in st.session_state:
                            st.session_state[key_destino] = []
                        while len(st.session_state[key_destino]) <= idx:
                            st.session_state[key_destino].append(_fila_vacia(seccion))
                        # limpiamos la bandera al copiar
                        fila_copia = {k: v for k, v in fila.items()}
                        fila_copia.pop("_exact_on_load", None)
                        st.session_state[key_destino][idx] = fila_copia
            st.success("Sección actualizada ✅")

# ===================== ⬇️ CARGA DESDE FIRESTORE A LA UI =====================
def cargar_doc_en_session(rutina_dict: dict, dias_disponibles: list[str]):
    for k in list(st.session_state.keys()):
        if k.startswith("rutina_dia_") or k.startswith("ej_") or k.startswith("buscar_"):
            st.session_state.pop(k, None)
    dias_ordenados = sorted([int(d) for d in dias_disponibles])
    for d in dias_ordenados:
        ejercicios_dia = rutina_dict.get(str(d), []) or []
        wu, wo = [], []
        for ej in ejercicios_dia:
            fila = _ejercicio_firestore_a_fila_ui(ej)
            # (la bandera _exact_on_load ya queda colocada dentro para Work Out)
            (wu if fila.get("Sección") == "Warm Up" else wo).append(fila)
        st.session_state[f"rutina_dia_{int(d)}_Warm_Up"] = wu
        st.session_state[f"rutina_dia_{int(d)}_Work_Out"] = wo
    st.session_state["dias_editables"] = [str(d) for d in dias_ordenados]

# ===================== ⬆️ RECOLECTOR UI -> FIRESTORE =====================
def construir_rutina_desde_session(dias_labels: list[str]) -> dict:
    nueva = {}
    for i, _ in enumerate(dias_labels):
        wu_key = f"rutina_dia_{i+1}_Warm_Up"
        wo_key = f"rutina_dia_{i+1}_Work_Out"
        ejercicios = (st.session_state.get(wu_key, []) or []) + (st.session_state.get(wo_key, []) or [])
        lista = []
        for fila in ejercicios:
            fila = {k: v for k, v in fila.items() if k != "_exact_on_load"}  # 🔧 no guardar bandera
            lista.append(_fila_ui_a_ejercicio_firestore_legacy(fila))
        nueva[str(i+1)] = lista
    return nueva

# ===================== 🧰 PÁGINA PRINCIPAL =====================
def editar_rutinas():
    st.markdown("<h2 class='h-accent'>Editar Rutina </h2>", unsafe_allow_html=True)

    db = get_db()

    # --- Selección de cliente / semana (en card) ---
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    clientes_dict = {}
    for doc in db.collection("rutinas_semanales").stream():
        data = doc.to_dict() or {}
        nombre = data.get("cliente")
        correo = data.get("correo")
        if nombre and correo:
            clientes_dict[nombre] = correo

    nombres_clientes = sorted(clientes_dict.keys())
    nombre_sel = st.selectbox("Selecciona el cliente:", nombres_clientes) if nombres_clientes else ""
    if not nombre_sel:
        st.info("No hay clientes con rutinas.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    correo = (clientes_dict[nombre_sel] or "").strip().lower()

    semanas_dict = {}
    for doc in db.collection("rutinas_semanales").where("correo","==",correo).stream():
        data = doc.to_dict() or {}
        f = data.get("fecha_lunes")
        if f:
            semanas_dict[f] = doc.id

    semanas = sorted(semanas_dict.keys())
    semana_sel = st.selectbox("Selecciona la semana a editar:", semanas) if semanas else ""
    if not semana_sel:
        st.warning("Este cliente no tiene semanas registradas.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    doc_id_semana = semanas_dict[semana_sel]
    st.markdown("</div>", unsafe_allow_html=True)  # /card

    # Leer y filtrar rutina: SOLO días numéricos
    doc_data = db.collection("rutinas_semanales").document(doc_id_semana).get().to_dict() or {}
    rutina_raw = doc_data.get("rutina", {}) or {}
    rutina = {k: v for k, v in rutina_raw.items() if str(k).isdigit()}

    # Días disponibles
    dias_disponibles = claves_dias(rutina) if rutina else ["1","2","3","4","5"]

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    dias_texto = ", ".join([f"**Día {int(d)}**" for d in dias_disponibles])
    st.markdown(f"**N° Días de la rutina:** {dias_texto}")
    if st.button("📥 Cargar rutina seleccionada", type="secondary"):
        cargar_doc_en_session(rutina, dias_disponibles)
        st.success("Rutina cargada en el editor ✅")
    st.markdown("</div>", unsafe_allow_html=True)

    st.markdown("<div class='hr-light'></div>", unsafe_allow_html=True)

    # ===== Control para agregar días =====
    col_add = st.columns([1,1,6])
    with col_add[0]:
        if st.button("➕ Agregar día", type="secondary"):
            if "dias_editables" not in st.session_state:
                cargar_doc_en_session(rutina, dias_disponibles)
            _agregar_dia()

    # Si aún no hay "dias_editables", usamos los disponibles
    dias_numericos = st.session_state.get("dias_editables", dias_disponibles)
    dias_labels = [f"Día {int(d)}" for d in dias_numericos]

    # Progresión activa
    progresion_activa = st.radio(
        "Progresión activa", ["Progresión 1", "Progresión 2", "Progresión 3"],
        horizontal=True, index=0
    )

    # Tabs por día
    tabs = st.tabs(dias_labels)

    for i, tab in enumerate(tabs):
        with tab:
            tools_cols = st.columns([1, 9])
            if tools_cols[0].button("🧹 Limpiar día", key=f"limpiar_dia_{i+1}",
                                    help="Deja el día con 0 filas en Warm Up y Work Out", type="secondary"):
                limpiar_dia(i + 1)

            st.markdown("<div class='card'>", unsafe_allow_html=True)
            _asegurar_dia_en_session(i+1)
            render_tabla_dia(i, "Warm Up", progresion_activa, dias_labels)
            st.markdown("<div class='hr-light'></div>", unsafe_allow_html=True)
            render_tabla_dia(i, "Work Out", progresion_activa, dias_labels)
            st.markdown("</div>", unsafe_allow_html=True)  # /card
        st.markdown("<div class='hr-light'></div>", unsafe_allow_html=True)

    # ====== Guardado hacia ADELANTE (incluye semana actual) ======
    if st.button("💾 Aplicar cambios", type="primary", use_container_width=True):
        try:
            fecha_sel = datetime.strptime(semana_sel, "%Y-%m-%d")
        except ValueError:
            st.error("Formato de fecha inválido en 'semana_sel'.")
        else:
            dias_numericos = st.session_state.get("dias_editables", claves_dias(rutina) or ["1","2","3","4","5"])
            dias_labels_save = [f"Día {i}" for i in range(1, len(dias_numericos)+1)]

            nueva_rutina = construir_rutina_desde_session(dias_labels_save)

            total = 0
            for doc in db.collection("rutinas_semanales").where("correo","==",correo).stream():
                data = doc.to_dict() or {}
                f = data.get("fecha_lunes","")
                try:
                    f_dt = datetime.strptime(f, "%Y-%m-%d")
                except:
                    continue
                if f_dt >= fecha_sel:
                    rutina_existente = data.get("rutina", {}) or {}
                    for k_dia, lista in nueva_rutina.items():
                        if str(k_dia).isdigit():
                            rutina_existente[str(k_dia)] = lista
                    db.collection("rutinas_semanales").document(doc.id).update({"rutina": rutina_existente})
                    total += 1

            st.success(f"✅ Cambios aplicados en {total} semana(s) (incluida la actual).")

# Para ejecuciónes directa en Streamlit multipage
if __name__ == "__main__":
    editar_rutinas()

