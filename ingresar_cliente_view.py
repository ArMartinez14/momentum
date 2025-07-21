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
    return correo.replace('@', '_').replace('.', '_')

def normalizar_texto(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower().replace(" ", "_")

def ingresar_cliente_o_video_o_ejercicio():
    st.title("Panel de Administración")

    opcion = st.selectbox(
        "¿Qué deseas hacer?",
        ["Selecciona...", "Cliente Nuevo", "Video de Ejercicio", "Ejercicio Nuevo o Editar"],
        index=0
    )

    # ================= CLIENTE NUEVO =================
    if opcion == "Cliente Nuevo":
        nombre = st.text_input("Nombre del cliente:")
        correo = st.text_input("Correo del cliente:")
        rol = st.selectbox("Rol:", ["deportista", "entrenador", "admin"])

        if st.button("Guardar Cliente"):
            if nombre and correo and rol:
                doc_id = normalizar_id(correo)
                data = {"nombre": nombre, "correo": correo, "rol": rol}
                try:
                    db.collection("usuarios").document(doc_id).set(data)
                    st.success(f"✅ Cliente '{nombre}' guardado correctamente")
                except Exception as e:
                    st.error(f"❌ Error al guardar: {e}")
            else:
                st.warning("⚠️ Completa todos los campos.")

    # ================= EJERCICIO NUEVO O EDITAR =================
    elif opcion == "Ejercicio Nuevo o Editar":
        st.subheader("📌 Crear o Editar Ejercicio")

        # Cargar ejercicios ya existentes
        docs = db.collection("ejercicios").stream()
        ejercicios_disponibles = {doc.id: doc.to_dict().get("nombre", doc.id) for doc in docs}

        modo = st.radio("¿Qué quieres hacer?", ["Nuevo ejercicio", "Editar ejercicio existente"])

        if modo == "Editar ejercicio existente":
            seleccion = st.selectbox("Selecciona un ejercicio:", list(ejercicios_disponibles.values()))
            doc_id = [k for k, v in ejercicios_disponibles.items() if v == seleccion][0]
            doc_ref = db.collection("ejercicios").document(doc_id).get()
            datos = doc_ref.to_dict() if doc_ref.exists else {}
        else:
            datos = {}

        # === FORMULARIO ORDENADO Y CON AUTO-NOMBRE ===
        col1, col2 = st.columns(2)
        with col1:
            implemento = st.text_input("Implemento:", value=datos.get("implemento", ""), key="implemento")
        with col2:
            detalle = st.text_input("Detalle:", value=datos.get("detalle", ""), key="detalle")

        col3, col4 = st.columns(2)
        with col3:
            caracteristica = st.text_input("Característica:", value=datos.get("caracteristica", ""), key="caracteristica")
        with col4:
            grupo = st.text_input("Grupo muscular principal:", value=datos.get("grupo_muscular_principal", ""), key="grupo")

        patron = st.text_input("Patrón de movimiento:", value=datos.get("patron_de_movimiento", ""), key="patron")

        # === NOMBRE AUTOCOMPLETADO ===
        nombre = f"{implemento.strip()} {detalle.strip()}".strip()
        st.text_input("Nombre completo del ejercicio:", value=nombre, key="nombre", disabled=True)

        if st.button("Guardar Ejercicio"):
            if nombre:
                doc_id = normalizar_texto(nombre)
                datos_guardar = {
                    "nombre": nombre,
                    "caracteristica": caracteristica,
                    "detalle": detalle,
                    "grupo_muscular_principal": grupo,
                    "implemento": implemento,
                    "patron_de_movimiento": patron
                }
                try:
                    db.collection("ejercicios").document(doc_id).set(datos_guardar)
                    st.success(f"✅ Ejercicio '{nombre}' guardado correctamente")
                except Exception as e:
                    st.error(f"❌ Error al guardar: {e}")
            else:
                st.warning("⚠️ El campo 'nombre' es obligatorio.")

    else:
        st.info("👈 Selecciona una opción para comenzar.")
