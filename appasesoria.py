import streamlit as st

# ⚡️ 1) SIEMPRE primero:
st.set_page_config(page_title="Momentum", layout="wide")
from seccion_ejercicios import base_ejercicios
from vista_rutinas import ver_rutinas
from borrar_rutinas import borrar_rutinas
from ingresar_cliente_view import ingresar_cliente_o_video_o_ejercicio
from crear_planificaciones import crear_rutinas
from editar_rutinas import editar_rutinas
from crear_descarga import descarga_rutina
from reportes import ver_reportes

import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
import json   # 👈 importante para leer el secreto


# === INICIALIZAR FIREBASE desde Secrets ===
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    initialize_app(cred)

db = firestore.client()

# === Estado ===
if "correo" not in st.session_state:
    st.session_state.correo = ""
if "rol" not in st.session_state:
    st.session_state.rol = ""
# 👇 nuevos estados para el saludo
if "nombre_completo" not in st.session_state:
    st.session_state.nombre_completo = ""
if "primer_nombre" not in st.session_state:
    st.session_state.primer_nombre = ""

def extraer_primer_nombre(nombre: str, correo: str) -> str:
    """
    Devuelve el primer nombre a partir del campo 'nombre'.
    Si viene vacío o None, usa la parte antes de la @ del correo.
    """
    try:
        if nombre and isinstance(nombre, str):
            # divide por espacios y toma el primer token no vacío
            tokens = [t for t in nombre.strip().split() if t]
            if tokens:
                return tokens[0]
        # Fallback: parte del correo antes de la @, capitalizada
        user = (correo.split("@")[0] if correo else "Usuario").replace(".", " ").strip()
        return user.title()
    except Exception:
        return "Usuario"

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
            st.session_state.nombre_completo = usuario.get("nombre", "") or ""
            st.session_state.primer_nombre = extraer_primer_nombre(
                st.session_state.nombre_completo, st.session_state.correo
            )

            # Mensaje de bienvenida con saludo personalizado
            st.success(f"👋 Hola {st.session_state.primer_nombre}. Bienvenido, {st.session_state.rol.title()} ✅")
            st.rerun()
        else:
            st.error("Correo no encontrado. Verifica o contacta al administrador.")
    st.stop()

# === 2️⃣ Deportista: va directo a ver rutina (con saludo) ===
if st.session_state.rol == "deportista":
    if st.session_state.primer_nombre:
        st.markdown(f"### 👋 Hola {st.session_state.primer_nombre}")
    ver_rutinas()
    st.stop()

# === 3️⃣ Menu para admin/entrenador ===
st.sidebar.title("Menú principal")

opciones_menu = (
    "Inicio",
    "Ver Rutinas",
    "Crear Rutinas",
    "Ingresar Deportista o Video",
    "Borrar Rutinas",
    "Editar Rutinas",
    "Ejercicios",
    "Descarga Rutina",
    "Reportes"  # 👈 Nueva opción
)
opcion = st.sidebar.radio("Selecciona una opción:", opciones_menu)

if opcion == "Inicio":
    primer_nombre = st.session_state.primer_nombre or "Usuario"
    
    st.markdown(f"""
        <div style='text-align: center; margin-top: 20px;'>
            <img src='https://i.ibb.co/YL1HbLj/motion-logo.png' width='100'><br>
            <h1 style="color:white; font-weight:bold;">
                👋 Hola {primer_nombre}! — Bienvenido a Momentum
            </h1>
            <p style='font-size:18px; color:white;'>Selecciona una opción del menú para comenzar</p>
        </div>
        """, unsafe_allow_html=True)


elif opcion == "Ver Rutinas":
    ver_rutinas()
elif opcion == "Ingresar Deportista o Video":
    ingresar_cliente_o_video_o_ejercicio()
elif opcion == "Borrar Rutinas":
    borrar_rutinas()
elif opcion == "Crear Rutinas":
    crear_rutinas()
elif opcion == "Editar Rutinas":
    editar_rutinas()
elif opcion == "Descarga Rutina":
    descarga_rutina()
elif opcion == "Ejercicios":
    base_ejercicios()
elif opcion == "Reportes":
    ver_reportes()
