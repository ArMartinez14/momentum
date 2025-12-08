import datetime
from typing import Optional

import firebase_admin
from firebase_admin import storage

from app_core.firebase_client import _ensure_initialized  # reusa la inicialización existente


def _get_bucket():
    if not firebase_admin._apps:
        _ensure_initialized()
    return storage.bucket()


def upload_bytes_get_url(
    data: bytes,
    path: str,
    *,
    content_type: Optional[str] = None,
    signed_ttl_days: int = 30,
) -> str:
    """
    Sube bytes al bucket y devuelve una URL firmada temporal.
    - path: ruta completa dentro del bucket (ej: reportes_videos/...)
    - signed_ttl_days: vigencia de la URL; el archivo permanece hasta que se borre (p. ej. regla lifecycle).
    """
    bucket = _get_bucket()
    blob = bucket.blob(path)
    blob.upload_from_string(data, content_type=content_type)
    return blob.generate_signed_url(datetime.timedelta(days=signed_ttl_days))


def delete_blob_safe(path: str) -> bool:
    """Borra el blob indicado; ignora si no existe."""
    try:
        bucket = _get_bucket()
        blob = bucket.blob(path)
        blob.delete()
        return True
    except Exception:
        return False
