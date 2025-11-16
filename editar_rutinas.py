from __future__ import annotations

import copy
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
import pandas as pd
import streamlit as st
from firebase_admin import firestore

from app_core.ejercicios_catalogo import obtener_ejercicios_disponibles
from app_core.firebase_client import get_db
from app_core.email_notifications import enviar_correo_rutina_disponible
from app_core.theme import inject_theme
from app_core.video_utils import (
    normalizar_link_youtube as _normalizar_link_youtube,
    normalizar_video_url as _normalizar_video_url,
)
from app_core.utils import (
    EMPRESA_ASESORIA,
    EMPRESA_DESCONOCIDA,
    EMPRESA_MOTION,
    correo_a_doc_id,
    empresa_de_usuario,
    usuario_activo,
)
from servicio_catalogos import add_item, get_catalogos

# ===================== 🎨 ESTILOS / CONFIG =====================
inject_theme()

DEFAULT_WU_ROWS_NEW_DAY = 0
DEFAULT_WO_ROWS_NEW_DAY = 0
SECTION_BREAK_HTML = "<div style='height:0;margin:14px 0;'></div>"
SECTION_CONTAINER_HTML = "<div class='editor-block'>"
RUTINA_STATE_OWNER_KEY = "_rutina_dias_owner"

# ===================== 🔧 HELPERS BÁSICOS =====================
def normalizar_texto(valor: str) -> str:
    txt = (valor or "").strip().lower()
    return unicodedata.normalize("NFD", txt).encode("ascii", "ignore").decode("utf-8")


def _f(valor) -> float | None:
    try:
        txt = str(valor).strip().replace(",", ".")
        if txt == "":
            return None
        if "-" in txt:
            txt = txt.split("-", 1)[0].strip()
        return float(txt)
    except Exception:
        return None


def _parse_series_count(valor) -> int:
    if isinstance(valor, (int, float)):
        return max(0, int(valor))
    s = str(valor or "").strip()
    if not s:
        return 0
    match = re.search(r"\d+", s)
    if not match:
        return 0
    try:
        return max(0, int(match.group()))
    except Exception:
        return 0


def _ensure_topset_len(data: list[dict] | None, length: int) -> list[dict]:
    plantilla = {"Series": "", "RepsMin": "", "RepsMax": "", "Peso": "", "RirMin": "", "RirMax": ""}
    data = list(data or [])
    if length < 0:
        length = 0
    while len(data) < length:
        data.append(dict(plantilla))
    while len(data) > length:
        data.pop()
    return data


def _normalizar_topset_data(raw) -> list[dict]:
    campos = ("Series", "RepsMin", "RepsMax", "Peso", "RirMin", "RirMax")
    if isinstance(raw, dict):
        iterable = raw.values()
    elif isinstance(raw, (list, tuple)):
        iterable = raw
    else:
        iterable = []
    resultado: list[dict] = []
    for item in iterable:
        if not isinstance(item, dict):
            continue
        limpio = {}
        tiene_valor = False
        for campo in campos:
            valor = item.get(campo)
            if valor in (None, ""):
                valor = item.get(campo.lower(), "")
            texto = str(valor).strip()
            limpio[campo] = texto
            if texto:
                tiene_valor = True
        if tiene_valor:
            resultado.append(limpio)
    return resultado


def _video_de_catalogo(nombre: str) -> str:
    meta = EJERCICIOS.get(nombre, {}) or {}
    return (meta.get("video") or meta.get("Video") or "").strip()


def _buscable_id(nombre: str) -> str:
    return normalizar_texto(nombre).replace(" ", "_")


def _candidatos_por_slug(db, slug: str) -> list[dict]:
    if not slug:
        return []
    cache = st.session_state.setdefault("_catalogo_por_slug_cache", {})
    if slug in cache:
        return cache[slug]
    try:
        snaps = list(db.collection("ejercicios").where("buscable_id", "==", slug).stream())
    except Exception as exc:
        if not st.session_state.get("_catalogo_slug_cache_error"):
            st.warning(f"No se pudo leer el catálogo de ejercicios para validar videos: {exc}")
            st.session_state["_catalogo_slug_cache_error"] = True
        cache[slug] = []
        return []
    resultado: list[dict] = []
    for snap in snaps:
        if not snap.exists:
            continue
        data = snap.to_dict() or {}
        data["_doc_id"] = snap.id
        resultado.append(data)
    cache[slug] = resultado
    return resultado


def _candidatos_locales_por_slug(slug: str) -> list[dict]:
    global EJERCICIOS
    if not slug:
        return []
    catalogo_local = EJERCICIOS or {}
    if not catalogo_local:
        catalogo_local = _refrescar_catalogo()
        if isinstance(catalogo_local, dict):
            EJERCICIOS.update(catalogo_local)
    coincidencias: list[dict] = []
    for nombre, data in catalogo_local.items():
        if _buscable_id(nombre) != slug:
            continue
        entrada = dict(data or {})
        if "_doc_id" not in entrada:
            doc_id = entrada.get("doc_id") or entrada.get("id") or ""
            if not doc_id:
                doc_id = slug
            entrada["_doc_id"] = doc_id
        coincidencias.append(entrada)
    return coincidencias


def _video_catalogo_para_nombre(db, nombre: str, correo_entrenador: str) -> tuple[str, str]:
    slug = _buscable_id(nombre)
    if not slug:
        return "", ""
    candidatos = _candidatos_por_slug(db, slug)
    if not candidatos:
        candidatos = _candidatos_locales_por_slug(slug)
    if not candidatos:
        return "", ""
    correo_norm = (correo_entrenador or "").strip().lower()
    mejor_video = ""
    mejor_doc = ""
    mejor_prioridad = -1
    for candidato in candidatos:
        video = (candidato.get("video") or candidato.get("Video") or "").strip()
        if not video:
            continue
        entrenador_doc = (candidato.get("entrenador") or "").strip().lower()
        prioridad = 0
        if correo_norm and entrenador_doc and entrenador_doc == correo_norm:
            prioridad = 3
        elif not entrenador_doc:
            prioridad = 2
        elif candidato.get("publico"):
            prioridad = 1
        if prioridad > mejor_prioridad:
            mejor_prioridad = prioridad
            mejor_video = video
            mejor_doc = candidato.get("_doc_id") or ""
    if mejor_prioridad < 0:
        return "", ""
    return mejor_video, mejor_doc


def _norm_text_admin(valor: str) -> str:
    raw = str(valor or "")
    raw = unicodedata.normalize("NFKD", raw).encode("ASCII", "ignore").decode("utf-8")
    return re.sub(r"\s+", " ", raw).strip().casefold()


def clamp_circuito_por_seccion(valor: str, seccion: str) -> str:
    opciones = ["A", "B", "C"] if (seccion or "").strip().lower() == "warm up" else list("DEFGHIJKL")
    return valor if valor in opciones else opciones[0]


def get_circuit_options(seccion: str) -> list[str]:
    return ["A", "B", "C"] if (seccion or "").strip().lower() == "warm up" else list("DEFGHIJKL")


def tiene_video(nombre: str, ejercicios_dict: dict) -> bool:
    return bool(_video_de_catalogo(nombre) or (ejercicios_dict.get(nombre, {}) or {}).get("video"))


def _resolver_id_implemento(marca: str, maquina: str) -> str:
    db = get_db()
    marca_in, maquina_in = (marca or "").strip(), (maquina or "").strip()
    if not marca_in or not maquina_in:
        return ""
    try:
        consulta = (
            db.collection("implementos")
            .where("marca", "==", marca_in)
            .where("maquina", "==", maquina_in)
        )
        hits = list(consulta.stream())
        if len(hits) == 1:
            return hits[0].id
        if len(hits) >= 2:
            return ""
    except Exception:
        pass

    clave_marca, clave_maquina = _norm_text_admin(marca_in), _norm_text_admin(maquina_in)
    try:
        candidatos: list[str] = []
        for doc in db.collection("implementos").limit(1000).stream():
            data = doc.to_dict() or {}
            if _norm_text_admin(data.get("marca")) == clave_marca and _norm_text_admin(data.get("maquina")) == clave_maquina:
                candidatos.append(doc.id)
        return candidatos[0] if len(candidatos) == 1 else ""
    except Exception:
        return ""


CARDIO_FIELDS = (
    "tipo",
    "modalidad",
    "indicaciones",
    "series",
    "intervalos",
    "tiempo_trabajo",
    "intensidad_trabajo",
    "tiempo_descanso",
    "tipo_descanso",
    "intensidad_descanso",
)


def _default_cardio_data() -> dict:
    return {
        "tipo": "LISS",
        "modalidad": "",
        "indicaciones": "",
        "series": "",
        "intervalos": "",
        "tiempo_trabajo": "",
        "intensidad_trabajo": "",
        "tiempo_descanso": "",
        "tipo_descanso": "",
        "intensidad_descanso": "",
    }


def _normalizar_cardio_data(cardio: dict | None) -> dict:
    data = _default_cardio_data()
    if isinstance(cardio, dict):
        for campo in data:
            valor = cardio.get(campo, data[campo])
            if isinstance(valor, str):
                data[campo] = valor.strip()
            else:
                data[campo] = valor
    if data["tipo"] not in {"LISS", "HIIT"}:
        data["tipo"] = "LISS"
    return data


def _cardio_tiene_datos(cardio: dict | None) -> bool:
    if not isinstance(cardio, dict):
        return False
    for campo in CARDIO_FIELDS:
        if campo == "tipo":
            continue
        valor = cardio.get(campo, "")
        if isinstance(valor, str) and valor.strip():
            return True
        if not isinstance(valor, str) and valor not in (None, ""):
            return True
    return False


def _set_cardio_en_session(idx_dia: int, cardio_data: dict | None) -> None:
    key = f"rutina_dia_{idx_dia}_Cardio"
    normalizado = _normalizar_cardio_data(cardio_data)
    st.session_state[key] = normalizado
    for campo, valor in normalizado.items():
        st.session_state[f"{key}_{campo}"] = valor


def _sync_cardio_desde_widgets(idx_dia: int) -> dict:
    key = f"rutina_dia_{idx_dia}_Cardio"
    base = _normalizar_cardio_data(st.session_state.get(key))
    for campo in CARDIO_FIELDS:
        widget_key = f"{key}_{campo}"
        if widget_key not in st.session_state:
            continue
        valor = st.session_state.get(widget_key)
        if isinstance(valor, str):
            base[campo] = valor.strip()
        else:
            base[campo] = valor
    st.session_state[key] = base
    return base


def correo_actual() -> str:
    return (st.session_state.get("correo") or "").strip().lower()


def es_admin() -> bool:
    rol = (st.session_state.get("rol") or "").strip().lower()
    return rol in {"admin", "administrador", "owner"}


def _tiene_permiso_agregar() -> bool:
    rol = (st.session_state.get("rol") or "").strip().lower()
    return rol in {"admin", "administrador", "entrenador"}


