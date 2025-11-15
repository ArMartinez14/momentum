# crear_descarga.py — Descarga con preview tipo editor + edición manual en grilla (igual a editar_rutinas)
import re
import unicodedata
import streamlit as st
from firebase_admin import credentials, firestore
from datetime import datetime
import firebase_admin
import json
import copy

from app_core.utils import (
    EMPRESA_ASESORIA,
    EMPRESA_DESCONOCIDA,
    EMPRESA_MOTION,
    correo_a_doc_id,
    empresa_de_usuario,
    usuario_activo,
)
from app_core.firebase_client import get_db
from app_core.video_utils import normalizar_link_youtube
from servicio_catalogos import get_catalogos, add_item

# =============== 🔐 FIREBASE ===============
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# =============== 🧰 UTILIDADES COMUNES ===============
def normalizar_correo(correo: str) -> str:
    return (correo or "").strip().lower().replace("@", "_").replace(".", "_")

def normalizar_texto(txt: str) -> str:
    txt = (txt or "").strip().lower()
    txt = unicodedata.normalize("NFD", txt).encode("ascii", "ignore").decode("utf-8")
    return re.sub(r"\s+", " ", txt)

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
    "Series", "RepsMin", "RepsMax", "Peso",
    "Tiempo", "Velocidad", "Descanso", "RIR",
    "RirMin", "RirMax", "Tipo", "Video",
    "Variable_1", "Cantidad_1", "Operacion_1", "Semanas_1",
    "CondicionVar_1", "CondicionOp_1", "CondicionValor_1",
    "Variable_2", "Cantidad_2", "Operacion_2", "Semanas_2",
    "CondicionVar_2", "CondicionOp_2", "CondicionValor_2",
    "Variable_3", "Cantidad_3", "Operacion_3", "Semanas_3",
    "CondicionVar_3", "CondicionOp_3", "CondicionValor_3",
    "BuscarEjercicio"
]

BASE_HEADERS = [
    "Circuito",
    "Buscar Ejercicio",
    "Ejercicio",
    "Detalle",
    "Series",
    "Repeticiones",
    "Peso",
    "RIR (Min/Max)",
    "Progresión",
    "Copiar",
    "Video",
    "Borrar",
]

BASE_SIZES = [1.0, 2.5, 2.5, 2.0, 0.7, 1.4, 1.0, 1.4, 1.0, 0.6, 0.6, 0.6]

PROGRESION_VAR_OPTIONS = ["", "peso", "velocidad", "tiempo", "descanso", "rir", "series", "repeticiones"]
PROGRESION_OP_OPTIONS = ["", "multiplicacion", "division", "suma", "resta"]
COND_VAR_OPTIONS = ["", "rir"]
COND_OP_OPTIONS = ["", ">", "<", ">=", "<="]


def tiene_video(nombre_ejercicio: str, ejercicios_dict: dict) -> bool:
    if not nombre_ejercicio:
        return False
    data = ejercicios_dict.get(nombre_ejercicio, {}) or {}
    link = str(data.get("video", "") or "").strip()
    return bool(link)


def get_circuit_options(seccion: str) -> list[str]:
    if (seccion or "").strip().lower() == "warm up":
        return ["A", "B", "C"]
    return list("DEFGHIJKL")


def clamp_circuito_por_seccion(circ: str, seccion: str) -> str:
    opciones = get_circuit_options(seccion)
    return circ if circ in opciones else opciones[0]


def _norm_text_admin(s: str) -> str:
    s = str(s or "")
    s = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("utf-8")
    s = re.sub(r"\\s+", " ", s).strip().casefold()
    return s


def _resolver_id_implemento(marca: str, maquina: str) -> str:
    db_local = get_db()
    marca_in = (marca or "").strip()
    maquina_in = (maquina or "").strip()
    if not marca_in or not maquina_in:
        return ""

    try:
        q = (
            db_local.collection("implementos")
            .where("marca", "==", marca_in)
            .where("maquina", "==", maquina_in)
        )
        hits = list(q.stream())
        if len(hits) == 1:
            return hits[0].id
        if len(hits) >= 2:
            return ""
    except Exception:
        pass

    mkey, maqkey = _norm_text_admin(marca_in), _norm_text_admin(maquina_in)
    try:
        candidatos = []
        for d in db_local.collection("implementos").limit(1000).stream():
            data = d.to_dict() or {}
            if _norm_text_admin(data.get("marca")) == mkey and _norm_text_admin(data.get("maquina")) == maqkey:
                candidatos.append(d.id)
        return candidatos[0] if len(candidatos) == 1 else ""
    except Exception:
        return ""


ADMIN_ROLES = {"admin", "administrador", "owner"}


def _tiene_permiso_agregar() -> bool:
    rol = (st.session_state.get("rol") or "").strip().lower()
    return rol in {"admin", "administrador", "entrenador"}


def es_admin() -> bool:
    rol = (st.session_state.get("rol") or "").strip().lower()
    return rol in {r.lower() for r in ADMIN_ROLES}


def correo_actual() -> str:
    return (st.session_state.get("correo") or "").strip().lower()


def slug_nombre(n: str) -> str:
    nn = normalizar_texto(n)
    return nn.replace(" ", "_")


