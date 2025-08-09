import streamlit as st
from firebase_admin import credentials, firestore
from datetime import datetime
import firebase_admin
import json
import copy

# === INICIALIZAR FIREBASE ===
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

def descarga_rutina():
    st.title("📉 Crear Rutina de Descarga")

    # === Buscar clientes ===
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

    # === Obtener última semana ===
    docs = db.collection("rutinas_semanales").where("correo", "==", correo).stream()
    semanas_dict = {}
    for doc in docs:
        data = doc.to_dict()
        fecha_lunes = data.get("fecha_lunes")
        if fecha_lunes:
            semanas_dict[fecha_lunes] = doc.id

    if not semanas_dict:
        st.warning("❌ No hay rutinas para este cliente.")
        return

    ultima_semana = max(semanas_dict.keys())
    doc_id_semana = semanas_dict[ultima_semana]
    st.info(f"Última semana encontrada: **{ultima_semana}**")

    # === Obtener rutina base ===
    doc_data = db.collection("rutinas_semanales").document(doc_id_semana).get().to_dict()
    rutina_original = doc_data.get("rutina", {})
    rutina_modificada = copy.deepcopy(rutina_original)

    # === Selección modalidad ===
    modalidad = st.selectbox("Selecciona modalidad de descarga:", [
        "Mantener series/reps y bajar 20% peso",
        "Mantener pesos y bajar 1 serie y 3 reps (min y max)",
        "Elección manual"
    ])

    # === Aplicar ajustes automáticos ===
    if modalidad == "Mantener series/reps y bajar 20% peso":
        for dia, ejercicios in rutina_modificada.items():
            for ej in ejercicios:
                try:
                    if ej.get("peso", "").strip() != "":
                        ej["peso"] = str(round(float(ej["peso"]) * 0.8, 1))
                except:
                    pass

    elif modalidad == "Mantener pesos y bajar 1 serie y 3 reps (min y max)":
        for dia, ejercicios in rutina_modificada.items():
            for ej in ejercicios:
                try:
                    if ej.get("series", "").isdigit():
                        ej["series"] = str(max(1, int(ej["series"]) - 1))
                except:
                    pass
                # Reps puede ser min, max o un solo valor
                try:
                    if "-" in ej.get("repeticiones", ""):
                        min_r, max_r = ej["repeticiones"].split("-")
                        min_r = str(max(0, int(min_r) - 3))
                        max_r = str(max(0, int(max_r) - 3))
                        ej["repeticiones"] = f"{min_r}-{max_r}"
                    elif ej.get("repeticiones", "").isdigit():
                        ej["repeticiones"] = str(max(0, int(ej["repeticiones"]) - 3))
                except:
                    pass

    elif modalidad == "Elección manual":
        dias_disponibles = sorted(rutina_modificada.keys(), key=lambda x: int(x))
        dia_sel = st.selectbox("Selecciona el día a editar:", dias_disponibles, format_func=lambda x: f"Día {x}")
        ejercicios_dia = rutina_modificada.get(dia_sel, {})
        bloques_disponibles = list(set(ej.get("bloque", "") for ej in ejercicios_dia))
        bloque_sel = st.selectbox("Selecciona el bloque:", bloques_disponibles)
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
            ejercicios_editados.append((idx, ejercicio))
        for idx, nuevo in ejercicios_editados:
            rutina_modificada[dia_sel][idx] = nuevo

    # === Previsualización ===
    st.subheader("👀 Previsualización de la rutina de descarga")
    for dia, ejercicios in rutina_modificada.items():
        st.markdown(f"**📅 Día {dia}**")
        for ej in ejercicios:
            st.write(f"{ej.get('ejercicio','')} | Series: {ej.get('series','')} | Reps: {ej.get('repeticiones','')} | Peso: {ej.get('peso','')} | RIR: {ej.get('rir','')}")

    # === Guardar ===
    nueva_fecha = st.date_input("Fecha de inicio de rutina de descarga", datetime.now()).strftime("%Y-%m-%d")
    if st.button("💾 Guardar rutina de descarga"):
        nuevo_doc = doc_data.copy()
        nuevo_doc["fecha_lunes"] = nueva_fecha
        nuevo_doc["rutina"] = rutina_modificada
        nuevo_doc["tipo"] = "descarga"
        nuevo_doc_id = f"{correo.replace('@', '_').replace('.', '_')}_{nueva_fecha.replace('-', '_')}"
        db.collection("rutinas_semanales").document(nuevo_doc_id).set(nuevo_doc)
        st.success(f"✅ Rutina de descarga creada para la semana {nueva_fecha}")
