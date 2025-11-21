"""Utilities para acceder a la colección de usuarios sin repetir queries pesadas."""
from __future__ import annotations

from typing import Dict, List

from app_core.cache import cache_data
from app_core.firebase_client import get_db
from app_core.utils import normalizar_correo, correo_a_doc_id


@cache_data("usuarios", show_spinner=False, ttl=300, max_entries=8)
def _fetch_all_users() -> List[dict]:
    """Obtiene todos los usuarios una sola vez y cachea el resultado."""

    db = get_db()
    usuarios: List[dict] = []
    for snap in db.collection("usuarios").stream():
        if not snap.exists:
            continue
        data = snap.to_dict() or {}
        data.setdefault("_id", snap.id)
        correo_norm = normalizar_correo(data.get("correo", ""))
        if correo_norm:
            data["_correo_norm"] = correo_norm
        usuarios.append(data)
    return usuarios


@cache_data("usuarios", show_spinner=False, ttl=300, max_entries=8)
def get_users_map() -> Dict[str, dict]:
    """Mapping correo/doc_id normalizado -> payload del usuario."""

    mapping: Dict[str, dict] = {}
    for user in _fetch_all_users():
        correo_norm = user.get("_correo_norm") or normalizar_correo(user.get("correo", ""))
        if not correo_norm:
            continue
        mapping[correo_norm] = user
        mapping[correo_a_doc_id(correo_norm)] = user
    return mapping


def list_users() -> List[dict]:
    """Expone la lista cacheada cuando se necesita iterar completa."""

    return list(_fetch_all_users())
