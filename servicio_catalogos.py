# servicio_catalogos.py
import json
import firebase_admin
from firebase_admin import credentials, firestore

# --- Opcional: usar Streamlit si existe, para cachear y leer secrets ---
_USE_ST = False
try:
    import streamlit as st
    _USE_ST = True
except Exception:
    st = None  # para evitar NameError

# === INICIALIZAR FIREBASE SOLO UNA VEZ ===
def _init_db():
    if not firebase_admin._apps:
        if _USE_ST:
            cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
        else:
            # Si ejecutas fuera de Streamlit, adapta esta lectura local:
            # with open("firebase_credentials.json") as f:
            #     cred_dict = json.load(f)
            raise RuntimeError("Ejecuta dentro de Streamlit o agrega lectura local de credenciales.")
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

COLL = "configuracion_app"
DOC  = "catalogos_ejercicios"

DEFAULTS = {
    "caracteristicas": [
        "Hypertrophy","Isometric","LB Plyometrics","Strength","UB Plyometrics"
    ],
    "patrones_movimiento": [
        "Activation","Antiextension","Antirotatory","LB Vertical Pull","LB Vertical Push","Mobility","Olympic","Stretching",
        "UB Diagonal Pull","UB Diagonal Push","UB Horizontal Pull","UB Horizontal Push","UB Vertical Pull","UB Vertical Push"
    ],
    "grupo_muscular_principal": [
        "Adductors","Ankle","Back","Biceps","Calves","Chest","Complex","Core","Glutes",
        "Hamstrings","Hip Flexors","Interescapular","Lower Back","Quadriceps","Rotator Cuff","Shoulder","Thoracic","Triceps"
    ],
}

if _USE_ST:
    try:
        from app_core.cache import cache_data as _cache_data_helper, clear_cache as _clear_cache_helper
    except Exception:
        _cache_data_helper = None
        _clear_cache_helper = None
else:
    _cache_data_helper = None
    _clear_cache_helper = None


# --- Decorador de caché: usa helper si hay Streamlit, si no, sin caché ---
def _cache(fn):
    if _USE_ST and _cache_data_helper:
        return _cache_data_helper("catalogos", show_spinner=False)(fn)
    if _USE_ST:
        return st.cache_data(show_spinner=False)(fn)
    return fn

@_cache
def _get_or_create_catalogos():
    db = _init_db()
    ref = db.collection(COLL).document(DOC)
    snap = ref.get()
    if not snap.exists:
        ref.set(DEFAULTS)
        data = DEFAULTS
    else:
        data = snap.to_dict() or {}
        # asegurar claves mínimas
        for k, v in DEFAULTS.items():
            if k not in data:
                data[k] = v
    return data

# 👇👀 ESTA es la función que importas desde tu otro archivo
def get_catalogos():
    return _get_or_create_catalogos()

def add_item(tipo: str, valor: str):
    valor = (valor or "").strip()
    if not valor:
        return
    db = _init_db()
    ref = db.collection(COLL).document(DOC)
    ref.update({tipo: firestore.ArrayUnion([valor])})
    if _USE_ST and _clear_cache_helper:
        _clear_cache_helper("catalogos")

def remove_item(tipo: str, valor: str):
    valor = (valor or "").strip()
    if not valor:
        return
    db = _init_db()
    ref = db.collection(COLL).document(DOC)
    ref.update({tipo: firestore.ArrayRemove([valor])})
    if _USE_ST and _clear_cache_helper:
        _clear_cache_helper("catalogos")

# Utilidad para reemplazar todo el documento (solo si quieres forzar nuevos defaults)
def set_catalogos(new_data: dict, overwrite: bool = True):
    db = _init_db()
    ref = db.collection(COLL).document(DOC)
    if overwrite:
        ref.set(new_data)
    else:
        ref.set(new_data, merge=True)
    if _USE_ST and _clear_cache_helper:
        _clear_cache_helper("catalogos")
