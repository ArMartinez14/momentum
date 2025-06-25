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
            ejercicio = e.get("ejercicio", f"Ejercicio {idx+1}")
            series = e.get("series", "")
            reps = e.get("repeticiones", "")
            peso = e.get("peso", "")
            ejercicio_id = f"{circuito}_{ejercicio}_{idx}".lower().replace(" ", "_").replace("(", "").replace(")", "").replace("/", "")

            st.markdown(
                f"<div class='ejercicio'>{ejercicio} &nbsp; <span style='font-size:16px; font-weight:normal;'>{series}x{reps} · {peso}kg</span></div>",
                unsafe_allow_html=True
            )

            if st.checkbox(f"Editar ejercicio {idx+1}", key=f"edit_{circuito}_{idx}"):
                col1, col2 = st.columns([3, 1])
                with col1:
                    e["peso_alcanzado"] = st.text_input("", value=e.get("peso_alcanzado", ""), placeholder="Peso", key=f"peso_{ejercicio_id}", label_visibility="collapsed")
                    e["comentario"] = st.text_input("", value=e.get("comentario", ""), placeholder="Comentario", key=f"coment_{ejercicio_id}", label_visibility="collapsed")
                with col2:
                    e["rir"] = st.text_input("", value=e.get("rir", ""), placeholder="RIR", key=f"rir_{ejercicio_id}", label_visibility="collapsed")

            if e.get("video"):
                st.video(e["video"])

        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div class='linea-blanca'></div>", unsafe_allow_html=True)

    # ✅ GUARDAR CAMBIOS
    if st.button("💾 Guardar cambios del día", key=f"guardar_{dia_sel}_{semana_sel}"):
        st.info("🚀 Iniciando guardado paso a paso...")

        fecha_norm = semana_sel.replace("-", "_")
        doc_id = f"{correo_cliente_norm}_{fecha_norm}"
        st.write(f"📌 Documento base: `{doc_id}`")

        try:
            st.write(f"📝 Guardando cambios en `{doc_id}` campo `rutina.{dia_sel}`...")
            db.collection("rutinas_semanales").document(doc_id).update({
                f"rutina.{dia_sel}": ejercicios
            })
            st.success(f"✅ Día `{dia_sel}` guardado correctamente en `{doc_id}`.")

            semanas_futuras = sorted([s for s in semanas if s > semana_sel])
            st.write(f"📅 Semanas futuras encontradas: {semanas_futuras}")

            for idx, e in enumerate(ejercicios):
                if e.get("peso_alcanzado"):
                    st.write(f"➡️ [{idx}] Ejercicio: `{e['ejercicio']}`")
                    st.write(f"   🔑 Variables:")
                    st.write(f"   - peso_actual: {e.get('peso', 0)}")
                    st.write(f"   - peso_alcanzado: {e['peso_alcanzado']}")

                    st.write(f"   🔄 Llamando `actualizar_progresiones_individual()` ...")
                    actualizar_progresiones_individual(
                        nombre=rutina_doc.get("cliente", ""),
                        correo=correo_cliente,  # ✅ ahora usa el correo correcto
                        ejercicio=e["ejercicio"],
                        circuito=e.get("circuito", ""),
                        bloque=e.get("bloque", e.get("seccion", "")),
                        fecha_actual_lunes=semana_sel,
                        dia_numero=int(dia_sel),
                        peso_alcanzado=float(e["peso_alcanzado"])
                    )
                    st.write("   ✅ Progresión individual actualizada.")

                    peso_alcanzado = float(e["peso_alcanzado"])
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
                        peso_base += delta
                        fecha_norm_fut = s.replace("-", "_")
                        doc_id_fut = f"{correo_cliente_norm}_{fecha_norm_fut}"
                        st.write(f"   📌 Semana `{s}` ➜ Documento `{doc_id_fut}` ➜ Nuevo peso base: {peso_base}")

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
                                    ef["peso"] = round(peso_base, 2)
                                    st.write(f"      ✔️ `{ef['ejercicio']}` actualizado a {ef['peso']}kg")

                            doc_ref.update({f"rutina.{dia_sel}": ejercicios_fut})
                            st.write(f"   🔄 Documento `{doc_id_fut}` actualizado con éxito.")
                        else:
                            st.warning(f"⚠️ Documento `{doc_id_fut}` no existe ➜ Se omite.")

            st.success("✅ TODOS LOS PASOS EJECUTADOS SIN ERRORES")

        except Exception as e:
            st.error("❌ Error durante el guardado paso a paso.")
            st.exception(e)
