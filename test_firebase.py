import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import json

st.title("🔌 Prueba de conexión con Firebase")

try:
    # === Inicializar Firebase desde Secrets ===
    if not firebase_admin._apps:
        cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)

    db = firestore.client()

    # === Leer documentos de prueba ===
    docs = db.collection("usuarios").limit(5).stream()  # Cambia a una colección que exista
    st.success("✅ Conexión a Firebase exitosa")
    st.subheader("📄 Documentos encontrados:")
    for doc in docs:
        st.write(doc.id, doc.to_dict())

except Exception as e:
    st.error("❌ Error al conectar con Firebase")
    st.exception(e)
