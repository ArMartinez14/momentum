# app.py
import streamlit as st

# 1) SIEMPRE PRIMERO
st.set_page_config(page_title="Aplicación Asesorías", layout="wide")

# 2) Soft login (usa el módulo que ya probaste)
from soft_login_full import soft_login_barrier, soft_logout

# 3) Imports del resto de la app
import json
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app

from seccion_ejercicios import base_ejercicios
from vista_rutinas import ver_rutinas
from borrar_rutinas import borrar_rutinas
from ingresar_cliente_view import ingresar_cliente_o_video_o_ejercicio
from crear_planificaciones import crear_rutinas
from editar_rutinas import editar_rutinas
from crear_descarga import descarga_rutina
from reportes import ver_reportes
from admin_resumen import ver_resumen_entrenadores  # si no lo usas, puedes comentar

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

# 7) Barra lateral: estado + logout
email = st.session_state.get("correo", "")
rol = (st.session_state.get("rol") or "").lower()
st.sidebar.success(f"Conectado: {email} ({rol})")
if st.sidebar.button("Cerrar sesión", key="btn_logout"):
    soft_logout()

# 8) Enrutamiento según rol
if rol == "deportista":
    # Vista simplificada: solo puede ver rutinas
    st.title("🏋️ Tu Rutina")
    ver_rutinas()
    st.stop()

# 9) Menú para entrenador/admin
st.sidebar.title("Menú principal")
opciones_menu = [
    "Inicio",
    "Ver Rutinas",
    "Crear Rutinas",                 # 🔒 entrenador/admin
    "Ingresar Deportista o Ejercicio",
    "Borrar Rutinas",
    "Editar Rutinas",
    "Ejercicios",
    "Crear Descarga",
    "Reportes",
]

# Opción extra solo para admin/Administrador
is_admin = rol in ("admin", "administrador") or (
    email and st.secrets.get("ADMIN_EMAIL", "").lower() == email.lower()
)
if is_admin:
    opciones_menu.append("Resumen (Admin)")

opcion = st.sidebar.radio("Selecciona una opción:", opciones_menu, index=0)

# 10) Vistas
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
    ver_rutinas()

elif opcion == "Crear Rutinas":
    # 🔒 Solo entrenador/admin
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

elif opcion == "Resumen (Admin)":
    if is_admin:
        ver_resumen_entrenadores()
    else:
        st.warning("Solo disponible para administradores.")
