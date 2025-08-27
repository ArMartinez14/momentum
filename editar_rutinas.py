# editar_rutinas.py
import json
import unicodedata
from datetime import datetime
import streamlit as st
import pandas as pd

import firebase_admin
from firebase_admin import credentials, firestore

# ====== 🔧 utilidades básicas ======
def normalizar_texto(txt: str) -> str:
    txt = (txt or "").strip().lower()
    txt = unicodedata.normalize("NFD", txt).encode("ascii", "ignore").decode("utf-8")
    return txt
def _f(v):
    try:
        s = str(v).strip().replace(",", ".")
        if s == "":
            return None
        if "-" in s:
            s = s.split("-", 1)[0].strip()
        return float(s)
    except:
        return None


def _ensure_len(lista: list[dict], n: int, plantilla: dict):
    if n < 0:
        n = 0
    while len(lista) < n:
        lista.append({k: "" for k in plantilla})
    while len(lista) > n:
        lista.pop()
    return lista

def claves_dias(rutina_dict: dict) -> list[str]:
    """Devuelve solo las claves que representan días ('1','2',...)."""
    if not rutina_dict:
        return []
    solo_dias = [str(k) for k in rutina_dict.keys() if str(k).isdigit()]
    return sorted(solo_dias, key=lambda x: int(x))

# ====== 🔥 Firebase (init perezoso + cacheado) ======
@st.cache_resource(show_spinner=False)
def get_db():
    if not firebase_admin._apps:
        cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# ====== 📦 Cargas cacheadas ======
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

EJERCICIOS  = cargar_ejercicios()
USUARIOS    = cargar_usuarios()
IMPLEMENTOS = cargar_implementos()

# ====== 🎛️ columnas de UI (idénticas a Crear Rutinas) ======
COLUMNAS_TABLA = [
    "Circuito", "Sección", "Ejercicio", "Detalle",
    "Series", "RepsMin", "RepsMax", "Peso", "RIR",
    "Tiempo", "Velocidad", "Tipo", "Video",
    "Variable_1", "Cantidad_1", "Operacion_1", "Semanas_1",
    "Variable_2", "Cantidad_2", "Operacion_2", "Semanas_2",
    "Variable_3", "Cantidad_3", "Operacion_3", "Semanas_3",
    "BuscarEjercicio"
]

CIRCUITOS = ["A","B","C","D","E","F","G","H","I","J","K","L"]
COL_SIZES = [0.9, 2.0, 3.0, 2.0, 0.8, 1.6, 1.0, 0.8, 1.2, 0.8]
HEADERS   = ["Circuito", "Buscar Ejercicio", "Ejercicio", "Detalle",
             "Series", "Repeticiones", "Peso", "RIR", "Progresión", "Copiar"]

# ====== 🔄 mapeos de lectura/escritura ======
def _ejercicio_firestore_a_fila_ui(ej: dict) -> dict:
    """Convierte un dict/ejercicio de Firestore a la fila usada por la UI."""
    fila = {k: "" for k in COLUMNAS_TABLA}

    # Sección (bloque)
    seccion = ej.get("Sección") or ej.get("bloque") or ""
    if seccion not in ["Warm Up", "Work Out"]:
        seccion = "Warm Up" if (ej.get("circuito","") in ["A","B","C"]) else (seccion or "Work Out")
    fila["Sección"] = seccion

    # Circuito
    fila["Circuito"] = ej.get("Circuito") or ej.get("circuito") or ""

    # Nombre ejercicio
    fila["Ejercicio"] = ej.get("Ejercicio") or ej.get("ejercicio") or ""

    # En Work Out, precargar el buscador con el ejercicio actual
    if fila["Sección"] == "Work Out":
        fila["BuscarEjercicio"] = fila["Ejercicio"]

    # Detalle / Series / RIR / Peso / Tiempo / Velocidad / Tipo / Video
    fila["Detalle"]   = ej.get("Detalle")    or ej.get("detalle")    or ""
    fila["Series"]    = ej.get("Series")     or ej.get("series")     or ""
    fila["RIR"]       = ej.get("RIR")        or ej.get("rir")        or ""
    fila["Peso"]      = ej.get("Peso")       or ej.get("peso")       or ""
    fila["Tiempo"]    = ej.get("Tiempo")     or ej.get("tiempo")     or ""
    fila["Velocidad"] = ej.get("Velocidad")  or ej.get("velocidad")  or ""
    fila["Tipo"]      = ej.get("Tipo")       or ej.get("tipo")       or ""
    fila["Video"]     = ej.get("Video")      or ej.get("video")      or ""

    # Repeticiones
    if "reps_min" in ej or "reps_max" in ej:
        fila["RepsMin"] = ej.get("reps_min", "")
        fila["RepsMax"] = ej.get("reps_max", "")
    elif "RepsMin" in ej or "RepsMax" in ej:
        fila["RepsMin"] = ej.get("RepsMin", "")
        fila["RepsMax"] = ej.get("RepsMax", "")
    else:
        rep = str(ej.get("repeticiones", "")).strip()
        if "-" in rep:
            mn, mx = rep.split("-", 1)
            fila["RepsMin"], fila["RepsMax"] = mn.strip(), mx.strip()
        else:
            fila["RepsMin"], fila["RepsMax"] = rep, ""

    # Progresiones
    for p in (1,2,3):
        fila[f"Variable_{p}"]  = ej.get(f"Variable_{p}",  "")
        fila[f"Cantidad_{p}"]  = ej.get(f"Cantidad_{p}",  "")
        fila[f"Operacion_{p}"] = ej.get(f"Operacion_{p}", "")
        fila[f"Semanas_{p}"]   = ej.get(f"Semanas_{p}",   "")

    return fila

