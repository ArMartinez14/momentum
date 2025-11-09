from __future__ import annotations

import re
import unicodedata
from datetime import datetime
import pandas as pd
import streamlit as st
from firebase_admin import firestore

from app_core.ejercicios_catalogo import obtener_ejercicios_disponibles
from app_core.firebase_client import get_db
from app_core.theme import inject_theme
from app_core.utils import (
    EMPRESA_ASESORIA,
    EMPRESA_DESCONOCIDA,
    EMPRESA_MOTION,
    correo_a_doc_id,
    empresa_de_usuario,
)
from servicio_catalogos import add_item, get_catalogos

# ===================== 🎨 ESTILOS / CONFIG =====================
inject_theme()

DEFAULT_WU_ROWS_NEW_DAY = 0
DEFAULT_WO_ROWS_NEW_DAY = 0
SECTION_BREAK_HTML = "<div style='height:0;margin:14px 0;'></div>"
SECTION_CONTAINER_HTML = "<div class='editor-block'>"

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


def _video_de_catalogo(nombre: str) -> str:
    meta = EJERCICIOS.get(nombre, {}) or {}
    return (meta.get("video") or meta.get("Video") or "").strip()


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


EJERCICIOS = _refrescar_catalogo()
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
    "Velocidad",
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
    "Copiar",
    "Video?",
    "Borrar",
]

BASE_SIZES = [0.9, 2.4, 2.8, 2.0, 0.8, 1.4, 1.0, 1.3, 1.0, 0.6, 0.6, 0.6]

PROGRESION_VAR_OPTIONS = ["", "peso", "velocidad", "tiempo", "descanso", "rir", "series", "repeticiones"]
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
    fila["Velocidad"] = ej.get("Velocidad") or ej.get("velocidad") or ""
    fila["RirMin"] = ej.get("RirMin") or ej.get("rir_min") or ""
    fila["RirMax"] = ej.get("RirMax") or ej.get("rir_max") or ""
    fila["RIR"] = ej.get("RIR") or ej.get("rir") or ""
    fila["Descanso"] = str(ej.get("Descanso") or ej.get("descanso") or "").split(" ")[0]
    fila["Tipo"] = ej.get("Tipo") or ej.get("tipo") or ""
    fila["Video"] = ej.get("Video") or ej.get("video") or ""
    fila["RirMin"] = fila["RirMin"] or fila["RIR"]
    fila["RirMax"] = fila["RirMax"] or fila["RIR"]

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
        fila["Video"] = _video_de_catalogo(fila["Ejercicio"])
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
        "velocidad": fila.get("Velocidad", ""),
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
        if not isinstance(ejercicios, list):
            continue
        for ejercicio in ejercicios:
            if not isinstance(ejercicio, dict):
                continue
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

    agrupados: dict[str, list[tuple[str, str]]] = {}
    for dia, nombre, link in pendientes:
        agrupados.setdefault(str(dia), []).append((nombre, link))

    rutina_nueva: dict[str, list] = {}
    total = 0
    for dia, ejercicios in rutina_actual.items():
        if not isinstance(ejercicios, list):
            rutina_nueva[dia] = ejercicios
            continue
        nuevas_filas = []
        for ejercicio in ejercicios:
            if not isinstance(ejercicio, dict):
                nuevas_filas.append(ejercicio)
                continue
            video_actual = (ejercicio.get("Video") or ejercicio.get("video") or "").strip()
            if video_actual:
                nuevas_filas.append(ejercicio)
                continue
            nombre = (ejercicio.get("Ejercicio") or ejercicio.get("ejercicio") or "").strip()
            candidatos = [link for nom, link in agrupados.get(str(dia), []) if nom == nombre]
            if candidatos:
                fila_actualizada = dict(ejercicio)
                fila_actualizada["Video"] = candidatos[0]
                fila_actualizada["video"] = candidatos[0]
                nuevas_filas.append(fila_actualizada)
                total += 1
            else:
                nuevas_filas.append(ejercicio)
        rutina_nueva[dia] = nuevas_filas

    if not total:
        return 0

    try:
        db.collection("rutinas_semanales").document(doc_id).update({"rutina": rutina_nueva})
    except Exception as exc:
        st.error(f"No pude actualizar los videos en Firestore: {exc}")
        return 0
    return total


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
        "video_flag_",
        "delete_",
        "do_copy_",
        "multiselect_",
    )
    for key in list(st.session_state.keys()):
        if key.startswith(patrones):
            st.session_state.pop(key, None)
    for clave in ("dias_editables", "dias_originales", "_dia_creado_msg"):
        st.session_state.pop(clave, None)


