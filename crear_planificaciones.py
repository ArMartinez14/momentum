import streamlit as st
import json
import unicodedata
from datetime import date, timedelta, datetime
import pandas as pd

import firebase_admin
from firebase_admin import credentials, firestore

from herramientas import aplicar_progresion
from guardar_rutina_view import guardar_rutina, aplicar_progresion_rango

# ---------- utilidades básicas ----------
def proximo_lunes(base: date | None = None) -> date:
    base = base or date.today()
    dias = (7 - base.weekday()) % 7
    if dias == 0:
        dias = 7
    return base + timedelta(days=dias)

def normalizar_texto(texto: str) -> str:
    texto = texto.lower().strip()
    texto = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("utf-8")
    return texto

# ---------- Firebase (init perezoso + cacheado) ----------
@st.cache_resource(show_spinner=False)
def get_db():
    if not firebase_admin._apps:
        cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# ---------- Cargas cacheadas ----------
@st.cache_data(show_spinner=False)
def cargar_ejercicios():
    db = get_db()
    docs = db.collection("ejercicios").stream()
    return {doc.to_dict().get("nombre", ""): (doc.to_dict() or {}) for doc in docs if doc.exists}

@st.cache_data(show_spinner=False)
def cargar_usuarios():
    db = get_db()
    docs = db.collection("usuarios").stream()
    return [doc.to_dict() for doc in docs if doc.exists]

@st.cache_data(show_spinner=False)
def cargar_implementos():
    db = get_db()
    impl = {}
    for doc in db.collection("implementos").stream():
        d = doc.to_dict() or {}
        d["pesos"] = d.get("pesos", [])
        impl[str(doc.id)] = d
    return impl

IMPLEMENTOS = cargar_implementos()

def _ensure_len(lista: list[dict], n: int, plantilla: dict):
    """Ajusta el largo de la lista al valor n."""
    if n < 0:
        n = 0
    while len(lista) < n:
        lista.append({k: "" for k in plantilla})
    while len(lista) > n:
        lista.pop()
    return lista