def _fila_ui_a_ejercicio_firestore_legacy(fila: dict) -> dict:
    """Convierte la fila UI al esquema histórico (minúsculas) y fuerza float/None en numéricos."""
    seccion = fila.get("Sección", "")
    if seccion not in ["Warm Up", "Work Out"]:
        seccion = "Warm Up" if (fila.get("Circuito","") in ["A","B","C"]) else "Work Out"

    series   = _f(fila.get("Series",""))
    reps_min = _f(fila.get("RepsMin",""))
    reps_max = _f(fila.get("RepsMax",""))
    peso     = _f(fila.get("Peso",""))
    rir      = _f(fila.get("RIR",""))
    tiempo   = fila.get("Tiempo","")      # si quieres, también _f
    velocidad= fila.get("Velocidad","")   # si quieres, también _f

    return {
        "bloque":     seccion,
        "circuito":   fila.get("Circuito",""),
        "ejercicio":  fila.get("Ejercicio",""),
        "detalle":    fila.get("Detalle",""),
        "series":     series,
        "reps_min":   reps_min,
        "reps_max":   reps_max,
        "peso":       peso,
        "tiempo":     tiempo,
        "velocidad":  velocidad,
        "rir":        rir,
        "tipo":       fila.get("Tipo",""),
        "video":      fila.get("Video",""),
    }

# ====== 🧩 helpers para días ======
def _filas_vacias_seccion(seccion: str) -> list[dict]:
    filas = [{k: "" for k in COLUMNAS_TABLA} for _ in range(6)]
    for f in filas:
        f["Sección"] = seccion
    return filas

def _asegurar_dia_en_session(idx_dia: int):
    """Crea en session_state las listas para Warm Up y Work Out del día dado (1-based)."""
    wu_key = f"rutina_dia_{idx_dia}_Warm_Up"
    wo_key = f"rutina_dia_{idx_dia}_Work_Out"
    if wu_key not in st.session_state:
        st.session_state[wu_key] = _filas_vacias_seccion("Warm Up")
    if wo_key not in st.session_state:
        st.session_state[wo_key] = _filas_vacias_seccion("Work Out")

def _agregar_dia():
    dias = st.session_state.get("dias_editables", [])
    nuevo_idx = (max([int(d) for d in dias]) + 1) if dias else 1
    dias.append(str(nuevo_idx))
    st.session_state["dias_editables"] = dias
    _asegurar_dia_en_session(nuevo_idx)
    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()

