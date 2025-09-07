# app.py
import streamlit as st

# 1) SIEMPRE PRIMERO
st.set_page_config(page_title="Aplicación Asesorías", layout="wide")

# 2) Soft login
from soft_login_full import soft_login_barrier, soft_logout

# 3) Firebase
import json
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app

# 4) Router por rol
from rol_router import set_role_adapter, run_feature, can, ROL_ADMIN, ROL_ENTRENADOR, ROL_DEPORTISTA

# 5) Registrar implementaciones de features de esta app (IMPORTANTE)
#    Este import realiza el registro (@exponer) de todas las features.
import funciones_asesoria  # noqa: F401

# ===== Estilos (opcional) =====
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
</style>
""", unsafe_allow_html=True)

# ===== Firebase (una sola vez) =====
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    initialize_app(cred)
db = firestore.client()

# ===== Soft login barrier =====
# Nota: si en tu flujo el login no requiere roles para mostrar la home, deja required_roles=None
if not soft_login_barrier(titulo="Bienvenido a Momentum", required_roles=None):
    st.stop()

# ===== Estado lateral + logout =====
email = st.session_state.get("correo", "")
rol = (st.session_state.get("rol") or "").lower()
st.sidebar.success(f"Conectado: {email} ({rol})")
if st.sidebar.button("Cerrar sesión", key="btn_logout"):
    soft_logout()

# ===== Conectar el router a tu rol actual =====
def _resolver_rol_actual():
    return (st.session_state.get("rol") or "").lower()
set_role_adapter(_resolver_rol_actual)

# ===== Helper para ejecutar features con captura de errores =====
def run_safe(feature_name: str):
    try:
        run_feature(feature_name)
    except Exception as e:
        st.error(f"Ocurrió un error al cargar la sección: {feature_name}")
        st.exception(e)

# ===== Home si es deportista (directo a ver rutinas) =====
if rol == ROL_DEPORTISTA:
    st.title("🏋️ Tu Rutina")
    run_safe("ver_rutinas")
    st.stop()

# ===== Menú dinámico según permisos =====
st.sidebar.title("Menú principal")

# Mapeo de etiquetas -> feature
MENU_ITEMS = [
    ("Inicio", None),
    ("Ver Rutinas", "ver_rutinas"),
    ("Crear Rutinas", "crear_rutinas"),
    ("Ingresar Deportista o Ejercicio", "gestionar_clientes"),
    ("Borrar Rutinas", None),             # sigue “local” (si quieres, llévalo al router)
    ("Editar Rutinas", "editar_rutinas"),
    ("Ejercicios", "ejercicios"),
    ("Crear Descarga", "descargar_rutinas"),
    ("Reportes", "ver_reportes"),
    ("Resumen (Admin)", "resumen_admin"),
]

# Filtrar items por permisos del rol actual (si tiene feature/capability)
def visible_for_role(label: str, feature: str | None) -> bool:
    if feature is None:
        return True
    return can(rol, feature)

menu_labels = [lbl for (lbl, feat) in MENU_ITEMS if visible_for_role(lbl, feat)]
opcion = st.sidebar.radio("Selecciona una opción:", menu_labels, index=0)

# ===== Render según selección =====
if opcion == "Inicio":
    primer_nombre = st.session_state.get("primer_nombre") or (
        email.split("@")[0].title() if email else "Usuario"
    )
    st.markdown(f"""
        <div style='text-align: center; margin-top: 20px;'>
            <img src='https://i.ibb.co/YL1HbLj/motion-logo.png' width='100' alt='Momentum Logo'><br>
            <h1 style="font-weight: 800; margin: 8px 0;">
                👋 Hola {primer_nombre}! — Bienvenido a Momentum
            </h1>
            <p style='font-size:18px; margin: 0;'>Selecciona una opción del menú para comenzar</p>
        </div>
        """, unsafe_allow_html=True)

elif opcion == "Ver Rutinas":
    run_safe("ver_rutinas")

elif opcion == "Crear Rutinas":
    run_safe("crear_rutinas")

elif opcion == "Ingresar Deportista o Ejercicio":
    run_safe("gestionar_clientes")

elif opcion == "Borrar Rutinas":
    # “Local”: no pasa por router aún
    from borrar_rutinas import borrar_rutinas
    try:
        borrar_rutinas()
    except Exception as e:
        st.error("No se pudo cargar Borrar Rutinas.")
        st.exception(e)

elif opcion == "Editar Rutinas":
    run_safe("editar_rutinas")

elif opcion == "Ejercicios":
    run_safe("ejercicios")

elif opcion == "Crear Descarga":
    run_safe("descargar_rutinas")

elif opcion == "Reportes":
    run_safe("ver_reportes")

elif opcion == "Resumen (Admin)":
    run_safe("resumen_admin")
