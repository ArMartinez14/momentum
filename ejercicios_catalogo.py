from __future__ import annotations

import streamlit as st

from app_core.firebase_client import get_db
from app_core.utils import empresa_de_usuario, EMPRESA_MOTION

ADMIN_ROLES = {"admin", "administrador", "owner"}


def _normalizar_correo(valor: str) -> str:
    return (valor or "").strip().lower()


def _es_admin(rol: str) -> bool:
    return (rol or "").strip().lower() in {r.lower() for r in ADMIN_ROLES}


def _debe_reemplazar(actual: dict | None, nuevo: dict, correo_prioritario: str) -> bool:
    if not actual:
        return True
    correo_prioritario = _normalizar_correo(correo_prioritario)
    if not correo_prioritario:
        return True
    owner_actual = _normalizar_correo(actual.get("entrenador"))
    owner_nuevo = _normalizar_correo(nuevo.get("entrenador"))
    if owner_actual == correo_prioritario and owner_nuevo != correo_prioritario:
        return False
    if owner_nuevo == correo_prioritario and owner_actual != correo_prioritario:
        return True
    video_actual = (actual.get("video") or actual.get("Video") or "").strip()
    video_nuevo = (nuevo.get("video") or nuevo.get("Video") or "").strip()
    if not video_actual and video_nuevo:
        return True
    return True


def _store(target: dict[str, dict], doc_id: str, data: dict, correo_prioritario: str = "") -> None:
    nombre = (data.get("nombre") or "").strip()
    if nombre:
        enriched = dict(data)
        enriched["_doc_id"] = doc_id
        if "video" not in enriched and "Video" in enriched:
            enriched["video"] = enriched.get("Video", "")
        if "Video" not in enriched and "video" in enriched:
            enriched["Video"] = enriched.get("video", "")
        if _debe_reemplazar(target.get(nombre), enriched, correo_prioritario):
            target[nombre] = enriched


@st.cache_data(show_spinner=False)
def cargar_ejercicios_filtrados(correo_usuario: str, rol: str) -> dict[str, dict]:
    db = get_db()
    correo_usuario = (correo_usuario or "").strip().lower()
    rol = (rol or "").strip()
    ejercicios_por_nombre: dict[str, dict] = {}

    try:
        if _es_admin(rol):
            for doc in db.collection("ejercicios").stream():
                if not doc.exists:
                    continue
                _store(ejercicios_por_nombre, doc.id, doc.to_dict() or {}, correo_usuario)
            return ejercicios_por_nombre

        empresa_usuario = empresa_de_usuario(correo_usuario) if correo_usuario else ""
        publicos: dict[str, dict] = {}
        personales: dict[str, dict] = {}
        compartidos: dict[str, dict] = {}

        if empresa_usuario == EMPRESA_MOTION:
            empresa_cache: dict[str, str] = {}

            def _empresa_de_creador(correo_creador: str) -> str:
                correo_creador = (correo_creador or "").strip().lower()
                if not correo_creador:
                    return ""
                if correo_creador not in empresa_cache:
                    try:
                        empresa_cache[correo_creador] = empresa_de_usuario(correo_creador)
                    except Exception:
                        empresa_cache[correo_creador] = ""
                return empresa_cache[correo_creador]

            for doc in db.collection("ejercicios").stream():
                if not doc.exists:
                    continue
                data = doc.to_dict() or {}
                if not data:
                    continue
                es_publico = bool(data.get("publico"))
                creador = (data.get("entrenador") or "").strip().lower()

                if es_publico:
                    _store(publicos, doc.id, data, correo_usuario)
                    continue

                if creador and creador == correo_usuario:
                    _store(personales, doc.id, data, correo_usuario)
                    continue

                empresa_doc = (data.get("empresa_propietaria") or "").strip().lower()
                if not empresa_doc:
                    empresa_doc = _empresa_de_creador(creador)

                if empresa_doc == EMPRESA_MOTION:
                    _store(compartidos, doc.id, data, correo_usuario)

            ejercicios_por_nombre.update(publicos)
            ejercicios_por_nombre.update(compartidos)
            ejercicios_por_nombre.update(personales)
        else:
            for doc in db.collection("ejercicios").where("publico", "==", True).stream():
                if not doc.exists:
                    continue
                _store(publicos, doc.id, doc.to_dict() or {}, correo_usuario)

            if correo_usuario:
                for doc in db.collection("ejercicios").where("entrenador", "==", correo_usuario).stream():
                    if not doc.exists:
                        continue
                    data = doc.to_dict() or {}
                    _store(personales, doc.id, data, correo_usuario)
                    publicos.pop((data.get("nombre") or "").strip(), None)

            ejercicios_por_nombre.update(publicos)
            ejercicios_por_nombre.update(personales)
    except Exception as e:
        st.error(f"Error cargando ejercicios: {e}")

    return ejercicios_por_nombre


def obtener_ejercicios_disponibles() -> dict[str, dict]:
    correo_usuario = (st.session_state.get("correo") or "").strip().lower()
    rol = (st.session_state.get("rol") or "").strip()
    return cargar_ejercicios_filtrados(correo_usuario, rol)
