import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime
from herramientas import aplicar_progresion
from guardar_rutina_view import guardar_rutina, aplicar_progresion_rango
import json
import pandas as pd
import matplotlib.pyplot as plt
import json
import firebase_admin
from firebase_admin import credentials, firestore
import streamlit as st
import unicodedata
from datetime import date, timedelta

def proximo_lunes(base: date | None = None) -> date:
    base = base or date.today()
    # 0=lunes ... 6=domingo
    dias = (7 - base.weekday()) % 7
    if dias == 0:
        dias = 7  # si hoy es lunes, ir al lunes de la semana siguiente
    return base + timedelta(days=dias)

def normalizar_texto(texto):
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFD", texto)
    texto = texto.encode("ascii", "ignore").decode("utf-8")
    return texto


# === INICIALIZAR FIREBASE SOLO UNA VEZ ===
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

# Solo una vez, al inicio del archivo (después de cargar Firebase)
@st.cache_data(show_spinner=False)
def cargar_ejercicios():
    docs = db.collection("ejercicios").stream()
    return {doc.to_dict().get("nombre", ""): doc.to_dict() for doc in docs if doc.exists}

ejercicios_dict = cargar_ejercicios()

# === Cargar usuarios ===
@st.cache_data(show_spinner=False)
def cargar_usuarios():
    docs = db.collection("usuarios").stream()
    return [doc.to_dict() for doc in docs if doc.exists]


