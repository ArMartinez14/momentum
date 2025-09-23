import json
from typing import Optional

try:
    import streamlit as st
except Exception:  # Permitir importar fuera de Streamlit (tests)
    st = None  # type: ignore

import firebase_admin
from firebase_admin import credentials, firestore


def _initialize_app_from_secrets() -> None:
    if st is None:
        raise RuntimeError("Streamlit no disponible para leer secrets.")
    try:
        cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])  # type: ignore[index]
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    except Exception as exc:  # pragma: no cover
        raise


def _initialize_app_adc() -> None:
    # Application Default Credentials (si la variable de entorno GOOGLE_APPLICATION_CREDENTIALS está definida)
    firebase_admin.initialize_app()


def _ensure_initialized() -> None:
    if firebase_admin._apps:  # ya inicializado
        return
    # Prioridad: secrets -> ADC
    try:
        _initialize_app_from_secrets()
    except Exception:
        _initialize_app_adc()


def get_db() -> firestore.Client:
    """Devuelve un cliente único de Firestore.

    - Prioriza credenciales en `st.secrets["FIREBASE_CREDENTIALS"]`.
    - Fallback a ADC si no existen secrets.
    - Cacheado a nivel de proceso vía singleton de firebase_admin.
    """
    # Cache a nivel Streamlit si está disponible
    if st is not None:
        return _get_db_cached()
    # Contexto sin Streamlit (tests/scripts)
    _ensure_initialized()
    return firestore.client()


if st is not None:
    @st.cache_resource(show_spinner=False)  # type: ignore[misc]
    def _get_db_cached() -> firestore.Client:
        _ensure_initialized()
        return firestore.client()
else:
    def _get_db_cached() -> firestore.Client:  # fallback para tipado
        _ensure_initialized()
        return firestore.client()
