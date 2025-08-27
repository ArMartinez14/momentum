import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import json
from herramientas import actualizar_progresiones_individual
import random
from datetime import date

# ✅ Lista única (normales + anime, sin mencionar series/personajes)
MENSAJES_MOTIVACIONALES = [
    # Base normales
    "💪 ¡Éxito en tu entrenamiento de hoy, {nombre}! 🔥",
    "🚀 {nombre}, cada repetición te acerca más a tu objetivo.",
    "🏋️‍♂️ {nombre}, hoy es un gran día para superar tus límites.",
    "🔥 Vamos {nombre}, conviértete en la mejor versión de ti mismo.",
    "⚡ {nombre}, la constancia es la clave. ¡Dalo todo hoy!",
    "🥇 {nombre}, cada sesión es un paso más hacia la victoria.",
    "🌟 Nunca te detengas, {nombre}. ¡Hoy vas a brillar en tu entrenamiento!",
    "🏆 {nombre}, recuerda: disciplina > motivación. ¡Tú puedes!",
    "🙌 A disfrutar el proceso, {nombre}. ¡Confía en ti!",
    "💥 {nombre}, el esfuerzo de hoy es el resultado de mañana.",

    # Frases de inspiración anime (sin referencias)
    "💥 {nombre}, el poder viene en respuesta a una necesidad, no a un deseo.",
    "⚡ {nombre}, supera tus límites ahora mismo.",
    "🔥 {nombre}, no rendirse es tu especialidad.",
    "🍃 {nombre}, jamás te rindas.",
    "🔥 {nombre}, el trabajo duro es inútil para quien no cree en sí mismo.",
    "🌀 {nombre}, los fracasos enseñan cosas que el éxito no.",
    "☠️ {nombre}, no importa cuán difícil se ponga, nunca retrocedas.",
    "🌊 {nombre}, los sueños nunca terminan.",
    "🔥 {nombre}, los sueños de los hombres nunca mueren.",
    "💥 {nombre}, un héroe sonríe incluso cuando tiene el corazón hecho pedazos.",
    "🌟 {nombre}, más allá de los límites, Plus Ultra.",
    "⚡ {nombre}, conviértete en el héroe que quieres ser.",
    "🛡️ {nombre}, si ganas, vives. Si pierdes, mueres. Si no luchas, no puedes ganar.",
    "⚔️ {nombre}, el mundo es cruel… pero también es muy hermoso.",
    "🔥 {nombre}, la única cosa que puedes hacer es no arrepentirte de tu elección.",
    "🏹 {nombre}, si vas a arriesgar tu vida, necesitas una razón.",
    "🌌 {nombre}, no te rindas pase lo que pase.",
    "💥 {nombre}, el deseo y la determinación mueven al cuerpo más allá de sus límites.",
    "⚔️ {nombre}, el miedo no es malo; te muestra dónde debes mejorar.",
    "🔥 {nombre}, si quieres vencer, aprende primero a soportar.",
    "🌌 {nombre}, protégente a ti mismo para poder proteger a otros.",
    "🔥 {nombre}, tu corazón es tu espada.",
    "🌙 {nombre}, no te detengas. Respira, concéntrate y avanza.",
    "⚔️ {nombre}, la determinación enciende un fuego que ni la noche apaga.",
    "⚖️ {nombre}, para obtener algo, algo de igual valor debe perderse.",
    "🔥 {nombre}, sigue adelante. No te detengas. No te arrepientas.",
    "💥 {nombre}, levántate tantas veces como haga falta.",
]
def _to_float_or_none(v):
    try:
        s = str(v).strip().replace(",", ".")
        if s == "":
            return None
        if "-" in s:
            s = s.split("-", 1)[0].strip()
        return float(s)
    except:
        return None

def _to_float_or_zero(v):
    f = _to_float_or_none(v)
    return 0.0 if f is None else f


def mensaje_motivador_del_dia(nombre: str, correo_id: str) -> str:
    """
    Devuelve un mensaje aleatorio, persistente para el día y para el usuario.
    - `correo_id` puede ser el correo normalizado que ya usas como ID de doc.
    """
    hoy = date.today().isoformat()
    key = f"mot_msg_{correo_id}_{hoy}"

    if key not in st.session_state:
        st.session_state[key] = random.choice(MENSAJES_MOTIVACIONALES).format(nombre=nombre or "Atleta")

    return st.session_state[key]