def crear_rutinas():
    st.title("Crear nueva rutina")

    cols = st.columns([5, 1])
    with cols[1]:
        if st.button("🔄", help="Recargar catálogos"):
            st.cache_data.clear()
            st.rerun()

    ejercicios_dict = cargar_ejercicios()
    usuarios = cargar_usuarios()

    nombres = sorted(set(u.get("nombre", "") for u in usuarios))
    correos_entrenadores = sorted([
        u["correo"] for u in usuarios if u.get("rol", "").lower() in ["entrenador", "admin", "administrador"]
    ])

    # === Selección de cliente/semana ===
    nombre_input = st.text_input("Escribe el nombre del cliente:")
    coincidencias = [n for n in nombres if nombre_input.lower() in n.lower()]
    nombre_sel = st.selectbox("Selecciona de la lista:", coincidencias) if coincidencias else ""

    correo_auto = next((u.get("correo", "") for u in usuarios if u.get("nombre") == nombre_sel), "")
    correo = st.text_input("Correo del cliente:", value=correo_auto)

    valor_defecto = proximo_lunes()
    sel = st.date_input(
        "Fecha de inicio de rutina:",
        value=valor_defecto,
        help="Solo se usan lunes. Si eliges otro día, se ajustará automáticamente al lunes de esa semana."
    )
    fecha_inicio = sel - timedelta(days=sel.weekday()) if sel.weekday() != 0 else sel
    if sel.weekday() != 0:
        st.info(f"🔁 Ajustado automáticamente al lunes {fecha_inicio.isoformat()}.")

    semanas = st.number_input("Semanas de duración:", min_value=1, max_value=12, value=4)
    # === Objetivo de la rutina (opcional) ===
    objetivo = st.text_area( "🎯 Objetivo de la rutina (opcional)",
        value=st.session_state.get("objetivo", ""),
    )
    st.session_state["objetivo"] = objetivo

    correo_login = (st.session_state.get("correo") or "").strip().lower()
    entrenador = st.text_input("Correo del entrenador responsable:", value=correo_login, disabled=True)

    st.markdown("---")
    st.subheader("Días de entrenamiento")

    dias_labels = ["Día 1", "Día 2", "Día 3", "Día 4", "Día 5"]
    tabs = st.tabs(dias_labels)
    dias = dias_labels  # alias para compat

    columnas_tabla = [
        "Circuito", "Sección", "Ejercicio", "Detalle", "Series", "Repeticiones",
        "Peso", "Tiempo", "Velocidad", "RIR", "Tipo", "Video"
    ]

    # === Progresión activa (se mantiene) ===
    progresion_activa = st.radio(
        "Progresión activa", ["Progresión 1", "Progresión 2", "Progresión 3"],
        horizontal=True, index=0
    )

    for i, tab in enumerate(tabs):
        with tab:
            dia_key = f"rutina_dia_{i+1}"

            # Estructura base por sección en session_state
            for seccion in ["Warm Up", "Work Out"]:
                key_seccion = f"{dia_key}_{seccion.replace(' ', '_')}"
                if key_seccion not in st.session_state:
                    st.session_state[key_seccion] = [{k: "" for k in columnas_tabla} for _ in range(6)]
                    for f in st.session_state[key_seccion]:
                        f["Sección"] = seccion

                st.subheader(seccion)

                # ---------- FORM por sección ----------
                with st.form(f"form_{key_seccion}", clear_on_submit=False):
                    # Control de cantidad de filas
                    n_filas = st.number_input(
                        "Filas", key=f"num_{key_seccion}", min_value=0, max_value=30,
                        value=len(st.session_state[key_seccion]), step=1
                    )
                    _ensure_len(st.session_state[key_seccion], n_filas, {k: "" for k in columnas_tabla})
                    st.markdown("")

                    # Encabezados
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

                    # ------ Render filas ------
                    for idx, fila in enumerate(st.session_state[key_seccion]):
                        key_entrenamiento = f"{i}_{seccion.replace(' ','_')}_{idx}"
                        cols = st.columns(col_sizes)

                        # 0) Circuito
                        opciones_circuito = ["A","B","C","D","E","F","G","H","I","J","K","L"]

                        fila["Circuito"] = cols[0].selectbox(
                            "",
                            opciones_circuito,
                            index=(opciones_circuito.index(fila.get("Circuito")) if fila.get("Circuito") in opciones_circuito else 0),
                            key=f"circ_{key_entrenamiento}",
                            label_visibility="collapsed"
                        )


                        # 1) Buscar + 2) Ejercicio
                        if seccion == "Work Out":
                            palabra = cols[1].text_input(
                                "", value=fila.get("BuscarEjercicio", ""),
                                key=f"buscar_{key_entrenamiento}", label_visibility="collapsed"
                            )
                            fila["BuscarEjercicio"] = palabra

                            try:
                                ejercicios_encontrados = (
                                    [n for n in ejercicios_dict.keys()
                                     if all(p in n.lower() for p in palabra.lower().split())]
                                    if palabra.strip() else []
                                )
                            except Exception:
                                ejercicios_encontrados = []

                            seleccionado = cols[2].selectbox(
                                "", ejercicios_encontrados if ejercicios_encontrados else ["(sin resultados)"],
                                key=f"select_{key_entrenamiento}", label_visibility="collapsed"
                            )
                            if seleccionado != "(sin resultados)":
                                fila["Ejercicio"] = seleccionado
                                if not fila.get("Video"):
                                    fila["Video"] = (ejercicios_dict.get(seleccionado, {}) or {}).get("video", "").strip()
                        else:
                            cols[1].markdown("&nbsp;", unsafe_allow_html=True)
                            fila["Ejercicio"] = cols[2].text_input(
                                "", value=fila.get("Ejercicio",""),
                                key=f"ej_{key_entrenamiento}", label_visibility="collapsed"
                            )

                        # 3) Detalle
                        fila["Detalle"] = cols[3].text_input(
                            "", value=fila.get("Detalle",""),
                            key=f"det_{key_entrenamiento}", label_visibility="collapsed"
                        )
                        # 4) Series
                        fila["Series"] = cols[4].text_input(
                            "", value=fila.get("Series",""),
                            key=f"ser_{key_entrenamiento}", label_visibility="collapsed"
                        )
                        # 5) Reps (min/max)
                        cmin, cmax = cols[5].columns(2)
                        try:
                            fila["RepsMin"] = int(cmin.text_input("", value=str(fila.get("RepsMin","")), key=f"rmin_{key_entrenamiento}", label_visibility="collapsed"))
                        except:
                            fila["RepsMin"] = ""
                        try:
                            fila["RepsMax"] = int(cmax.text_input("", value=str(fila.get("RepsMax","")), key=f"rmax_{key_entrenamiento}", label_visibility="collapsed"))
                        except:
                            fila["RepsMax"] = ""

                        # 6) Peso (cache IMPLEMENTOS, sin lecturas por fila)
                        peso_widget_key = f"peso_{key_entrenamiento}"
                        peso_value = fila.get("Peso","")
                        pesos_disponibles = []
                        usar_text_input = True
                        try:
                            nombre_ej = fila.get("Ejercicio","")
                            ej_doc = ejercicios_dict.get(nombre_ej, {}) or {}
                            id_impl = str(ej_doc.get("id_implemento","") or "")
                            if id_impl and id_impl != "1" and id_impl in IMPLEMENTOS:
                                pesos_disponibles = IMPLEMENTOS[id_impl].get("pesos", []) or []
                                usar_text_input = not bool(pesos_disponibles)
                        except Exception:
                            usar_text_input = True

                        if not usar_text_input:
                            if str(peso_value) not in [str(p) for p in pesos_disponibles]:
                                peso_value = str(pesos_disponibles[0])
                            fila["Peso"] = cols[6].selectbox(
                                "", options=[str(p) for p in pesos_disponibles],
                                index=[str(p) for p in pesos_disponibles].index(str(peso_value)),
                                key=peso_widget_key, label_visibility="collapsed"
                            )
                        else:
                            fila["Peso"] = cols[6].text_input(
                                "", value=str(peso_value),
                                key=peso_widget_key, label_visibility="collapsed", placeholder="Kg"
                            )

                        # 7) RIR
                        fila["RIR"] = cols[7].text_input(
                            "", value=fila.get("RIR",""),
                            key=f"rir_{key_entrenamiento}", label_visibility="collapsed"
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
                            p = int(progresion_activa.split()[-1])  # 1, 2 o 3
                            pcols = st.columns(4)

                            variable_key = f"Variable_{p}"
                            cantidad_key = f"Cantidad_{p}"
                            operacion_key = f"Operacion_{p}"
                            semanas_key = f"Semanas_{p}"

                            opciones_var = ["", "peso", "velocidad", "tiempo", "rir", "series", "repeticiones"]
                            opciones_ope = ["", "multiplicacion", "division", "suma", "resta"]

                            fila[variable_key] = pcols[0].selectbox(
                                f"Variable {p}",
                                opciones_var,
                                index=(opciones_var.index(fila.get(variable_key, "")) if fila.get(variable_key, "") in opciones_var else 0),
                                key=f"var{p}_{key_entrenamiento}_{idx}"
                            )
                            fila[cantidad_key] = pcols[1].text_input(
                                f"Cantidad {p}", value=fila.get(cantidad_key, ""), key=f"cant{p}_{key_entrenamiento}_{idx}"
                            )
                            fila[operacion_key] = pcols[2].selectbox(
                                f"Operación {p}", opciones_ope,
                                index=(opciones_ope.index(fila.get(operacion_key, "")) if fila.get(operacion_key, "") in opciones_ope else 0),
                                key=f"ope{p}_{key_entrenamiento}_{idx}"
                            )
                            fila[semanas_key] = pcols[3].text_input(
                                f"Semanas {p}", value=fila.get(semanas_key, ""), key=f"sem{p}_{key_entrenamiento}_{idx}"
                            )

                        # === COPIA === (se ejecuta al submit del form)
                        if mostrar_copia:
                            copiar_cols = st.columns([1, 3])
                            st.caption("Selecciona día(s) y presiona **Actualizar sección** para copiar.")
                            dias_copia = copiar_cols[1].multiselect(
                                "Días destino",
                                dias,  # alias de dias_labels
                                key=f"multiselect_{key_entrenamiento}_{idx}"
                            )
                            # Marcador en session_state para saber que esta fila quiere copiarse
                            st.session_state[f"do_copy_{key_entrenamiento}_{idx}"] = True
                        else:
                            # Limpia selección si se desactiva
                            st.session_state.pop(f"multiselect_{key_entrenamiento}_{idx}", None)
                            st.session_state.pop(f"do_copy_{key_entrenamiento}_{idx}", None)

                    # ---- Submit del FORM: actualiza sección y procesa copias ----
                    submitted = st.form_submit_button("Actualizar sección")
                    if submitted:
                        # Procesar copias pendientes dentro de esta sección
                        for idx, fila in enumerate(st.session_state[key_seccion]):
                            key_entrenamiento = f"{i}_{seccion.replace(' ','_')}_{idx}"
                            do_copy_key = f"do_copy_{key_entrenamiento}_{idx}"
                            multisel_key = f"multiselect_{key_entrenamiento}_{idx}"

                            if st.session_state.get(do_copy_key):
                                dias_copia = st.session_state.get(multisel_key, [])
                                if dias_copia:
                                    for dia_destino in dias_copia:
                                        idx_dia = dias.index(dia_destino)
                                        key_destino = f"rutina_dia_{idx_dia + 1}_{seccion.replace(' ', '_')}"
                                        if key_destino not in st.session_state:
                                            st.session_state[key_destino] = []

                                        nuevo_ejercicio = {k: v for k, v in fila.items()}

                                        while len(st.session_state[key_destino]) <= idx:
                                            fila_vacia = {k: "" for k in columnas_tabla}
                                            fila_vacia["Sección"] = seccion
                                            st.session_state[key_destino].append(fila_vacia)

                                        st.session_state[key_destino][idx] = nuevo_ejercicio
                        st.success("Sección actualizada ✅")

            st.markdown("---")

    # ==========================
    #  Análisis en Sidebar
    # ==========================
    st.markdown("---")
    opcion_categoria = st.sidebar.selectbox(
        "📋 Categoría para análisis:",
        ["grupo_muscular_principal", "patron_de_movimiento"]
    )

    contador = {}
    nombres_originales = {}
    dias_keys = [k for k in st.session_state if k.startswith("rutina_dia_") and "_Work_Out" in k]

    for key_dia in dias_keys:
        ejercicios = st.session_state.get(key_dia, [])
        for ejercicio in ejercicios:
            nombre_raw = str(ejercicio.get("Ejercicio", "")).strip()
            nombre_norm = normalizar_texto(nombre_raw)

            try:
                series = int(ejercicio.get("Series", 0))
            except:
                series = 0

            if not nombre_norm:
                continue

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

            categoria_norm = normalizar_texto(str(categoria_valor))
            if categoria_norm in contador:
                contador[categoria_norm] += series
                nombres_originales[categoria_norm].add(categoria_valor)
            else:
                contador[categoria_norm] = series
                nombres_originales[categoria_norm] = {categoria_valor}

    with st.sidebar:
        st.markdown("### 🧮 Series por categoría")
        if contador:
            df = pd.DataFrame({
                "Categoría": [
                    ", ".join(sorted(cat.replace("_", " ").capitalize() for cat in nombres_originales[k]))
                    for k in contador
                ],
                "Series": [contador[k] for k in contador]
            }).sort_values("Series", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos de series aún.")

    # ==========================
    #  Previsualización
    # ==========================
    if st.button("🔍 Previsualizar rutina"):
        st.subheader("📅 Previsualización de todas las semanas con progresiones aplicadas")

        for semana_idx in range(1, int(semanas) + 1):
            with st.expander(f"Semana {semana_idx}"):
                for i, dia_nombre in enumerate(dias):
                    wu_key = f"rutina_dia_{i + 1}_Warm_Up"
                    wo_key = f"rutina_dia_{i + 1}_Work_Out"
                    ejercicios = (st.session_state.get(wu_key, []) or []) + (st.session_state.get(wo_key, []) or [])
                    if not ejercicios:
                        continue

                    st.write(f"**{dia_nombre}**")

                    tabla = []
                    for ejercicio in ejercicios:
                        ejercicio_mod = ejercicio.copy()
                        seccion = ejercicio_mod.get("Sección") or ("Warm Up" if ejercicio_mod.get("Circuito","") in ["A","B","C"] else "Work Out")

                        # Aplicar progresiones si corresponde a esta semana
                        for p in range(1, 4):
                            variable = str(ejercicio.get(f"Variable_{p}", "")).strip().lower()
                            cantidad = ejercicio.get(f"Cantidad_{p}", "")
                            operacion = str(ejercicio.get(f"Operacion_{p}", "")).strip().lower()
                            semanas_txt = str(ejercicio.get(f"Semanas_{p}", ""))

                            if not (variable and operacion and cantidad):
                                continue
                            try:
                                semanas_aplicar = [int(s.strip()) for s in semanas_txt.split(",") if s.strip().isdigit()]
                            except:
                                semanas_aplicar = []

                            if semana_idx in semanas_aplicar:
                                if variable == "repeticiones":
                                    nuevo_min, nuevo_max = aplicar_progresion_rango(
                                        ejercicio_mod.get("RepsMin",""), ejercicio_mod.get("RepsMax",""), cantidad, operacion
                                    )
                                    ejercicio_mod["RepsMin"], ejercicio_mod["RepsMax"] = nuevo_min, nuevo_max
                                else:
                                    key_cap = variable.capitalize()  # Peso, Velocidad, Tiempo, Rir, Series
                                    val = ejercicio_mod.get(key_cap, "")
                                    if val != "":
                                        try:
                                            ejercicio_mod[key_cap] = aplicar_progresion(val, float(cantidad), operacion)
                                        except:
                                            pass

                        # Reps como string
                        mn, mx = ejercicio_mod.get("RepsMin",""), ejercicio_mod.get("RepsMax","")
                        rep_str = f"{mn}–{mx}" if mn != "" and mx != "" else (str(mn or mx) if (mn != "" or mx != "") else "")

                        tabla.append({
                            "bloque": seccion,
                            "circuito": ejercicio_mod.get("Circuito",""),
                            "ejercicio": ejercicio_mod.get("Ejercicio",""),
                            "series": ejercicio_mod.get("Series",""),
                            "repeticiones": rep_str,
                            "peso": ejercicio_mod.get("Peso",""),
                            "tiempo": ejercicio_mod.get("Tiempo",""),
                            "velocidad": ejercicio_mod.get("Velocidad",""),
                            "rir": ejercicio_mod.get("RIR",""),
                            "tipo": ejercicio_mod.get("Tipo",""),
                        })

                    st.dataframe(pd.DataFrame(tabla), use_container_width=True, hide_index=True)

    # ======= Guardar =======
    if st.button("Guardar Rutina"):
        if nombre_sel and correo and entrenador:
            objetivo = st.session_state.get("objetivo", "")
            # ✅ compatible hacia atrás: 'objetivo' es opcional en la función
            guardar_rutina(nombre_sel, correo, entrenador, fecha_inicio, semanas, dias_labels, objetivo=objetivo)
        else:
            st.warning("⚠️ Completa nombre, correo y entrenador antes de guardar.")