def _cargar_rutina_en_session(rutina_dict: dict):
    _limpiar_estado_rutina()
    dias = claves_dias(rutina_dict) or ["1"]
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


def _construir_rutina_desde_session(dias_originales: list[str]) -> dict[str, list[dict]]:
    resultado: dict[str, list[dict]] = {}
    for idx, dia in enumerate(dias_originales, start=1):
        warm = st.session_state.get(f"rutina_dia_{idx}_Warm_Up", []) or []
        work = st.session_state.get(f"rutina_dia_{idx}_Work_Out", []) or []
        filas = []
        for fila in warm + work:
            filas.append(_fila_ui_a_ejercicio_firestore_legacy(fila))
        resultado[str(dia)] = filas
    return resultado


def _guardar_cambios_en_documentos(
    db,
    doc_ids: list[str],
    dias_originales: list[str],
    rutina_actualizada: dict[str, list[dict]],
):
    total = 0
    for doc_id in doc_ids:
        ref = db.collection("rutinas_semanales").document(doc_id)
        snap = ref.get()
        data = snap.to_dict() or {}
        rutina_actual = data.get("rutina", {}) or {}
        nueva_rutina = dict(rutina_actual)
        for dia in dias_originales:
            nueva_rutina[str(dia)] = rutina_actualizada.get(str(dia), [])
        try:
            ref.update({"rutina": nueva_rutina})
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
    i0 = idx_dia - 1
    patrones = [f"_{i0}_Warm_Up_", f"_{i0}_Work_Out_"]
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
        "vel",
        "desc",
        "rirmin",
        "rirmax",
    ]
    for pref in prefixes:
        st.session_state.pop(f"{pref}_{key_entrenamiento}", None)

    for p in (1, 2, 3):
        st.session_state.pop(f"var{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"ope{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"cant{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"sem{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"condvar{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"condop{p}_{key_entrenamiento}", None)
        st.session_state.pop(f"condval{p}_{key_entrenamiento}", None)

    st.session_state.pop(f"prog_check_{key_entrenamiento}", None)
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

    toggle_cols = st.columns([6.8, 1.1, 1.2, 1.2, 1.7], gap="small")
    toggle_cols[0].markdown(f"<h4 class='h-accent' style='margin-top:2px'>{seccion}</h4>", unsafe_allow_html=True)

    show_tiempo = toggle_cols[1].toggle("Tiempo", key=f"show_tiempo_{key_seccion}")
    show_velocidad = toggle_cols[2].toggle("Velocidad", key=f"show_vel_{key_seccion}")
    show_descanso = toggle_cols[3].toggle("Descanso", key=f"show_desc_{key_seccion}")

    if _tiene_permiso_agregar():
        pop = toggle_cols[4].popover("＋", use_container_width=True)
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
        toggle_cols[4].button("＋", use_container_width=True, disabled=True)

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
    if show_velocidad:
        headers.insert(rir_idx, "Velocidad")
        sizes.insert(rir_idx, 1.0)
        rir_idx += 1
    if show_descanso:
        headers.insert(rir_idx, "Descanso")
        sizes.insert(rir_idx, 0.9)

    def _buscar_fuzzy(palabra: str) -> list[str]:
        if not palabra.strip():
            return []
        tokens = normalizar_texto(palabra).split()
        candidatos = []
        for nombre in ejercicios_dict.keys():
            if all(token in normalizar_texto(nombre) for token in tokens):
                candidatos.append(nombre)
        return candidatos

    section_container = st.container()
    with section_container:
        st.caption("Los cambios se guardan automáticamente.")
        header_cols = st.columns(sizes)
        for c, title in zip(header_cols, headers):
            slug = _header_slug(title)
            c.markdown(f"<div class='header-center header-center--{slug}'>{title}</div>", unsafe_allow_html=True)

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

            seleccionado = cols[pos["Ejercicio"]].selectbox(
                "",
                resultados,
                key=f"select_{key_entrenamiento}",
                label_visibility="collapsed",
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

            if "Velocidad" in pos:
                fila["Velocidad"] = cols[pos["Velocidad"]].text_input(
                    "",
                    value=str(fila.get("Velocidad", "")),
                    key=f"vel_{key_entrenamiento}",
                    label_visibility="collapsed",
                    placeholder="m/s",
                )
            else:
                fila.setdefault("Velocidad", "")

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

            prog_cols = cols[pos["Progresión"]].columns([1, 1, 1])
            mostrar_progresion = prog_cols[1].checkbox("", key=f"prog_check_{key_entrenamiento}")

            copy_cols = cols[pos["Copiar"]].columns([1, 1, 1])
            mostrar_copia = copy_cols[1].checkbox("", key=f"copy_check_{key_entrenamiento}")

            if mostrar_progresion:
                st.markdown(SECTION_BREAK_HTML, unsafe_allow_html=True)
                p = int(progresion_activa.split()[-1])
                pcols = st.columns([0.9, 0.9, 0.7, 0.8, 0.9, 0.9, 1.0])
                var_key = f"var{p}_{key_entrenamiento}"
                ope_key = f"ope{p}_{key_entrenamiento}"
                cant_key = f"cant{p}_{key_entrenamiento}"
                sem_key = f"sem{p}_{key_entrenamiento}"
                cond_var_key = f"condvar{p}_{key_entrenamiento}"
                cond_op_key = f"condop{p}_{key_entrenamiento}"
                cond_val_key = f"condval{p}_{key_entrenamiento}"

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

            if "Video?" in pos:
                nombre_ej = str(fila.get("Ejercicio", "")).strip()
                has_video = bool((fila.get("Video") or "").strip() or _video_de_catalogo(nombre_ej))
                video_cols = cols[pos["Video?"]].columns([1, 1, 1])
                video_cols[1].checkbox("", value=has_video, disabled=True, key=f"video_flag_{i}_{seccion}_{idx}")

            borrar_key = f"delete_{key_entrenamiento}"
            borrar_cols = cols[pos["Borrar"]].columns([1, 1, 1])
            marcado_borrar = borrar_cols[1].checkbox("", key=borrar_key)
            if marcado_borrar:
                filas_marcadas.append((idx, key_entrenamiento))
                fila["_delete_marked"] = True
            else:
                fila.pop("_delete_marked", None)
                st.session_state.pop(borrar_key, None)

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

        if permitido:
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

    estado_actual = st.session_state.get("_editar_rutina_actual")
    clave_actual = f"{correo_cliente}__{doc_id_semana}"
    if estado_actual != clave_actual:
        rutina_dict = doc_data.get("rutina", {}) or {}
        _cargar_rutina_en_session(rutina_dict)
        st.session_state["_editar_rutina_actual"] = clave_actual

    st.caption(f"Semana seleccionada: **{semana_sel}** · Cliente: **{nombre_cliente}**")

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

    dias_actualizados = st.session_state.get("dias_originales", dias_originales)
    rutina_nueva = _construir_rutina_desde_session(dias_actualizados)

    if st.button("Guardar rutina", type="primary"):
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

        total = _guardar_cambios_en_documentos(db, doc_ids_destino, dias_actualizados, rutina_nueva)
        if total:
            for doc_id in doc_ids_destino:
                snap = db.collection("rutinas_semanales").document(doc_id).get()
                datos_cache[doc_id] = snap.to_dict() or {}
            doc_data = datos_cache.get(doc_id_semana) or {}
            st.success(f"Rutina guardada en {total} semana(s).")
            st.session_state["_editar_rutina_actual"] = clave_actual
            _trigger_rerun()


if __name__ == "__main__":
    editar_rutinas()
