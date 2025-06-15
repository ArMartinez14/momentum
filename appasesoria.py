import streamlit as st

# ⚡️ 1) SIEMPRE primero:
st.set_page_config(page_title="Momentum", layout="wide")

from vista_rutinas import ver_rutinas
from borrar_rutinas import borrar_rutinas
from ingresar_cliente_view import ingresar_cliente_o_video
from crear_planificaciones import crear_rutinas

import firebase_admin
from firebase_admin import credentials, firestore

# === INICIALIZAR FIREBASE ===
if not firebase_admin._apps:
    cred = credentials.Certificate("aplicacion-asesorias-firebase-adminsdk-fbsvc-71e1560593.json")
    firebase_admin.initialize_app(cred)
db = firestore.client()

# === Estado ===
if "correo" not in st.session_state:
    st.session_state.correo = ""
if "rol" not in st.session_state:
    st.session_state.rol = ""

# === 1️⃣ LOGIN obligatorio ===
if not st.session_state.correo:
    st.title("Bienvenido a Momentum")
    correo_input = st.text_input("Por favor, ingresa tu correo:")

    if correo_input:
        docs = db.collection("usuarios").where("correo", "==", correo_input).limit(1).stream()
        usuario = None
        for doc in docs:
            usuario = doc.to_dict()
            break

        if usuario:
            st.session_state.correo = correo_input
            st.session_state.rol = usuario.get("rol", "").lower()
            st.success(f"Bienvenido, {st.session_state.rol.title()} ✅")
            st.rerun()
        else:
            st.error("Correo no encontrado. Verifica o contacta al administrador.")
    st.stop()

# === 2️⃣ Deportista: va directo a ver rutina ===
if st.session_state.rol == "deportista":
    ver_rutinas()
    st.stop()

# === 3️⃣ Menu para admin/entrenador ===
st.sidebar.title("Menú principal")

opciones_menu = ("Inicio", "Ver Rutinas", "Crear Rutinas", "Ingresar Deportista o Video", "Borrar Rutinas", "Editar Rutinas")
opcion = st.sidebar.radio("Selecciona una opción:", opciones_menu)

if opcion == "Inicio":
    st.markdown("""
        <div style='text-align: center; margin-top: 100px;'>
            <img src='https://i.ibb.co/YL1HbLj/motion-logo.png' width='100'>
            <h1>Bienvenido a Momentum</h1>
            <p style='font-size:18px;'>Selecciona una opción del menú para comenzar</p>
        </div>
        """, unsafe_allow_html=True)
elif opcion == "Ver Rutinas":
    ver_rutinas()
elif opcion == "Ingresar Deportista o Video":
    ingresar_cliente_o_video()
elif opcion == "Borrar Rutinas":
    borrar_rutinas()
elif opcion == "Crear Rutinas":
    crear_rutinas()
elif opcion == "Editar Rutinas":
    st.write("Aquí iría el módulo de editar rutinas.")
