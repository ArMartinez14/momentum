import datetime
import json
import os
from typing import Optional

try:
    import streamlit as st
except Exception:  # pragma: no cover - permite reutilizar en scripts/tests
    st = None  # type: ignore

import firebase_admin
from firebase_admin import storage

from app_core.firebase_client import _ensure_initialized  # reusa la inicialización existente


def _normalize_bucket_name(name: str | None) -> str | None:
    """Acepta entradas tipo URL/domino y devuelve solo el ID del bucket."""
    if not name:
        return None
    cleaned = name.strip()
    if not cleaned:
        return None
    cleaned = cleaned.replace("gs://", "")
    cleaned = cleaned.replace("https://", "").replace("http://", "")
    if cleaned.startswith("firebasestorage.googleapis.com"):
        # p.ej. firebasestorage.googleapis.com/v0/b/<bucket>/o
        parts = cleaned.split("/b/", 1)
        if len(parts) == 2:
            cleaned = parts[1]
    cleaned = cleaned.split("/", 1)[0]
    cleaned = cleaned.strip()
    return cleaned or None


def _get_configured_bucket_name() -> str | None:
    """
    Intenta resolver el bucket explícito desde secrets/env.
    Prioriza:
      1) st.secrets["FIREBASE_STORAGE_BUCKET"]
      2) `storageBucket` dentro de st.secrets["FIREBASE_CONFIG"]
      3) Variables de entorno FIREBASE_STORAGE_BUCKET / STORAGE_BUCKET
    """
    bucket_name = None
    if st is not None:
        try:
            bucket_name = st.secrets.get("FIREBASE_STORAGE_BUCKET")  # type: ignore[assignment]
        except Exception:
            bucket_name = None
        if not bucket_name:
            try:
                config_raw = st.secrets.get("FIREBASE_CONFIG")
            except Exception:
                config_raw = None
            if config_raw:
                try:
                    config_json = json.loads(config_raw)
                    bucket_name = config_json.get("storageBucket")
                except Exception:
                    bucket_name = None
    if not bucket_name:
        bucket_name = os.environ.get("FIREBASE_STORAGE_BUCKET") or os.environ.get("STORAGE_BUCKET")
    return _normalize_bucket_name(bucket_name)


def _get_bucket():
    if not firebase_admin._apps:
        _ensure_initialized()
    bucket_name = _get_configured_bucket_name()
    if bucket_name:
        return storage.bucket(bucket_name)
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
