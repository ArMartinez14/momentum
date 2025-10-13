import csv
import firebase_admin
from firebase_admin import credentials, firestore
import unicodedata
import json
import streamlit as st

# 🔤 Normalizar claves
def normalizar_campo(texto):
    if not texto:
        return ""
    texto = texto.strip().lower()
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto.replace(" ", "_").replace("-", "_")

# 🔤 Crear ID a partir del nombre
def formatear_id(texto):
    return normalizar_campo(texto).replace("°", "")

# 🔐 Inicializar Firebase (usando Streamlit secrets)
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# 📄 Leer archivo CSV
with open("MOMENTUM.xlsx - APP-2.csv", encoding="utf-8-sig") as archivo:
    lector = csv.DictReader(archivo)
    ejercicios_raw = list(lector)

# 🔁 Procesar y subir cada fila
subidos = 0
omitidos = 0
for fila in ejercicios_raw:
    implemento = fila.get("Implemento", "").strip()
    detalle = fila.get("Detalle", "").strip()

    # Validar que al menos uno esté presente
    if not implemento and not detalle:
        print("❌ Fila omitida: sin implemento ni detalle")
        omitidos += 1
        continue

    # Construir nombre combinando implemento y detalle
    if implemento:
        nombre = f"{implemento} {detalle}".strip()
    else:
        nombre = detalle

    doc_id = formatear_id(nombre)

    # Verificar si ya existe en Firebase
    doc_ref = db.collection("ejercicios").document(doc_id)
    if doc_ref.get().exists:
        print(f"⚠️ Ya existe: {nombre}")
        omitidos += 1
        continue

    # Armar documento final con claves normalizadas y valores originales
    fila_formateada = {}
    for clave_original, valor in fila.items():
        clave_normalizada = normalizar_campo(clave_original)
        fila_formateada[clave_normalizada] = valor

    fila_formateada["nombre"] = nombre  # agregar campo 'nombre' final

    doc_ref.set(fila_formateada)
    print(f"✅ Subido: {nombre}")
    subidos += 1

print(f"\n✅ Total subidos: {subidos} | ⛔️ Omitidos: {omitidos}")
