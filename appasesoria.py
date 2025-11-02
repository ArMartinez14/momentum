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


def _viewport_mode() -> str:
    st.markdown(
        """
        <script>
        (function() {
          const mode = window.innerWidth >= 1024 ? 'desktop' : 'mobile';
          const params = new URLSearchParams(window.location.search);
          if (params.get('device') !== mode) {
            params.set('device', mode);
            const payload = {
              isStreamlitMessage: true,
              type: 'streamlit:setQueryParams',
              queryParams: Object.fromEntries(params.entries()),
            };
            (window.parent || window).postMessage(payload, '*');
          }
        })();
        </script>
        """,
        unsafe_allow_html=True,
    )
    qp = st.query_params.get("device")
    if isinstance(qp, list):
        qp = qp[0] if qp else None
    if qp in ("desktop", "mobile"):
        st.session_state["_viewport_mode_cache"] = qp
        return qp
    return st.session_state.get("_viewport_mode_cache", "desktop")


def _menu_groups(opciones_menu: list[str]) -> list[dict[str, object]]:
    grupos: list[dict[str, object]] = []
    restantes = list(opciones_menu)
    restantes_set = set(restantes)

    def _agregar(grupo_id: str, etiqueta: str, items: list[str]):
        disponibles = [op for op in items if op in restantes_set]
        if not disponibles:
            return
        for op in disponibles:
            restantes_set.discard(op)
        grupos.append({"id": grupo_id, "label": etiqueta, "items": disponibles})

    _agregar("inicio", "Inicio", ["Inicio"])
    _agregar("rutinas", "Rutinas", [
        "Ver Rutinas",
        "Crear Rutinas",
        "Editar Rutinas",
        "Borrar Rutinas",
        "Crear Descarga",
    ])
    _agregar("atletas", "Atletas", [
        "Ingresar Deportista o Ejercicio",
        "Anamnesis",
        "Ejercicios",
    ])
    _agregar("seguimiento", "Seguimiento", [
        "Reportes",
        SEGUIMIENTO_LABEL,
    ])
    _agregar("admin", "Administración", ["Resumen (Admin)", "Previsualizar Correos"])

    restantes_final = [op for op in restantes if op in restantes_set]
    if restantes_final:
        grupos.append({
            "id": "otros",
            "label": "Otros",
            "items": restantes_final,
        })
    return grupos


def _render_navigation(opciones_menu: list[str], menu_actual: str) -> None:
    if not opciones_menu:
        return

    modo = _viewport_mode()

    st.markdown(
        """
        <div class='nav-section'>
          <div class='nav-section__title'>Navegación</div>
          <div class='nav-section__hint'>Mantén tu flujo y vuelve a donde estabas en un toque.</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    grupos = _menu_groups(opciones_menu)
    if not grupos:
        return

    grupo_actual_id = next((g["id"] for g in grupos if menu_actual in g["items"]), None)
    grupo_ids = [g["id"] for g in grupos]
    grupo_sel = st.session_state.get("_nav_group")
    if grupo_sel not in grupo_ids:
        grupo_sel = grupo_actual_id or grupos[0]["id"]
    st.session_state["_nav_group"] = grupo_sel

    grupo_activo = next((g for g in grupos if g["id"] == grupo_sel), grupos[0])
    items = grupo_activo["items"]
    if menu_actual in items:
        st.session_state["_nav_item_idx"] = items.index(menu_actual)
    elif st.session_state.get("_nav_item_idx") is None or st.session_state.get("_nav_item_idx") >= len(items):
        st.session_state["_nav_item_idx"] = 0

    if modo == "desktop":
        with st.container():
            st.markdown("<div class='nav-desktop'>", unsafe_allow_html=True)
            cols_groups = st.columns(len(grupos), gap="small")
            for col, grupo in zip(cols_groups, grupos):
                with col:
                    activo = grupo["id"] == st.session_state["_nav_group"]
                    if st.button(
                        grupo["label"],
                        key=f"nav_desktop_group_{grupo['id']}",
                        type="primary" if activo else "secondary",
                        use_container_width=True,
                    ):
                        st.session_state["_nav_group"] = grupo["id"]
                        st.session_state["_nav_item_idx"] = 0
                        if menu_actual not in grupo["items"] and grupo["items"]:
                            _goto(grupo["items"][0])
                            st.markdown("</div>", unsafe_allow_html=True)
                            return

            if items:
                cols_items = st.columns(len(items), gap="small")
                for col, opcion in zip(cols_items, items):
                    with col:
                        activo = opcion == menu_actual
                        if st.button(
                            opcion,
                            key=f"nav_desktop_item_{opcion}",
                            type="primary" if activo else "secondary",
                            use_container_width=True,
                        ):
                            st.session_state["_nav_item_idx"] = items.index(opcion)
                            if not activo:
                                _goto(opcion)
                                st.markdown("</div>", unsafe_allow_html=True)
                                return
            st.markdown("</div>", unsafe_allow_html=True)
        return

    with st.container():
        st.markdown("<div class='nav-mobile'>", unsafe_allow_html=True)

        grupo_label_actual = next(
            (g["label"] for g in grupos if g["id"] == st.session_state["_nav_group"]),
            grupos[0]["label"],
        )
        etiqueta_item_actual = menu_actual if menu_actual else "Selecciona una sección"

        st.markdown(
            f"""
            <div style='text-align:center;'>
              <div style='font-size:0.75rem; text-transform:uppercase; letter-spacing:0.14em; color:rgba(255,251,249,0.72);'>
                {grupo_label_actual}
              </div>
              <div style='font-weight:700; font-size:1.08rem; color:#FFFBF9; letter-spacing:0.05em;'>
                {etiqueta_item_actual}
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        with st.expander("Cambiar sección", expanded=False):
            etiquetas_grupo = [g["label"] for g in grupos]
            idx_defecto = etiquetas_grupo.index(grupo_label_actual) if grupo_label_actual in etiquetas_grupo else 0

            grupo_label_sel = st.radio(
                "Categoría",
                etiquetas_grupo,
                index=idx_defecto,
                key="nav_mobile_group_radio",
                label_visibility="collapsed",
            )

            grupo_seleccionado = next((g for g in grupos if g["label"] == grupo_label_sel), grupos[0])
            if grupo_seleccionado["id"] != st.session_state["_nav_group"]:
                st.session_state["_nav_group"] = grupo_seleccionado["id"]
                st.session_state["_nav_item_idx"] = 0
                if grupo_seleccionado["items"]:
                    _goto(grupo_seleccionado["items"][0])
                    st.markdown("</div>", unsafe_allow_html=True)
                    return

            items = grupo_seleccionado["items"]

            if items and menu_actual not in items:
                st.session_state["_nav_item_idx"] = 0
                _goto(items[0])
                st.markdown("</div>", unsafe_allow_html=True)
                return

            if items:
                idx_item_actual = items.index(menu_actual) if menu_actual in items else 0
                opcion_sel = st.radio(
                    "Sección",
                    items,
                    index=idx_item_actual,
                    key=f"nav_mobile_item_radio_{grupo_seleccionado['id']}",
                    label_visibility="collapsed",
                )

                if opcion_sel != menu_actual:
                    st.session_state["_nav_item_idx"] = items.index(opcion_sel)
                    _goto(opcion_sel)
                    st.markdown("</div>", unsafe_allow_html=True)
                    return

        st.markdown("</div>", unsafe_allow_html=True)

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
from admin_email_preview import ver_previsualizacion_correos
from anamnesis_view import render_anamnesis, necesita_anamnesis

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
    "Anamnesis",
    "Ver Rutinas",
]

