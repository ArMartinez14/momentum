import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import unicodedata
import json

# === INICIALIZAR FIREBASE SOLO UNA VEZ ===
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

def normalizar_id(correo):
    """Convierte el correo en un ID válido para Firestore."""
    return correo.replace('@', '_').replace('.', '_')

def normalizar_texto(texto):
    """Normaliza texto para IDs de Firestore (para ejercicios)."""
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower().replace(" ", "_")

def ingresar_cliente_o_video():
    st.title("Ingresar Cliente o Video")

    # Opción principal: Cliente o Video
    opcion = st.selectbox(
        "¿Qué deseas agregar?",
        ["Selecciona...", "Cliente Nuevo", "Video de Ejercicio"],
        index=0
    )
    if opcion == "Cliente Nuevo":
        # Inicializar estados si no existen
        if "nombre_cliente" not in st.session_state:
            st.session_state["nombre_cliente"] = ""
        if "correo_cliente" not in st.session_state:
            st.session_state["correo_cliente"] = ""
        if "rol_cliente" not in st.session_state:
            st.session_state["rol_cliente"] = "deportista"

        nombre = st.text_input("Nombre del cliente:", key="nombre_cliente")
        correo = st.text_input("Correo del cliente:", key="correo_cliente")

        roles = ["deportista", "entrenador", "admin"]
        rol_actual = st.session_state.get("rol_cliente", "deportista")
        if rol_actual not in roles:
            rol_actual = "deportista"

        rol = st.selectbox(
            "Rol:",
            roles,
            index=roles.index(rol_actual),
            key="rol_cliente"
        )

        if st.button("Guardar Cliente"):
            if nombre and correo and rol:
                doc_id = normalizar_id(correo)
                data = {
                    "nombre": nombre,
                    "correo": correo,
                    "rol": rol
                }
                try:
                    db.collection("usuarios").document(doc_id).set(data)
                    st.success(f"✅ Cliente '{nombre}' guardado correctamente con ID '{doc_id}'")

                    # Limpiar estado
                    st.session_state["nombre_cliente"] = ""
                    st.session_state["correo_cliente"] = ""
                    st.session_state["rol_cliente"] = "deportista"

                    st.experimental_rerun()

                except Exception as e:
                    st.error(f"❌ Error al guardar: {e}")
            else:
                st.warning("⚠️ Por favor completa todos los campos.")


    # === Si elige Video ===
    elif opcion == "Video de Ejercicio":
        # Inicializar estados para Video si no existen
        for key in ["nombre_video", "url_video", "descripcion_video", "duracion_video"]:
            if key not in st.session_state:
                st.session_state[key] = ""

        nombre_ejercicio = st.text_input("Nombre del ejercicio:", key="nombre_video")
        url_video = st.text_input("URL del video:", key="url_video")
        descripcion = st.text_area("Descripción (opcional):", key="descripcion_video")

        if st.button("Guardar Video"):
            if nombre_ejercicio and url_video:
                doc_id = normalizar_texto(nombre_ejercicio)
                data = {
                    "nombre_ejercicio": nombre_ejercicio,
                    "url_video": url_video,
                    "descripcion": descripcion,
                }
                try:
                    db.collection("videos").document(doc_id).set(data)
                    st.success(f"✅ Video para '{nombre_ejercicio}' guardado correctamente con ID '{doc_id}'")

                    # Limpiar estados
                    st.session_state["nombre_video"] = ""
                    st.session_state["url_video"] = ""
                    st.session_state["descripcion_video"] = ""

                    st.experimental_rerun()

                except Exception as e:
                    st.error(f"❌ Error al guardar: {e}")
            else:
                st.warning("⚠️ Por favor completa nombre y URL del video.")

    else:
        st.info("👈 Selecciona una opción para comenzar.")
