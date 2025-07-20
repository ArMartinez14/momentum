import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import json
from herramientas import actualizar_progresiones_individual


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

    dias_disponibles = sorted(rutina_doc["rutina"].keys(), key=int)
    dia_sel = st.selectbox("📅 Día", dias_disponibles, key="dia_sel")

    ejercicios = rutina_doc["rutina"][dia_sel]
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
            # === Inicio del bucle de ejercicios
            ejercicio = e.get("ejercicio", f"Ejercicio {idx+1}")
            series = e.get("series", "")
            reps = e.get("repeticiones", "")
            peso = e.get("peso", "")
            ejercicio_id = f"{circuito}_{ejercicio}_{idx}".lower().replace(" ", "_").replace("(", "").replace(")", "").replace("/", "")

            peso_str = f"{peso}kg" if peso else ""
            tiempo = e.get("tiempo", "")
            tiempo_str = f"{tiempo} seg" if tiempo else ""
            rir = e.get("rir", "")
            rir_str = f"RIR {rir}" if rir else ""

            # === Buscar datos alcanzados de la semana anterior (para mostrarlos esta semana)
            reps_alcanzadas = None
            rir_alcanzado = None

            try:
                idx_actual = semanas.index(semana_sel)
                if idx_actual + 1 < len(semanas):
                    semana_anterior = semanas[idx_actual + 1]
                    doc_ant = next((r for r in rutinas_cliente if r["fecha_lunes"] == semana_anterior), None)
                    if doc_ant:
                        ejercicios_prev = doc_ant.get("rutina", {}).get(str(dia_sel), [])
                        nombre_actual = e.get("ejercicio", "").strip().lower()
                        circuito_actual = e.get("circuito", "").strip().lower()
                        match_prev = next(
                            (
                                ex for ex in ejercicios_prev
                                if ex.get("ejercicio", "").strip().lower() == nombre_actual and
                                ex.get("circuito", "").strip().lower() == circuito_actual
                            ),
                            None
                        )
                        if match_prev:
                            reps_alcanzadas = match_prev.get("reps_alcanzadas")
                            rir_alcanzado = match_prev.get("rir_alcanzado")
            except Exception as err:
                st.error(f"⚠️ Error buscando valores alcanzados previos: {err}")


            # === Mostrar repeticiones en formato mínimo-máximo ===
            reps_min = e.get("reps_min", "")
            reps_max = e.get("reps_max", "")
            series = e.get("series", "")

            # Asegurarse que todo sea string (por seguridad en join/display)
            rep_min_str = str(reps_min) if reps_min != "" else ""
            rep_max_str = str(reps_max) if reps_max != "" else ""

            if rep_min_str and rep_max_str:
                rep_str = f"{series}x {rep_min_str} a {rep_max_str}"
            elif rep_min_str:
                rep_str = f"{series}x{rep_min_str}+"
            elif rep_max_str:
                rep_str = f"{series}x≤{rep_max_str}"
            else:
                rep_str = f"{series}x"

            rir_str = f"RIR {rir}"
            if rir_alcanzado is not None:
                try:
                    rir_str += f"({int(rir_alcanzado)})"
                except:
                    pass


            info_partes = [rep_str]
            if peso_str:
                info_partes.append(peso_str)
            if tiempo_str:
                info_partes.append(tiempo_str)
            if rir_str:
                info_partes.append(rir_str)


            info_str = " · ".join(info_partes)

            st.markdown(
                f"<div class='ejercicio'>{ejercicio} &nbsp; <span style='font-size:16px; font-weight:normal;'>{info_str}</span></div>",
                unsafe_allow_html=True
            )

            col1, col2 = st.columns([1, 1.2])
            editar = col1.checkbox(f"Editar ejercicio {idx+1}", key=f"edit_{circuito}_{idx}")
            ver_sesion_ant = col2.checkbox("📂 Sesión anterior", key=f"prev_{circuito}_{idx}")

            match_ant = None  # se usa si copiamos luego

            # === Mostrar sesión anterior aunque NO se edite
            if ver_sesion_ant:
                try:
                    idx_semana_actual = semanas.index(semana_sel)
                    if idx_semana_actual + 1 < len(semanas):
                        semana_ant = semanas[idx_semana_actual + 1]
                        #st.info(f"🔍 Buscando en semana anterior: `{semana_ant}`")

                        doc_ant = next((r for r in rutinas_cliente if r["fecha_lunes"] == semana_ant), None)

                        if doc_ant:
                            rutina_ant = doc_ant.get("rutina", {})
                            ejercicios_ant = rutina_ant.get(str(dia_sel), [])

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

                            if match_ant and isinstance(match_ant.get("series_data", []), list):
                                if ver_sesion_ant:
                                    st.markdown("📌 <b>Datos de la sesión anterior:</b>", unsafe_allow_html=True)
                                    for s_idx, serie_ant in enumerate(match_ant["series_data"]):
                                        reps = serie_ant.get("reps", "-") or "-"
                                        peso = serie_ant.get("peso", "-") or "-"
                                        rir = serie_ant.get("rir", "-") or "-"
                                        st.markdown(
                                            f"<div style='font-size:16px; padding-left:10px;'>"
                                            f" <b>Serie {s_idx+1}:</b> {reps}x{peso}kg · RIR {rir}"
                                            f"</div>",
                                            unsafe_allow_html=True
                                        )
                            
                            else:
                                st.warning("⚠️ No se encontró ejercicio coincidente.")
                        else:
                            st.warning("⚠️ No se encontró documento de semana anterior.")
                    else:
                        st.info("ℹ️ Esta es la semana más antigua disponible.")
                except Exception as err:
                    st.error(f"❌ Error buscando datos anteriores: {err}")

            # === Edición del ejercicio (solo si está activo)
            if editar:
                try:
                    num_series = int(e.get("series", 0))
                except:
                    num_series = 0

                if "series_data" not in e or not isinstance(e["series_data"], list) or len(e["series_data"]) != num_series:
                    e["series_data"] = [{"reps": "", "peso": "", "rir": ""} for _ in range(num_series)]

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

            if e.get("video"):
                st.video(e["video"])



        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div class='linea-blanca'></div>", unsafe_allow_html=True)

    # === RPE DE LA SESIÓN ===
    rpe_key = f"rpe_sesion_{semana_sel}_{dia_sel}"
    valor_rpe_inicial = rutina_doc["rutina"].get(dia_sel + "_rpe", "")

    st.markdown("### 📌 RPE de la sesión")
    rpe_valor = st.number_input(
    "RPE percibido del día (0-10)", min_value=0.0, max_value=10.0, step=0.5,
    value=float(valor_rpe_inicial) if valor_rpe_inicial != "" else 0.0,
    key=rpe_key
)

    # ✅ GUARDAR CAMBIOS
    if st.button("💾 Guardar cambios del día", key=f"guardar_{dia_sel}_{semana_sel}"):
        st.info("🚀 Iniciando guardado paso a paso...")

        fecha_norm = semana_sel.replace("-", "_")
        doc_id = f"{correo_cliente_norm}_{fecha_norm}"
        st.write(f"📌 Documento base: `{doc_id}`")

        try:
            semanas_futuras = sorted([s for s in semanas if s > semana_sel])
            st.write(f"📅 Semanas futuras encontradas: {semanas_futuras}")

            for idx, e in enumerate(ejercicios):
                series_data = e.get("series_data", [])

                pesos, reps, rirs = [], [], []

                for s_idx, s in enumerate(series_data):
                    peso_raw = s.get("peso", "").strip()
                    reps_raw = s.get("reps", "").strip()
                    rir_raw = s.get("rir", "").strip()

                    try:
                        if peso_raw.replace(",", ".").replace("kg", "").strip() != "":
                            peso_val = float(peso_raw.replace(",", ".").replace("kg", "").strip())
                            pesos.append(peso_val)
                    except Exception as err:
                        st.write(f"❌ Error en peso serie {s_idx+1}: {peso_raw} ➜ {err}")

                    try:
                        if reps_raw.isdigit():
                            reps_val = int(reps_raw)
                            reps.append(reps_val)
                    except Exception as err:
                        st.write(f"❌ Error en reps serie {s_idx+1}: {reps_raw} ➜ {err}")

                    try:
                        if rir_raw.replace(",", ".") != "":
                            rir_val = float(rir_raw.replace(",", "."))
                            rirs.append(rir_val)
                    except Exception as err:
                        st.write(f"❌ Error en RIR serie {s_idx+1}: {rir_raw} ➜ {err}")

                peso_alcanzado = max(pesos) if pesos else None
                reps_alcanzadas = max(reps) if reps else None
                rir_alcanzado = min(rirs) if rirs else None

                if peso_alcanzado is not None:
                    e["peso_alcanzado"] = peso_alcanzado
                if reps_alcanzadas is not None:
                    e["reps_alcanzadas"] = reps_alcanzadas
                if rir_alcanzado is not None:
                    e["rir_alcanzado"] = rir_alcanzado
                # Detectar si el coach editó algo
                comentario = e.get("comentario", "").strip()
                hay_input = bool(pesos or reps or rirs or comentario)

                if hay_input:
                    e["coach_responsable"] = correo_raw
                    st.write(f"   🧑‍🏫 Coach responsable: {correo_raw}")

                st.write(f"➡️ [{idx}] Ejercicio: `{e['ejercicio']}`")
                st.write(f"   🔑 Variables:")
                st.write(f"   - peso_actual: {e.get('peso', 0)}")
                st.write(f"   - peso_alcanzado: {peso_alcanzado}")
                st.write(f"   - reps_alcanzadas: {reps_alcanzadas}")
                st.write(f"   - rir_alcanzado: {rir_alcanzado}")

                if peso_alcanzado is None:
                    st.warning("   ⚠️ No hay peso válido para este ejercicio. Se omite.")
                    continue

                st.write(f"   🔄 Llamando `actualizar_progresiones_individual()` ...")
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
                st.write("   ✅ Progresión individual actualizada.")

                peso_actual = float(e.get("peso", 0))
                delta = peso_alcanzado - peso_actual
                st.write(f"   📐 Delta = {peso_alcanzado} - {peso_actual} = {delta}")

                if delta == 0:
                    st.write("   ⚠️ Delta = 0 ➜ No se aplican cambios a semanas futuras.")
                    continue

                nombre_ejercicio = e["ejercicio"]
                circuito = e.get("circuito", "")
                bloque = e.get("bloque", e.get("seccion", ""))
                peso_base = peso_actual

                for s in semanas_futuras:
                    fecha_norm_fut = s.replace("-", "_")
                    doc_id_fut = f"{correo_cliente_norm}_{fecha_norm_fut}"
                    st.write(f"   📌 Semana `{s}` ➜ Documento `{doc_id_fut}` ➜ Aplicar delta de {delta}kg")

                    doc_ref = db.collection("rutinas_semanales").document(doc_id_fut)
                    doc = doc_ref.get()

                    if doc.exists:
                        rutina_fut = doc.to_dict().get("rutina", {})
                        ejercicios_fut = rutina_fut.get(dia_sel, [])

                        for ef in ejercicios_fut:
                            if (
                                ef.get("ejercicio") == nombre_ejercicio and
                                ef.get("circuito") == circuito and
                                (ef.get("bloque") == bloque or ef.get("seccion") == bloque)
                            ):
                                peso_futuro_original = float(ef.get("peso", 0))
                                nuevo_peso = round(peso_futuro_original + delta, 2)
                                ef["peso"] = nuevo_peso
                                st.write(f"      ✔️ `{ef['ejercicio']}`: {peso_futuro_original} + {delta} = {nuevo_peso}kg")

                        # ✅ Actualizar solo el día específico
                        doc_ref.update({f"rutina.{dia_sel}": ejercicios_fut})
                        st.write(f"   🔄 Documento `{doc_id_fut}` actualizado con éxito.")
                    else:
                        st.warning(f"⚠️ Documento `{doc_id_fut}` no existe ➜ Se omite.")

            # ✅ Paso final: guardar nuevamente ejercicios actualizados en la semana actual
            # ✅ Guardar ejercicios y RPE
            db.collection("rutinas_semanales").document(doc_id).update({
                f"rutina.{dia_sel}": ejercicios,
                f"rutina.{dia_sel}_rpe": rpe_valor
            })

            st.success(f"✅ TODOS LOS CAMBIOS guardados correctamente en `{doc_id}`.")

        except Exception as e:
            st.error("❌ Error durante el guardado paso a paso.")
            st.exception(e)
