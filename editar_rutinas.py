import streamlit as st
from firebase_admin import credentials, firestore
from datetime import datetime
import firebase_admin
import json

# === INICIALIZAR FIREBASE ===
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

def editar_rutinas():
    st.title("✏️ Editar Rutina y Aplicar Cambios a Futuras Semanas")

    # === Buscar clientes desde la colección ===
    docs = db.collection("rutinas_semanales").stream()
    clientes_dict = {}
    for doc in docs:
        data = doc.to_dict()
        nombre = data.get("cliente")
        correo = data.get("correo")
        if nombre and correo:
            clientes_dict[nombre] = correo

    nombres_clientes = sorted(clientes_dict.keys())
    nombre_sel = st.selectbox("Selecciona el cliente:", nombres_clientes)
    if not nombre_sel:
        return

    correo = clientes_dict[nombre_sel]


    # === Obtener semanas disponibles ===
    docs = db.collection("rutinas_semanales") \
        .where("correo", "==", correo) \
        .stream()

    semanas_dict = {}
    for doc in docs:
        data = doc.to_dict()
        fecha_lunes = data.get("fecha_lunes")
        if fecha_lunes:
            semanas_dict[fecha_lunes] = doc.id

    semanas = sorted(semanas_dict.keys())
    semana_sel = st.selectbox("Selecciona la semana a editar:", semanas)
    if not semana_sel:
        return

    doc_id_semana = semanas_dict[semana_sel]
    doc_data = db.collection("rutinas_semanales").document(doc_id_semana).get().to_dict()
    rutina = doc_data.get("rutina", {})

    dias_disponibles = sorted(rutina.keys(), key=lambda x: int(x))
    dia_sel = st.selectbox("Selecciona el día a editar:", dias_disponibles, format_func=lambda x: f"Día {x}")
    if not dia_sel:
        return

    # === Obtener todos los bloques únicos en ese día ===
    ejercicios_dia = rutina.get(dia_sel, {})
    bloques_disponibles = list(set(ej.get("bloque", "") for ej in ejercicios_dia))
    bloque_sel = st.selectbox("Selecciona el bloque:", bloques_disponibles)
    if not bloque_sel:
        return

    # === Mostrar ejercicios del bloque seleccionado ===
    st.markdown(f"### 📝 Editar ejercicios del Día {dia_sel} - Bloque {bloque_sel}")
    ejercicios_editados = []

    for idx, ej in enumerate(ejercicios_dia):
        if ej.get("bloque", "") != bloque_sel:
            continue

        st.markdown(f"**Ejercicio {idx + 1}**")
        ejercicio = ej.copy()

        cols = st.columns([4, 1, 2, 2, 1])
        ejercicio["ejercicio"] = cols[0].text_input("Ejercicio", value=ej.get("ejercicio", ""), key=f"ej_{idx}_nombre")
        ejercicio["series"] = cols[1].text_input("Series", value=ej.get("series", ""), key=f"ej_{idx}_series")
        ejercicio["repeticiones"] = cols[2].text_input("Reps (min o máx)", value=ej.get("repeticiones", ""), key=f"ej_{idx}_reps")
        ejercicio["peso"] = cols[3].text_input("Peso", value=ej.get("peso", ""), key=f"ej_{idx}_peso")
        ejercicio["rir"] = cols[4].text_input("RIR", value=ej.get("rir", ""), key=f"ej_{idx}_rir")

        col_desc, col_com = st.columns([2, 3])
        ejercicio["descripcion"] = col_desc.text_input("Descripción", value=ej.get("descripcion", ""), key=f"ej_{idx}_descripcion")
        ejercicio["comentario"] = col_com.text_input("Comentario", value=ej.get("comentario", ""), key=f"ej_{idx}_comentario")

        ejercicio["bloque"] = bloque_sel
        ejercicios_editados.append((idx, ejercicio))
        st.markdown("---")


    if st.button("✅ Aplicar cambios a este bloque y futuras semanas"):
        try:
            fecha_sel = datetime.strptime(semana_sel, "%Y-%m-%d")
        except ValueError:
            st.error("Formato de fecha inválido")
            return

        docs_futuras = db.collection("rutinas_semanales") \
            .where("correo", "==", correo) \
            .stream()

        total_actualizados = 0

        for doc in docs_futuras:
            data = doc.to_dict()
            fecha_doc_str = data.get("fecha_lunes", "")
            try:
                fecha_doc = datetime.strptime(fecha_doc_str, "%Y-%m-%d")
                if fecha_doc >= fecha_sel:
                    rutina_futura = data.get("rutina", {})
                    if dia_sel in rutina_futura:
                        dia_data = rutina_futura[dia_sel]
                        for idx, nuevo_ejercicio in ejercicios_editados:
                            if idx in dia_data and dia_data[idx].get("bloque", "") == bloque_sel:
                                dia_data[idx] = nuevo_ejercicio
                        db.collection("rutinas_semanales").document(doc.id).update({"rutina": rutina_futura})
                        total_actualizados += 1
            except:
                continue

        st.success(f"✅ Cambios aplicados en {total_actualizados} semana(s).")