def guardar_ejercicio_firestore(nombre_final: str, payload_base: dict) -> None:
    db = get_db()
    admin_flag = es_admin()
    correo = correo_actual()

    publico_flag = bool(payload_base.pop("publico_flag", False)) if admin_flag else False
    empresa_propietaria = empresa_de_usuario(correo) if correo else ""

    meta = {
        "nombre": nombre_final,
        "video": payload_base.get("video", ""),
        "implemento": payload_base.get("implemento", ""),
        "detalle": payload_base.get("detalle", ""),
        "caracteristica": payload_base.get("caracteristica", ""),
        "patron_de_movimiento": payload_base.get("patron_de_movimiento", ""),
        "grupo_muscular_principal": payload_base.get("grupo_muscular_principal", ""),
        "grupo_muscular": payload_base.get("grupo_muscular_principal", ""),
        "buscable_id": normalizar_texto(nombre_final).replace(" ", "_"),
        "publico": publico_flag,
        "entrenador": ("" if admin_flag else correo),
        "empresa_propietaria": empresa_propietaria,
        "updated_at": firestore.SERVER_TIMESTAMP,
        "created_at": firestore.SERVER_TIMESTAMP,
    }
    meta.update(payload_base or {})

    doc_id = (
        normalizar_texto(nombre_final).replace(" ", "_")
        if admin_flag
        else f"{normalizar_texto(nombre_final).replace(' ', '_')}__{correo or 'sin_correo'}"
    )
    db.collection("ejercicios").document(doc_id).set(meta, merge=True)


# ===================== 📦 CACHE =====================
@st.cache_data(show_spinner=False)
def cargar_usuarios():
    db = get_db()
    return [doc.to_dict() for doc in db.collection("usuarios").stream() if doc.exists]


@st.cache_data(show_spinner=False)
def cargar_implementos():
    db = get_db()
    impl: dict[str, dict] = {}
    for doc in db.collection("implementos").stream():
        data = doc.to_dict() or {}
        data["pesos"] = data.get("pesos", [])
        impl[str(doc.id)] = data
    return impl


def _refrescar_catalogo() -> dict[str, dict]:
    return obtener_ejercicios_disponibles()


EJERCICIOS: dict[str, dict] = {}
USUARIOS = cargar_usuarios()
IMPLEMENTOS = cargar_implementos()


def obtener_lista_ejercicios(data_dia):
    if data_dia is None:
        return []
    if isinstance(data_dia, dict):
        if "ejercicios" in data_dia:
            ejercicios = data_dia["ejercicios"]
            if isinstance(ejercicios, dict):
                try:
                    pares = sorted(ejercicios.items(), key=lambda kv: int(kv[0]))
                    return [e for _, e in pares if isinstance(e, (dict, str))]
                except Exception:
                    return [e for e in ejercicios.values() if isinstance(e, (dict, str))]
            if isinstance(ejercicios, list):
                return [e for e in ejercicios if isinstance(e, (dict, str))]
            return []
        claves_num = [k for k in data_dia.keys() if str(k).isdigit()]
        if claves_num:
            try:
                pares = sorted(((k, data_dia[k]) for k in claves_num), key=lambda kv: int(kv[0]))
                return [v for _, v in pares if isinstance(v, (dict, str))]
            except Exception:
                return [data_dia[k] for k in data_dia if isinstance(data_dia[k], (dict, str))]
        return [v for v in data_dia.values() if isinstance(v, (dict, str))]
    if isinstance(data_dia, list):
        if len(data_dia) == 1 and isinstance(data_dia[0], dict) and "ejercicios" in data_dia[0]:
            return obtener_lista_ejercicios(data_dia[0])
        return [e for e in data_dia if isinstance(e, (dict, str))]
    if isinstance(data_dia, str):
        return [data_dia]
    return []


def _es_ejercicio_dict(entry) -> bool:
    if not isinstance(entry, dict):
        return False
    nombre = (entry.get("Ejercicio") or entry.get("ejercicio") or "").strip()
    return bool(nombre)


def _iterar_ejercicios_en_obj(data) -> list[dict]:
    """Devuelve todas las referencias de ejercicios sin importar la estructura del día."""
    ejercicios: list[dict] = []
    stack = [data]
    while stack:
        actual = stack.pop()
        if isinstance(actual, dict):
            if _es_ejercicio_dict(actual):
                ejercicios.append(actual)
                continue
            for value in actual.values():
                if isinstance(value, (dict, list)):
                    stack.append(value)
        elif isinstance(actual, list):
            for item in actual:
                if isinstance(item, (dict, list)):
                    stack.append(item)
    return ejercicios


def _obtener_data_dia(rutina: dict, dia_clave: str):
    claves = [dia_clave]
    try:
        idx = int(dia_clave)
        claves.append(str(idx))
        claves.append(idx)
    except Exception:
        claves.append(str(dia_clave))
    for clave in claves:
        if clave in rutina:
            return rutina[clave]
    return None


def _aplicar_videos_faltantes_en_obj(obj, pendientes: list[dict]) -> int:
    cambios = 0
    if isinstance(obj, dict):
        if _es_ejercicio_dict(obj):
            video_actual = (obj.get("Video") or obj.get("video") or "").strip()
            if not video_actual:
                nombre = (obj.get("Ejercicio") or obj.get("ejercicio") or "").strip()
                nombre_norm = normalizar_texto(nombre)
                idx = next((i for i, item in enumerate(pendientes) if item["nombre_norm"] == nombre_norm), None)
                if idx is not None:
                    link = pendientes.pop(idx)["link"]
                    obj["Video"] = link
                    obj["video"] = link
                    cambios += 1
            return cambios
        for valor in obj.values():
            if isinstance(valor, (dict, list)):
                cambios += _aplicar_videos_faltantes_en_obj(valor, pendientes)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                cambios += _aplicar_videos_faltantes_en_obj(item, pendientes)
    return cambios


def _aplicar_videos_catalogo_en_obj(obj, reemplazos: list[dict]) -> int:
    cambios = 0
    if isinstance(obj, dict):
        if _es_ejercicio_dict(obj):
            nombre = (obj.get("Ejercicio") or obj.get("ejercicio") or "").strip()
            video_actual = (obj.get("Video") or obj.get("video") or "").strip()
            nombre_norm = normalizar_texto(nombre)
            video_norm = _normalizar_video_url(video_actual)
            idx = next(
                (
                    i
                    for i, item in enumerate(reemplazos)
                    if item["nombre_norm"] == nombre_norm and item["video_actual_norm"] == video_norm
                ),
                None,
            )
            if idx is not None:
                link = reemplazos.pop(idx)["video_catalogo"]
                obj["Video"] = link
                obj["video"] = link
                cambios += 1
            return cambios
        for valor in obj.values():
            if isinstance(valor, (dict, list)):
                cambios += _aplicar_videos_catalogo_en_obj(valor, reemplazos)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                cambios += _aplicar_videos_catalogo_en_obj(item, reemplazos)
    return cambios

# ===================== DEF. COLUMNAS UI =====================
COLUMNAS_TABLA = [
    "Circuito",
    "Sección",
    "Ejercicio",
    "Detalle",
    "Series",
    "RepsMin",
    "RepsMax",
    "Peso",
    "Tiempo",
    "Descanso",
    "RIR",
    "RirMin",
    "RirMax",
    "Tipo",
    "Video",
    "Variable_1",
    "Cantidad_1",
    "Operacion_1",
    "Semanas_1",
    "CondicionVar_1",
    "CondicionOp_1",
    "CondicionValor_1",
    "Variable_2",
    "Cantidad_2",
    "Operacion_2",
    "Semanas_2",
    "CondicionVar_2",
    "CondicionOp_2",
    "CondicionValor_2",
    "Variable_3",
    "Cantidad_3",
    "Operacion_3",
    "Semanas_3",
    "CondicionVar_3",
    "CondicionOp_3",
    "CondicionValor_3",
    "BuscarEjercicio",
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
    "Set Mode",
    "Copiar",
    "Borrar",
    "Video",
]

BASE_SIZES = [0.9, 2.4, 2.8, 2.0, 0.8, 1.4, 1.0, 1.3, 1.0, 1.0, 0.6, 0.6, 0.9]

PROGRESION_VAR_OPTIONS = ["", "peso", "tiempo", "descanso", "rir", "series", "repeticiones"]
PROGRESION_OP_OPTIONS = ["", "multiplicacion", "division", "suma", "resta"]
COND_VAR_OPTIONS = ["", "rir"]
COND_OP_OPTIONS = ["", ">", "<", ">=", "<="]


