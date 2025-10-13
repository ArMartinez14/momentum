# app.py
import streamlit as st

# 1) SIEMPRE PRIMERO
st.set_page_config(page_title="Aplicación Asesorías", layout="wide")

def _goto(menu_label: str):
    st.session_state["_menu_target"] = menu_label
    st.rerun()


def _get_query_param_first(name: str) -> str | None:
    try:
        raw = st.query_params.get(name)
    except Exception:
        raw = None
    if raw is None:
        try:
            raw = st.experimental_get_query_params().get(name)
        except Exception:
            raw = None
    if isinstance(raw, list):
        return raw[0] if raw else None
    return raw


def _sync_menu_query_param(value: str) -> None:
    target = value or ""
    try:
        current = st.query_params.get("menu")
        if isinstance(current, list):
            current = current[0] if current else None
    except Exception:
        current = None
    if current == target:
        return
    try:
        st.query_params.update({"menu": target})
        return
    except Exception:
        pass
    try:
        params = st.experimental_get_query_params()
        if isinstance(params, dict):
            normalized = {}
            for k, v in params.items():
                if isinstance(v, list):
                    normalized[k] = v[0] if v else ""
                elif v is not None:
                    normalized[k] = str(v)
            normalized["menu"] = target
            st.experimental_set_query_params(**normalized)
    except Exception:
        pass

# 2) Soft login (usa el módulo que ya probaste)
from soft_login_full import soft_login_barrier, soft_logout
from inicio import inicio_deportista, SEGUIMIENTO_LABEL
# 3) Imports del resto de la app
import json
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
from seguimiento_entrenamiento import app as seguimiento_app  # NUEVO
from seccion_ejercicios import base_ejercicios
from vista_rutinas import ver_rutinas
from borrar_rutinas import borrar_rutinas
from ingresar_cliente_view import ingresar_cliente_o_video_o_ejercicio
from crear_planificaciones import crear_rutinas
from editar_rutinas import editar_rutinas
from crear_descarga import descarga_rutina
from reportes import ver_reportes
from admin_resumen import ver_resumen_entrenadores  # si no lo usas, puedes comentar

# ➕ utilidades para cargar el módulo de seguimiento
import importlib

# 4) Estilos (opcional)
st.markdown("""
<style>
@media (prefers-color-scheme: light) {
  h1, h2, h3, h4, h5, h6, p, label, span, li,
  div[data-testid="stMarkdownContainer"] { color: #111111 !important; }
  input, textarea, select { color: #111111 !important; }
}
@media (prefers-color-scheme: dark) {
  h1, h2, h3, h4, h5, h6, p, label, span, li,
  div[data-testid="stMarkdownContainer"] { color: #ffffff !important; }
  input, textarea, select { color: #ffffff !important; }
}
.main .block-container {
  padding-top: 0.2rem !important;
}
.app-header-card {
  background: #0b1018;
  border: 1px solid rgba(148, 163, 184, 0.15);
  border-radius: 14px;
  padding: 14px 18px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.app-header-card__label {
  font-size: 0.75rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: rgba(226, 232, 240, 0.65);
}
.app-header-card__value {
  font-size: 0.95rem;
  font-weight: 700;
  color: #e2e8f0;
}

div[data-testid="stButton"][data-key="btn_back_inicio"] button {
  background: linear-gradient(135deg, #34d399, #10b981) !important;
  color: #012b1a !important;
  border: 1px solid rgba(16, 185, 129, 0.4) !important;
  box-shadow: none !important;
}

div[data-testid="stButton"][data-key="btn_refresh"] button {
  background: linear-gradient(135deg, #38bdf8, #0ea5e9) !important;
  color: #01243b !important;
  border: 1px solid rgba(14, 165, 233, 0.45) !important;
  box-shadow: none !important;
}

div[data-testid="stButton"][data-key="btn_logout"] button {
  background: linear-gradient(135deg, #f97316, #ef4444) !important;
  color: #fff !important;
  border: 1px solid rgba(249, 115, 22, 0.45) !important;
  box-shadow: none !important;
}

div[data-testid="stButton"][data-key="btn_back_inicio"] button {
  background: linear-gradient(135deg, #34d399, #10b981) !important;
  color: #012b1a !important;
  border: 1px solid rgba(16, 185, 129, 0.4) !important;
  box-shadow: none !important;
}
</style>
""", unsafe_allow_html=True)

# 5) Inicializar Firebase (una sola vez)
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    initialize_app(cred)
db = firestore.client()

# 6) Barrera de Soft Login (persistente con cookie)
#    Cambia required_roles si quieres restringir el ingreso a ciertos roles globalmente.
if not soft_login_barrier(titulo="Bienvenido a Momentum", required_roles=None):
    st.stop()

