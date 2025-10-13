# auth_guard.py
import streamlit as st
import json
import firebase_admin
from firebase_admin import credentials, auth as admin_auth, firestore
from datetime import datetime, timezone
from typing import Optional

# Inicializa Admin SDK una vez
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

_db = firestore.client()

def _normalizar_id(correo: str) -> str:
    return correo.replace("@","_").replace(".","_")

def verify_id_token(id_token: str) -> Optional[dict]:
    try:
        return admin_auth.verify_id_token(id_token)
    except Exception:
        return None

def fetch_user_role(email: str) -> str:
    """Lee el rol desde tu colección 'usuarios' (si existe)."""
    try:
        doc_id = _normalizar_id(email)
        snap = _db.collection("usuarios").document(doc_id).get()
        if snap.exists:
            data = snap.to_dict() or {}
            return (data.get("rol") or "").strip()
    except Exception:
        pass
    return ""

def ensure_user_session(id_token: str) -> bool:
    decoded = verify_id_token(id_token)
    if not decoded:
        return False

    email = (decoded.get("email") or "").lower()
    if not email:
        return False

    # Rellena session_state
    st.session_state["user"] = {
        "email": email,
        "uid": decoded.get("uid"),
        "name": decoded.get("name") or "",
        "picture": decoded.get("picture") or "",
        "exp": decoded.get("exp"),
        "iat": decoded.get("iat"),
        "auth_time": decoded.get("auth_time"),
    }
    st.session_state["correo"] = email

    # Rol desde tu colección (opcional)
    if "rol" not in st.session_state or not st.session_state["rol"]:
        st.session_state["rol"] = fetch_user_role(email)

    return True

def is_token_expired() -> bool:
    u = st.session_state.get("user")
    if not u:
        return True
    exp = u.get("exp")
    if not exp:
        return True
    now = datetime.now(timezone.utc).timestamp()
    return now > (exp - 120)  # margen 2min
