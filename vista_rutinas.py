import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta
import json
from herramientas import actualizar_progresiones_individual


def ver_rutinas():
    # === INICIALIZAR FIREBASE SOLO UNA VEZ solo una===
    if not firebase_admin._apps:
        # ✅ Cargar credenciales desde el Secret de Streamlit
        cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)

    db = firestore.client()

    # === Función utilidades ===
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

    # === 1️⃣ OBTENER CORREO y ROL desde session_state ===
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

    # === 2️⃣ MOSTRAR INFO USUARIO ===
    mostrar_info = st.checkbox("👤 Mostrar información personal", value=True)
    if mostrar_info:
        st.success(f"Bienvenido {nombre} ({rol})")

    # === 3️⃣ CARGAR RUTINAS FILTRADAS ===
    rutinas = cargar_rutinas_filtradas(correo_raw, rol)
    if not rutinas:
        st.warning("⚠️ No se encontraron rutinas.")
        st.stop()

    # === 4️⃣ FILTRO CLIENTE Y SEMANA ===
    if es_entrenador(rol):
        clientes = sorted(set(r["cliente"] for r in rutinas if "cliente" in r))
        cliente_input = st.text_input("👤 Escribe el nombre del cliente:", key="cliente_input")
        cliente_opciones = [c for c in clientes if cliente_input.lower() in c.lower()]
        cliente_sel = st.selectbox(
            "Selecciona cliente:",
            cliente_opciones if cliente_opciones else clientes,
            key="cliente_sel"
        )
        rutinas_cliente = [r for r in rutinas if r.get("cliente") == cliente_sel]
    else:
        rutinas_cliente = rutinas

    semanas = sorted({r["fecha_lunes"] for r in rutinas_cliente}, reverse=True)
    semana_actual = obtener_fecha_lunes()
    semana_sel = st.selectbox(
        "📆 Semana",
        semanas,
        index=semanas.index(semana_actual) if semana_actual in semanas else 0,
        key="semana_sel"
    )

    rutina_doc = next((r for r in rutinas_cliente if r["fecha_lunes"] == semana_sel), None)
    if not rutina_doc:
        st.warning("⚠️ No hay rutina para esa semana.")
        st.stop()

    # === 5️⃣ SELECCIONAR DÍA ===
    dias_disponibles = sorted(rutina_doc["rutina"].keys(), key=int)
    dia_sel = st.selectbox("📅 Día", dias_disponibles, key="dia_sel")

    ejercicios = rutina_doc["rutina"][dia_sel]
    ejercicios.sort(key=ordenar_circuito)

    st.markdown(f"### Ejercicios del día {dia_sel}")

    # === 6️⃣ ESTILOS ===
    st.markdown("""
        <style>
        .compact-input input { font-size: 12px !important; width: 100px !important; }
        .linea-blanca { border-bottom: 2px solid white; margin: 15px 0; }
        .ejercicio { font-size: 18px !important; font-weight: bold; }
        </style>
    """, unsafe_allow_html=True)

    # === 7️⃣ MOSTRAR EJERCICIOS POR CIRCUITO ===
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
            series = e.get("series", "")
            reps = e.get("repeticiones", "")
            peso = e.get("peso", "")
            ejercicio_id = f"{circuito}_{ejercicio}_{idx}".lower().replace(" ", "_").replace("(", "").replace(")", "").replace("/", "")

            st.markdown(
                f"<div class='ejercicio'>{ejercicio} &nbsp; <span style='font-size:16px; font-weight:normal;'>{series}x{reps} · {peso}kg</span></div>",
                unsafe_allow_html=True
            )

            mostrar = st.checkbox(f"Editar ejercicio {idx+1}", key=f"edit_{circuito}_{idx}")

            if mostrar:
                col1, col2 = st.columns([3, 1])
                with col1:
                    e["peso_alcanzado"] = st.text_input(
                        "",
                        value=e.get("peso_alcanzado", ""),
                        placeholder="Peso",
                        key=f"peso_{ejercicio_id}",
                        label_visibility="collapsed"
                    )
                    e["comentario"] = st.text_input(
                        "",
                        value=e.get("comentario", ""),
                        placeholder="Comentario",
                        key=f"coment_{ejercicio_id}",
                        label_visibility="collapsed"
                    )
                with col2:
                    e["rir"] = st.text_input(
                        "",
                        value=e.get("rir", ""),
                        placeholder="RIR",
                        key=f"rir_{ejercicio_id}",
                        label_visibility="collapsed"
                    )

            if e.get("video"):
                st.video(e["video"])

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div class='linea-blanca'></div>", unsafe_allow_html=True)

    # === 8️⃣ BOTÓN GUARDAR CAMBIOS ===
            # === 8️⃣ BOTÓN GUARDAR CAMBIOS ===
        if st.button("💾 Guardar cambios del día"):
            fecha_norm = semana_sel.replace("-", "_")
            doc_id = f"{correo_norm}_{fecha_norm}"

            try:
                # 1️⃣ Guarda semana actual
                db.collection("rutinas_semanales").document(doc_id).update({ f"rutina.{dia_sel}": ejercicios })
                st.success("✅ Día actualizado correctamente.")

                # 2️⃣ Detecta semanas futuras
                semanas_futuras = sorted([s for s in semanas if s > semana_sel])

                for e in ejercicios:
                    if e.get("peso_alcanzado"):
                        # Actualiza progresión individual
                        actualizar_progresiones_individual(
                            nombre=rutina_doc.get("cliente", ""),
                            correo=correo_raw,  # usa el original, NO normalizado
                            ejercicio=e["ejercicio"],
                            circuito=e.get("circuito", ""),
                            bloque=e.get("bloque", e.get("seccion", "")),
                            fecha_actual_lunes=semana_sel,
                            dia_numero=int(dia_sel),
                            peso_alcanzado=float(e["peso_alcanzado"])
                        )

                        try:
                            peso_alcanzado = float(e["peso_alcanzado"])
                            peso_actual = float(e.get("peso", 0))
                            delta = peso_alcanzado - peso_actual

                            if delta == 0:
                                continue  # sin cambios

                            nombre_ejercicio = e["ejercicio"]
                            circuito = e.get("circuito", "")
                            bloque = e.get("bloque", e.get("seccion", ""))

                            peso_base = peso_actual

                            for s in semanas_futuras:
                                peso_base += delta  # aplica delta acumulado

                                fecha_norm_futura = s.replace("-", "_")
                                doc_id_futuro = f"{correo_norm}_{fecha_norm_futura}"

                                doc_ref = db.collection("rutinas_semanales").document(doc_id_futuro)
                                doc = doc_ref.get()

                                if doc.exists:
                                    rutina_futura = doc.to_dict().get("rutina", {})
                                    ejercicios_futuros = rutina_futura.get(dia_sel, [])

                                    for ef in ejercicios_futuros:
                                        if (
                                            ef.get("ejercicio") == nombre_ejercicio and
                                            ef.get("circuito") == circuito and
                                            (ef.get("bloque") == bloque or ef.get("seccion") == bloque)
                                        ):
                                            ef["peso"] = round(peso_base, 2)

                                    doc_ref.update({ f"rutina.{dia_sel}": ejercicios_futuros })

                        except Exception as inner_error:
                            st.warning(f"⚠️ Error aplicando delta: {inner_error}")

            except Exception as error:
                st.error("❌ Error al guardar.")
                st.exception(error)