def guardar_ejercicio_firestore(nombre_final: str, payload_base: dict) -> None:
    db_local = get_db()
    _es_admin = es_admin()
    _correo = correo_actual()

    publico_flag = bool(payload_base.pop("publico_flag", False)) if _es_admin else False

    empresa_propietaria = ""
    if _correo:
        empresa_propietaria = empresa_de_usuario(_correo)

    meta = {
        "nombre": nombre_final,
        "video": payload_base.get("video", ""),
        "implemento": payload_base.get("implemento", ""),
        "detalle": payload_base.get("detalle", ""),
        "caracteristica": payload_base.get("caracteristica", ""),
        "patron_de_movimiento": payload_base.get("patron_de_movimiento", ""),
        "grupo_muscular_principal": payload_base.get("grupo_muscular_principal", ""),
        "grupo_muscular": payload_base.get("grupo_muscular_principal", ""),
        "buscable_id": slug_nombre(nombre_final),
        "publico": publico_flag,
        "entrenador": ("" if _es_admin else _correo),
        "empresa_propietaria": empresa_propietaria,
        "updated_at": firestore.SERVER_TIMESTAMP,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    meta.update(payload_base or {})

    doc_id = slug_nombre(nombre_final) if _es_admin else f"{slug_nombre(nombre_final)}__{_correo or 'sin_correo'}"
    db_local.collection("ejercicios").document(doc_id).set(meta, merge=True)

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
    fila["Peso"]      = ej.get("Peso")      or ej.get("peso")      or ""
    fila["Tiempo"]    = ej.get("Tiempo")    or ej.get("tiempo")    or ""
    fila["Velocidad"] = ej.get("Velocidad") or ej.get("velocidad") or ""
    fila["RirMin"]    = ej.get("RirMin")    or ej.get("rir_min")   or ""
    fila["RirMax"]    = ej.get("RirMax")    or ej.get("rir_max")   or ""

    descanso_raw = ej.get("Descanso") or ej.get("descanso") or ""
    if isinstance(descanso_raw, str):
        s = descanso_raw.strip()
        fila["Descanso"] = s.split()[0] if s else ""
    elif descanso_raw is None:
        fila["Descanso"] = ""
    else:
        try:
            fila["Descanso"] = str(descanso_raw)
        except Exception:
            fila["Descanso"] = ""

    rir_str = ej.get("RIR") or ej.get("rir") or ""
    if not rir_str and (fila["RirMin"] or fila["RirMax"]):
        rmin = str(fila.get("RirMin") or "").strip()
        rmax = str(fila.get("RirMax") or "").strip()
        if rmin and rmax:
            rir_str = f"{rmin}-{rmax}"
        else:
            rir_str = rmin or rmax or ""
    fila["RIR"] = rir_str

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
    for p in (1, 2, 3):
        fila[f"Variable_{p}"] = ej.get(f"Variable_{p}", "")
        fila[f"Cantidad_{p}"] = ej.get(f"Cantidad_{p}", "")
        fila[f"Operacion_{p}"] = ej.get(f"Operacion_{p}", "")
        fila[f"Semanas_{p}"] = ej.get(f"Semanas_{p}", "")
        fila[f"CondicionVar_{p}"] = ej.get(f"CondicionVar_{p}", "")
        fila[f"CondicionOp_{p}"] = ej.get(f"CondicionOp_{p}", "")
        fila[f"CondicionValor_{p}"] = ej.get(f"CondicionValor_{p}", "")
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
    tiempo   = fila.get("Tiempo","")
    velocidad= fila.get("Velocidad","")
    descanso = str(fila.get("Descanso","") or "").strip()
    rir_min_txt = str(fila.get("RirMin","") or "").strip()
    rir_max_txt = str(fila.get("RirMax","") or "").strip()
    rir_min = _f(rir_min_txt)
    rir_max = _f(rir_max_txt)
    rir_str = str(fila.get("RIR","") or "").strip()
    if not rir_str:
        if rir_min_txt and rir_max_txt:
            rir_str = f"{rir_min_txt}-{rir_max_txt}"
        else:
            rir_str = rir_min_txt or rir_max_txt or ""
    resultado = {
        "bloque":    seccion,
        "circuito":  fila.get("Circuito",""),
        "ejercicio": fila.get("Ejercicio",""),
        "detalle":   fila.get("Detalle",""),
        "series":    series,
        "reps_min":  reps_min,
        "reps_max":  reps_max,
        "peso":      peso,
        "tiempo":    tiempo,
        "velocidad": velocidad,
        "descanso":  descanso,
        "rir":       rir_str,
        "rir_min":   rir_min,
        "rir_max":   rir_max,
        "tipo":      fila.get("Tipo",""),
        "video":     fila.get("Video",""),
    }
    for p in (1, 2, 3):
        resultado[f"Variable_{p}"] = fila.get(f"Variable_{p}", "")
        resultado[f"Cantidad_{p}"] = fila.get(f"Cantidad_{p}", "")
        resultado[f"Operacion_{p}"] = fila.get(f"Operacion_{p}", "")
        resultado[f"Semanas_{p}"] = fila.get(f"Semanas_{p}", "")
        resultado[f"CondicionVar_{p}"] = fila.get(f"CondicionVar_{p}", "")
        resultado[f"CondicionOp_{p}"] = fila.get(f"CondicionOp_{p}", "")
        resultado[f"CondicionValor_{p}"] = fila.get(f"CondicionValor_{p}", "")
    return resultado

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


def _limpiar_fila_manual(key_seccion: str, fila_idx: int, bloque_sel: str, key_ent: str) -> None:
    filas = st.session_state.get(key_seccion)
    if not isinstance(filas, list) or not (0 <= fila_idx < len(filas)):
        return
    filas[fila_idx] = _fila_vacia(bloque_sel)
    prefixes = [
        "circ",
        "buscar",
        "select",
        "det",
        "ser",
        "rmin",
        "rmax",
        "peso",
        "tiempo",
        "vel",
        "desc",
        "rirmin",
        "rirmax",
    ]
    for pref in prefixes:
        st.session_state.pop(f"{pref}_{key_ent}", None)
    for p in (1, 2, 3):
        st.session_state.pop(f"var{p}_{key_ent}", None)
        st.session_state.pop(f"ope{p}_{key_ent}", None)
        st.session_state.pop(f"cant{p}_{key_ent}", None)
        st.session_state.pop(f"sem{p}_{key_ent}", None)
        st.session_state.pop(f"condvar{p}_{key_ent}", None)
        st.session_state.pop(f"condop{p}_{key_ent}", None)
        st.session_state.pop(f"condval{p}_{key_ent}", None)
    st.session_state.pop(f"prog_check_{key_ent}", None)
    st.session_state.pop(f"copy_check_{key_ent}", None)
    st.session_state.pop(f"delete_{key_ent}", None)


def _limpiar_copy_destinos_descarga(key_seccion: str, dias_disponibles: list[str]) -> None:
    prefix = f"copy_dest_{key_seccion}_"
    for dia in dias_disponibles:
        st.session_state.pop(f"{prefix}{dia}", None)


def _get_or_init_descarga_rows(
    dia: str,
    bloque_sel: str,
    rutina_modificada_ref: dict,
) -> list[dict]:
    key_destino = f"descarga_dia_{dia}_{bloque_sel.replace(' ', '_')}"
    filas = st.session_state.get(key_destino)
    if not isinstance(filas, list):
        filas = []
    if not filas:
        ejercicios_dest = obtener_lista_ejercicios(rutina_modificada_ref.get(dia, []))
        filas = [
            _ejercicio_firestore_a_fila_ui(e)
            for e in ejercicios_dest
            if (e.get("bloque", "") == bloque_sel or e.get("Sección", "") == bloque_sel)
        ]
        for fila in filas:
            fila["Sección"] = bloque_sel
            fila["Circuito"] = clamp_circuito_por_seccion(fila.get("Circuito", "") or "", bloque_sel)
        st.session_state[key_destino] = filas
    return filas


def _copiar_filas_descarga(
    filas_para_copiar: list[tuple[int, dict]],
    dias_destino: list[str],
    dia_origen: str,
    bloque_sel: str,
    rutina_modificada_ref: dict,
) -> None:
    if not filas_para_copiar or not dias_destino:
        return
    for dia_dest in dias_destino:
        if dia_dest == dia_origen:
            continue
        dest_rows = _get_or_init_descarga_rows(dia_dest, bloque_sel, rutina_modificada_ref)
        for fila_idx, fila_src in filas_para_copiar:
            while len(dest_rows) <= fila_idx:
                base = _fila_vacia(bloque_sel)
                base["Sección"] = bloque_sel
                base["Circuito"] = clamp_circuito_por_seccion(base.get("Circuito", "") or "", bloque_sel)
                dest_rows.append(base)
            clon = dict(fila_src)
            clon["Sección"] = bloque_sel
            clon["Circuito"] = clamp_circuito_por_seccion(clon.get("Circuito", "") or "", bloque_sel)
            clon.pop("_delete_marked", None)
            dest_rows[fila_idx] = clon

        ejercicios_dia = obtener_lista_ejercicios(rutina_modificada_ref.get(dia_dest, []))
        otros = [
            e
            for e in ejercicios_dia
            if (e.get("bloque", "") != bloque_sel and e.get("Sección", "") != bloque_sel)
        ]
        rutina_modificada_ref[dia_dest] = otros + [_fila_ui_a_ejercicio_firestore_legacy(f) for f in dest_rows]


# =============== ✏️ EDICIÓN MANUAL EN GRILLA (igual al editor) ===============
def _asegurar_lista_session(key: str):
    if key not in st.session_state:
        st.session_state[key] = []

def _fila_vacia(seccion: str) -> dict:
    base = {k: "" for k in COLUMNAS_TABLA}
    base["Sección"] = seccion
    base["Circuito"] = clamp_circuito_por_seccion("", seccion)
    base["Descanso"] = ""
    base["RirMin"] = ""
    base["RirMax"] = ""
    return base


def _render_tabla_manual(
    dia_sel: str,
    bloque_sel: str,
    ejercicios_dia: list[dict],
    rutina_modificada_ref: dict,
    dias_disponibles: list[str],
):
    """
    Muestra y edita el bloque seleccionado replicando la UI de crear/editar rutina.
    Al enviar, reemplaza SOLO ese bloque dentro de rutina_modificada_ref[dia_sel].
    """
    key_seccion = f"descarga_dia_{dia_sel}_{bloque_sel.replace(' ','_')}"
    _asegurar_lista_session(key_seccion)

    if not st.session_state[key_seccion]:
        filas_ui = [
            _ejercicio_firestore_a_fila_ui(e)
            for e in ejercicios_dia
            if (e.get("bloque", "") == bloque_sel or e.get("Sección", "") == bloque_sel)
        ]
        filas_ui = _ordenar_por_circuito(filas_ui)
        for fila in filas_ui:
            fila["Sección"] = bloque_sel
            fila["Circuito"] = clamp_circuito_por_seccion(fila.get("Circuito", "") or "", bloque_sel)
            if fila.get("Sección") == "Work Out" and fila.get("Ejercicio"):
                fila["BuscarEjercicio"] = fila["Ejercicio"]
                fila["_exact_on_load"] = True
        st.session_state[key_seccion] = filas_ui

    st.subheader(bloque_sel)
    progresion_activa = st.radio(
        "Progresión activa",
        ["Progresión 1", "Progresión 2", "Progresión 3"],
        key=f"descarga_prog_{key_seccion}",
        horizontal=True,
    )

    ejercicios_dict = EJERCICIOS

    head_cols = st.columns([6.9, 1.1, 1.2, 1.2, 1.6], gap="small")
    head_cols[0].markdown(f"<h4 class='h-accent' style='margin-top:2px'>{bloque_sel}</h4>", unsafe_allow_html=True)

    show_tiempo_sec = head_cols[1].toggle(
        "Tiempo",
        key=f"show_tiempo_{key_seccion}",
        value=st.session_state.get(f"show_tiempo_{key_seccion}", False),
    )
    show_vel_sec = head_cols[2].toggle(
        "Velocidad",
        key=f"show_vel_{key_seccion}",
        value=st.session_state.get(f"show_vel_{key_seccion}", False),
    )
    show_descanso_sec = head_cols[3].toggle(
        "Descanso",
        key=f"show_desc_{key_seccion}",
        value=st.session_state.get(f"show_desc_{key_seccion}", False),
    )

    if _tiene_permiso_agregar():
        pop = head_cols[4].popover("＋", use_container_width=True)
        with pop:
            st.markdown("**📌 Crear o Editar Ejercicio (rápido)**")

            try:
                cat = get_catalogos()
            except Exception as e:
                st.error(f"No pude cargar catálogos: {e}")
                cat = {}
            catalogo_carac = cat.get("caracteristicas", []) or []
            catalogo_patron = cat.get("patrones_movimiento", []) or []
            catalogo_grupo_p = cat.get("grupo_muscular_principal", []) or []
            catalogo_grupo_s = cat.get("grupo_muscular_secundario", []) or []

            def _combo_con_agregar(label: str, opciones: list[str], key_base: str, valor_inicial: str = "") -> str:
                SENT = "➕ Agregar nuevo…"
                base_opts = sorted(opciones or [])
                if valor_inicial and valor_inicial not in base_opts:
                    base_opts.append(valor_inicial)
                opts = ["— Selecciona —"] + base_opts + [SENT]
                index_default = 0
                if valor_inicial:
                    try:
                        index_default = opts.index(valor_inicial)
                    except ValueError:
                        index_default = 0
                sel = st.selectbox(label, opts, index=index_default, key=f"{key_base}_sel_{key_seccion}")
                if sel == SENT:
                    st.markdown("<div class='card'>", unsafe_allow_html=True)
                    nuevo = st.text_input(
                        f"Ingresar nuevo valor para {label.lower()}:",
                        key=f"{key_base}_nuevo_{key_seccion}",
                    )
                    cols_add = st.columns([1, 1, 6])
                    with cols_add[0]:
                        if st.button("Guardar", key=f"{key_base}_guardar_{key_seccion}", type="primary"):
                            valor_limpio = (nuevo or "").strip()
                            if valor_limpio:
                                t = label.lower()
                                if "característica" in t or "caracteristica" in t:
                                    tipo = "caracteristicas"
                                elif "patrón" in t or "patron" in t:
                                    tipo = "patrones_movimiento"
                                elif "grupo muscular secundario" in t:
                                    tipo = "grupo_muscular_secundario"
                                elif "grupo muscular principal" in t:
                                    tipo = "grupo_muscular_principal"
                                else:
                                    tipo = "otros_catalogos"
                                add_item(tipo, valor_limpio)
                                st.success(f"Agregado: {valor_limpio}")
                                st.cache_data.clear()
                                st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
                    return ""
                if sel == "— Selecciona —":
                    return ""
                return sel

            detalle_prefill = ""
            pref_key = f"buscar_{dia_sel}_{bloque_sel.replace(' ','_')}_"
            try:
                for k, val in st.session_state.items():
                    if isinstance(val, str) and k.startswith(pref_key) and val.strip():
                        detalle_prefill = val.strip()
                        break
            except Exception:
                pass

            col_a, col_b = st.columns(2)
            with col_a:
                marca = st.text_input("Marca (opcional):", key=f"marca_top_{key_seccion}").strip()
            with col_b:
                maquina = st.text_input("Máquina (opcional):", key=f"maquina_top_{key_seccion}").strip()

            detalle = st.text_input("Detalle:", value=detalle_prefill, key=f"detalle_top_{key_seccion}")

            col_c, col_d = st.columns(2)
            with col_c:
                caracteristica = _combo_con_agregar("Característica", catalogo_carac, "carac_top")
            with col_d:
                patron = _combo_con_agregar("Patrón de Movimiento", catalogo_patron, "patron_top")

            col_e, col_f = st.columns(2)
            with col_e:
                grupo_p = _combo_con_agregar("Grupo Muscular Principal", catalogo_grupo_p, "grupo_p_top")
            with col_f:
                grupo_s = _combo_con_agregar("Grupo Muscular Secundario", catalogo_grupo_s, "grupo_s_top")

            video_url = st.text_input("URL del video (opcional):", key=f"video_top_{key_seccion}", placeholder="https://youtu.be/…")

            if marca and maquina:
                try:
                    implemento_id = _resolver_id_implemento(marca, maquina)
                    if implemento_id:
                        snap = get_db().collection("implementos").document(str(implemento_id)).get()
                        if snap.exists:
                            data_impl = snap.to_dict() or {}
                            st.success(f"Implemento detectado: ID **{implemento_id}** · {data_impl.get('marca','')} – {data_impl.get('maquina','')}")
                            pesos = data_impl.get("pesos", [])
                            if isinstance(pesos, dict):
                                pesos = [v for _, v in sorted(pesos.items(), key=lambda kv: int(kv[0]))]
                            if pesos:
                                st.caption("Pesos disponibles: " + ", ".join(str(p) for p in pesos))
                except Exception:
                    pass

            nombre_completo = " ".join(x for x in [marca, maquina, detalle] if x).strip()
            st.text_input("Nombre completo del ejercicio:", value=nombre_completo, key=f"nombre_top_{key_seccion}", disabled=True)

            publico_default = es_admin()
            publico_check = st.checkbox("Hacer público (visible para todos los entrenadores)", value=publico_default, key=f"pub_chk_{key_seccion}")

            col_btn, _ = st.columns([1, 3])
            with col_btn:
                if st.button("💾 Guardar Ejercicio", key=f"btn_guardar_top_{key_seccion}", type="primary", use_container_width=True):
                    faltantes = [
                        etiqueta
                        for etiqueta, valor in {
                            "Característica": caracteristica,
                            "Patrón de Movimiento": patron,
                            "Grupo Muscular Principal": grupo_p,
                        }.items()
                        if not (valor or "").strip()
                    ]
                    if faltantes:
                        st.warning("⚠️ Completa: " + ", ".join(faltantes))
                    else:
                        nombre_final = (nombre_completo or detalle or maquina or marca or "").strip()
                        if not nombre_final:
                            st.warning("⚠️ El campo 'nombre' es obligatorio (usa al menos Detalle/Máquina/Marca).")
                        else:
                            id_impl_final = _resolver_id_implemento(marca, maquina) if (marca and maquina) else ""
                            payload = {
                                "nombre": nombre_final,
                                "marca": marca,
                                "maquina": maquina,
                                "detalle": detalle,
                                "caracteristica": caracteristica,
                                "patron_de_movimiento": patron,
                                "grupo_muscular_principal": grupo_p,
                                "grupo_muscular_secundario": grupo_s or "",
                                "id_implemento": id_impl_final,
                                "video": (video_url or "").strip(),
                                "publico_flag": bool(publico_check),
                            }
                            try:
                                guardar_ejercicio_firestore(nombre_final, payload)
                                ejercicios_dict[nombre_final] = {
                                    "nombre": nombre_final,
                                    "marca": marca,
                                    "maquina": maquina,
                                    "detalle": detalle,
                                    "caracteristica": caracteristica,
                                    "patron_de_movimiento": patron,
                                    "grupo_muscular_principal": grupo_p,
                                    "grupo_muscular_secundario": grupo_s or "",
                                    "id_implemento": id_impl_final if id_impl_final else "",
                                    "publico": bool(publico_check),
                                    "video": (video_url or "").strip(),
                                }
                                st.success(f"✅ Ejercicio '{nombre_final}' guardado correctamente")
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as e:
                                st.error(f"❌ Error al guardar: {e}")
    else:
        head_cols[4].button("＋", use_container_width=True, disabled=True)
        head_cols[4].markdown(
            "<small>Solo Administrador o Entrenador pueden crear ejercicios.</small>",
            unsafe_allow_html=True,
        )

    ctrl_cols = st.columns([1.4, 1.4, 1.6, 5.6], gap="small")
    add_n = ctrl_cols[2].number_input(
        "N",
        min_value=1,
        max_value=10,
        value=1,
        key=f"addn_{key_seccion}",
        label_visibility="collapsed",
    )
    if ctrl_cols[0].button("➕ Agregar fila", key=f"add_{key_seccion}", type="secondary"):
        nuevas = [_fila_vacia(bloque_sel) for _ in range(int(add_n))]
        for fila in nuevas:
            fila["Sección"] = bloque_sel
            fila["Circuito"] = clamp_circuito_por_seccion(fila.get("Circuito", "") or "", bloque_sel)
        st.session_state[key_seccion].extend(nuevas)
        st.rerun()
    if ctrl_cols[1].button("➖ Quitar última", key=f"del_{key_seccion}", type="secondary"):
        if st.session_state[key_seccion]:
            st.session_state[key_seccion].pop()
            st.rerun()

    headers = BASE_HEADERS.copy()
    sizes = BASE_SIZES.copy()
    rir_idx = headers.index("RIR (Min/Max)")
    if show_tiempo_sec:
        headers.insert(rir_idx, "Tiempo")
        sizes.insert(rir_idx, 0.9)
        rir_idx += 1
    if show_vel_sec:
        headers.insert(rir_idx, "Velocidad")
        sizes.insert(rir_idx, 1.0)
        rir_idx += 1
    if show_descanso_sec:
        headers.insert(rir_idx, "Descanso")
        sizes.insert(rir_idx, 0.9)

    def _buscar_fuzzy_local(palabra: str) -> list[str]:
        if not palabra.strip():
            return []
        tokens = normalizar_texto(palabra).split()
        res = []
        for nombre in ejercicios_dict.keys():
            nn = normalizar_texto(nombre)
            if all(t in nn for t in tokens):
                res.append(nombre)
        return res

    st.caption("Los cambios se guardan automáticamente.")
    header_cols = st.columns(sizes)
    for c, title in zip(header_cols, headers):
        if title == "Video":
            inner = c.columns([1, 1, 1])
            inner[1].markdown("<div class='header-center'>Video</div>", unsafe_allow_html=True)
        else:
            c.markdown(f"<div class='header-center'>{title}</div>", unsafe_allow_html=True)

    filas_marcadas: list[tuple[int, str]] = []
    filas_para_copiar: list[tuple[int, dict]] = []
    pos = {header: idx for idx, header in enumerate(headers)}

    for idx, fila in enumerate(st.session_state[key_seccion]):
        fila["Sección"] = bloque_sel
        key_ent = f"{dia_sel}_{bloque_sel.replace(' ','_')}_{idx}"
        cols = st.columns(sizes)

        opciones_circuito = get_circuit_options(bloque_sel)
        circ_actual = fila.get("Circuito") or ""
        if circ_actual not in opciones_circuito:
            circ_actual = clamp_circuito_por_seccion(circ_actual, bloque_sel)
            fila["Circuito"] = circ_actual

        fila["Circuito"] = cols[pos["Circuito"]].selectbox(
            "",
            opciones_circuito,
            index=(opciones_circuito.index(fila["Circuito"]) if fila["Circuito"] in opciones_circuito else 0),
            key=f"circ_{key_ent}",
            label_visibility="collapsed",
        )

        buscar_key = f"buscar_{key_ent}"
        if buscar_key not in st.session_state:
            st.session_state[buscar_key] = fila.get("BuscarEjercicio", "")
        previo_buscar = fila.get("BuscarEjercicio", "")
        palabra = cols[pos["Buscar Ejercicio"]].text_input(
            "",
            value=st.session_state[buscar_key],
            key=buscar_key,
            label_visibility="collapsed",
            placeholder="Buscar ejercicio…",
        )
        if normalizar_texto(palabra) != normalizar_texto(previo_buscar):
            st.session_state.pop(f"select_{key_ent}", None)
            fila["_exact_on_load"] = False
        fila["BuscarEjercicio"] = palabra

        nombre_original = (fila.get("Ejercicio", "") or "").strip()
        exact_on_load = bool(fila.get("_exact_on_load", False))

        if exact_on_load:
            if (not palabra.strip()) or (normalizar_texto(palabra) == normalizar_texto(nombre_original)):
                ejercicios_encontrados = [nombre_original] if nombre_original else []
            else:
                ejercicios_encontrados = _buscar_fuzzy_local(palabra)
                fila["_exact_on_load"] = False
        else:
            ejercicios_encontrados = _buscar_fuzzy_local(palabra)

        if not ejercicios_encontrados and nombre_original:
            ejercicios_encontrados = [nombre_original]

        vistos = set()
        ejercicios_encontrados = [e for e in ejercicios_encontrados if not (e in vistos or vistos.add(e))]

        if not ejercicios_encontrados and palabra.strip():
            ejercicios_encontrados = [palabra.strip()]
        elif not ejercicios_encontrados:
            ejercicios_encontrados = ["(sin resultados)"]

        seleccionado = cols[pos["Ejercicio"]].selectbox(
            "",
            ejercicios_encontrados,
            key=f"select_{key_ent}",
            index=0,
            label_visibility="collapsed",
        )
        if seleccionado == "(sin resultados)":
            fila["Ejercicio"] = palabra.strip()
            fila["Video"] = (ejercicios_dict.get(fila["Ejercicio"], {}) or {}).get("video", "").strip()
        else:
            fila["Ejercicio"] = seleccionado
            fila["Video"] = (ejercicios_dict.get(seleccionado, {}) or {}).get("video", "").strip()

        fila["Detalle"] = cols[pos["Detalle"]].text_input(
            "",
            value=fila.get("Detalle", ""),
            key=f"det_{key_ent}",
            label_visibility="collapsed",
            placeholder="Notas (opcional)",
        )
        fila["Series"] = cols[pos["Series"]].text_input(
            "",
            value=fila.get("Series", ""),
            key=f"ser_{key_ent}",
            label_visibility="collapsed",
            placeholder="N°",
        )

        rep_cols = cols[pos["Repeticiones"]].columns(2)
        fila["RepsMin"] = rep_cols[0].text_input(
            "",
            value=str(fila.get("RepsMin", "")),
            key=f"rmin_{key_ent}",
            label_visibility="collapsed",
            placeholder="Min",
        )
        fila["RepsMax"] = rep_cols[1].text_input(
            "",
            value=str(fila.get("RepsMax", "")),
            key=f"rmax_{key_ent}",
            label_visibility="collapsed",
            placeholder="Max",
        )

        peso_widget_key = f"peso_{key_ent}"
        peso_value = fila.get("Peso", "")
        usar_text_input = True
        pesos_disponibles = []
        try:
            nombre_ej = fila.get("Ejercicio", "")
            ej_doc = ejercicios_dict.get(nombre_ej, {}) or {}
            id_impl = str(ej_doc.get("id_implemento", "") or "")
            if id_impl and id_impl != "1" and id_impl in IMPLEMENTOS:
                pesos_disponibles = IMPLEMENTOS[id_impl].get("pesos", []) or []
                if isinstance(pesos_disponibles, dict):
                    pesos_disponibles = [
                        v for _, v in sorted(pesos_disponibles.items(), key=lambda kv: int(kv[0]))
                    ]
                usar_text_input = not bool(pesos_disponibles)
        except Exception:
            usar_text_input = True

        if not usar_text_input and pesos_disponibles:
            opciones_peso = [str(p) for p in pesos_disponibles]
            if str(peso_value) not in opciones_peso:
                peso_value = opciones_peso[0]
            fila["Peso"] = cols[pos["Peso"]].selectbox(
                "",
                options=opciones_peso,
                index=(opciones_peso.index(str(peso_value)) if str(peso_value) in opciones_peso else 0),
                key=peso_widget_key,
                label_visibility="collapsed",
            )
        else:
            fila["Peso"] = cols[pos["Peso"]].text_input(
                "",
                value=str(peso_value),
                key=peso_widget_key,
                label_visibility="collapsed",
                placeholder="Kg",
            )

        if "Tiempo" in pos:
            fila["Tiempo"] = cols[pos["Tiempo"]].text_input(
                "",
                value=str(fila.get("Tiempo", "")),
                key=f"tiempo_{key_ent}",
                label_visibility="collapsed",
                placeholder="Seg",
            )
        else:
            fila.setdefault("Tiempo", "")

        if "Velocidad" in pos:
            fila["Velocidad"] = cols[pos["Velocidad"]].text_input(
                "",
                value=str(fila.get("Velocidad", "")),
                key=f"vel_{key_ent}",
                label_visibility="collapsed",
                placeholder="m/s",
            )
        else:
            fila.setdefault("Velocidad", "")

        if "Descanso" in pos:
            opciones_descanso = ["", "1", "2", "3", "4", "5"]
            valor_actual_desc = str(fila.get("Descanso", "")).strip().split(" ")[0]
            idx_desc = opciones_descanso.index(valor_actual_desc) if valor_actual_desc in opciones_descanso else 0
            fila["Descanso"] = cols[pos["Descanso"]].selectbox(
                "",
                options=opciones_descanso,
                index=idx_desc,
                key=f"desc_{key_ent}",
                label_visibility="collapsed",
                help="Minutos de descanso (1–5). Deja vacío si no aplica.",
            )
        else:
            fila.setdefault("Descanso", "")

        rir_cols = cols[pos["RIR (Min/Max)"]].columns(2)
        fila["RirMin"] = rir_cols[0].text_input(
            "",
            value=str(fila.get("RirMin", "")),
            key=f"rirmin_{key_ent}",
            label_visibility="collapsed",
            placeholder="Min",
        )
        fila["RirMax"] = rir_cols[1].text_input(
            "",
            value=str(fila.get("RirMax", "")),
            key=f"rirmax_{key_ent}",
            label_visibility="collapsed",
            placeholder="Max",
        )
        rmin_txt = str(fila.get("RirMin", "")).strip()
        rmax_txt = str(fila.get("RirMax", "")).strip()
        if rmin_txt and rmax_txt:
            fila["RIR"] = f"{rmin_txt}-{rmax_txt}"
        else:
            fila["RIR"] = rmin_txt or rmax_txt or ""

        prog_cols = cols[pos["Progresión"]].columns([1, 1, 1])
        mostrar_progresion = prog_cols[1].checkbox("", key=f"prog_check_{key_ent}")

        copy_cols = cols[pos["Copiar"]].columns([1, 1, 1])
        mostrar_copia = copy_cols[1].checkbox("", key=f"copy_check_{key_ent}")

        if mostrar_progresion:
            p = int(progresion_activa.split()[-1])
            pcols = st.columns([0.9, 0.9, 0.7, 0.8, 0.9, 0.9, 1.0])
            var_key = f"var{p}_{key_ent}"
            ope_key = f"ope{p}_{key_ent}"
            cant_key = f"cant{p}_{key_ent}"
            sem_key = f"sem{p}_{key_ent}"
            cond_var_key = f"condvar{p}_{key_ent}"
            cond_op_key = f"condop{p}_{key_ent}"
            cond_val_key = f"condval{p}_{key_ent}"

            fila[f"Variable_{p}"] = pcols[0].selectbox(
                "Variable",
                PROGRESION_VAR_OPTIONS,
                index=PROGRESION_VAR_OPTIONS.index(fila.get(f"Variable_{p}", "")) if fila.get(f"Variable_{p}", "") in PROGRESION_VAR_OPTIONS else 0,
                key=var_key,
            )
            fila[f"Operacion_{p}"] = pcols[1].selectbox(
                "Operación",
                PROGRESION_OP_OPTIONS,
                index=PROGRESION_OP_OPTIONS.index(fila.get(f"Operacion_{p}", "")) if fila.get(f"Operacion_{p}", "") in PROGRESION_OP_OPTIONS else 0,
                key=ope_key,
            )
            fila[f"Cantidad_{p}"] = pcols[2].text_input("Cant.", value=fila.get(f"Cantidad_{p}", ""), key=cant_key)
            fila[f"Semanas_{p}"] = pcols[3].text_input("Semanas", value=fila.get(f"Semanas_{p}", ""), key=sem_key)
            fila[f"CondicionVar_{p}"] = pcols[4].selectbox(
                "Condición",
                COND_VAR_OPTIONS,
                index=COND_VAR_OPTIONS.index(fila.get(f"CondicionVar_{p}", "")) if fila.get(f"CondicionVar_{p}", "") in COND_VAR_OPTIONS else 0,
                key=cond_var_key,
            )
            fila[f"CondicionOp_{p}"] = pcols[5].selectbox(
                "Operador",
                COND_OP_OPTIONS,
                index=COND_OP_OPTIONS.index(fila.get(f"CondicionOp_{p}", "")) if fila.get(f"CondicionOp_{p}", "") in COND_OP_OPTIONS else 0,
                key=cond_op_key,
            )
            fila[f"CondicionValor_{p}"] = pcols[6].text_input(
                "Valor condición",
                value=str(fila.get(f"CondicionValor_{p}", "") or ""),
                key=cond_val_key,
            )

        if mostrar_copia:
            filas_para_copiar.append((idx, dict(fila)))

        video_col_idx = pos.get("Video")
        if video_col_idx is not None:
            nombre_ej = str(fila.get("Ejercicio", "")).strip()
            video_url = str(fila.get("Video") or "").strip()
            if not video_url and nombre_ej:
                meta_video = ejercicios_dict.get(nombre_ej, {}) or {}
                video_url = str(meta_video.get("video") or meta_video.get("Video") or "").strip()
            video_cols = cols[video_col_idx].columns([1, 1, 1])
            video_url_norm = normalizar_link_youtube(video_url)
            if video_url_norm:
                with video_cols[1].popover("▶️", use_container_width=False):
                    st.video(video_url_norm)
            elif video_url:
                video_cols[1].markdown(f"[Ver video]({video_url})")
            else:
                video_cols[1].markdown("")

        borrar_key = f"delete_{key_ent}"
        borrar_cols = cols[pos["Borrar"]].columns([1, 1, 1])
        if borrar_cols[1].checkbox("", key=borrar_key):
            filas_marcadas.append((idx, key_ent))
            fila["_delete_marked"] = True
        else:
            fila.pop("_delete_marked", None)
            st.session_state.pop(borrar_key, None)

    total_dias = len(dias_disponibles)
    if filas_para_copiar and total_dias > 1:
        st.markdown("**📋 Copiar ejercicios marcados a otros días**")
        st.caption("Selecciona los días destino. La copia se ejecuta automáticamente.")
        destinos: list[str] = []
        prefix = f"copy_dest_{key_seccion}_"
        layout = [0.9] * total_dias + [6]
        dest_cols = st.columns(layout, gap="small")
        for idx_dia, dia in enumerate(dias_disponibles):
            col = dest_cols[idx_dia]
            disabled = dia == dia_sel
            checked = col.checkbox(
                f"Día {dia}",
                key=f"{prefix}{dia}",
                value=st.session_state.get(f"{prefix}{dia}", False),
                disabled=disabled,
            )
            if checked and not disabled:
                destinos.append(dia)
        if destinos:
            _copiar_filas_descarga(filas_para_copiar, destinos, dia_sel, bloque_sel, rutina_modificada_ref)
    else:
        _limpiar_copy_destinos_descarga(key_seccion, dias_disponibles)

    action_cols = st.columns([1.4, 1.6, 4.5])
    limpiar_clicked = action_cols[0].button("Limpiar sección", key=f"limpiar_{key_seccion}", type="secondary")
    aplicar_clicked = action_cols[1].button("Aplicar cambios en este bloque", key=f"aplicar_{key_seccion}", type="primary")
    pending_key = f"pending_clear_{key_seccion}"

    if limpiar_clicked:
        if filas_marcadas:
            for idx_sel, key_sel in filas_marcadas:
                _limpiar_fila_manual(key_seccion, idx_sel, bloque_sel, key_sel)
            st.session_state.pop(pending_key, None)
            st.success("Fila(s) limpiadas ✅")
            st.rerun()
        elif st.session_state.get(pending_key):
            for idx_sel in range(len(st.session_state[key_seccion])):
                key_sel = f"{dia_sel}_{bloque_sel.replace(' ', '_')}_{idx_sel}"
                _limpiar_fila_manual(key_seccion, idx_sel, bloque_sel, key_sel)
            st.session_state[key_seccion] = [_fila_vacia(bloque_sel)]
            _limpiar_copy_destinos_descarga(key_seccion, dias_disponibles)
            st.session_state.pop(pending_key, None)
            st.success("Sección limpiada ✅")
            st.rerun()
        else:
            st.session_state[pending_key] = True

    if st.session_state.get(pending_key) and not filas_marcadas:
        st.warning("Vuelve a presionar **Limpiar sección** para confirmar el borrado.")
    elif filas_marcadas:
        st.session_state.pop(pending_key, None)

    if aplicar_clicked:
        if filas_marcadas:
            for idx_sel, _ in sorted(filas_marcadas, reverse=True):
                if 0 <= idx_sel < len(st.session_state[key_seccion]):
                    st.session_state[key_seccion].pop(idx_sel)

        nuevos = [_fila_ui_a_ejercicio_firestore_legacy(f) for f in st.session_state[key_seccion]]

        ejercicios_dia_full = obtener_lista_ejercicios(rutina_modificada_ref.get(dia_sel, []))
        otros = [
            e
            for e in ejercicios_dia_full
            if (e.get("bloque", "") != bloque_sel and e.get("Sección", "") != bloque_sel)
        ]
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

        if permitido and usuario_activo(correo_cli, usuarios_map, default_if_missing=True):
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
        _render_tabla_manual(dia_sel, bloque_sel, ejercicios_dia, rutina_modificada, dias_disponibles)

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
