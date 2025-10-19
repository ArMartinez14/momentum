# app.py
import re
import streamlit as st

# 1) SIEMPRE PRIMERO
st.set_page_config(page_title="Aplicación Asesorías", layout="wide")

def _goto(menu_label: str):
    st.session_state["_menu_target"] = menu_label
    st.rerun()


def _role_label(rol: str | None) -> str:
    mapping = {
        "admin": "Administrador",
        "administrador": "Administrador",
        "entrenador": "Entrenador",
        "deportista": "Deportista",
    }
    key = (rol or "").strip().lower()
    if not key:
        return "Sin rol definido"
    return mapping.get(key, key.title())


def _nav_button_key(label: str, suffix: int) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_") or "item"
    return f"nav_{slug}_{suffix}"


def _render_navigation(opciones_menu: list[str], menu_actual: str) -> None:
    if not opciones_menu:
        return

    st.markdown(
        """
        <div class='nav-section'>
          <div class='nav-section__title'>Navegación</div>
          <div class='nav-section__hint'>Mantén tu flujo y vuelve a donde estabas en un toque.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    max_cols = 4
    for idx in range(0, len(opciones_menu), max_cols):
        fila = opciones_menu[idx: idx + max_cols]
        cols = st.columns(len(fila), gap="small")
        for col, opcion in zip(cols, fila):
            with col:
                activo = opcion == menu_actual
                tipo = "primary" if activo else "secondary"
                if st.button(
                    opcion,
                    key=_nav_button_key(opcion, idx),
                    type=tipo,
                    use_container_width=True,
                ):
                    if not activo:
                        _goto(opcion)

# 2) Soft login (usa el módulo que ya probaste)
from soft_login_full import soft_login_barrier, soft_logout
from inicio import inicio_deportista, SEGUIMIENTO_LABEL
from app_core.theme import inject_theme
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
# 4) Tema base (paleta Momentum)
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

# Inyección de tema moderno (respeta la paleta actual definida en app_core/theme.py)
inject_theme()

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

target_menu = st.session_state.pop("_menu_target", None)
if "menu_radio" not in st.session_state:
    st.session_state["menu_radio"] = opciones_menu[0]

def _normalizar_menu(value: str | None) -> str:
    if value in (label_seg_2, SEGUIMIENTO_LABEL):
        return SEGUIMIENTO_LABEL
    return value or ""

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

last_menu = st.session_state.get("_last_menu")
menu_cambio = last_menu != menu_actual
st.session_state["_last_menu"] = menu_actual

header = st.container()
with header:
    nombre_display = (
        st.session_state.get("primer_nombre")
        or st.session_state.get("nombre")
        or (email.split("@")[0].title() if email else "Equipo Momentum")
    )
    rol_legible = _role_label(rol)
    chip_html = (
        f"<div><span class='hero-card__chip'>Sección actual · {menu_actual}</span></div>"
        if menu_actual else ""
    )
    hero_html = f"""
        <div class='hero-card'>
          <span class='hero-card__label'>Momentum Today</span>
          <span class='hero-card__title'>Hola, {nombre_display}</span>
          <span class='hero-card__meta'>{rol_legible}</span>
          {chip_html}
        </div>
    """

    top_cols = st.columns([3, 2], gap="large")
    with top_cols[0]:
        st.markdown(hero_html, unsafe_allow_html=True)

    with top_cols[1]:
        session_html = f"""
            <div class='session-card'>
              <span class='session-card__label'>Correo activo</span>
              <span class='session-card__value'>{email or 'Sin correo'}</span>
            </div>
        """
        st.markdown(session_html, unsafe_allow_html=True)

    mostrar_back = menu_actual != "Inicio"
    action_cols = st.columns(3 if mostrar_back else 2, gap="small")
    idx = 0
    if mostrar_back:
        with action_cols[0]:
            if st.button(
                "← Inicio",
                key="btn_back_inicio",
                type="secondary",
                use_container_width=True,
                help="Volver a Inicio",
            ):
                _goto("Inicio")
        idx = 1

    with action_cols[idx]:
        if st.button(
            "Actualizar",
            key="btn_refresh",
            type="secondary",
            use_container_width=True,
            help="Actualizar datos y refrescar cachés",
        ):
            st.cache_data.clear()
            st.rerun()

    with action_cols[idx + 1]:
        if st.button(
            "Cerrar sesión",
            key="btn_logout",
            type="secondary",
            use_container_width=True,
            help="Finaliza tu sesión actual",
        ):
            soft_logout()

_render_navigation(opciones_menu, menu_actual)

opcion = menu_actual

# 10) Ruteo
if opcion == "Inicio":
    inicio_deportista()   # ← SIEMPRE aterriza en Inicio

elif opcion == "Ver Rutinas":
    if menu_cambio:
        st.session_state.pop("dia_sel", None)
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
