from __future__ import annotations
from typing import Optional

try:
    import streamlit as st
except Exception:
    st = None  # type: ignore

from .firebase_client import get_db


def normalizar_correo(correo: str) -> str:
    """Normaliza el correo para IDs: minúsculas y reemplazo @/. por _.
    Compatibiliza con usos existentes en el repositorio.
    """
    return (correo or "").strip().lower().replace("@", "_").replace(".", "_")


def correo_actual() -> str:
    if st is None:
        return ""
    return (st.session_state.get("correo") or "").strip()


def rol_actual() -> str:
    if st is None:
        return ""
    return (st.session_state.get("rol") or "").strip().lower()


_ADMIN_ROLES = {"admin", "administrador", "owner", "Admin", "Administrador"}


def es_admin() -> bool:
    return rol_actual() in {r.lower() for r in _ADMIN_ROLES}


def rol_es(*roles: str) -> bool:
    r = rol_actual()
    return any(r == x.lower() for x in roles)


def buscar_usuario_por_correo(correo: str) -> Optional[dict]:
    """Consulta colección `usuarios` por campo 'correo' (normalizado)."""
    db = get_db()
    correo_norm = (correo or "").strip().lower()
    try:
        docs = list(db.collection("usuarios").where("correo", "==", correo_norm).limit(1).stream())
        if not docs:
            return None
        data = docs[0].to_dict() or {}
        # Conserva forma original
        return {
            "correo": data.get("correo") or correo_norm,
            "rol": (data.get("rol") or "").lower(),
            "nombre": data.get("nombre", ""),
        }
    except Exception:
        return None