def crear_rutinas():
    st.title("Crear nueva rutina")
    cols = st.columns([5, 1])
    with cols[1]:
        if st.button("🔄", help="Recargar ejercicios"):
            st.cache_data.clear()

    ejercicios_dict = cargar_ejercicios()



    usuarios = cargar_usuarios()

    nombres = sorted(set(u.get("nombre", "") for u in usuarios))

    correos_entrenadores = sorted([
        u["correo"] for u in usuarios if u.get("rol", "").lower() in ["entrenador", "admin", "administrador"]
    ])


    nombre_input = st.text_input("Escribe el nombre del cliente:")
    coincidencias = [n for n in nombres if nombre_input.lower() in n.lower()]
    nombre_sel = st.selectbox("Selecciona de la lista:", coincidencias) if coincidencias else ""

    correo_auto = next((u.get("correo", "") for u in usuarios if u.get("nombre") == nombre_sel), "")
    correo = st.text_input("Correo del cliente:", value=correo_auto)

    # Valor por defecto: lunes de la semana siguiente
    valor_defecto = proximo_lunes()

    sel = st.date_input(
        "Fecha de inicio de rutina:",
        value=valor_defecto,
        help="Solo se usan lunes. Si eliges otro día, se ajustará automáticamente al lunes de esa semana."
    )

    # Forzar lunes: si no es lunes, ajustamos al lunes de esa semana
    if sel.weekday() != 0:
        fecha_inicio = sel - timedelta(days=sel.weekday())  # lunes de esa semana
        st.info(f"🔁 Ajustado automáticamente al lunes {fecha_inicio.isoformat()}.")
    else:
        fecha_inicio = sel
    semanas = st.number_input("Semanas de duración:", min_value=1, max_value=12, value=4)
    # ⬇️ Traer correo del login desde Home
    correo_login = (st.session_state.get("correo") or "").strip().lower()

    # Mostrar con el estilo de un input, pero deshabilitado
    entrenador = st.text_input(
        "Correo del entrenador responsable:",
        value=correo_login,
        disabled=True
    )

    st.markdown("---")
    st.subheader("Días de entrenamiento")

    dias = ["Día 1", "Día 2", "Día 3", "Día 4", "Día 5"]
    tabs = st.tabs(dias)

    columnas_tabla = [
    "Circuito", "Sección", "Ejercicio", "Detalle", "Series", "Repeticiones",
    "Peso", "Tiempo", "Velocidad", "RIR", "Tipo", "Video"
]

    progresion_activa = st.radio(
        "Progresión activa", ["Progresión 1", "Progresión 2", "Progresión 3"],
        horizontal=True, index=0
    )

    for i, tab in enumerate(tabs):
        with tab:
            with st.expander(f"Ejercicios para {dias[i]}", expanded=(i == 0)):
                dia_key = f"rutina_dia_{i + 1}"

                if dia_key not in st.session_state:
                    st.session_state[dia_key] = [{k: "" for k in columnas_tabla} for _ in range(2)]
                # 👇 aquí va todo el contenido restante de ese día

            
            for seccion in ["Warm Up", "Work Out"]:
                st.subheader(f"{seccion}" if seccion == "Warm Up" else f"{seccion}")
                # === Botón para agregar fila en la sección correspondiente
                key_seccion = f"{dia_key}_{seccion.replace(' ', '_')}"

                if st.button(f"➕ Agregar fila a {seccion} ({dias[i]})", key=f"add_row_{i}_{seccion}"):
                    nueva_fila = {k: "" for k in columnas_tabla}
                    nueva_fila["Sección"] = seccion

                    if key_seccion not in st.session_state:
                        st.session_state[key_seccion] = []

                    st.session_state[key_seccion].append(nueva_fila)

                if key_seccion not in st.session_state:
                    st.session_state[key_seccion] = [{k: "" for k in columnas_tabla} for _ in range(6)]
                    for f in st.session_state[key_seccion]:
                        f["Sección"] = seccion

                # === Definir una vez: 10 columnas, header centrado ===
                col_sizes = [0.9, 2.0, 3.0, 2.0, 0.8, 1.6, 1.0, 0.8, 1.2, 0.8]
                headers = [
                    "Circuito", "Buscar Ejercicio", "Ejercicio", "Detalle",
                    "Series", "Repeticiones", "Peso", "RIR", "Progresión", "Copiar"
                ]

                header_cols = st.columns(col_sizes)
                for c, title in zip(header_cols, headers):
                    c.markdown(
                        f"<div style='text-align:center; white-space:nowrap'><b>{title}</b></div>",
                        unsafe_allow_html=True
                    )

                # === Fila de inputs por ejercicio ===
                for idx, fila in enumerate(st.session_state[key_seccion]):
                    key_entrenamiento = f"{i}_{seccion.replace(' ', '_')}_{idx}"
                    cols = st.columns(col_sizes)

                    # 0) Circuito
                    fila["Circuito"] = cols[0].selectbox(
                        "", ["A", "B", "C", "D", "E", "F"],
                        index=(["A","B","C","D","E","F"].index(fila["Circuito"]) if fila.get("Circuito") else 0),
                        key=f"circ_{key_entrenamiento}", label_visibility="collapsed"
                    )

                    # 1) Buscar Ejercicio
                    if seccion == "Work Out":
                        palabra_busqueda = cols[1].text_input(
                            "", value=fila.get("BuscarEjercicio", ""),
                            key=f"buscar_{key_entrenamiento}", label_visibility="collapsed", placeholder=""
                        )
                        fila["BuscarEjercicio"] = palabra_busqueda

                        # Filtrado
                        ejercicios_encontrados = []
                        try:
                            if palabra_busqueda.strip():
                                palabras = palabra_busqueda.lower().strip().split()
                                ejercicios_encontrados = [
                                    nombre for nombre in ejercicios_dict.keys()
                                    if all(p in nombre.lower() for p in palabras)
                                ]
                        except Exception as e:
                            st.warning(f"Error al buscar ejercicios: {e}")
                            ejercicios_encontrados = []

                        # 2) Ejercicio (selectbox)
                        seleccionado = cols[2].selectbox(
                            "", ejercicios_encontrados if ejercicios_encontrados else ["(sin resultados)"],
                            key=f"selectbox_{key_entrenamiento}", label_visibility="collapsed"
                        )
                        if seleccionado != "(sin resultados)":
                            fila["Ejercicio"] = seleccionado
                            if not fila.get("Video"):
                                video_auto = ejercicios_dict.get(seleccionado, {}).get("video", "").strip()
                                if video_auto:
                                    fila["Video"] = video_auto
                        else:
                            fila["Ejercicio"] = fila.get("Ejercicio", "")
                    else:
                        # Warm Up: mantenemos la columna Buscar vacía para no romper la grilla
                        cols[1].markdown("&nbsp;", unsafe_allow_html=True)
                        fila["Ejercicio"] = cols[2].text_input(
                            "", value=fila.get("Ejercicio", ""),
                            key=f"ej_{key_entrenamiento}", label_visibility="collapsed", placeholder="Ejercicio"
                        )

                    # 3) Detalle
                    fila["Detalle"] = cols[3].text_input(
                        "", value=fila.get("Detalle", ""),
                        key=f"detalle_{key_entrenamiento}", label_visibility="collapsed", placeholder=""
                    )

                    # 4) Series
                    fila["Series"] = cols[4].text_input(
                        "", value=fila.get("Series", ""),
                        key=f"ser_{key_entrenamiento}", label_visibility="collapsed", placeholder=""
                    )

                    # 5) Repeticiones (Min/Max juntos)
                    min_max = cols[5].columns([1, 1])
                    reps_min = min_max[0].text_input(
                        "", value=str(fila.get("RepsMin", "")),
                        key=f"repsmin_{key_entrenamiento}", label_visibility="collapsed", placeholder="Min"
                    )
                    reps_max = min_max[1].text_input(
                        "", value=str(fila.get("RepsMax", "")),
                        key=f"repsmax_{key_entrenamiento}", label_visibility="collapsed", placeholder="Max"
                    )
                    try: fila["RepsMin"] = int(reps_min)
                    except: fila["RepsMin"] = ""
                    try: fila["RepsMax"] = int(reps_max)
                    except: fila["RepsMax"] = ""

                    # === Obtener pesos desde la colección implementos ===
                    pesos_disponibles = []
                    usar_text_input = False  # Por defecto usamos selectbox si hay pesos

                    try:
                        nombre_ejercicio = fila.get("Ejercicio", "")
                        if nombre_ejercicio and nombre_ejercicio in ejercicios_dict:
                            id_implemento = ejercicios_dict[nombre_ejercicio].get("id_implemento", "")

                            if id_implemento == "1":
                                usar_text_input = True
                            elif id_implemento:
                                doc_impl = db.collection("implementos").document(id_implemento).get()
                                if doc_impl.exists:
                                    pesos_disponibles = doc_impl.to_dict().get("pesos", [])
                                    usar_text_input = not pesos_disponibles  # True si no hay pesos
                                else:
                                    usar_text_input = True
                            else:
                                usar_text_input = True
                        else:
                            usar_text_input = True
                    except Exception as e:
                        st.warning(f"Error al cargar pesos del implemento: {e}")
                        usar_text_input = True
                     # === Mostrar input de peso ===
                    if not usar_text_input:
                        fila["Peso"] = cols[6].selectbox(
                            "", options=pesos_disponibles,
                            index=pesos_disponibles.index(fila.get("Peso")) if fila.get("Peso") in pesos_disponibles else 0,
                            key=f"peso_{key_entrenamiento}", label_visibility="collapsed"
                        )
                    else:
                        fila["Peso"] = cols[6].text_input(
                            "", value=fila.get("Peso", ""),
                            key=f"peso_{key_entrenamiento}", label_visibility="collapsed", placeholder="Kg"
                        )

                    # 7) RIR
                    fila["RIR"] = cols[7].text_input(
                        "", value=fila.get("RIR", ""),
                        key=f"rir_{key_entrenamiento}", label_visibility="collapsed", placeholder=""
                    )

                    # 8) Progresión (checkbox centrado)
                    prog_cell = cols[8].columns([1, 1, 1])
                    mostrar_progresion = prog_cell[1].checkbox("", key=f"prog_check_{key_entrenamiento}_{idx}")

                    # 9) Copiar (checkbox centrado)
                    copy_cell = cols[9].columns([1, 1, 1])
                    mostrar_copia = copy_cell[1].checkbox("", key=f"copy_check_{key_entrenamiento}_{idx}")

                    # === PROGRESIONES ===
                    if mostrar_progresion:
                        st.markdown("#### Progresiones activas")
                        p = int(progresion_activa.split()[-1])  # Detectar si es Progresión 1, 2, 3
                        pcols = st.columns(4)

                        variable_key = f"Variable_{p}"
                        cantidad_key = f"Cantidad_{p}"
                        operacion_key = f"Operacion_{p}"
                        semanas_key = f"Semanas_{p}"

                        fila[variable_key] = pcols[0].selectbox(
                            f"Variable {p}",
                            ["", "peso", "velocidad", "tiempo", "rir", "series", "repeticiones"],
                            index=["", "peso", "velocidad", "tiempo", "rir", "series", "repeticiones"].index(fila.get(variable_key, "")),
                            key=f"var{p}_{key_entrenamiento}_{idx}"
                        )
                        fila[cantidad_key] = pcols[1].text_input(
                            f"Cantidad {p}", value=fila.get(cantidad_key, ""), key=f"cant{p}_{key_entrenamiento}_{idx}"
                        )
                        fila[operacion_key] = pcols[2].selectbox(
                            f"Operación {p}", ["", "multiplicacion", "division", "suma", "resta"],
                            index=["", "multiplicacion", "division", "suma", "resta"].index(fila.get(operacion_key, "")),
                            key=f"ope{p}_{key_entrenamiento}_{idx}"
                        )
                        fila[semanas_key] = pcols[3].text_input(
                            f"Semanas {p}", value=fila.get(semanas_key, ""), key=f"sem{p}_{key_entrenamiento}_{idx}"
                        )

                    # === COPIA ===
                    if mostrar_copia:
                        copiar_cols = st.columns([1, 3])
                        dias_copia = copiar_cols[1].multiselect(
                            "Selecciona día(s) para copiar este ejercicio",
                            dias,
                            key=f"multiselect_{key_entrenamiento}_{idx}"
                        )

                        if copiar_cols[0].button("✅ Confirmar copia", key=f"confirmar_copia_{key_entrenamiento}_{idx}") and dias_copia:
                            for dia_destino in dias_copia:
                                idx_dia = dias.index(dia_destino)
                                key_destino = f"rutina_dia_{idx_dia + 1}_{seccion.replace(' ', '_')}"
                                if key_destino not in st.session_state:
                                    st.session_state[key_destino] = []

                                nuevo_ejercicio = {k: v for k, v in fila.items()}

                                # Asegurar que la lista tenga suficiente largo
                                while len(st.session_state[key_destino]) <= idx:
                                    fila_vacia = {k: "" for k in columnas_tabla}
                                    fila_vacia["Sección"] = seccion
                                    st.session_state[key_destino].append(fila_vacia)

                                # Reemplazar o insertar en la misma posición
                                st.session_state[key_destino][idx] = nuevo_ejercicio

                            st.success(f"✅ Ejercicio copiado como Ejercicio {idx + 1} a: {', '.join(dias_copia)}")

    # === IMPORTANTE: Selección de categoría
    st.markdown("---")
    
    # === Normalizador de texto
    import unicodedata
    def normalizar_texto(texto):
        texto = texto.lower().strip()
        texto = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("utf-8")
        return texto

    opcion_categoria = st.sidebar.selectbox("📋 Categoría para análisis:", ["grupo_muscular_principal", "patron_de_movimiento"])

    contador = {}
    nombres_originales = {}

    dias_keys = [k for k in st.session_state if k.startswith("rutina_dia_") and "_Work_Out" in k]

    for key_dia in dias_keys:
        ejercicios = st.session_state[key_dia]

        for ejercicio in ejercicios:
            nombre_raw = ejercicio.get("Ejercicio", "").strip()
            nombre_norm = normalizar_texto(nombre_raw)

            try:
                series = int(ejercicio.get("Series", 0))
            except:
                series = 0

            if not nombre_norm:
                continue

            # Buscar coincidencia exacta normalizada
            coincidencias = [
                data for nombre, data in ejercicios_dict.items()
                if normalizar_texto(nombre) == nombre_norm
            ]
            data = coincidencias[0] if coincidencias else None

            if not data:
                categoria_valor = "(no encontrado)"
            else:
                try:
                    categoria_valor = data.get(opcion_categoria, "(sin dato)")
                except:
                    categoria_valor = "(error)"

            categoria_norm = normalizar_texto(categoria_valor)
            if categoria_norm in contador:
                contador[categoria_norm] += series
                nombres_originales[categoria_norm].add(categoria_valor)
            else:
                contador[categoria_norm] = series
                nombres_originales[categoria_norm] = {categoria_valor}


    # === Mostrar tabla fija en sidebar
    with st.sidebar:
        st.markdown("### 🧮 Series por categoría")
        if contador:
            df = pd.DataFrame({
                "Categoría": [
                    ", ".join(
                        sorted(
                            cat.replace("_", " ").capitalize()
                            for cat in nombres_originales[k]
                        )
                    ) for k in contador
                ],
                "Series": [contador[k] for k in contador]
            }).sort_values("Series", ascending=False)

            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos de series aún.")

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
                                try:
                                    semanas_aplicar = [int(s.strip()) for s in semanas_txt.split(",") if s.strip().isdigit()]
                                except:
                                    semanas_aplicar = []

                                for s in range(2, semana_idx + 1):
                                    if s in semanas_aplicar:
                                        if variable == "repeticiones":
                                            reps_min = ejercicio_mod.get("RepsMin", "")
                                            reps_max = ejercicio_mod.get("RepsMax", "")
                                            nuevo_min, nuevo_max = aplicar_progresion_rango(reps_min, reps_max, cantidad, operacion)
                                            ejercicio_mod["RepsMin"] = nuevo_min
                                            ejercicio_mod["RepsMax"] = nuevo_max
                                        else:
                                            valor_base = ejercicio_mod.get(variable.capitalize(), "")
                                            if valor_base != "":
                                                valor_base = aplicar_progresion(valor_base, float(cantidad), operacion)
                                                ejercicio_mod[variable.capitalize()] = valor_base


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