def mostrar_banner_motivador(texto: str):
    st.markdown(
        f"""
        <div style='
            background: linear-gradient(90deg, #1e88e5 0%, #42a5f5 100%);
            padding:14px 16px;
            border-radius:12px;
            margin:14px 0;
            color:white;
            font-size:18px;
            text-align:center;
            font-weight:700;'>
            {texto}
        </div>
        """,
        unsafe_allow_html=True
    )

# ✅ Normaliza cualquier "ejercicio" a dict uniforme
def _to_ej_dict(x):
    if isinstance(x, dict):
        return x
    if isinstance(x, str):
        return {
            "bloque": "",
            "seccion": "",
            "circuito": "",
            "ejercicio": x,
            "detalle": "",
            "series": "",
            "reps_min": "",
            "reps_max": "",
            "peso": "",
            "tiempo": "",
            "velocidad": "",
            "rir": "",
            "tipo": "",
            "video": "",
        }
    return {}

# ✅ Orden seguro por circuito (quita la definición duplicada)
def ordenar_circuito(ejercicio):
    if not isinstance(ejercicio, dict):
        return 99
    orden = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7}
    return orden.get(str(ejercicio.get("circuito", "")).upper(), 99)

# === Reemplaza ESTA función por una más robusta
def obtener_lista_ejercicios(data_dia):
    """
    Devuelve SIEMPRE una lista de dicts (ejercicios).
    Soporta formatos:
    - {"ejercicios": {"0": {...}, "1": {...}}}
    - {"0": {...}, "1": {...}}
    - [ {...}, {...} ]
    """
    if data_dia is None:
        return []

    # Caso dict
    if isinstance(data_dia, dict):
        # 1) Estructura con clave 'ejercicios'
        if "ejercicios" in data_dia:
            ejercicios = data_dia["ejercicios"]
            if isinstance(ejercicios, dict):
                # ordenar por índice numérico si se puede
                try:
                    pares = sorted(ejercicios.items(), key=lambda kv: int(kv[0]))
                    return [v for _, v in pares if isinstance(v, dict)]
                except Exception:
                    return [v for v in ejercicios.values() if isinstance(v, dict)]
            elif isinstance(ejercicios, list):
                return [e for e in ejercicios if isinstance(e, dict)]
            else:
                return []

        # 2) Estructura como mapa indexado {"0": {...}}
        #    (si hay claves numéricas, tomamos esos values)
        claves_numericas = [k for k in data_dia.keys() if str(k).isdigit()]
        if claves_numericas:
            try:
                pares = sorted(((k, data_dia[k]) for k in claves_numericas), key=lambda kv: int(kv[0]))
                return [v for _, v in pares if isinstance(v, dict)]
            except Exception:
                return [data_dia[k] for k in data_dia if isinstance(data_dia[k], dict)]

        # 3) Si no hay nada de lo anterior, por si acaso mira los values
        return [v for v in data_dia.values() if isinstance(v, dict)]

    # Caso lista (ya viene como lista de ejercicios o trae cosas mezcladas)
    if isinstance(data_dia, list):
        # si accidentalmente vino una lista que contiene un dict con 'ejercicios'
        if len(data_dia) == 1 and isinstance(data_dia[0], dict) and "ejercicios" in data_dia[0]:
            return obtener_lista_ejercicios(data_dia[0])
        return [e for e in data_dia if isinstance(e, dict)]

    # Cualquier otro tipo
    return []

import re

def _num_or_empty(x):
    s = str(x).strip()
    m = re.search(r"-?\d+(\.\d+)?", s)
    return m.group(0) if m else ""

def defaults_de_ejercicio(e: dict):
    # reps: prioriza reps_min; si no hay, usa 'repeticiones'
    reps_def = _num_or_empty(e.get("reps_min", "")) or _num_or_empty(e.get("repeticiones", ""))
    # peso: usa campo 'peso' del ejercicio
    peso_def = _num_or_empty(e.get("peso", ""))
    # rir: usa campo 'rir'
    rir_def  = _num_or_empty(e.get("rir", ""))
    return reps_def, peso_def, rir_def