def _header_slug(label: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", label.lower()).strip("-")
    return slug or "col"


METRIC_LEGEND_HTML = """
<div class="metric-legend metric-legend--rutina">
  <span class="metric-chip metric-chip--series">Texto Series</span>
  <span class="metric-chip metric-chip--reps">Texto Repeticiones</span>
  <span class="metric-chip metric-chip--peso">Texto Peso</span>
  <span class="metric-chip metric-chip--rir">Texto RIR</span>
  <span class="video-legend-button" role="status">Ejercicio con video</span>
</div>
"""


# ===================== MAPEO RUTINA <-> UI =====================
def _fila_vacia(seccion: str) -> dict:
    base = {k: "" for k in COLUMNAS_TABLA}
    base["Sección"] = seccion
    base["Circuito"] = clamp_circuito_por_seccion("", seccion)
    base["RirMin"] = ""
    base["RirMax"] = ""
    base["Descanso"] = ""
    return base


def _ejercicio_firestore_a_fila_ui(ej: dict) -> dict:
    fila = _fila_vacia(ej.get("Sección") or ej.get("bloque") or "")
    seccion = fila["Sección"]
    circuito_original = (ej.get("Circuito") or ej.get("circuito") or "").strip()
    fila["Circuito"] = circuito_original or clamp_circuito_por_seccion("", seccion)
    if not seccion:
        if circuito_original in {"A", "B", "C"}:
            fila["Sección"] = "Warm Up"
        elif circuito_original:
            fila["Sección"] = "Work Out"
        seccion = fila["Sección"]
    fila["Ejercicio"] = ej.get("Ejercicio") or ej.get("ejercicio") or ""
    if seccion == "Work Out":
        fila["BuscarEjercicio"] = fila["Ejercicio"]
        fila["_exact_on_load"] = True
    fila["Detalle"] = ej.get("Detalle") or ej.get("detalle") or ""
    fila["Series"] = ej.get("Series") or ej.get("series") or ""
    fila["Peso"] = ej.get("Peso") or ej.get("peso") or ""
    fila["Tiempo"] = ej.get("Tiempo") or ej.get("tiempo") or ""
    fila["RirMin"] = ej.get("RirMin") or ej.get("rir_min") or ""
    fila["RirMax"] = ej.get("RirMax") or ej.get("rir_max") or ""
    fila["RIR"] = ej.get("RIR") or ej.get("rir") or ""
    fila["Descanso"] = str(ej.get("Descanso") or ej.get("descanso") or "").split(" ")[0]
    fila["Tipo"] = ej.get("Tipo") or ej.get("tipo") or ""
    video_raw = ej.get("Video") or ej.get("video") or ""
    video_norm = _normalizar_video_url(video_raw)
    fila["Video"] = video_norm or video_raw or ""
    fila["RirMin"] = fila["RirMin"] or fila["RIR"]
    fila["RirMax"] = fila["RirMax"] or fila["RIR"]
    top_sets_raw = ej.get("TopSetData") or ej.get("top_sets") or ej.get("TopSets")
    fila["TopSetData"] = _normalizar_topset_data(top_sets_raw)

    reps = ej.get("repeticiones")
    if "RepsMin" in ej or "RepsMax" in ej:
        fila["RepsMin"] = ej.get("RepsMin", "")
        fila["RepsMax"] = ej.get("RepsMax", "")
    elif "reps_min" in ej or "reps_max" in ej:
        fila["RepsMin"] = ej.get("reps_min", "")
        fila["RepsMax"] = ej.get("reps_max", "")
    elif isinstance(reps, str):
        if "-" in reps:
            mn, mx = reps.split("-", 1)
            fila["RepsMin"], fila["RepsMax"] = mn.strip(), mx.strip()
        else:
            fila["RepsMin"], fila["RepsMax"] = reps.strip(), ""

    for p in (1, 2, 3):
        fila[f"Variable_{p}"] = ej.get(f"Variable_{p}", "")
        fila[f"Cantidad_{p}"] = ej.get(f"Cantidad_{p}", "")
        fila[f"Operacion_{p}"] = ej.get(f"Operacion_{p}", "")
        fila[f"Semanas_{p}"] = ej.get(f"Semanas_{p}", "")
        fila[f"CondicionVar_{p}"] = ej.get(f"CondicionVar_{p}", "")
        fila[f"CondicionOp_{p}"] = ej.get(f"CondicionOp_{p}", "")
        fila[f"CondicionValor_{p}"] = ej.get(f"CondicionValor_{p}", "")

    if not fila["Video"]:
        video_catalogo = _video_de_catalogo(fila["Ejercicio"])
        fila["Video"] = video_catalogo or ""
    return fila


def _fila_ui_a_ejercicio_firestore_legacy(fila: dict) -> dict:
    seccion = fila.get("Sección") or ""
    if seccion not in ["Warm Up", "Work Out"]:
        seccion = "Warm Up" if (fila.get("Circuito") or "") in ["A", "B", "C"] else "Work Out"
    reps_min = _f(fila.get("RepsMin"))
    reps_max = _f(fila.get("RepsMax"))
    rir_min = _f(fila.get("RirMin"))
    rir_max = _f(fila.get("RirMax"))
    rir_txt = fila.get("RIR") or ""

    resultado = {
        "bloque": seccion,
        "circuito": fila.get("Circuito", ""),
        "ejercicio": fila.get("Ejercicio", ""),
        "detalle": fila.get("Detalle", ""),
        "series": _f(fila.get("Series")),
        "reps_min": reps_min,
        "reps_max": reps_max,
        "peso": _f(fila.get("Peso")),
        "tiempo": fila.get("Tiempo", ""),
        "descanso": fila.get("Descanso", ""),
        "rir_min": rir_min if rir_min is not None else _f(rir_txt),
        "rir_max": rir_max if rir_max is not None else _f(rir_txt),
        "rir": rir_txt,
        "tipo": fila.get("Tipo", ""),
        "video": fila.get("Video", ""),
    }
    for p in (1, 2, 3):
        resultado[f"Variable_{p}"] = fila.get(f"Variable_{p}", "")
        resultado[f"Cantidad_{p}"] = fila.get(f"Cantidad_{p}", "")
        resultado[f"Operacion_{p}"] = fila.get(f"Operacion_{p}", "")
        resultado[f"Semanas_{p}"] = fila.get(f"Semanas_{p}", "")
        resultado[f"CondicionVar_{p}"] = fila.get(f"CondicionVar_{p}", "")
        resultado[f"CondicionOp_{p}"] = fila.get(f"CondicionOp_{p}", "")
        resultado[f"CondicionValor_{p}"] = fila.get(f"CondicionValor_{p}", "")
    top_sets = fila.get("TopSetData")
    normalizados = _normalizar_topset_data(top_sets)
    if normalizados:
        resultado["TopSetData"] = normalizados
    return resultado


def claves_dias(rutina_dict: dict) -> list[str]:
    dias = [str(k) for k in (rutina_dict or {}).keys() if str(k).isdigit()]
    return sorted(dias, key=lambda x: int(x))


# ===================== SINCRONIZACIÓN VIDEOS =====================
def _buscar_videos_faltantes(doc_data: dict, catalogo: dict[str, dict]) -> list[tuple[str, str, str]]:
    rutina_actual = doc_data.get("rutina", {}) or {}
    if not isinstance(rutina_actual, dict):
        return []
    pendientes: list[tuple[str, str, str]] = []
    for dia, ejercicios in rutina_actual.items():
        for ejercicio in _iterar_ejercicios_en_obj(ejercicios):
            video_actual = (ejercicio.get("Video") or ejercicio.get("video") or "").strip()
            if video_actual:
                continue
            nombre = (ejercicio.get("Ejercicio") or ejercicio.get("ejercicio") or "").strip()
            if not nombre:
                continue
            link = (catalogo.get(nombre, {}) or {}).get("video") or (catalogo.get(nombre, {}) or {}).get("Video") or ""
            link = link.strip()
            if link:
                pendientes.append((str(dia), nombre, link))
    return pendientes


def _completar_videos_rutina(
    db,
    doc_id: str,
    doc_data: dict,
    catalogo: dict[str, dict],
    pendientes: list[tuple[str, str, str]],
) -> int:
    if not pendientes:
        return 0
    rutina_actual = doc_data.get("rutina", {}) or {}
    if not isinstance(rutina_actual, dict):
        return 0

    agrupados: dict[str, list[dict]] = {}
    for dia, nombre, link in pendientes:
        agrupados.setdefault(str(dia), []).append(
            {"nombre": (nombre or "").strip(), "nombre_norm": normalizar_texto(nombre), "link": link}
        )

    rutina_nueva = copy.deepcopy(rutina_actual)
    total = 0
    for dia, lista in agrupados.items():
        data_dia = _obtener_data_dia(rutina_nueva, dia)
        if data_dia is None:
            continue
        total += _aplicar_videos_faltantes_en_obj(data_dia, lista)

    if not total:
        return 0

    try:
        db.collection("rutinas_semanales").document(doc_id).update({"rutina": rutina_nueva})
    except Exception as exc:
        st.error(f"No pude actualizar los videos en Firestore: {exc}")
        return 0
    return total


def _buscar_videos_inconsistentes(db, doc_data: dict) -> list[dict]:
    rutina_actual = doc_data.get("rutina", {}) or {}
    if not isinstance(rutina_actual, dict):
        return []
    correo_entrenador = (doc_data.get("entrenador") or "").strip().lower()
    pendientes: list[dict] = []
    for dia, ejercicios in rutina_actual.items():
        for ejercicio in _iterar_ejercicios_en_obj(ejercicios):
            nombre = (ejercicio.get("Ejercicio") or ejercicio.get("ejercicio") or "").strip()
            video_actual = (ejercicio.get("Video") or ejercicio.get("video") or "").strip()
            if not (nombre and video_actual):
                continue
            video_actual_norm = _normalizar_video_url(video_actual)
            if not video_actual_norm:
                continue
            video_catalogo, doc_id_catalogo = _video_catalogo_para_nombre(db, nombre, correo_entrenador)
            video_catalogo_norm = _normalizar_video_url(video_catalogo)
            if not video_catalogo_norm or video_catalogo_norm == video_actual_norm:
                continue
            pendientes.append(
                {
                    "dia": str(dia),
                    "ejercicio": nombre,
                    "video_actual": video_actual,
                    "video_catalogo": video_catalogo,
                    "video_actual_norm": video_actual_norm,
                    "video_catalogo_norm": video_catalogo_norm,
                    "doc_id": doc_id_catalogo,
                }
            )
    return pendientes


def _reemplazar_videos_inconsistentes(
    db,
    doc_id: str,
    doc_data: dict,
    pendientes: list[dict],
) -> int:
    if not pendientes:
        return 0
    rutina_actual = doc_data.get("rutina", {}) or {}
    if not isinstance(rutina_actual, dict):
        return 0

    agrupados: dict[str, list[dict]] = {}
    for item in pendientes:
        dia = str(item.get("dia") or "")
        if not dia:
            continue
        reemplazos = agrupados.setdefault(dia, [])
        reemplazos.append(
            {
                "nombre_norm": normalizar_texto(item.get("ejercicio")),
                "video_catalogo": item.get("video_catalogo", ""),
                "video_actual_norm": item.get("video_actual_norm")
                or _normalizar_video_url(item.get("video_actual", "")),
            }
        )

    if not agrupados:
        return 0

    rutina_nueva = copy.deepcopy(rutina_actual)
    total = 0
    for dia, lista in agrupados.items():
        data_dia = _obtener_data_dia(rutina_nueva, dia)
        if data_dia is None:
            continue
        total += _aplicar_videos_catalogo_en_obj(data_dia, lista)

    if not total:
        return 0

    try:
        db.collection("rutinas_semanales").document(doc_id).update({"rutina": rutina_nueva})
    except Exception as exc:
        st.error(f"No se pudo actualizar los videos en la rutina: {exc}")
        return 0
    return total


def _reset_video_diff_selection() -> None:
    for key in list(st.session_state.keys()):
        if key.startswith("_video_diff_chk_"):
            st.session_state.pop(key, None)
        elif key.startswith("_video_diff_show_"):
            st.session_state.pop(key, None)


def _sync_video_diff_checkbox_state(total: int) -> None:
    for key in list(st.session_state.keys()):
        if not key.startswith("_video_diff_chk_"):
            continue
        try:
            idx = int(key.rsplit("_", 1)[-1])
        except ValueError:
            continue
        if idx >= total:
            st.session_state.pop(key, None)


def _render_video_preview_button(url: str, label: str, key_suffix: str) -> None:
    url = (url or "").strip()
    if not url:
        st.caption(f"{label}: sin video")
        return
    video_norm = _normalizar_video_url(url)
    if not video_norm:
        st.markdown(f"{label}: [Ver enlace]({url})")
        return
    btn_key = f"_video_diff_btn_{key_suffix}"
    show_key = f"_video_diff_show_{key_suffix}"
    if st.button(f"{label} ▶️", key=btn_key):
        st.session_state[show_key] = not st.session_state.get(show_key, False)
    if st.session_state.get(show_key):
        st.video(video_norm)


def _limpiar_estado_rutina():
    patrones = (
        "rutina_dia_",
        "addn_rutina_dia_",
        "show_tiempo_rutina_dia_",
        "show_vel_rutina_dia_",
        "show_desc_rutina_dia_",
        "buscar_",
        "select_",
        "det_",
        "ser_",
        "rmin_",
        "rmax_",
        "peso_",
        "tiempo_",
        "vel_",
        "desc_",
        "rir_",
        "rirmin_",
        "rirmax_",
        "prog_check_",
        "copy_check_",
        "delete_",
        "do_copy_",
        "multiselect_",
    )
    for key in list(st.session_state.keys()):
        if key.startswith(patrones):
            st.session_state.pop(key, None)
    for clave in ("dias_editables", "dias_originales", "_dia_creado_msg"):
        st.session_state.pop(clave, None)
    st.session_state.pop(RUTINA_STATE_OWNER_KEY, None)


def limpiar_estado_editar_rutinas():
    """Resetea los campos del editor al abandonar la vista."""
    _limpiar_estado_rutina()
    for key in ("_editar_rutina_actual", "_videos_pendientes", "_videos_catalogo", "_videos_checked"):
        st.session_state.pop(key, None)


def _cargar_rutina_en_session(rutina_dict: dict, cardio_dict: dict | None = None):
    _limpiar_estado_rutina()
    dias = claves_dias(rutina_dict) or []
    cardio_dict = cardio_dict or {}
    dias_cardio = [str(k) for k in cardio_dict.keys() if str(k).isdigit()]
    if dias_cardio:
        dias = sorted(set(dias) | set(dias_cardio), key=lambda x: int(x or 0))
    if not dias:
        dias = ["1"]
    st.session_state["dias_editables"] = dias.copy()
    st.session_state["dias_originales"] = dias.copy()

    for idx, dia in enumerate(dias, start=1):
        ejercicios_raw = obtener_lista_ejercicios(rutina_dict.get(str(dia)) or rutina_dict.get(dia))
        warm_up: list[dict] = []
        work_out: list[dict] = []
        for ej in ejercicios_raw:
            if isinstance(ej, str):
                ej = {"Ejercicio": ej, "bloque": "Work Out"}
            fila_ui = _ejercicio_firestore_a_fila_ui(ej if isinstance(ej, dict) else {})
            (warm_up if fila_ui.get("Sección") == "Warm Up" else work_out).append(fila_ui)
        st.session_state[f"rutina_dia_{idx}_Warm_Up"] = warm_up
        st.session_state[f"rutina_dia_{idx}_Work_Out"] = work_out
        cardio_payload = cardio_dict.get(str(dia)) or cardio_dict.get(dia)
        _set_cardio_en_session(idx, cardio_payload)
        st.session_state[f"mostrar_cardio_{idx}"] = _cardio_tiene_datos(cardio_payload)
    st.session_state[RUTINA_STATE_OWNER_KEY] = "editar"


def _construir_rutina_desde_session(dias_originales: list[str]) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    resultado: dict[str, list[dict]] = {}
    cardio_resultado: dict[str, dict] = {}
    for idx, dia in enumerate(dias_originales, start=1):
        warm = st.session_state.get(f"rutina_dia_{idx}_Warm_Up", []) or []
        work = st.session_state.get(f"rutina_dia_{idx}_Work_Out", []) or []
        filas = []
        for fila in warm + work:
            filas.append(_fila_ui_a_ejercicio_firestore_legacy(fila))
        resultado[str(dia)] = filas
        cardio_norm = _normalizar_cardio_data(st.session_state.get(f"rutina_dia_{idx}_Cardio"))
        if _cardio_tiene_datos(cardio_norm):
            cardio_resultado[str(dia)] = cardio_norm
    return resultado, cardio_resultado


REPORTE_FIELDS = (
    "series_data",
    "peso_alcanzado",
    "reps_alcanzadas",
    "rir_alcanzado",
    "comentario",
    "coach_responsable",
)


def _clave_ejercicio_para_reporte(ejercicio: dict) -> tuple[str, str, str]:
    bloque = (ejercicio.get("bloque") or ejercicio.get("Sección") or ejercicio.get("seccion") or "").strip().lower()
    circuito = (ejercicio.get("circuito") or ejercicio.get("Circuito") or "").strip().upper()
    nombre = (ejercicio.get("ejercicio") or ejercicio.get("Ejercicio") or "").strip().lower()
    return bloque, circuito, nombre


def _series_data_con_datos(series_data) -> bool:
    if not isinstance(series_data, list):
        return False
    for serie in series_data:
        if not isinstance(serie, dict):
            continue
        if any(str(val).strip() for val in serie.values()):
            return True
    return False


def _copiar_datos_reporte(origen: dict, destino: dict) -> None:
    if not isinstance(origen, dict) or not isinstance(destino, dict):
        return
    series_prev = origen.get("series_data")
    if _series_data_con_datos(series_prev):
        destino["series_data"] = copy.deepcopy(series_prev)
    for campo in REPORTE_FIELDS[1:]:
        valor = origen.get(campo)
        if valor not in (None, "", []):
            destino[campo] = copy.deepcopy(valor)


def _fusionar_con_reportes_existentes(ejercicios_originales, ejercicios_nuevos: list[dict]) -> list[dict]:
    lista_original = obtener_lista_ejercicios(ejercicios_originales)
    if not lista_original:
        return ejercicios_nuevos

    indice = defaultdict(list)
    for ex in lista_original:
        if isinstance(ex, dict):
            indice[_clave_ejercicio_para_reporte(ex)].append(ex)

    fusionados: list[dict] = []
    for ex in ejercicios_nuevos:
        nuevo = dict(ex) if isinstance(ex, dict) else ex
        if isinstance(nuevo, dict):
            clave = _clave_ejercicio_para_reporte(nuevo)
            candidatos = indice.get(clave) or []
            if candidatos:
                previo = candidatos.pop(0)
                _copiar_datos_reporte(previo, nuevo)
        fusionados.append(nuevo)
    return fusionados


def _guardar_cambios_en_documentos(
    db,
    doc_ids: list[str],
    dias_originales: list[str],
    rutina_actualizada: dict[str, list[dict]],
    cardio_actualizado: dict[str, dict],
    objetivo_actualizado: str | None = None,
):
    total = 0
    for doc_id in doc_ids:
        ref = db.collection("rutinas_semanales").document(doc_id)
        snap = ref.get()
        data = snap.to_dict() or {}
        rutina_actual = data.get("rutina", {}) or {}
        cardio_actual = data.get("cardio", {}) or {}
        nueva_rutina = dict(rutina_actual)
        nuevo_cardio = dict(cardio_actual)
        for dia in dias_originales:
            dia_clave = str(dia)
            ejercicios_nuevos = rutina_actualizada.get(dia_clave, [])
            if not isinstance(ejercicios_nuevos, list):
                ejercicios_nuevos = []
            ejercicios_previos = rutina_actual.get(dia_clave, [])
            nueva_rutina[dia_clave] = _fusionar_con_reportes_existentes(ejercicios_previos, ejercicios_nuevos)
            cardio_dia = cardio_actualizado.get(dia_clave)
            if _cardio_tiene_datos(cardio_dia):
                nuevo_cardio[dia_clave] = _normalizar_cardio_data(cardio_dia)
            else:
                nuevo_cardio.pop(dia_clave, None)
        payload = {"rutina": nueva_rutina}
        if nuevo_cardio:
            payload["cardio"] = nuevo_cardio
        elif cardio_actual:
            payload["cardio"] = {}
        if objetivo_actualizado is not None:
            payload["objetivo"] = objetivo_actualizado
        try:
            ref.update(payload)
            total += 1
        except Exception as exc:
            st.error(f"No pude guardar cambios en '{doc_id}': {exc}")
    return total


# ===================== CONTROL DE DÍAS =====================
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
    cardio_key = f"rutina_dia_{idx_dia}_Cardio"
    if cardio_key not in st.session_state or not isinstance(st.session_state[cardio_key], dict):
        _set_cardio_en_session(idx_dia, _default_cardio_data())
    else:
        _sync_cardio_desde_widgets(idx_dia)


def _trigger_rerun():
    rerun_fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if rerun_fn:
        rerun_fn()


def _agregar_dia():
    dias_actuales = st.session_state.get("dias_editables")
    if not dias_actuales:
        existentes = [key.split("_")[2] for key in st.session_state.keys() if key.startswith("rutina_dia_") and "Warm_Up" in key]
        dias_actuales = sorted({d for d in existentes if d.isdigit()}, key=lambda x: int(x))
        if not dias_actuales:
            dias_actuales = ["1"]

    nuevas = list(dias_actuales)
    nuevo_idx = (max(int(d) for d in nuevas) + 1) if nuevas else 1
    nuevas.append(str(nuevo_idx))
    st.session_state["dias_editables"] = nuevas
    st.session_state["dias_originales"] = nuevas.copy()
    _asegurar_dia_en_session(nuevo_idx)
    st.session_state["_dia_creado_msg"] = f"Día {nuevo_idx} agregado. Completa sus ejercicios y guarda los cambios."
    _trigger_rerun()


def limpiar_dia(idx_dia: int):
    for seccion in ["Warm Up", "Work Out"]:
        key = f"rutina_dia_{idx_dia}_{seccion.replace(' ', '_')}"
        st.session_state[key] = []
    st.session_state[f"rutina_dia_{idx_dia}_Cardio"] = _default_cardio_data()
    st.session_state.pop(f"mostrar_cardio_{idx_dia}", None)
    i0 = idx_dia - 1
    patrones = [f"_{i0}_Warm_Up_", f"_{i0}_Work_Out_", f"_{i0}_Cardio_"]
    claves_borrar = []
    for k in list(st.session_state.keys()):
        if any(p in k for p in patrones) or k.startswith(f"multiselect_{i0}_") or k.startswith(f"do_copy_{i0}_"):
            claves_borrar.append(k)
    for k in claves_borrar:
        st.session_state.pop(k, None)
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()


def _limpiar_fila_ui(key_seccion: str, fila_idx: int, seccion_actual: str, key_entrenamiento: str) -> None:
    filas = st.session_state.get(key_seccion)
    if not isinstance(filas, list) or not (0 <= fila_idx < len(filas)):
        return
    filas[fila_idx] = _fila_vacia(seccion_actual)

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
        "desc",
        "rirmin",
        "rirmax",
    ]
    for pref in prefixes:
        st.session_state.pop(f"{pref}_{key_entrenamiento}", None)

    for p in (1, 2, 3):
        st.session_state.pop(f"var{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"var{p}_{key_entrenamiento}_{fila_idx}", None)
        st.session_state.pop(f"ope{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"ope{p}_{key_entrenamiento}_{fila_idx}", None)
        st.session_state.pop(f"cant{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"cant{p}_{key_entrenamiento}_{fila_idx}", None)
        st.session_state.pop(f"sem{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"sem{p}_{key_entrenamiento}_{fila_idx}", None)
        st.session_state.pop(f"condvar{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"condvar{p}_{key_entrenamiento}_{fila_idx}", None)
        st.session_state.pop(f"condop{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"condop{p}_{key_entrenamiento}_{fila_idx}", None)
        st.session_state.pop(f"condval{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"condval{p}_{key_entrenamiento}_{fila_idx}", None)

    st.session_state.pop(f"prog_check_{key_entrenamiento}", None)
    st.session_state.pop(f"prog_check_{key_entrenamiento}_{fila_idx}", None)
    st.session_state.pop(f"topset_check_{key_entrenamiento}", None)
    st.session_state.pop(f"topset_check_{key_entrenamiento}_{fila_idx}", None)
    st.session_state.pop(f"copy_check_{key_entrenamiento}", None)
    st.session_state.pop(f"delete_{key_entrenamiento}", None)


def _limpiar_destinos_copy_state(key_seccion: str, total_dias: int) -> None:
    prefix = f"copy_dest_{key_seccion}_"
    for idx in range(total_dias):
        st.session_state.pop(f"{prefix}{idx}", None)


def _copiar_filas_a_dias(
    filas_para_copiar: list[tuple[int, dict]],
    destino_indices: list[int],
    seccion: str,
) -> None:
    if not filas_para_copiar or not destino_indices:
        return

    seccion_slug = seccion.replace(" ", "_")
    for dest_idx in destino_indices:
        key_destino = f"rutina_dia_{dest_idx + 1}_{seccion_slug}"
        destino_filas = st.session_state.setdefault(key_destino, [])
        for fila_idx, fila_origen in filas_para_copiar:
            while len(destino_filas) <= fila_idx:
                destino_filas.append(_fila_vacia(seccion))
            clon = dict(fila_origen)
            clon["Sección"] = seccion
            clon["Circuito"] = clamp_circuito_por_seccion(clon.get("Circuito", "") or "", seccion)
            clon.pop("_delete_marked", None)
            destino_filas[fila_idx] = clon


# ===================== RENDER TABLA =====================
def render_tabla_dia(i: int, seccion: str, progresion_activa: str, dias_labels: list[str]):
    key_seccion = f"rutina_dia_{i+1}_{seccion.replace(' ', '_')}"
    if key_seccion not in st.session_state:
        st.session_state[key_seccion] = []

    st.markdown(SECTION_CONTAINER_HTML, unsafe_allow_html=True)

    ejercicios_dict = EJERCICIOS

    toggle_cols = st.columns([6.5, 1.1, 1.1, 1.1, 1.1, 1.7], gap="small")
    toggle_cols[0].markdown(f"<h4 class='h-accent' style='margin-top:2px'>{seccion}</h4>", unsafe_allow_html=True)

    show_tiempo = toggle_cols[1].toggle("Tiempo", key=f"show_tiempo_{key_seccion}")
    show_progresion = toggle_cols[2].toggle("Progresión", key=f"show_prog_{key_seccion}")
    show_top_set_sec = toggle_cols[3].toggle("Set Mode", key=f"show_topset_{key_seccion}")
    show_descanso = toggle_cols[4].toggle("Descanso", key=f"show_desc_{key_seccion}")

    if _tiene_permiso_agregar():
        pop = toggle_cols[5].popover("＋", use_container_width=True)
        with pop:
            st.markdown("**📌 Crear o Editar Ejercicio (rápido)**")
            try:
                cat = get_catalogos()
            except Exception as exc:
                st.error(f"No pude cargar catálogos: {exc}")
                cat = {}

            catalogo_carac = cat.get("caracteristicas", []) or []
            catalogo_patron = cat.get("patrones_movimiento", []) or []
            catalogo_grupo_p = cat.get("grupo_muscular_principal", []) or []
            catalogo_grupo_s = cat.get("grupo_muscular_secundario", []) or []

            def _combo(label: str, opciones: list[str], key_base: str, valor_inicial: str = "") -> str:
                sentencia = "➕ Agregar nuevo…"
                base = sorted(opciones or [])
                if valor_inicial and valor_inicial not in base:
                    base.append(valor_inicial)
                lista = ["— Selecciona —"] + base + [sentencia]
                index = lista.index(valor_inicial) if valor_inicial in lista else 0
                elegido = st.selectbox(label, lista, index=index, key=f"{key_base}_sel_{key_seccion}")
                if elegido == sentencia:
                    st.markdown("<div class='card'>", unsafe_allow_html=True)
                    nuevo = st.text_input(f"Ingresar nuevo valor para {label.lower()}:", key=f"{key_base}_nuevo_{key_seccion}")
                    cols_accion = st.columns([1, 1, 4])
                    with cols_accion[0]:
                        if st.button("Guardar", key=f"{key_base}_guardar_{key_seccion}", type="primary"):
                            limpio = (nuevo or "").strip()
                            if limpio:
                                etiqueta = label.lower()
                                if "característica" in etiqueta or "caracteristica" in etiqueta:
                                    tipo = "caracteristicas"
                                elif "patrón" in etiqueta or "patron" in etiqueta:
                                    tipo = "patrones_movimiento"
                                elif "secundario" in etiqueta:
                                    tipo = "grupo_muscular_secundario"
                                elif "principal" in etiqueta:
                                    tipo = "grupo_muscular_principal"
                                else:
                                    tipo = "otros_catalogos"
                                add_item(tipo, limpio)
                                st.success(f"Agregado: {limpio}")
                                st.cache_data.clear()
                                st.rerun()
                    st.markdown("</div>", unsafe_allow_html=True)
                    return ""
                if elegido == "— Selecciona —":
                    return ""
                return elegido

            detalle_prefill = ""
            pref_key = f"buscar_{i}_{seccion.replace(' ','_')}_"
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
                caracteristica = _combo("Característica", catalogo_carac, "carac_top")
            with col_d:
                patron = _combo("Patrón de Movimiento", catalogo_patron, "patron_top")

            col_e, col_f = st.columns(2)
            with col_e:
                grupo_p = _combo("Grupo Muscular Principal", catalogo_grupo_p, "grupo_p_top")
            with col_f:
                grupo_s = _combo("Grupo Muscular Secundario", catalogo_grupo_s, "grupo_s_top")

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
                            implemento_id = _resolver_id_implemento(marca, maquina) if (marca and maquina) else ""
                            payload = {
                                "nombre": nombre_final,
                                "marca": marca,
                                "maquina": maquina,
                                "detalle": detalle,
                                "caracteristica": caracteristica,
                                "patron_de_movimiento": patron,
                                "grupo_muscular_principal": grupo_p,
                                "grupo_muscular_secundario": grupo_s or "",
                                "id_implemento": implemento_id,
                                "video": (video_url or "").strip(),
                                "publico_flag": bool(publico_check),
                            }
                            try:
                                guardar_ejercicio_firestore(nombre_final, payload)
                                EJERCICIOS[nombre_final] = {
                                    "nombre": nombre_final,
                                    "id_implemento": implemento_id,
                                    "video": (video_url or "").strip(),
                                    "Video": (video_url or "").strip(),
                                    "publico": bool(publico_check),
                                }
                                st.success(f"✅ Ejercicio '{nombre_final}' guardado correctamente.")
                                st.cache_data.clear()
                                _trigger_rerun()
                            except Exception as exc:
                                st.error(f"❌ Error al guardar: {exc}")
    else:
        toggle_cols[5].button("＋", use_container_width=True, disabled=True)

    ctrl_cols = st.columns([1.3, 1.3, 1.6, 5.6], gap="small")
    add_n = ctrl_cols[2].number_input("N", min_value=1, max_value=10, value=1, key=f"addn_{key_seccion}", label_visibility="collapsed")
    if ctrl_cols[0].button("➕ Agregar fila", key=f"add_{key_seccion}", type="secondary"):
        st.session_state[key_seccion].extend([_fila_vacia(seccion) for _ in range(int(add_n))])
        st.rerun()
    if ctrl_cols[1].button("➖ Quitar última", key=f"del_{key_seccion}", type="secondary"):
        if st.session_state[key_seccion]:
            st.session_state[key_seccion].pop()
            st.rerun()

    headers = BASE_HEADERS.copy()
    sizes = BASE_SIZES.copy()
    rir_idx = headers.index("RIR (Min/Max)")
    if show_tiempo:
        headers.insert(rir_idx, "Tiempo")
        sizes.insert(rir_idx, 0.9)
        rir_idx += 1
    if show_descanso:
        headers.insert(rir_idx, "Descanso")
        sizes.insert(rir_idx, 0.9)
    if not show_top_set_sec:
        try:
            set_idx = headers.index("Set Mode")
        except ValueError:
            set_idx = -1
        if set_idx >= 0:
            headers.pop(set_idx)
            sizes.pop(set_idx)
    if not show_progresion:
        prog_idx = headers.index("Progresión")
        headers.pop(prog_idx)
        sizes.pop(prog_idx)

    def _buscar_fuzzy(palabra: str) -> list[str]:
        if not palabra.strip():
            return []
        patron = normalizar_texto(palabra)
        if not patron:
            return []
        candidatos = []
        for nombre, data in ejercicios_dict.items():
            nombre_norm = normalizar_texto(nombre)
            slug_norm = normalizar_texto((data or {}).get("buscable_id") or _buscable_id(nombre))
            extra_texto = f"{nombre_norm} {slug_norm}".strip()
            if patron in extra_texto:
                candidatos.append(nombre)
        return candidatos

    section_container = st.container()
    with section_container:
        st.caption("Los cambios se guardan automáticamente.")
        header_cols = st.columns(sizes)
        for c, title in zip(header_cols, headers):
            slug = _header_slug(title)
            if title == "Video":
                inner = c.columns([1, 1, 1])
                inner[1].markdown(
                    f"<div class='header-center header-center--{slug}'>Video</div>",
                    unsafe_allow_html=True,
                )
            else:
                c.markdown(
                    f"<div class='header-center header-center--{slug}'>{title}</div>",
                    unsafe_allow_html=True,
                )

        filas_marcadas: list[tuple[int, str]] = []
        filas_para_copiar: list[tuple[int, dict]] = []
        pos = {header: idx for idx, header in enumerate(headers)}

        for idx, fila in enumerate(st.session_state[key_seccion]):
            key_entrenamiento = f"{i}_{seccion.replace(' ', '_')}_{idx}"
            cols = st.columns(sizes)

            fila.setdefault("Sección", seccion)
            opciones_circuito = get_circuit_options(seccion)
            valor_circuito = (fila.get("Circuito") or "").strip()
            if valor_circuito and valor_circuito not in opciones_circuito:
                opciones_circuito = [valor_circuito] + [opt for opt in opciones_circuito if opt != valor_circuito]
            indice_circuito = opciones_circuito.index(valor_circuito) if valor_circuito in opciones_circuito else 0
            fila["Circuito"] = cols[pos["Circuito"]].selectbox(
                "",
                opciones_circuito,
                index=indice_circuito,
                key=f"circ_{key_entrenamiento}",
                label_visibility="collapsed",
            )

            palabra = cols[pos["Buscar Ejercicio"]].text_input(
                "",
                value=fila.get("BuscarEjercicio", ""),
                key=f"buscar_{key_entrenamiento}",
                label_visibility="collapsed",
                placeholder="Buscar ejercicio…",
            )
            fila["BuscarEjercicio"] = palabra

            nombre_original = (fila.get("Ejercicio", "") or "").strip()
            exacto = bool(fila.get("_exact_on_load"))
            if exacto and normalizar_texto(palabra) in ("", normalizar_texto(nombre_original)):
                resultados = [nombre_original] if nombre_original else []
            else:
                resultados = _buscar_fuzzy(palabra)
                fila["_exact_on_load"] = False
            if not resultados and nombre_original:
                resultados = [nombre_original]
            if not resultados and palabra.strip():
                resultados = [palabra.strip()]
            if not resultados:
                resultados = ["(sin resultados)"]

            nombre_actual = (fila.get("Ejercicio", "") or "").strip()
            if nombre_actual:
                vistos = set()
                resultados = [r for r in resultados if not (r in vistos or vistos.add(r))]
                if nombre_actual not in resultados:
                    resultados = [nombre_actual] + [opt for opt in resultados if opt != nombre_actual]
            idx_sel = resultados.index(nombre_actual) if nombre_actual in resultados else 0

            seleccionado = cols[pos["Ejercicio"]].selectbox(
                "",
                resultados,
                key=f"select_{key_entrenamiento}",
                label_visibility="collapsed",
                index=idx_sel,
            )
            if seleccionado == "(sin resultados)":
                fila["Ejercicio"] = palabra.strip()
            else:
                fila["Ejercicio"] = seleccionado
            fila["Video"] = fila.get("Video") or _video_de_catalogo(fila["Ejercicio"])

            fila["Detalle"] = cols[pos["Detalle"]].text_input(
                "",
                value=fila.get("Detalle", ""),
                key=f"det_{key_entrenamiento}",
                label_visibility="collapsed",
                placeholder="Notas (opcional)",
            )

            fila["Series"] = cols[pos["Series"]].text_input(
                "",
                value=fila.get("Series", ""),
                key=f"ser_{key_entrenamiento}",
                label_visibility="collapsed",
                placeholder="N°",
            )

            reps_cols = cols[pos["Repeticiones"]].columns(2)
            fila["RepsMin"] = reps_cols[0].text_input(
                "",
                value=str(fila.get("RepsMin", "")),
                key=f"rmin_{key_entrenamiento}",
                label_visibility="collapsed",
                placeholder="Min",
            )
            fila["RepsMax"] = reps_cols[1].text_input(
                "",
                value=str(fila.get("RepsMax", "")),
                key=f"rmax_{key_entrenamiento}",
                label_visibility="collapsed",
                placeholder="Max",
            )

            peso_widget = f"peso_{key_entrenamiento}"
            peso_valor = fila.get("Peso", "")
            usar_text_input = True
            pesos_disponibles = []
            try:
                doc_ej = ejercicios_dict.get(fila.get("Ejercicio"), {}) or {}
                id_impl = str(doc_ej.get("id_implemento") or "")
                if id_impl and id_impl != "1" and id_impl in IMPLEMENTOS:
                    pesos_disponibles = IMPLEMENTOS[id_impl].get("pesos", []) or []
                    if isinstance(pesos_disponibles, dict):
                        pesos_disponibles = [v for _, v in sorted(pesos_disponibles.items(), key=lambda kv: int(kv[0]))]
                    usar_text_input = not bool(pesos_disponibles)
            except Exception:
                usar_text_input = True

            if not usar_text_input and pesos_disponibles:
                opciones_peso = [str(p) for p in pesos_disponibles]
                if str(peso_valor) not in opciones_peso:
                    peso_valor = opciones_peso[0]
                fila["Peso"] = cols[pos["Peso"]].selectbox(
                    "",
                    options=opciones_peso,
                    index=(opciones_peso.index(str(peso_valor)) if str(peso_valor) in opciones_peso else 0),
                    key=peso_widget,
                    label_visibility="collapsed",
                )
            else:
                fila["Peso"] = cols[pos["Peso"]].text_input(
                    "",
                    value=str(peso_valor),
                    key=peso_widget,
                    label_visibility="collapsed",
                    placeholder="Kg",
                )

            if "Tiempo" in pos:
                fila["Tiempo"] = cols[pos["Tiempo"]].text_input(
                    "",
                    value=str(fila.get("Tiempo", "")),
                    key=f"tiempo_{key_entrenamiento}",
                    label_visibility="collapsed",
                    placeholder="Seg",
                )
            else:
                fila.setdefault("Tiempo", "")

            if "Descanso" in pos:
                opciones_descanso = ["", "1", "2", "3", "4", "5"]
                valor_desc = str(fila.get("Descanso", "")).split(" ")[0]
                idx_desc = opciones_descanso.index(valor_desc) if valor_desc in opciones_descanso else 0
                fila["Descanso"] = cols[pos["Descanso"]].selectbox(
                    "",
                    options=opciones_descanso,
                    index=idx_desc,
                    key=f"desc_{key_entrenamiento}",
                    label_visibility="collapsed",
                    help="Minutos de descanso (1–5). Deja vacío si no aplica.",
                )
            else:
                fila.setdefault("Descanso", "")

            rir_cols = cols[pos["RIR (Min/Max)"]].columns(2)
            fila["RirMin"] = rir_cols[0].text_input(
                "",
                value=str(fila.get("RirMin", "")),
                key=f"rirmin_{key_entrenamiento}",
                label_visibility="collapsed",
                placeholder="Min",
            )
            fila["RirMax"] = rir_cols[1].text_input(
                "",
                value=str(fila.get("RirMax", "")),
                key=f"rirmax_{key_entrenamiento}",
                label_visibility="collapsed",
                placeholder="Max",
            )
            rmin_txt, rmax_txt = str(fila.get("RirMin", "")).strip(), str(fila.get("RirMax", "")).strip()
            fila["RIR"] = f"{rmin_txt}-{rmax_txt}" if (rmin_txt and rmax_txt) else (rmin_txt or rmax_txt or "")

            mostrar_top_set = False
            top_set_state_key = f"topset_check_{key_entrenamiento}_{idx}"
            if show_top_set_sec and "Set Mode" in pos:
                top_cols = cols[pos["Set Mode"]].columns([1, 1, 1])
                mostrar_top_set = top_cols[1].checkbox(
                    "",
                    key=top_set_state_key,
                    label_visibility="collapsed",
                )
            else:
                st.session_state.pop(top_set_state_key, None)

            if mostrar_top_set:
                st.markdown(SECTION_BREAK_HTML, unsafe_allow_html=True)
                num_sets = _parse_series_count(fila.get("Series"))
                if num_sets <= 0:
                    st.info("Define un número de series para generar los Set Mode.")
                    fila.pop("TopSetData", None)
                else:
                    datos_top = fila.get("TopSetData")
                    if not isinstance(datos_top, list):
                        datos_top = []
                    datos_top = _ensure_topset_len(datos_top, num_sets)
                    for set_idx in range(num_sets):
                        set_key = f"topset_{key_entrenamiento}_{idx}_{set_idx}"
                        fila_cols_top = st.columns(sizes)
                        datos_top[set_idx]["Series"] = fila_cols_top[pos["Series"]].text_input(
                            "",
                            value=str(datos_top[set_idx].get("Series", "")),
                            key=f"{set_key}_series",
                            label_visibility="collapsed",
                            placeholder=f"Serie {set_idx + 1}",
                        )
                        rep_cols_top = fila_cols_top[pos["Repeticiones"]].columns(2)
                        datos_top[set_idx]["RepsMin"] = rep_cols_top[0].text_input(
                            "",
                            value=str(datos_top[set_idx].get("RepsMin", "")),
                            key=f"{set_key}_rmin",
                            label_visibility="collapsed",
                            placeholder="Min",
                        )
                        datos_top[set_idx]["RepsMax"] = rep_cols_top[1].text_input(
                            "",
                            value=str(datos_top[set_idx].get("RepsMax", "")),
                            key=f"{set_key}_rmax",
                            label_visibility="collapsed",
                            placeholder="Max",
                        )
                        datos_top[set_idx]["Peso"] = fila_cols_top[pos["Peso"]].text_input(
                            "",
                            value=str(datos_top[set_idx].get("Peso", "")),
                            key=f"{set_key}_peso",
                            label_visibility="collapsed",
                            placeholder="Kg",
                        )
                        rir_cols_top = fila_cols_top[pos["RIR (Min/Max)"]].columns(2)
                        datos_top[set_idx]["RirMin"] = rir_cols_top[0].text_input(
                            "",
                            value=str(datos_top[set_idx].get("RirMin", "")),
                            key=f"{set_key}_rirmin",
                            label_visibility="collapsed",
                            placeholder="Min",
                        )
                        datos_top[set_idx]["RirMax"] = rir_cols_top[1].text_input(
                            "",
                            value=str(datos_top[set_idx].get("RirMax", "")),
                            key=f"{set_key}_rirmax",
                            label_visibility="collapsed",
                            placeholder="Max",
                        )
                    fila["TopSetData"] = datos_top
            else:
                if show_top_set_sec:
                    fila.pop("TopSetData", None)

            mostrar_progresion = False
            if show_progresion and "Progresión" in pos:
                prog_cols = cols[pos["Progresión"]].columns([1, 1, 1])
                mostrar_progresion = prog_cols[1].checkbox(
                    "",
                    key=f"prog_check_{key_entrenamiento}_{idx}",
                    label_visibility="collapsed",
                )

            copy_cols = cols[pos["Copiar"]].columns([1, 1, 1])
            mostrar_copia = copy_cols[1].checkbox("", key=f"copy_check_{key_entrenamiento}")

            if mostrar_progresion:
                st.markdown(SECTION_BREAK_HTML, unsafe_allow_html=True)
                p = int(progresion_activa.split()[-1])
                pcols = st.columns([0.9, 0.9, 0.7, 0.8, 0.9, 0.9, 1.0])
                var_key = f"var{p}_{key_entrenamiento}_{idx}"
                ope_key = f"ope{p}_{key_entrenamiento}_{idx}"
                cant_key = f"cant{p}_{key_entrenamiento}_{idx}"
                sem_key = f"sem{p}_{key_entrenamiento}_{idx}"
                cond_var_key = f"condvar{p}_{key_entrenamiento}_{idx}"
                cond_op_key = f"condop{p}_{key_entrenamiento}_{idx}"
                cond_val_key = f"condval{p}_{key_entrenamiento}_{idx}"

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

            borrar_key = f"delete_{key_entrenamiento}"
            borrar_cols = cols[pos["Borrar"]].columns([1, 1, 1])
            marcado_borrar = borrar_cols[1].checkbox("", key=borrar_key)
            if marcado_borrar:
                filas_marcadas.append((idx, key_entrenamiento))
                fila["_delete_marked"] = True
            else:
                fila.pop("_delete_marked", None)
                st.session_state.pop(borrar_key, None)

            video_col_idx = pos.get("Video")
            if video_col_idx is not None:
                nombre_ej = str(fila.get("Ejercicio", "")).strip()
                video_url = str(fila.get("Video") or "").strip()
                if not video_url and nombre_ej:
                    video_url = str(_video_de_catalogo(nombre_ej) or "").strip()
                video_url_norm = _normalizar_video_url(video_url)
                video_cols = cols[video_col_idx].columns([1, 1, 1])
                if video_url_norm:
                    with video_cols[1].popover("▶️", use_container_width=False):
                        st.video(video_url_norm)
                elif video_url:
                    video_cols[1].markdown(f"[Ver video]({video_url})")
                else:
                    video_cols[1].markdown("")

        total_dias = len(dias_labels)
        if filas_para_copiar and total_dias > 1:
            st.markdown(SECTION_BREAK_HTML, unsafe_allow_html=True)
            st.markdown("**📋 Copiar ejercicios marcados a otros días**")
            st.caption("Selecciona el/los día(s) destino. La copia se aplica automáticamente manteniendo el índice de fila.")
            dest_cols = st.columns(total_dias)
            destinos: list[int] = []
            prefix = f"copy_dest_{key_seccion}_"
            for dia_idx, col in enumerate(dest_cols):
                label = dias_labels[dia_idx]
                disabled = dia_idx == i
                checked = col.checkbox(
                    label,
                    key=f"{prefix}{dia_idx}",
                    value=st.session_state.get(f"{prefix}{dia_idx}", False),
                    disabled=disabled,
                )
                if checked and not disabled:
                    destinos.append(dia_idx)
            if destinos:
                _copiar_filas_a_dias(filas_para_copiar, destinos, seccion)
        else:
            _limpiar_destinos_copy_state(key_seccion, total_dias)

        action_cols = st.columns([1.4, 5.6])
        limpiar_clicked = action_cols[0].button("Limpiar sección", key=f"limpiar_{key_seccion}", type="secondary")
        pending_key = f"pending_clear_{key_seccion}"

        if limpiar_clicked:
            if filas_marcadas:
                for idx_sel, key_sel in filas_marcadas:
                    _limpiar_fila_ui(key_seccion, idx_sel, seccion, key_sel)
                st.session_state.pop(pending_key, None)
                st.success("Fila(s) limpiadas ✅")
                _trigger_rerun()
            elif st.session_state.get(pending_key):
                for idx_sel in range(len(st.session_state[key_seccion])):
                    key_sel = f"{i}_{seccion.replace(' ', '_')}_{idx_sel}"
                    _limpiar_fila_ui(key_seccion, idx_sel, seccion, key_sel)
                st.session_state[key_seccion] = [_fila_vacia(seccion)]
                _limpiar_destinos_copy_state(key_seccion, total_dias)
                st.session_state.pop(pending_key, None)
                st.success("Sección limpiada ✅")
                _trigger_rerun()
            else:
                st.session_state[pending_key] = True

        if st.session_state.get(pending_key) and not filas_marcadas:
            st.warning("Vuelve a presionar **Limpiar sección** para confirmar el borrado.")
        elif filas_marcadas:
            st.session_state.pop(pending_key, None)


def render_cardio_dia(idx_tab: int):
    dia_idx = idx_tab + 1
    cardio_key = f"rutina_dia_{dia_idx}_Cardio"
    flag_key = f"mostrar_cardio_{dia_idx}"
    if cardio_key not in st.session_state or not isinstance(st.session_state.get(cardio_key), dict):
        _set_cardio_en_session(dia_idx, _default_cardio_data())
    cardio_data = _sync_cardio_desde_widgets(dia_idx)
    if flag_key not in st.session_state:
        st.session_state[flag_key] = _cardio_tiene_datos(cardio_data)

    if not st.session_state.get(flag_key):
        if st.button("➕ Agregar cardio", key=f"add_cardio_{dia_idx}", type="secondary"):
            st.session_state[flag_key] = True
            _set_cardio_en_session(dia_idx, cardio_data)
            _sync_cardio_desde_widgets(dia_idx)
            _trigger_rerun()
        st.caption("Este día no tiene trabajo cardiovascular registrado.")
        return

    st.markdown(SECTION_CONTAINER_HTML, unsafe_allow_html=True)
    header_cols = st.columns([6.5, 1.3])
    header_cols[0].markdown("<h4 class='h-accent' style='margin-top:2px'>Cardio</h4>", unsafe_allow_html=True)
    if header_cols[1].button("Eliminar", key=f"clear_cardio_{dia_idx}", type="secondary"):
        _set_cardio_en_session(dia_idx, _default_cardio_data())
        st.session_state[flag_key] = False
        _trigger_rerun()

    tipo_key = f"{cardio_key}_tipo"
    if tipo_key not in st.session_state:
        st.session_state[tipo_key] = cardio_data.get("tipo", "LISS") or "LISS"
    tipo_sel = st.radio("Tipo de cardio", ["LISS", "HIIT"], key=tipo_key, horizontal=True)
    cardio_data["tipo"] = tipo_sel

    modalidad_key = f"{cardio_key}_modalidad"
    if modalidad_key not in st.session_state:
        st.session_state[modalidad_key] = cardio_data.get("modalidad", "")
    cardio_data["modalidad"] = st.text_input(
        "Modalidad",
        key=modalidad_key,
        placeholder="Ej. caminata en cinta, bike, remo…",
    )

    if tipo_sel == "HIIT":
        hiit_cols_1 = st.columns(2, gap="small")
        series_key = f"{cardio_key}_series"
        if series_key not in st.session_state:
            st.session_state[series_key] = cardio_data.get("series", "")
        cardio_data["series"] = hiit_cols_1[0].text_input("Número de series", key=series_key, placeholder="Ej. 4")

        intervalos_key = f"{cardio_key}_intervalos"
        if intervalos_key not in st.session_state:
            st.session_state[intervalos_key] = cardio_data.get("intervalos", "")
        cardio_data["intervalos"] = hiit_cols_1[1].text_input("Número de intervalos", key=intervalos_key, placeholder="Ej. 6")

        hiit_cols_2 = st.columns(2, gap="small")
        tiempo_trabajo_key = f"{cardio_key}_tiempo_trabajo"
        if tiempo_trabajo_key not in st.session_state:
            st.session_state[tiempo_trabajo_key] = cardio_data.get("tiempo_trabajo", "")
        cardio_data["tiempo_trabajo"] = hiit_cols_2[0].text_input(
            "Tiempo intervalo de trabajo",
            key=tiempo_trabajo_key,
            placeholder="Ej. 40\"",
        )

        intensidad_trabajo_key = f"{cardio_key}_intensidad_trabajo"
        if intensidad_trabajo_key not in st.session_state:
            st.session_state[intensidad_trabajo_key] = cardio_data.get("intensidad_trabajo", "")
        cardio_data["intensidad_trabajo"] = hiit_cols_2[1].text_input(
            "Intensidad del intervalo de trabajo",
            key=intensidad_trabajo_key,
            placeholder="Ej. RPE 8/10",
        )

        hiit_cols_3 = st.columns(2, gap="small")
        tiempo_descanso_key = f"{cardio_key}_tiempo_descanso"
        if tiempo_descanso_key not in st.session_state:
            st.session_state[tiempo_descanso_key] = cardio_data.get("tiempo_descanso", "")
        cardio_data["tiempo_descanso"] = hiit_cols_3[0].text_input(
            "Tiempo de descanso",
            key=tiempo_descanso_key,
            placeholder="Ej. 20\"",
        )

        tipo_descanso_key = f"{cardio_key}_tipo_descanso"
        if tipo_descanso_key not in st.session_state:
            st.session_state[tipo_descanso_key] = cardio_data.get("tipo_descanso", "")
        cardio_data["tipo_descanso"] = hiit_cols_3[1].text_input(
            "Tipo de descanso",
            key=tipo_descanso_key,
            placeholder="Ej. activo, completo…",
        )

        intensidad_descanso_key = f"{cardio_key}_intensidad_descanso"
        if intensidad_descanso_key not in st.session_state:
            st.session_state[intensidad_descanso_key] = cardio_data.get("intensidad_descanso", "")
        cardio_data["intensidad_descanso"] = st.text_input(
            "Intensidad del intervalo de descanso",
            key=intensidad_descanso_key,
            placeholder="Ej. RPE 4/10",
        )
    else:
        # cuando el modo es LISS mantenemos consistencia en los widgets
        for campo in ("series", "intervalos", "tiempo_trabajo", "intensidad_trabajo", "tiempo_descanso", "tipo_descanso", "intensidad_descanso"):
            st.session_state.setdefault(f"{cardio_key}_{campo}", cardio_data.get(campo, ""))

    indicaciones_key = f"{cardio_key}_indicaciones"
    if indicaciones_key not in st.session_state:
        st.session_state[indicaciones_key] = cardio_data.get("indicaciones", "")
    cardio_data["indicaciones"] = st.text_area(
        "Indicaciones",
        key=indicaciones_key,
        placeholder="Notas extra sobre el trabajo cardiovascular…",
    )
    st.markdown("</div>", unsafe_allow_html=True)
    _sync_cardio_desde_widgets(dia_idx)


def editar_rutinas():
    st.markdown("<h2 class='h-accent'>✏️ Editar Rutinas</h2>", unsafe_allow_html=True)
    db = get_db()

    # ===== Clientes disponibles según permisos =====
    usuarios_map: dict[str, dict] = {}
    for user in USUARIOS:
        correo_u = (user.get("correo") or "").strip().lower()
        if correo_u:
            usuarios_map[correo_u] = user
            usuarios_map[correo_a_doc_id(correo_u)] = user

    correo_login = (st.session_state.get("correo") or "").strip().lower()
    rol_login = (st.session_state.get("rol") or "").strip().lower()
    empresa_login = empresa_de_usuario(correo_login, usuarios_map) if correo_login else EMPRESA_DESCONOCIDA

    global EJERCICIOS
    EJERCICIOS = _refrescar_catalogo()

    clientes_por_nombre: dict[str, list[str]] = {}
    for doc in db.collection("rutinas_semanales").stream():
        data = doc.to_dict() or {}
        nombre = (data.get("cliente") or "").strip()
        correo_cli = (data.get("correo") or "").strip().lower()
        if not nombre or not correo_cli:
            continue

        empresa_cli = empresa_de_usuario(correo_cli, usuarios_map)
        entrenador_doc = (data.get("entrenador") or "").strip().lower()
        coach_cli = ((usuarios_map.get(correo_cli) or {}).get("coach_responsable") or "").strip().lower()
        if not coach_cli:
            coach_cli = ((data.get("coach_responsable") or "").strip().lower())
        if not coach_cli:
            coach_cli = entrenador_doc

        permitido = True
        if rol_login in ("entrenador",):
            if empresa_login == EMPRESA_ASESORIA:
                permitido = coach_cli == correo_login or entrenador_doc == correo_login
            elif empresa_login == EMPRESA_MOTION:
                if empresa_cli == EMPRESA_MOTION:
                    permitido = True
                elif empresa_cli == EMPRESA_DESCONOCIDA:
                    permitido = coach_cli == correo_login or entrenador_doc == correo_login
                else:
                    permitido = False
            else:
                permitido = coach_cli == correo_login or entrenador_doc == correo_login
        elif rol_login not in ("admin", "administrador"):
            permitido = coach_cli == correo_login or entrenador_doc == correo_login

        if permitido and usuario_activo(correo_cli, usuarios_map, default_if_missing=True):
            lista = clientes_por_nombre.setdefault(nombre, [])
            if correo_cli not in lista:
                lista.append(correo_cli)

    clientes_dict: dict[str, str] = {}
    for nombre in sorted(clientes_por_nombre.keys()):
        correos_unique = sorted(set(clientes_por_nombre[nombre]))
        if len(correos_unique) == 1:
            clientes_dict[nombre] = correos_unique[0]
        else:
            for correo_cli in correos_unique:
                display = f"{nombre} ({correo_cli})"
                clientes_dict[display] = correo_cli

    if not clientes_dict:
        st.warning("❌ No hay clientes con rutinas para editar.")
        return

    nombre_cliente = st.selectbox("Selecciona el cliente:", sorted(clientes_dict.keys()))
    if not nombre_cliente:
        return
    correo_cliente = clientes_dict[nombre_cliente]

    # ===== Semanas disponibles del cliente =====
    semanas_dict: dict[str, str] = {}
    datos_cache: dict[str, dict] = {}
    for snap in db.collection("rutinas_semanales").where("correo", "==", correo_cliente).stream():
        data = snap.to_dict() or {}
        fecha = (data.get("fecha_lunes") or "").strip()
        if not fecha:
            continue
        semanas_dict[fecha] = snap.id
        datos_cache[snap.id] = data

    if not semanas_dict:
        st.warning("❌ Ese cliente aún no tiene rutinas registradas.")
        return

    semanas_ordenadas = sorted(semanas_dict.keys())
    idx_default = len(semanas_ordenadas) - 1 if semanas_ordenadas else 0
    semana_sel = st.selectbox("Selecciona la semana:", semanas_ordenadas, index=idx_default)
    doc_id_semana = semanas_dict[semana_sel]
    doc_data = datos_cache.get(doc_id_semana) or db.collection("rutinas_semanales").document(doc_id_semana).get().to_dict() or {}

    with st.expander("🔍 Revisar videos faltantes"):
        if st.button("Buscar ejercicios sin video", key="btn_buscar_videos"):
            catalogo_actual = _refrescar_catalogo()
            pendientes = _buscar_videos_faltantes(doc_data, catalogo_actual)
            st.session_state["_videos_pendientes"] = pendientes
            st.session_state["_videos_catalogo"] = catalogo_actual
            st.session_state["_videos_checked"] = True

        pendientes: list[tuple[str, str, str]] = st.session_state.get("_videos_pendientes", [])
        revisado = st.session_state.get("_videos_checked", False)

        if revisado:
            if pendientes:
                df = pd.DataFrame(
                    [{"Día": dia, "Ejercicio": ejercicio, "Video sugerido": url} for dia, ejercicio, url in pendientes]
                )
                st.dataframe(df, use_container_width=True, hide_index=True)
                if st.button("Aplicar videos sugeridos", type="primary", key="btn_aplicar_videos"):
                    catalogo_actual = st.session_state.get("_videos_catalogo") or _refrescar_catalogo()
                    aplicados = _completar_videos_rutina(db, doc_id_semana, doc_data, catalogo_actual, pendientes)
                    if aplicados:
                        st.success(f"Se actualizaron {aplicados} ejercicio(s) con video.")
                        st.session_state.pop("_videos_pendientes", None)
                        st.session_state.pop("_videos_catalogo", None)
                        st.session_state.pop("_videos_checked", None)
                        st.session_state["_editar_rutina_actual"] = None
                        datos_cache[doc_id_semana] = db.collection("rutinas_semanales").document(doc_id_semana).get().to_dict() or {}
                        _trigger_rerun()
                    else:
                        st.info("No se realizaron cambios. Verifica que los ejercicios sigan sin video.")
            else:
                st.info("Todos los ejercicios de la rutina ya tienen video o no hay sugerencias disponibles.")
        else:
            st.caption("Usa el botón para detectar ejercicios sin video y sugerir enlaces desde la colección.")

    with st.expander("🔁 Verificar videos distintos al catálogo"):
        if st.button("Buscar videos distintos", key="btn_buscar_videos_diff"):
            inconsistentes = _buscar_videos_inconsistentes(db, doc_data)
            _reset_video_diff_selection()
            st.session_state["_videos_diff_lista"] = inconsistentes
            st.session_state["_videos_diff_checked"] = True

        inconsistentes: list[dict] = st.session_state.get("_videos_diff_lista", [])
        revisado_diff = st.session_state.get("_videos_diff_checked", False)

        if revisado_diff:
            if inconsistentes:
                _sync_video_diff_checkbox_state(len(inconsistentes))
                df_diff = pd.DataFrame(
                    [
                        {
                            "Día": item["dia"],
                            "Ejercicio": item["ejercicio"],
                            "Video en rutina": item["video_actual"],
                            "Video catálogo": item["video_catalogo"],
                            "Doc catálogo": item.get("doc_id", ""),
                        }
                        for item in inconsistentes
                    ]
                )
                st.dataframe(df_diff, use_container_width=True, hide_index=True)
                st.caption("Selecciona los ejercicios a corregir y previsualiza los videos si lo necesitas:")
                seleccionados: list[dict] = []
                for idx, item in enumerate(inconsistentes):
                    cols_diff = st.columns([3, 1, 1])
                    key_chk = f"_video_diff_chk_{idx}"
                    etiqueta = f"Día {item['dia']} · {item['ejercicio']}"
                    with cols_diff[0]:
                        if key_chk not in st.session_state:
                            st.session_state[key_chk] = True
                        marcado = st.checkbox(etiqueta, key=key_chk)
                        if marcado:
                            seleccionados.append(item)
                    with cols_diff[1]:
                        _render_video_preview_button(item.get("video_actual", ""), "Video rutina", f"actual_{idx}")
                    with cols_diff[2]:
                        _render_video_preview_button(item.get("video_catalogo", ""), "Video catálogo", f"catalogo_{idx}")
                if st.button("Reemplazar por video del catálogo", type="primary", key="btn_aplicar_videos_diff"):
                    if not seleccionados:
                        st.info("Selecciona al menos un ejercicio para corregir.")
                    else:
                        aplicados = _reemplazar_videos_inconsistentes(db, doc_id_semana, doc_data, seleccionados)
                    if aplicados:
                        st.success(f"Se actualizaron {aplicados} ejercicio(s) con el video del catálogo.")
                        st.session_state.pop("_videos_diff_lista", None)
                        st.session_state.pop("_videos_diff_checked", None)
                        _reset_video_diff_selection()
                        st.session_state["_editar_rutina_actual"] = None
                        datos_cache[doc_id_semana] = (
                            db.collection("rutinas_semanales").document(doc_id_semana).get().to_dict() or {}
                        )
                        _trigger_rerun()
                    else:
                        st.info("No se realizaron cambios. Verifica que los videos sigan siendo distintos.")
            else:
                st.info("No se detectaron diferencias entre la rutina y el catálogo.")
        else:
            st.caption("Compara los videos guardados en la semana con los del catálogo de ejercicios.")

    estado_actual = st.session_state.get("_editar_rutina_actual")
    clave_actual = f"{correo_cliente}__{doc_id_semana}"
    if estado_actual != clave_actual:
        rutina_dict = doc_data.get("rutina", {}) or {}
        _cargar_rutina_en_session(rutina_dict, doc_data.get("cardio") or {})
        st.session_state["_editar_rutina_actual"] = clave_actual

    st.caption(f"Semana seleccionada: **{semana_sel}** · Cliente: **{nombre_cliente}**")

    objetivo_widget_key = f"editar_objetivo_{doc_id_semana}"
    objetivo_input = st.text_area(
        "🎯 Objetivo de la rutina (se muestra en la vista de rutinas)",
        value=str(doc_data.get("objetivo") or ""),
        key=objetivo_widget_key,
        placeholder="Describe en pocas líneas el foco principal de este bloque (opcional).",
        help="Este texto aparecerá bajo el nombre del cliente cuando se consulte la rutina.",
    )

    if st.button("➕ Agregar día", type="secondary"):
        _agregar_dia()

    if msg := st.session_state.pop("_dia_creado_msg", None):
        st.info(msg)

    dias_originales = st.session_state.get("dias_editables") or ["1"]
    st.session_state.setdefault("dias_originales", list(dias_originales))

    dias_labels = [f"Día {dia}" for dia in dias_originales]
    progresion_activa = st.radio(
        "Progresión activa",
        ["Progresión 1", "Progresión 2", "Progresión 3"],
        horizontal=True,
        key="editar_rutinas_progresion",
    )

    st.markdown(
        """
        <style>
            div[data-testid="stTabs"] div[role="tablist"] > button[aria-selected="true"] {
                border-bottom: 3px solid #d60000;
            }
        </style>
        """,
        unsafe_allow_html=True,
    )
    st.markdown(METRIC_LEGEND_HTML, unsafe_allow_html=True)

    tabs = st.tabs(dias_labels)
    for idx, tab in enumerate(tabs):
        with tab:
            render_tabla_dia(idx, "Warm Up", progresion_activa, dias_labels)
            st.markdown(SECTION_BREAK_HTML, unsafe_allow_html=True)
            render_tabla_dia(idx, "Work Out", progresion_activa, dias_labels)
            st.markdown(SECTION_BREAK_HTML, unsafe_allow_html=True)
            render_cardio_dia(idx)

    dias_actualizados = st.session_state.get("dias_originales", dias_originales)
    rutina_nueva, cardio_nuevo = _construir_rutina_desde_session(dias_actualizados)

    action_cols = st.columns([1, 1], gap="medium")
    notificar_correo = action_cols[0].checkbox(
        "Notificar por correo",
        value=False,
        key="editar_rutinas_notificar_correo",
        help="Envía un correo al atleta avisando que su rutina fue actualizada.",
    )
    guardar_clicked = action_cols[1].button("Guardar rutina", type="primary", use_container_width=True)

    if guardar_clicked:
        try:
            bloque_actual = doc_data.get("bloque_rutina", "")
            fecha_base = datetime.strptime(semana_sel, "%Y-%m-%d")
        except ValueError:
            st.error("La semana seleccionada no tiene un formato válido (YYYY-MM-DD).")
            return

        doc_ids_destino = [doc_id_semana]
        for fecha, doc_id in semanas_dict.items():
            if doc_id == doc_id_semana:
                continue
            try:
                fecha_doc = datetime.strptime(fecha, "%Y-%m-%d")
            except ValueError:
                continue
            if fecha_doc < fecha_base:
                continue
            datos_doc = datos_cache.get(doc_id)
            if datos_doc is None:
                snap_doc = db.collection("rutinas_semanales").document(doc_id).get()
                datos_doc = snap_doc.to_dict() or {}
                datos_cache[doc_id] = datos_doc
            if bloque_actual and datos_doc.get("bloque_rutina") != bloque_actual:
                continue
            doc_ids_destino.append(doc_id)

        objetivo_para_guardar = objetivo_input.strip()
        total = _guardar_cambios_en_documentos(
            db,
            doc_ids_destino,
            dias_actualizados,
            rutina_nueva,
            cardio_nuevo,
            objetivo_para_guardar,
        )
        if total:
            for doc_id in doc_ids_destino:
                snap = db.collection("rutinas_semanales").document(doc_id).get()
                datos_cache[doc_id] = snap.to_dict() or {}
            doc_data = datos_cache.get(doc_id_semana) or {}
            st.success(f"Rutina guardada en {total} semana(s).")
            if notificar_correo:
                nombre_email = (doc_data.get("cliente") or "").strip()
                if not nombre_email:
                    nombre_email = str(nombre_cliente).split("(")[0].strip()
                empresa_cliente = empresa_de_usuario(correo_cliente, usuarios_map)
                coach_correo = (doc_data.get("entrenador") or correo_login or "").strip()
                semanas_notificadas = max(1, len(doc_ids_destino))
                envio_ok = enviar_correo_rutina_disponible(
                    correo=correo_cliente,
                    nombre=nombre_email,
                    fecha_inicio=fecha_base,
                    semanas=semanas_notificadas,
                    empresa=empresa_cliente,
                    coach=coach_correo,
                )
                if envio_ok:
                    st.caption("El cliente fue notificado por correo con la rutina editada.")
                else:
                    st.caption("No se pudo enviar el aviso por correo; revisa la configuración de notificaciones.")
            else:
                st.caption("No se envió correo porque la notificación está desactivada.")
            st.session_state["_editar_rutina_actual"] = clave_actual
            _trigger_rerun()


if __name__ == "__main__":
    editar_rutinas()
