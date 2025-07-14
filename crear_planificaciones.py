import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from herramientas import aplicar_progresion
from guardar_rutina_view import guardar_rutina
import json

# === INICIALIZAR FIREBASE SOLO UNA VEZ ===
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

def crear_rutinas():
    st.title("Crear nueva rutina")

    # === Cargar usuarios ===
    docs = db.collection("usuarios").stream()
    usuarios = [doc.to_dict() for doc in docs if doc.exists]
    nombres = sorted(set(u.get("nombre", "") for u in usuarios))

    nombre_input = st.text_input("Escribe el nombre del cliente:")
    coincidencias = [n for n in nombres if nombre_input.lower() in n.lower()]
    nombre_sel = st.selectbox("Selecciona de la lista:", coincidencias) if coincidencias else ""

    correo_auto = next((u.get("correo", "") for u in usuarios if u.get("nombre") == nombre_sel), "")
    correo = st.text_input("Correo del cliente:", value=correo_auto)

    fecha_inicio = st.date_input("Fecha de inicio de rutina:", value=datetime.today())
    semanas = st.number_input("Semanas de duración:", min_value=1, max_value=12, value=4)
    entrenador = st.text_input("Nombre del entrenador responsable:")

    st.markdown("---")
    st.subheader("Días de entrenamiento")

    dias = ["Día 1", "Día 2", "Día 3", "Día 4", "Día 5"]
    tabs = st.tabs(dias)

    columnas_tabla = [
        "Circuito", "Sección", "Ejercicio", "Series", "Repeticiones",
        "Peso", "Tiempo", "Velocidad", "RIR", "Tipo", "Video"
    ]

    progresion_activa = st.radio(
        "Progresión activa", ["Progresión 1", "Progresión 2", "Progresión 3"],
        horizontal=True, index=0
    )

    for i, tab in enumerate(tabs):
        with tab:
            dia_key = f"rutina_dia_{i + 1}"
            if dia_key not in st.session_state:
                st.session_state[dia_key] = [{k: "" for k in columnas_tabla} for _ in range(8)]

            st.write(f"Ejercicios para {dias[i]}")
            if st.button(f"Agregar fila en {dias[i]}", key=f"add_row_{i}"):
                st.session_state[dia_key].append({k: "" for k in columnas_tabla})

            for seccion in ["Warm Up", "Work Out"]:
                st.subheader(f"{seccion}" if seccion == "Warm Up" else f"{seccion}")

                key_seccion = f"{dia_key}_{seccion.replace(' ', '_')}"
                if key_seccion not in st.session_state:
                    st.session_state[key_seccion] = [{k: "" for k in columnas_tabla} for _ in range(6)]
                    for f in st.session_state[key_seccion]:
                        f["Sección"] = seccion

                for idx, fila in enumerate(st.session_state[key_seccion]):
                    # ✅ Título + checkbox a la derecha
                    cols_titulo = st.columns([9, 1, 1])
                    with cols_titulo[0]:
                        st.markdown(f"#### Ejercicio {idx + 1} - {fila.get('Ejercicio', '')}")
                   # with cols_titulo[1]:
                        #st.markdown("<div style='text-align: right; padding-top: 6px;'>Progresiones</div>", unsafe_allow_html=True)
                   # with cols_titulo[2]:
                        #mostrar_progresion = st.checkbox(" ", key=f"mostrar_prog_{i}_{seccion}_{idx}", label_visibility="collapsed")

                    # === Inputs principales ===
                    cols = st.columns(11)

                    # ✅ Clave única segura para evitar conflicto
                    key_entrenamiento = f"{i}_{seccion.replace(' ', '_')}_{idx}"

                    fila["Circuito"] = cols[0].selectbox(
                        "", ["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"],
                        index=["A", "B", "C", "D", "E", "F", "G", "H", "I", "J"].index(fila["Circuito"]) if fila["Circuito"] else 0,
                        key=f"circ_{key_entrenamiento}", label_visibility="collapsed"
                    )

                    fila["Ejercicio"] = cols[1].text_input(
                        "", value=fila["Ejercicio"],
                        key=f"ej_{key_entrenamiento}", label_visibility="collapsed", placeholder="Ejercicio"
                    )

                    fila["Series"] = cols[2].text_input(
                        "", value=fila["Series"],
                        key=f"ser_{key_entrenamiento}", label_visibility="collapsed", placeholder="Series"
                    )

                    fila["Peso"] = cols[3].text_input(
                        "", value=fila["Peso"],
                        key=f"peso_{key_entrenamiento}", label_visibility="collapsed", placeholder="Kg"
                    )

                    fila["RIR"] = cols[4].text_input(
                        "", value=fila["RIR"],
                        key=f"rir_{key_entrenamiento}", label_visibility="collapsed", placeholder="RIR"
                    )

                    # ✅ Selector de variable extra en misma fila
                    variables_extra = ["", "Tiempo", "Velocidad", "Repeticiones", "Series"]
                    fila["VariableExtra"] = cols[5].selectbox(
                        "", options=variables_extra,
                        index=variables_extra.index(fila.get("VariableExtra", "")),
                        key=f"extra_{key_entrenamiento}",
                        label_visibility="collapsed"
                    )

                    # === Inputs dinámicos según variable extra seleccionada ===

                    fila["Repeticiones"] = cols[6].text_input(
                        "", value=fila["Repeticiones"],
                        key=f"rep_{key_entrenamiento}",
                        label_visibility="collapsed", placeholder="Reps"
                    ) if fila.get("VariableExtra") == "Repeticiones" else fila.get("Repeticiones", "")

                    fila["Tiempo"] = cols[7].text_input(
                        "", value=fila["Tiempo"],
                        key=f"tiempo_{key_entrenamiento}",
                        label_visibility="collapsed", placeholder="Seg"
                    ) if fila.get("VariableExtra") == "Tiempo" else fila.get("Tiempo", "")

                    fila["Velocidad"] = cols[8].text_input(
                        "", value=fila["Velocidad"],
                        key=f"vel_{key_entrenamiento}",
                        label_visibility="collapsed", placeholder="Vel"
                    ) if fila.get("VariableExtra") == "Velocidad" else fila.get("Velocidad", "")

                    # Ocultar tipo pero mantenerlo en estructura
                    fila["Tipo"] = fila.get("Tipo", "")

                    # ✅ Mostrar checkboxes en la misma fila
                    # ✅ Fila con checkboxes alineados a la derecha
                    cbox_cols = st.columns([6, 1, 1])  # espacio vacío + 2 columnas para checkboxes

                    with cbox_cols[1]:
                        mostrar_video = st.checkbox("Link de video", key=f"video_check_{key_entrenamiento}")

                    with cbox_cols[2]:
                        mostrar_progresion = st.checkbox("Progresiones", key=f"mostrar_prog_{key_entrenamiento}")

                    # === VIDEO ===
                    if mostrar_video:
                        fila["Video"] = st.text_input(
                            "Link de video (opcional)", value=fila.get("Video", ""),
                            key=f"video_input_{key_entrenamiento}"
                        )
                    else:
                        fila["Video"] = fila.get("Video", "")

                    # === PROGRESIONES ===
                    if mostrar_progresion:
                        st.markdown("#### Progresiones activas")
                        pcols = st.columns(4)
                        for p in range(1, 4):
                            if progresion_activa == f"Progresión {p}":
                                fila[f"Variable_{p}"] = pcols[0].selectbox(
                                    f"Variable {p}", ["", "peso", "velocidad", "tiempo", "rir", "series", "repeticiones"],
                                    index=0 if not fila.get(f"Variable_{p}") else ["", "peso", "velocidad", "tiempo", "rir", "series", "repeticiones"].index(fila[f"Variable_{p}"]),
                                    key=f"var{p}_{key_entrenamiento}"
                                )
                                fila[f"Cantidad_{p}"] = pcols[1].text_input(
                                    f"Cantidad {p}", value=fila.get(f"Cantidad_{p}", ""), key=f"cant{p}_{key_entrenamiento}"
                                )
                                fila[f"Operacion_{p}"] = pcols[2].selectbox(
                                    f"Operación {p}", ["", "multiplicacion", "division", "suma", "resta"],
                                    index=0 if not fila.get(f"Operacion_{p}") else ["", "multiplicacion", "division", "suma", "resta"].index(fila[f"Operacion_{p}"]),
                                    key=f"ope{p}_{key_entrenamiento}"
                                )
                                fila[f"Semanas_{p}"] = pcols[3].text_input(
                                    f"Semanas {p}", value=fila.get(f"Semanas_{p}", ""), key=f"sem{p}_{key_entrenamiento}"
                                )
                    else:
                        for p in range(1, 4):
                            fila[f"Variable_{p}"] = fila.get(f"Variable_{p}", "")
                            fila[f"Cantidad_{p}"] = fila.get(f"Cantidad_{p}", "")
                            fila[f"Operacion_{p}"] = fila.get(f"Operacion_{p}", "")
                            fila[f"Semanas_{p}"] = fila.get(f"Semanas_{p}", "")

    st.markdown("---")


    # ✅ NUEVO BOTÓN: Previsualizar rutina
    if st.button("🔍 Previsualizar rutina"):
        st.subheader("📅 Previsualización de todas las semanas con progresiones aplicadas")

        for semana_idx in range(1, int(semanas) + 1):
            with st.expander(f"Semana {semana_idx}"):
                for i, dia_nombre in enumerate(dias):
                    dia_key = f"rutina_dia_{i + 1}"
                    ejercicios = st.session_state.get(dia_key, [])
                    if not ejercicios:
                        continue

                    st.write(f"**{dia_nombre}**")

                    tabla = []
                    for ejercicio in ejercicios:
                        ejercicio_mod = ejercicio.copy()

                        # Determinar sección por circuito
                        circuito = ejercicio.get("Circuito", "")
                        ejercicio_mod["Sección"] = "Warm Up" if circuito in ["A", "B", "C"] else "Work Out"

                        # Aplicar progresiones
                        for p in range(1, 4):
                            variable = ejercicio.get(f"Variable_{p}", "").strip().lower()
                            cantidad = ejercicio.get(f"Cantidad_{p}", "")
                            operacion = ejercicio.get(f"Operacion_{p}", "").strip().lower()
                            semanas_txt = ejercicio.get(f"Semanas_{p}", "")

                            if variable and operacion and cantidad:
                                valor_base = ejercicio_mod.get(variable.capitalize(), "")
                                if valor_base:
                                    valor_actual = valor_base
                                    try:
                                        semanas_aplicar = [int(s.strip()) for s in semanas_txt.split(",") if s.strip().isdigit()]
                                    except:
                                        semanas_aplicar = []

                                    for s in range(2, semana_idx + 1):
                                        if s in semanas_aplicar:
                                            valor_actual = aplicar_progresion(valor_actual, float(cantidad), operacion)
                                    ejercicio_mod[variable.capitalize()] = valor_actual

                        tabla.append({
                            "bloque": ejercicio_mod["Sección"],
                            "circuito": ejercicio_mod["Circuito"],
                            "ejercicio": ejercicio_mod["Ejercicio"],
                            "series": ejercicio_mod["Series"],
                            "repeticiones": ejercicio_mod["Repeticiones"],
                            "peso": ejercicio_mod["Peso"],
                            "tiempo": ejercicio_mod["Tiempo"],
                            "velocidad": ejercicio_mod["Velocidad"],
                            "rir": ejercicio_mod["RIR"],
                            "tipo": ejercicio_mod["Tipo"]
                        })

                    st.dataframe(tabla, use_container_width=True)

    if st.button("Guardar Rutina"):
        if nombre_sel and correo and entrenador:
            guardar_rutina(nombre_sel, correo, entrenador, fecha_inicio, semanas, dias)
        else:
            st.warning("⚠️ Completa nombre, correo y entrenador antes de guardar.")