# 7) Menú principal según rol
email = st.session_state.get("correo", "")
rol = (st.session_state.get("rol") or "").lower()

label_seg_2 = "seguimiento_entrenamiento"
is_admin = rol in ("admin", "administrador") or (
    email and st.secrets.get("ADMIN_EMAIL", "").lower() == email.lower()
)

MENU_DEPORTISTA = [
    "Inicio",
    "Ver Rutinas",
    "Crear Descarga",
]

MENU_ENTRENADOR = [
    "Inicio",
    "Ver Rutinas",
    "Crear Rutinas",
    "Ingresar Deportista o Ejercicio",
    "Borrar Rutinas",
    "Editar Rutinas",
    "Ejercicios",
    "Crear Descarga",
    "Reportes",
    SEGUIMIENTO_LABEL,
]

MENU_ADMIN = MENU_ENTRENADOR + ["Resumen (Admin)"]

if is_admin:
    opciones_menu = MENU_ADMIN
elif rol == "entrenador":
    opciones_menu = MENU_ENTRENADOR
else:
    opciones_menu = MENU_DEPORTISTA

def _normalizar_menu(value: str | None) -> str:
    if value in (label_seg_2, SEGUIMIENTO_LABEL):
        return SEGUIMIENTO_LABEL
    return value or ""

qp_menu_raw = _get_query_param_first("menu")
qp_menu_norm = _normalizar_menu(qp_menu_raw) if qp_menu_raw else None

target_menu = st.session_state.pop("_menu_target", None)
if "menu_radio" not in st.session_state:
    if qp_menu_norm and qp_menu_norm in opciones_menu:
        st.session_state["menu_radio"] = qp_menu_norm
    else:
        st.session_state["menu_radio"] = opciones_menu[0]

if target_menu is not None:
    target_menu = _normalizar_menu(target_menu)
    if target_menu in opciones_menu:
        st.session_state["menu_radio"] = target_menu
    else:
        st.session_state["menu_radio"] = opciones_menu[0]

menu_actual = _normalizar_menu(st.session_state.get("menu_radio"))
if menu_actual not in opciones_menu:
    menu_actual = opciones_menu[0]
    st.session_state["menu_radio"] = menu_actual

_sync_menu_query_param(menu_actual)

header = st.container()
with header:
    mostrar_back = menu_actual != "Inicio"
    cols = st.columns([6, 1, 1, 1], gap="small") if mostrar_back else st.columns([6, 1, 1], gap="small")

    with cols[0]:
        st.markdown(
            f"""
            <div class="app-header-card">
              <span class="app-header-card__label">Sesión activa</span>
              <span class="app-header-card__value">{email or 'Sin correo'}</span>
            </div>
            """,
            unsafe_allow_html=True,
        )

    col_offset = 1
    if mostrar_back:
        with cols[1]:
            if st.button(
                "⬅️",
                key="btn_back_inicio",
                type="secondary",
                use_container_width=True,
                help="Volver al inicio",
            ):
                _goto("Inicio")
        col_offset = 2

    with cols[col_offset]:
        if st.button(
            "🔄",
            key="btn_refresh",
            type="secondary",
            use_container_width=True,
            help="Actualizar datos",
        ):
            st.cache_data.clear()
            st.rerun()

    with cols[col_offset + 1]:
        if st.button(
            "🚪",
            key="btn_logout",
            type="secondary",
            use_container_width=True,
            help="Cerrar sesión",
        ):
            soft_logout()

opcion = menu_actual

# 10) Ruteo
if opcion == "Inicio":
    inicio_deportista()   # ← SIEMPRE aterriza en Inicio

elif opcion == "Ver Rutinas":
    st.session_state.pop("dia_sel", None)   # opcional
    ver_rutinas()

elif opcion == "Crear Rutinas":
    if rol in ("entrenador", "admin", "administrador"):
        crear_rutinas()
    else:
        st.warning("No tienes permisos para crear rutinas.")

elif opcion == "Ingresar Deportista o Ejercicio":
    ingresar_cliente_o_video_o_ejercicio()

elif opcion == "Borrar Rutinas":
    borrar_rutinas()

elif opcion == "Editar Rutinas":
    editar_rutinas()

elif opcion == "Ejercicios":
    base_ejercicios()

elif opcion == "Crear Descarga":
    descarga_rutina()

elif opcion == "Reportes":
    ver_reportes()

elif opcion in (SEGUIMIENTO_LABEL, label_seg_2):
    if rol in ("entrenador", "admin", "administrador"):
        st.header("📈 Seguimiento (Entre Evaluaciones)")
        seguimiento_app()
    else:
        st.warning("No tienes permisos para acceder a Seguimiento.")

elif opcion == "Resumen (Admin)":
    if is_admin:
        ver_resumen_entrenadores()
    else:
        st.warning("Solo disponible para administradores.")