def limpiar_dia(idx_dia: int):
    """
    Resetea Warm Up y Work Out del día dado (1-based) a 6 filas vacías
    y limpia estados de widgets asociados a ese día.
    """
    for seccion in ["Warm Up", "Work Out"]:
        key = f"rutina_dia_{idx_dia}_{seccion.replace(' ', '_')}"
        st.session_state[key] = _filas_vacias_seccion(seccion)
        # ⚠️ Importante: no fijar valor del number_input; eliminar la key para evitar warning
        num_key = f"num_{key}"
        st.session_state.pop(num_key, None)

    # Borrar estados de widgets del día (i es 0-based en los keys)
    i0 = idx_dia - 1
    patrones = [f"_{i0}_Warm_Up_", f"_{i0}_Work_Out_"]
    claves_borrar = []
    for k in list(st.session_state.keys()):
        if any(p in k for p in patrones) or k.startswith(f"multiselect_{i0}_") or k.startswith(f"do_copy_{i0}_"):
            claves_borrar.append(k)
    for k in claves_borrar:
        st.session_state.pop(k, None)

    try:
        st.rerun()
    except AttributeError:
        st.experimental_rerun()

# ====== 🧩 Render de tabla por día/sección ======
def render_tabla_dia(i: int, seccion: str, progresion_activa: str, dias_labels: list[str]):
    key_seccion = f"rutina_dia_{i+1}_{seccion.replace(' ', '_')}"
    if key_seccion not in st.session_state:
        st.session_state[key_seccion] = _filas_vacias_seccion(seccion)

    st.subheader(seccion)

    with st.form(f"form_{key_seccion}", clear_on_submit=False):
        # Cantidad filas (respetar session_state si ya existe para evitar warning)
        num_key = f"num_{key_seccion}"
        valor_inicial = st.session_state.get(num_key, len(st.session_state[key_seccion]))
        n_filas = st.number_input(
            "Filas", key=num_key, min_value=0, max_value=30,
            value=valor_inicial, step=1
        )
        _ensure_len(st.session_state[key_seccion], n_filas, {k: "" for k in COLUMNAS_TABLA})
        st.markdown("")

        # Encabezados
        header_cols = st.columns(COL_SIZES)
        for c, title in zip(header_cols, HEADERS):
            c.markdown(
                f"<div style='text-align:center; white-space:nowrap'><b>{title}</b></div>",
                unsafe_allow_html=True
            )

        # Filas
        for idx, fila in enumerate(st.session_state[key_seccion]):
            key_entrenamiento = f"{i}_{seccion.replace(' ','_')}_{idx}"
            cols = st.columns(COL_SIZES)

            # 0) Circuito
            fila["Circuito"] = cols[0].selectbox(
                "", CIRCUITOS,
                index=(CIRCUITOS.index(fila.get("Circuito")) if fila.get("Circuito") in CIRCUITOS else 0),
                key=f"circ_{key_entrenamiento}",
                label_visibility="collapsed"
            )

            # 1) Buscar Ejercicio
            valor_busqueda_inicial = fila.get("BuscarEjercicio","") if seccion == "Work Out" else ""
            palabra = cols[1].text_input(
                "", value=valor_busqueda_inicial,
                key=f"buscar_{key_entrenamiento}", label_visibility="collapsed"
            )
            fila["BuscarEjercicio"] = palabra if seccion == "Work Out" else ""

            # 2) Select "Ejercicio" filtrado por el texto del buscador
            tokens = [t.strip().lower() for t in palabra.split() if t.strip()]
            if tokens:
                opciones = [n for n in EJERCICIOS.keys() if all(t in n.lower() for t in tokens)]
            else:
                opciones = list(EJERCICIOS.keys())

            nombre_actual = (fila.get("Ejercicio") or "").strip()
            if nombre_actual and nombre_actual not in opciones:
                opciones = [nombre_actual] + opciones
            if not opciones:
                opciones = ["(sin resultados)"]

            idx_default = opciones.index(nombre_actual) if nombre_actual in opciones else 0
            seleccionado = cols[2].selectbox(
                "", opciones, index=idx_default,
                key=f"select_{key_entrenamiento}", label_visibility="collapsed"
            )

            if seleccionado != "(sin resultados)":
                fila["Ejercicio"] = seleccionado
                if not fila.get("Video"):
                    fila["Video"] = (EJERCICIOS.get(seleccionado, {}) or {}).get("video","").strip()

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
            # 5) Reps min/max
            cmin, cmax = cols[5].columns(2)
            try:
                fila["RepsMin"] = cmin.text_input("", value=str(fila.get("RepsMin","")), key=f"rmin_{key_entrenamiento}", label_visibility="collapsed")
            except:
                fila["RepsMin"] = ""
            try:
                fila["RepsMax"] = cmax.text_input("", value=str(fila.get("RepsMax","")), key=f"rmax_{key_entrenamiento}", label_visibility="collapsed")
            except:
                fila["RepsMax"] = ""

            # 6) Peso (ligado a implementos si aplica)
            peso_widget_key = f"peso_{key_entrenamiento}"
            peso_value = fila.get("Peso","")
            pesos_disponibles = []
            usar_text_input = True
            try:
                nombre_ej = fila.get("Ejercicio","")
                ej_doc = EJERCICIOS.get(nombre_ej, {}) or {}
                id_impl = str(ej_doc.get("id_implemento","") or "")
                if id_impl and id_impl != "1" and id_impl in IMPLEMENTOS:
                    pesos_disponibles = IMPLEMENTOS[id_impl].get("pesos", []) or []
                    usar_text_input = not bool(pesos_disponibles)
            except Exception:
                usar_text_input = True

            if not usar_text_input:
                opciones_peso = [str(p) for p in pesos_disponibles]
                if str(peso_value) not in opciones_peso and opciones_peso:
                    peso_value = opciones_peso[0]
                fila["Peso"] = cols[6].selectbox(
                    "", options=opciones_peso,
                    index=(opciones_peso.index(str(peso_value)) if peso_value in opciones_peso else 0),
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
            prog_cell = cols[8].columns([1,1,1])
            mostrar_progresion = prog_cell[1].checkbox("", key=f"prog_check_{key_entrenamiento}_{idx}")

            # 9) Copiar (checkbox centrado)
            copy_cell = cols[9].columns([1,1,1])
            mostrar_copia = copy_cell[1].checkbox("", key=f"copy_check_{key_entrenamiento}_{idx}")

            # === PROGRESIONES ===
            if mostrar_progresion:
                st.markdown("#### Progresiones activas")
                p = int(progresion_activa.split()[-1])  # 1..3
                pcols = st.columns(4)
                opciones_var = ["", "peso", "velocidad", "tiempo", "rir", "series", "repeticiones"]
                opciones_ope = ["", "multiplicacion", "division", "suma", "resta"]

                fila[f"Variable_{p}"] = pcols[0].selectbox(
                    f"Variable {p}", opciones_var,
                    index=(opciones_var.index(fila.get(f"Variable_{p}", "")) if fila.get(f"Variable_{p}","") in opciones_var else 0),
                    key=f"var{p}_{key_entrenamiento}_{idx}"
                )
                fila[f"Cantidad_{p}"] = pcols[1].text_input(
                    f"Cantidad {p}", value=fila.get(f"Cantidad_{p}", ""), key=f"cant{p}_{key_entrenamiento}_{idx}"
                )
                fila[f"Operacion_{p}"] = pcols[2].selectbox(
                    f"Operación {p}", opciones_ope,
                    index=(opciones_ope.index(fila.get(f"Operacion_{p}", "")) if fila.get(f"Operacion_{p}","") in opciones_ope else 0),
                    key=f"ope{p}_{key_entrenamiento}_{idx}"
                )
                fila[f"Semanas_{p}"] = pcols[3].text_input(
                    f"Semanas {p}", value=fila.get(f"Semanas_{p}", ""), key=f"sem{p}_{key_entrenamiento}_{idx}"
                )

            # === Copia a otros días ===
            if mostrar_copia:
                st.caption("Selecciona día(s) y presiona **Actualizar sección** para copiar.")
                dias_copia = st.multiselect(
                    "Días destino", dias_labels,
                    key=f"multiselect_{key_entrenamiento}_{idx}"
                )
                st.session_state[f"do_copy_{key_entrenamiento}_{idx}"] = True
            else:
                st.session_state.pop(f"multiselect_{key_entrenamiento}_{idx}", None)
                st.session_state.pop(f"do_copy_{key_entrenamiento}_{idx}", None)

        # Submit del form
        submitted = st.form_submit_button("Actualizar sección")
        if submitted:
            # Procesar copias dentro de esta sección
            for idx, fila in enumerate(st.session_state[key_seccion]):
                key_entrenamiento = f"{i}_{seccion.replace(' ','_')}_{idx}"
                do_copy_key = f"do_copy_{key_entrenamiento}_{idx}"
                multisel_key = f"multiselect_{key_entrenamiento}_{idx}"
                if st.session_state.get(do_copy_key):
                    dias_copia = st.session_state.get(multisel_key, [])
                    for dia_destino in dias_copia:
                        idx_dia = dias_labels.index(dia_destino)
                        key_destino = f"rutina_dia_{idx_dia + 1}_{seccion.replace(' ', '_')}"
                        if key_destino not in st.session_state:
                            st.session_state[key_destino] = []
                        while len(st.session_state[key_destino]) <= idx:
                            fila_vacia = {k: "" for k in COLUMNAS_TABLA}
                            fila_vacia["Sección"] = seccion
                            st.session_state[key_destino].append(fila_vacia)
                        st.session_state[key_destino][idx] = {k: v for k, v in fila.items()}
            st.success("Sección actualizada ✅")

# ====== ⬇️ Carga desde Firestore a la UI (session_state) ======
def cargar_doc_en_session(rutina_dict: dict, dias_disponibles: list[str]):
    # Limpiar claves anteriores
    for k in list(st.session_state.keys()):
        if k.startswith("rutina_dia_") or k.startswith("ej_") or k.startswith("buscar_"):
            st.session_state.pop(k, None)

    # Construir por día (solo días numéricos)
    dias_ordenados = sorted([int(d) for d in dias_disponibles])
    for d in dias_ordenados:
        ejercicios_dia = rutina_dict.get(str(d), []) or []
        # separar por seccion
        wu, wo = [], []
        for ej in ejercicios_dia:
            fila = _ejercicio_firestore_a_fila_ui(ej)
            (wu if fila.get("Sección") == "Warm Up" else wo).append(fila)
        # setear en session
        st.session_state[f"rutina_dia_{int(d)}_Warm_Up"] = wu if wu else _filas_vacias_seccion("Warm Up")
        st.session_state[f"rutina_dia_{int(d)}_Work_Out"] = wo if wo else _filas_vacias_seccion("Work Out")

    # Guardamos la lista editable de días en session_state
    st.session_state["dias_editables"] = [str(d) for d in dias_ordenados]

# ====== ⬆️ Recolector desde la UI a Firestore (formato histórico) ======
def construir_rutina_desde_session(dias_labels: list[str]) -> dict:
    """
    Construye el dict 'rutina' con claves '1','2',... y valores = lista de ejercicios
    en el esquema histórico (minúsculas).
    """
    nueva = {}
    for i, _ in enumerate(dias_labels):
        wu_key = f"rutina_dia_{i+1}_Warm_Up"
        wo_key = f"rutina_dia_{i+1}_Work_Out"
        ejercicios = (st.session_state.get(wu_key, []) or []) + (st.session_state.get(wo_key, []) or [])
        lista = []
        for fila in ejercicios:
            lista.append(_fila_ui_a_ejercicio_firestore_legacy(fila))
        nueva[str(i+1)] = lista
    return nueva

# ====== 🧰 PÁGINA PRINCIPAL ======
def editar_rutinas():
    st.title("✏️ Editar Rutina (misma UI que Crear Rutinas)")

    db = get_db()

    # --- Selección de cliente / semana ---
    clientes_dict = {}
    for doc in db.collection("rutinas_semanales").stream():
        data = doc.to_dict() or {}
        nombre = data.get("cliente")
        correo = data.get("correo")
        if nombre and correo:
            clientes_dict[nombre] = correo

    nombres_clientes = sorted(clientes_dict.keys())
    nombre_sel = st.selectbox("Selecciona el cliente:", nombres_clientes) if nombres_clientes else ""
    if not nombre_sel:
        st.info("No hay clientes con rutinas.")
        return

    correo = (clientes_dict[nombre_sel] or "").strip().lower()

    # semanas del cliente
    semanas_dict = {}
    for doc in db.collection("rutinas_semanales").where("correo","==",correo).stream():
        data = doc.to_dict() or {}
        f = data.get("fecha_lunes")
        if f:
            semanas_dict[f] = doc.id

    semanas = sorted(semanas_dict.keys())
    semana_sel = st.selectbox("Selecciona la semana a editar:", semanas) if semanas else ""
    if not semana_sel:
        st.warning("Este cliente no tiene semanas registradas.")
        return

    doc_id_semana = semanas_dict[semana_sel]

    # Leer y filtrar rutina: SOLO días numéricos
    doc_data = db.collection("rutinas_semanales").document(doc_id_semana).get().to_dict() or {}
    rutina_raw = doc_data.get("rutina", {}) or {}
    rutina = {k: v for k, v in rutina_raw.items() if str(k).isdigit()}

    # Días disponibles
    dias_disponibles = claves_dias(rutina) if rutina else ["1","2","3","4","5"]

    st.markdown("### 📅 Días en la rutina actual:")
    st.markdown(", ".join([f"**Día {d}**" for d in dias_disponibles]))

    # --- Botón: cargar doc en UI ---
    if st.button("📥 Cargar rutina seleccionada"):
        cargar_doc_en_session(rutina, dias_disponibles)
        st.success("Rutina cargada en el editor ✅")

    st.markdown("---")

    # ===== NUEVO: control para agregar días =====
    col_add = st.columns([1,1,6])
    with col_add[0]:
        if st.button("➕ Agregar día"):
            if "dias_editables" not in st.session_state:
                cargar_doc_en_session(rutina, dias_disponibles)
            _agregar_dia()

    # Si aún no hay "dias_editables", usamos los disponibles
    dias_numericos = st.session_state.get("dias_editables", dias_disponibles)
    dias_labels = [f"Día {int(d)}" for d in dias_numericos]

    # Progresión activa
    progresion_activa = st.radio(
        "Progresión activa", ["Progresión 1", "Progresión 2", "Progresión 3"],
        horizontal=True, index=0
    )

    # Tabs por día
    tabs = st.tabs(dias_labels)

    for i, tab in enumerate(tabs):
        with tab:
            tools_cols = st.columns([1, 9])
            if tools_cols[0].button("🧹 Limpiar día", key=f"limpiar_dia_{i+1}",
                                    help="Borra todos los inputs de Warm Up y Work Out del día actual"):
                limpiar_dia(i + 1)

            _asegurar_dia_en_session(i+1)
            render_tabla_dia(i, "Warm Up", progresion_activa, dias_labels)
            st.markdown("---")
            render_tabla_dia(i, "Work Out", progresion_activa, dias_labels)
        st.markdown("---")

    # ====== Guardado SOLO en esta semana ======
    if st.button("💾 Guardar cambios SOLO en esta semana"):
        dias_labels = [f"Día {i}" for i in range(1, len(dias_numericos)+1)]
        nueva_rutina = construir_rutina_desde_session(dias_labels)
        rutina_existente = doc_data.get("rutina", {}) or {}
        for k_dia, lista in nueva_rutina.items():
            if str(k_dia).isdigit():
                rutina_existente[str(k_dia)] = lista
        db.collection("rutinas_semanales").document(doc_id_semana).update({"rutina": rutina_existente})
        st.success("Cambios guardados en la semana seleccionada ✅")

    # ====== Aplicar a futuras semanas ======
    if st.button("⏩ Aplicar cambios a FUTURAS semanas (mismo cliente)"):
        try:
            fecha_sel = datetime.strptime(semana_sel, "%Y-%m-%d")
        except ValueError:
            st.error("Formato de fecha inválido en 'semana_sel'.")
            return

        dias_labels = [f"Día {i}" for i in range(1, len(dias_numericos)+1)]
        nueva_rutina = construir_rutina_desde_session(dias_labels)
        total = 0

        for doc in db.collection("rutinas_semanales").where("correo","==",correo).stream():
            data = doc.to_dict() or {}
            f = data.get("fecha_lunes","")
            try:
                f_dt = datetime.strptime(f, "%Y-%m-%d")
            except:
                continue
            if f_dt >= fecha_sel:
                rutina_existente = data.get("rutina", {}) or {}
                for k_dia, lista in nueva_rutina.items():
                    if str(k_dia).isdigit():
                        rutina_existente[str(k_dia)] = lista
                db.collection("rutinas_semanales").document(doc.id).update({"rutina": rutina_existente})
                total += 1

        st.success(f"✅ Cambios aplicados en {total} semana(s) (incluida la actual).")