def a_lista_de_ejercicios(ejercicios):
    if ejercicios is None:
        return []

    # Si viene como dict { "0": {...}, "1": {...} }
    if isinstance(ejercicios, dict):
        # Ordenar por clave numérica si aplica y tomar los values
        try:
            pares = sorted(ejercicios.items(), key=lambda kv: int(kv[0]))
            ejercicios = [v for _, v in pares]
        except Exception:
            # Si las claves no son numéricas, tomar values sin ordenar
            ejercicios = list(ejercicios.values())

    # Si viene como algo que no es lista ni dict, lo vacío
    if not isinstance(ejercicios, list):
        ejercicios = []

    # Filtrar solo dicts válidos
    ejercicios = [e for e in ejercicios if isinstance(e, dict)]
    return ejercicios

def ver_rutinas():
    # === INICIALIZAR FIREBASE SOLO UNA VEZ solo una===
    if not firebase_admin._apps:
        cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)

    db = firestore.client()

    def normalizar_correo(correo):
        return correo.strip().lower().replace("@", "_").replace(".", "_")

    def obtener_fecha_lunes():
        hoy = datetime.now()
        lunes = hoy - timedelta(days=hoy.weekday())
        return lunes.strftime("%Y-%m-%d")

    def es_entrenador(rol):
        return rol.lower() in ["entrenador", "admin", "administrador"]

    def puede_ver_sesion_anterior(rol: str) -> bool:
        """Solo los roles distintos a 'deportista' pueden ver el botón Sesión Anterior."""
        return rol.strip().lower() != "deportista"

    # === Endurece el key de orden para evitar crashear
    def ordenar_circuito(ejercicio):
        if not isinstance(ejercicio, dict):
            return 99
        orden = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7}
        return orden.get(str(ejercicio.get("circuito", "")).upper(), 99)
    def ordenar_circuito(ejercicio):
            orden = {"A": 1, "B": 2, "C": 3, "D": 4, "E": 5, "F": 6, "G": 7}
            return orden.get(ejercicio.get("circuito", ""), 99)

    @st.cache_data
    def cargar_rutinas_filtradas(correo, rol):
        if es_entrenador(rol):
            docs = db.collection("rutinas_semanales").stream()
        else:
            docs = db.collection("rutinas_semanales").where("correo", "==", correo).stream()
        return [doc.to_dict() for doc in docs]

    correo_raw = st.session_state.get("correo", "").strip().lower()
    if not correo_raw:
        st.error("❌ No hay correo registrado. Por favor vuelve a iniciar sesión.")
        st.stop()

    correo_norm = normalizar_correo(correo_raw)

    doc_user = db.collection("usuarios").document(correo_norm).get()
    if not doc_user.exists:
        st.error(f"❌ No se encontró el usuario con ID '{correo_norm}'. Contacta a soporte.")
        st.stop()

    datos_usuario = doc_user.to_dict()
    nombre = datos_usuario.get("nombre", "Usuario")
    rol = datos_usuario.get("rol", "desconocido")
    rol = st.session_state.get("rol", rol)
    # Mensaje motivador solo para deportistas (persistente por día)
    if rol.strip().lower() == "deportista":
        # Usa el correo normalizado como ID estable por usuario
        mensaje = mensaje_motivador_del_dia(nombre, correo_norm)
        mostrar_banner_motivador(mensaje)

    cols = st.columns([5, 1])
    with cols[1]:
        if st.button("🔄"):
            st.cache_data.clear()

    if st.checkbox("👤 Mostrar información personal", value=True):
        st.success(f"Bienvenido {nombre} ({rol})")

    rutinas = cargar_rutinas_filtradas(correo_raw, rol)
    if not rutinas:
        st.warning("⚠️ No se encontraron rutinas.")
        st.stop()

    if es_entrenador(rol):
        clientes = sorted(set(r["cliente"] for r in rutinas if "cliente" in r))
        cliente_input = st.text_input("👤 Escribe el nombre del cliente:", key="cliente_input")
        cliente_opciones = [c for c in clientes if cliente_input.lower() in c.lower()]
        cliente_sel = st.selectbox("Selecciona cliente:", cliente_opciones if cliente_opciones else clientes, key="cliente_sel")
        rutinas_cliente = [r for r in rutinas if r.get("cliente") == cliente_sel]
    else:
        rutinas_cliente = rutinas

    # ✅ Obtener correo real del cliente seleccionado
    correo_cliente = rutinas_cliente[0].get("correo", "")
    correo_cliente_norm = normalizar_correo(correo_cliente)

    semanas = sorted({r["fecha_lunes"] for r in rutinas_cliente}, reverse=True)
    semana_actual = obtener_fecha_lunes()
    semana_sel = st.selectbox("📆 Semana", semanas, index=semanas.index(semana_actual) if semana_actual in semanas else 0, key="semana_sel")

    rutina_doc = next((r for r in rutinas_cliente if r["fecha_lunes"] == semana_sel), None)
    if not rutina_doc:
        st.warning("⚠️ No hay rutina para esa semana.")
        st.stop()
    # === Mostrar bloque de rutina (si existe)
    bloque_id = rutina_doc.get("bloque_rutina")

    if bloque_id:
        # Buscar todas las semanas con este bloque para este cliente
        bloques_mismo_cliente = [
            r for r in rutinas_cliente if r.get("bloque_rutina") == bloque_id
        ]
        fechas_bloque = sorted([r["fecha_lunes"] for r in bloques_mismo_cliente])
        
        try:
            semana_actual_idx = fechas_bloque.index(semana_sel) + 1
            total_semanas_bloque = len(fechas_bloque)
            st.markdown(f"📦 <b>Bloque de rutina:</b> Semana {semana_actual_idx} de {total_semanas_bloque}", unsafe_allow_html=True)
        except ValueError:
            st.info("ℹ️ Semana no encontrada en bloque de rutina.")
    else:
        st.warning("⚠️ Esta rutina no tiene un identificador de bloque.")

    dias_disponibles = sorted(
        [k for k in rutina_doc["rutina"].keys() if k.isdigit()],
        key=int
    )

    # === Donde obtienes los ejercicios del día, usa SIEMPRE el extractor
    dia_sel = st.selectbox("📅 Día", dias_disponibles, key="dia_sel")
    ejercicios = obtener_lista_ejercicios(rutina_doc["rutina"][dia_sel])
    ejercicios.sort(key=ordenar_circuito)


    st.markdown(f"### Ejercicios del día {dia_sel}")
    
    st.markdown("""
        <style>
        .compact-input input { font-size: 12px !important; width: 100px !important; }
        .linea-blanca { border-bottom: 2px solid white; margin: 15px 0; }
        .ejercicio { font-size: 18px !important; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)

    ejercicios_por_circuito = {}
    for e in ejercicios:
        circuito = e.get("circuito", "Z").upper()
        ejercicios_por_circuito.setdefault(circuito, []).append(e)

    for circuito, lista in sorted(ejercicios_por_circuito.items()):
        if circuito == "A":
            st.subheader("Warm-Up")
        elif circuito == "D":
            st.subheader("Workout")

        st.markdown(f"### Circuito {circuito}")
        st.markdown("<div class='bloque'>", unsafe_allow_html=True)

        for idx, e in enumerate(lista):
            ejercicio = e.get("ejercicio", f"Ejercicio {idx+1}")
            ejercicio_id = f"{circuito}_{ejercicio}_{idx}".lower().replace(" ", "_").replace("(", "").replace(")", "").replace("/", "")
            # === Obtener información del ejercicio ===
            ejercicio = e.get("ejercicio", f"Ejercicio {idx+1}")
            detalle = e.get("detalle", "").strip()
            series = e.get("series", "")
            peso = e.get("peso", "")
            reps_min = e.get("reps_min") or e.get("RepsMin", "")
            reps_max = e.get("reps_max") or e.get("RepsMax", "")
            repeticiones = e.get("repeticiones", "")
            rir = e.get("rir", "")
            tiempo = e.get("tiempo", "")

            # === Construir string de repeticiones
            if reps_min != "" and reps_max != "":
                rep_str = f"{series}x {reps_min} a {reps_max}"
            elif reps_min != "":
                rep_str = f"{series}x{reps_min}+"
            elif reps_max != "":
                rep_str = f"{series}x≤{reps_max}"
            elif repeticiones:
                rep_str = f"{series}x{repeticiones}"
            else:
                rep_str = f"{series}x"

            peso_str = f"{peso}kg" if peso else ""
            tiempo_str = f"{tiempo} seg" if tiempo else ""
            rir_str = f"RIR {rir}" if rir else ""

            info_partes = [rep_str]
            if peso_str: info_partes.append(peso_str)
            if tiempo_str: info_partes.append(tiempo_str)
            if rir_str: info_partes.append(rir_str)
            info_str = " · ".join(info_partes)

            # === Mostrar nombre + detalle si existe
            nombre_mostrar = ejercicio
            if detalle:
                nombre_mostrar += f" — {detalle}"

            # === Mostrar como botón solo si tiene video
            video_url = e.get("video", "").strip()
            video_btn_key = f"video_btn_{circuito}_{idx}"
            mostrar_video_key = f"mostrar_video_{circuito}_{idx}"

            if video_url:
                boton_presionado = st.button(
                    f"{nombre_mostrar} 🎥 — {info_str}",
                    key=video_btn_key,
                    help="Haz clic para ver video"
                )

                if boton_presionado:
                    st.session_state[mostrar_video_key] = not st.session_state.get(mostrar_video_key, False)

                # Mostrar video si fue activado
                if st.session_state.get(mostrar_video_key, False):
                    if "youtube.com/shorts/" in video_url:
                        try:
                            video_id = video_url.split("shorts/")[1].split("?")[0]
                            video_url = f"https://www.youtube.com/watch?v={video_id}"
                        except:
                            pass
                    st.video(video_url)
            else:
                # Sin video ➜ solo texto
                st.markdown(f"**{nombre_mostrar} — {info_str}**")

            # === Verificar si hay datos de la sesión anterior antes de mostrar el botón
            hay_sesion_anterior = False
            match_ant = None

            try:
                idx_semana_actual = semanas.index(semana_sel)
                if idx_semana_actual + 1 < len(semanas):
                    semana_ant = semanas[idx_semana_actual + 1]
                    doc_ant = next((r for r in rutinas_cliente if r["fecha_lunes"] == semana_ant), None)

                    if doc_ant:
                        # === En la sección "sesión anterior", usa el mismo extractor
                        ...
                        rutina_ant = doc_ant.get("rutina", {})
                        ejercicios_ant = obtener_lista_ejercicios(rutina_ant.get(str(dia_sel), []))
                        ...

                        nombre_actual = e.get("ejercicio", "").strip().lower()
                        circuito_actual = e.get("circuito", "").strip().lower()

                        match_ant = next(
                            (
                                ex for ex in ejercicios_ant
                                if ex.get("ejercicio", "").strip().lower() == nombre_actual and
                                ex.get("circuito", "").strip().lower() == circuito_actual
                            ),
                            None
                        )

                        if match_ant:
                            hay_sesion_anterior = True
            except Exception as err:
                st.warning(f"⚠️ Error buscando sesión anterior: {err}")

            
            # === Mostrar el botón solo si hay sesión anterior Y el rol lo permite
            if hay_sesion_anterior and puede_ver_sesion_anterior(rol):
                ver_sesion_ant = st.checkbox("📂 Sesión anterior", key=f"prev_{ejercicio_id}")
                if ver_sesion_ant:
                    series_ant = match_ant.get("series_data", [])
                    if match_ant and isinstance(series_ant, list) and len(series_ant) > 0:
                        st.markdown("📌 <b>Datos de la sesión anterior:</b>", unsafe_allow_html=True)
                        for s_idx, serie_ant in enumerate(series_ant):
                            reps = serie_ant.get("reps", "-") or "-"
                            peso = serie_ant.get("peso", "-") or "-"
                            rir  = serie_ant.get("rir", "-")  or "-"
                            st.markdown(
                                f"<div style='font-size:16px; padding-left:10px;'>"
                                f"<b>Serie {s_idx+1}:</b> {reps} reps · {peso} kg · RIR {rir if rir != '' else '-'}</div>",
                                unsafe_allow_html=True
                            )
                    else:
                        st.info("ℹ️ No hay datos registrados de la sesión anterior para este ejercicio.")

        # === Mostrar reporte por circuito ===
        if f"mostrar_reporte_{circuito}" not in st.session_state:
            st.session_state[f"mostrar_reporte_{circuito}"] = False

        if st.button(f"📝 Reporte {circuito}", key=f"btn_reporte_{circuito}"):
            st.session_state[f"mostrar_reporte_{circuito}"] = not st.session_state[f"mostrar_reporte_{circuito}"]

        if st.session_state[f"mostrar_reporte_{circuito}"]:
            st.markdown(f"### 📋 Registro del circuito {circuito}")

            for idx, e in enumerate(lista):
                ejercicio = e.get("ejercicio", f"Ejercicio {idx+1}")
                ejercicio_id = f"{circuito}_{ejercicio}_{idx}".lower().replace(" ", "_").replace("(", "").replace(")", "").replace("/", "")
                st.markdown(f"#### {ejercicio}")

                try:
                    num_series = int(e.get("series", 0))
                except:
                    num_series = 0

                # Construir/ajustar series_data con defaults (reps_min, peso, rir)
                reps_def, peso_def, rir_def = defaults_de_ejercicio(e)

                if "series_data" not in e or not isinstance(e["series_data"], list) or len(e["series_data"]) != num_series:
                    e["series_data"] = [{"reps": reps_def, "peso": peso_def, "rir": rir_def} for _ in range(num_series)]
                else:
                    # Si ya hay series_data, solo rellenar los campos vacíos con defaults
                    for s in e["series_data"]:
                        if not str(s.get("reps", "")).strip():
                            s["reps"] = reps_def
                        if not str(s.get("peso", "")).strip():
                            s["peso"] = peso_def
                        if not str(s.get("rir", "")).strip():
                            s["rir"] = rir_def

                for s_idx in range(num_series):
                    st.markdown(f"**Serie {s_idx + 1}**")
                    s_cols = st.columns(3)

                    e["series_data"][s_idx]["reps"] = s_cols[0].text_input(
                        "Reps", value=e["series_data"][s_idx].get("reps", ""),
                        placeholder="Reps", key=f"rep_{ejercicio_id}_{s_idx}", label_visibility="collapsed"
                    )

                    e["series_data"][s_idx]["peso"] = s_cols[1].text_input(
                        "Peso", value=e["series_data"][s_idx].get("peso", ""),
                        placeholder="Kg", key=f"peso_{ejercicio_id}_{s_idx}", label_visibility="collapsed"
                    )

                    e["series_data"][s_idx]["rir"] = s_cols[2].text_input(
                        "RIR", value=e["series_data"][s_idx].get("rir", ""),
                        placeholder="RIR", key=f"rir_{ejercicio_id}_{s_idx}", label_visibility="collapsed"
                    )

                e["comentario"] = st.text_input(
                    "Comentario general", value=e.get("comentario", ""),
                    placeholder="Comentario", key=f"coment_{ejercicio_id}"
                )

    # === RPE DE LA SESIÓN ===
    rpe_key = f"rpe_sesion_{semana_sel}_{dia_sel}"
    valor_rpe_inicial = rutina_doc["rutina"].get(dia_sel + "_rpe", "")

    st.markdown("### 📌 RPE de la sesión")
    rpe_valor = st.number_input(
    "RPE percibido del día (0-10)", min_value=0.0, max_value=10.0, step=0.5,
    value=float(valor_rpe_inicial) if valor_rpe_inicial != "" else 0.0,
    key=rpe_key
)
    st.markdown("---")
    
    # ✅ GUARDAR CAMBIOS (reemplaza este bloque completo)
    if st.button("💾 Guardar cambios del día", key=f"guardar_{dia_sel}_{semana_sel}"):
        with st.spinner("Guardando..."):
            fecha_norm = semana_sel.replace("-", "_")
            doc_id = f"{correo_cliente_norm}_{fecha_norm}"

            try:
                semanas_futuras = sorted([s for s in semanas if s > semana_sel])

                for idx, e in enumerate(ejercicios):
                    series_data = e.get("series_data", [])
                    pesos, reps, rirs = [], [], []

                    for s_idx, s in enumerate(series_data):
                        peso_raw = s.get("peso", "").strip()
                        reps_raw = s.get("reps", "").strip()
                        rir_raw  = s.get("rir", "").strip()

                        # Silenciado: solo parseo, sin prints
                        try:
                            val = peso_raw.replace(",", ".").replace("kg", "").strip()
                            if val != "":
                                pesos.append(float(val))
                        except:
                            pass
                        try:
                            if reps_raw.isdigit():
                                reps.append(int(reps_raw))
                        except:
                            pass
                        try:
                            val = rir_raw.replace(",", ".")
                            if val != "":
                                rirs.append(float(val))
                        except:
                            pass

                    peso_alcanzado  = max(pesos) if pesos else None
                    reps_alcanzadas = max(reps)  if reps  else None
                    rir_alcanzado   = min(rirs)  if rirs  else None

                    if peso_alcanzado is not None: e["peso_alcanzado"] = peso_alcanzado
                    if reps_alcanzadas is not None: e["reps_alcanzadas"] = reps_alcanzadas
                    if rir_alcanzado is not None:   e["rir_alcanzado"]  = rir_alcanzado

                    comentario = e.get("comentario", "").strip()
                    hay_input = bool(pesos or reps or rirs or comentario)
                    if hay_input:
                        e["coach_responsable"] = correo_raw

                    # Si no hay peso alcanzado, omite silenciosamente
                    if peso_alcanzado is None:
                        continue

                    # Actualiza progresión sin imprimir
                    actualizar_progresiones_individual(
                        nombre=rutina_doc.get("cliente", ""),
                        correo=correo_cliente,
                        ejercicio=e["ejercicio"],
                        circuito=e.get("circuito", ""),
                        bloque=e.get("bloque", e.get("seccion", "")),
                        fecha_actual_lunes=semana_sel,
                        dia_numero=int(dia_sel),
                        peso_alcanzado=peso_alcanzado
                    )

                    # Propaga delta de peso a semanas futuras
                    # Propaga delta de peso a semanas futuras (todo como float)
                    peso_actual = _to_float_or_zero(e.get("peso"))
                    delta = float(peso_alcanzado) - float(peso_actual)

                    if delta == 0:
                        continue

                    nombre_ejercicio = e["ejercicio"]
                    circuito = e.get("circuito", "")
                    bloque   = e.get("bloque", e.get("seccion", ""))

                    for s in semanas_futuras:
                        fecha_norm_fut = s.replace("-", "_")
                        doc_id_fut = f"{correo_cliente_norm}_{fecha_norm_fut}"
                        doc_ref = db.collection("rutinas_semanales").document(doc_id_fut)
                        doc = doc_ref.get()
                        if not doc.exists:
                            continue

                        rutina_fut = doc.to_dict().get("rutina", {})
                        # ✅ usar siempre el extractor (soporta dict/list/'ejercicios')
                        ejercicios_fut_raw = rutina_fut.get(dia_sel, [])
                        ejercicios_fut = obtener_lista_ejercicios(ejercicios_fut_raw)

                        changed = False
                        for j, ef_raw in enumerate(ejercicios_fut):
                            ef = _to_ej_dict(ef_raw)  # <-- normaliza si venía como string

                            mismo_ejercicio = (ef.get("ejercicio", "") == nombre_ejercicio)
                            mismo_circuito  = (ef.get("circuito", "")  == circuito)
                            mismo_bloque    = (ef.get("bloque", ef.get("seccion", "")) == bloque)

                            if mismo_ejercicio and mismo_circuito and mismo_bloque:
                                base = _to_float_or_zero(ef.get("peso"))
                                ef["peso"] = round(base + float(delta), 2)

                                ejercicios_fut[j] = ef
                                changed = True

                        if changed:
                            # Guardar el día como lista uniforme
                            doc_ref.update({f"rutina.{dia_sel}": ejercicios_fut})


                # ✅ Actualiza documento actual
                doc_ref_final = db.collection("rutinas_semanales").document(doc_id)
                doc_final = doc_ref_final.get()

                if doc_final.exists:
                    doc_ref_final.update({
                        f"rutina.{dia_sel}": ejercicios,
                        f"rutina.{dia_sel}_rpe": rpe_valor
                    })
                    # ✅ ÚNICO MENSAJE FINAL
                    if rol.strip().lower() == "deportista":
                        st.success(f"✅ Cambios guardados, {nombre}. ¡Buen entrenamiento! 💪")
                    else:
                        st.success(f"✅ Cambios guardados para {rutina_doc.get('cliente','')}.")
                else:
                    # si prefieres ocultar también este warning, cámbialo a 'pass'
                    st.warning("⚠️ No se encontró el documento. No se guardaron los cambios.")
            except Exception as e:
                st.error("❌ Error durante el guardado.")
                st.exception(e)