MENU_ENTRENADOR = [
    "Inicio",
    "Ver Rutinas",
    "Crear Rutinas",
    "Ingresar Deportista o Ejercicio",
    "Anamnesis",
    "Borrar Rutinas",
    "Editar Rutinas",
    "Ejercicios",
    "Crear Descarga",
    "Reportes",
    SEGUIMIENTO_LABEL,
]

MENU_ADMIN = MENU_ENTRENADOR + ["Resumen (Admin)", "Previsualizar Correos"]

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

anamnesis_pendiente = False
if rol == "deportista":
    try:
        anamnesis_pendiente = necesita_anamnesis(db, email)
    except Exception:
        anamnesis_pendiente = False
else:
    st.session_state.pop("anamnesis_pendiente", None)

if anamnesis_pendiente and menu_actual != "Anamnesis":
    st.session_state["menu_radio"] = "Anamnesis"
    menu_actual = "Anamnesis"

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

    left_col, right_col = st.columns([3, 1], gap="large")
    with left_col:
        st.markdown(hero_html, unsafe_allow_html=True)

    with right_col:
        st.markdown(
            """
            <style>
            div[data-testid="stButton"][data-button-key="btn_logout"] button,
            div[data-testid="stButton"][data-button-key="btn_refresh"] button,
            div[data-testid="stButton"][data-button-key="btn_back_inicio"] button {
                padding: 0.35rem 0.9rem;
                font-size: 0.5rem;
            }
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown("<div class='top-actions'>", unsafe_allow_html=True)

        if st.button(
            "Cerrar sesión",
            key="btn_logout",
            type="secondary",
            help="Finaliza tu sesión actual",
            use_container_width=True,
        ):
            soft_logout()

        if st.button(
            "Actualizar",
            key="btn_refresh",
            type="secondary",
            help="Actualizar datos y refrescar cachés",
            use_container_width=True,
        ):
            st.cache_data.clear()
            st.rerun()

        if menu_actual != "Inicio":
            if st.button(
                "Inicio",
                key="btn_back_inicio",
                type="secondary",
                help="Volver a Inicio",
                use_container_width=True,
            ):
                _goto("Inicio")
        st.markdown("</div>", unsafe_allow_html=True)

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

elif opcion == "Anamnesis":
    render_anamnesis(db=db)

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

elif opcion == "Previsualizar Correos":
    if is_admin:
        ver_previsualizacion_correos()
    else:
        st.warning("Solo disponible para administradores.")
