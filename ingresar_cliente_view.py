import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import unicodedata
import json
import re
from datetime import datetime

# 👇 servicio de catálogos (tuyo)
from servicio_catalogos import get_catalogos, add_item

# === INICIALIZAR FIREBASE SOLO UNA VEZ ===
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

def normalizar_id(correo: str) -> str:
    return (correo or "").replace('@', '_').replace('.', '_')

def normalizar_texto(texto: str) -> str:
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower().replace(" ", "_")

# === normalización fuerte de correo ===
import re as _re
def normalizar_correo(correo: str) -> str:
    if not correo:
        return ""
    c = str(correo)
    c = c.replace("\u00A0", "")
    c = _re.sub(r"\s+", "", c, flags=_re.UNICODE)
    c = c.casefold()
    return c

# ====== detectar si el usuario actual es admin ======
ADMIN_ROLES = {"admin", "administrador", "owner", "Admin", "Administrador"}

def es_admin() -> bool:
    correo = (st.session_state.get("correo") or "").strip().lower()
    rol_ss = (st.session_state.get("rol") or "").strip()
    if rol_ss in ADMIN_ROLES:
        return True
    if correo:
        try:
            doc_id = normalizar_id(correo)
            snap = db.collection("usuarios").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict() or {}
                rol_fb = (data.get("rol") or data.get("role") or "").strip()
                return rol_fb in ADMIN_ROLES
        except Exception:
            pass
    return False

# 👇 helper para selectbox con “➕ Agregar nuevo…”
def combo_con_agregar(titulo: str, opciones: list[str], key_base: str, valor_inicial: str = "") -> str:
    SENTINEL = "➕ Agregar nuevo…"

    base_opts = sorted(opciones or [])
    if valor_inicial and valor_inicial not in base_opts:
        base_opts.append(valor_inicial)

    opts = ["— Selecciona —"] + base_opts + [SENTINEL]
    index_default = 0
    if valor_inicial:
        try:
            index_default = opts.index(valor_inicial)
        except ValueError:
            index_default = 0

    sel = st.selectbox(titulo, opts, index=index_default, key=f"{key_base}_select")

    if sel == SENTINEL:
        nuevo = st.text_input(f"Ingresar nuevo valor para {titulo.lower()}:", key=f"{key_base}_nuevo")
        cols = st.columns([1, 1, 6])
        with cols[0]:
            if st.button("Guardar", key=f"{key_base}_guardar"):
                valor_limpio = (nuevo or "").strip()
                if valor_limpio:
                    if "Característica" in titulo:
                        tipo = "caracteristicas"
                    elif "Patrón" in titulo or "Patron" in titulo:
                        tipo = "patrones_movimiento"
                    else:
                        tipo = "grupo_muscular_principal"
                    add_item(tipo, valor_limpio)
                    st.success(f"Agregado: {valor_limpio}")
                    st.rerun()
        return ""
    elif sel == "— Selecciona —":
        return ""
    else:
        return sel

# === Callback para limpiar el input en session_state ===
def _cb_normalizar_correo(key_name: str):
    raw = st.session_state.get(key_name, "")
    st.session_state[key_name] = normalizar_correo(raw)

def ingresar_cliente_o_video_o_ejercicio():
    st.title("Panel de Administración")

    opcion = st.selectbox(
        "¿Qué deseas hacer?",
        ["Selecciona...", "Cliente Nuevo", "Ejercicio Nuevo o Editar"],
        index=0
    )

    # ================= CLIENTE NUEVO =================
    if opcion == "Cliente Nuevo":
        nombre = st.text_input("Nombre del cliente:")

        if "correo_cliente_nuevo" in st.session_state:
            st.session_state["correo_cliente_nuevo"] = normalizar_correo(st.session_state["correo_cliente_nuevo"])

        correo_input = st.text_input(
            "Correo del cliente:",
            key="correo_cliente_nuevo",
            on_change=_cb_normalizar_correo,
            args=("correo_cliente_nuevo",)
        )
        correo_limpio = st.session_state.get("correo_cliente_nuevo", "")

        if correo_input:
            st.caption(f"Se guardará como: **{correo_limpio or '—'}**")

        if st.session_state.get("rol") == "admin":
            opciones_rol = ["deportista", "entrenador", "admin"]
        else:
            opciones_rol = ["deportista"]

        rol = st.selectbox("Rol:", opciones_rol)

        if st.button("Guardar Cliente"):
            if not nombre:
                st.warning("⚠️ Ingresa el nombre.")
                return

            correo_limpio = normalizar_correo(correo_input)
            if not correo_limpio:
                st.warning("⚠️ Ingresa el correo.")
                return

            patron_correo = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
            if not re.match(patron_correo, correo_limpio):
                st.warning("⚠️ El correo no parece válido. Revisa el formato (ej: nombre@dominio.com).")
                return

            if not rol:
                st.warning("⚠️ Selecciona el rol.")
                return

            doc_id = normalizar_id(correo_limpio)
            data = {"nombre": nombre, "correo": correo_limpio, "rol": rol}

            try:
                db.collection("usuarios").document(doc_id).set(data)
                st.success(f"✅ Cliente '{nombre}' guardado correctamente con correo: {correo_limpio}")
            except Exception as e:
                st.error(f"❌ Error al guardar: {e}")

    # ================= EJERCICIO NUEVO O EDITAR =================
    elif opcion == "Ejercicio Nuevo o Editar":
        st.subheader("📌 Crear o Editar Ejercicio")

        # Identidad del usuario (para 'entrenador' y permisos)
        correo_usuario = (st.session_state.get("correo") or "").strip().lower()
        if not correo_usuario:
            st.warning("Primero ingresa tu correo en la app (st.session_state['correo']).")
            st.stop()

        admin = es_admin()

        # Cargar ejercicios ya existentes
        docs = db.collection("ejercicios").stream()
        ejercicios_disponibles = {doc.id: doc.to_dict().get("nombre", doc.id) for doc in docs}

        modo = st.radio("¿Qué quieres hacer?", ["Nuevo ejercicio", "Editar ejercicio existente"], horizontal=True)

        doc_id_sel = None
        datos = {}
        if modo == "Editar ejercicio existente" and ejercicios_disponibles:
            seleccion = st.selectbox("Selecciona un ejercicio:", list(ejercicios_disponibles.values()))
            doc_id_sel = [k for k, v in ejercicios_disponibles.items() if v == seleccion][0]
            snap = db.collection("ejercicios").document(doc_id_sel).get()
            datos = snap.to_dict() if snap.exists else {}

        # === catálogos ===
        cat = get_catalogos()
        catalogo_carac  = cat.get("caracteristicas", [])
        catalogo_patron = cat.get("patrones_movimiento", [])
        catalogo_grupo  = cat.get("grupo_muscular_principal", [])

        # === FORMULARIO ===
        col1, col2 = st.columns(2)
        with col1:
            implemento = st.text_input("Implemento:", value=datos.get("implemento", ""), key="implemento")
        with col2:
            detalle = st.text_input("Detalle:", value=datos.get("detalle", ""), key="detalle")

        col3, col4 = st.columns(2)
        with col3:
            caracteristica = combo_con_agregar(
                "Característica",
                catalogo_carac,
                key_base="caracteristica",
                valor_inicial=datos.get("caracteristica", "")
            )
        with col4:
            grupo = combo_con_agregar(
                "Grupo muscular principal",
                catalogo_grupo,
                key_base="grupo",
                valor_inicial=datos.get("grupo_muscular_principal", "")
            )

        patron = combo_con_agregar(
            "Patrón de movimiento",
            catalogo_patron,
            key_base="patron",
            valor_inicial=datos.get("patron_de_movimiento", "")
        )

        nombre_ej = f"{implemento.strip()} {detalle.strip()}".strip()
        st.text_input("Nombre completo del ejercicio:", value=nombre_ej, key="nombre", disabled=True)

        # ✅ Checkbox visible para TODOS (entrenador o admin). Por defecto:
        #    - admin: True  | entrenador: False
        publico_default = True if admin else False
        publico_check = st.checkbox("Hacer público (visible para todos los entrenadores)", value=publico_default)

        if st.button("💾 Guardar Ejercicio", key="btn_guardar_ejercicio"):
            if not nombre_ej:
                st.warning("⚠️ El campo 'nombre' es obligatorio.")
                return

            datos_guardar = {
                "nombre": nombre_ej,
                "caracteristica": caracteristica,
                "detalle": detalle,
                "grupo_muscular_principal": grupo,
                "implemento": implemento,
                "patron_de_movimiento": patron,
                "actualizado_por": correo_usuario,
                "fecha_actualizacion": datetime.utcnow(),
                # 👇 Gobernado SOLO por el checkbox (si está activo, queda True independiente del rol)
                "publico": bool(publico_check),
            }

            # Reglas solicitadas:
            # - Si NO está marcado y el usuario es entrenador => publico False (ya lo cumple por defecto).
            # - Si NO está marcado y es admin => publico False (puede crear privados).
            # - Si está marcado => publico True para cualquiera.

            # Validaciones mínimas
            faltantes = [k for k, v in {
                "Característica": caracteristica,
                "Grupo muscular principal": grupo,
                "Patrón de movimiento": patron
            }.items() if not (v or "").strip()]

            if faltantes:
                st.warning("⚠️ Completa: " + ", ".join(faltantes))
                return

            try:
                if modo == "Editar ejercicio existente" and doc_id_sel:
                    # Mantener 'entrenador' original si existe; si no existe, lo ponemos
                    entrenador_original = datos.get("entrenador")
                    if not entrenador_original:
                        datos_guardar["entrenador"] = correo_usuario  # backfill si faltaba
                    # Actualizar
                    db.collection("ejercicios").document(doc_id_sel).update(datos_guardar)
                    st.success(f"✅ Ejercicio '{datos.get('nombre', doc_id_sel)}' actualizado correctamente")
                else:
                    # Nuevo: ID por nombre normalizado
                    doc_id = normalizar_texto(nombre_ej)
                    db.collection("ejercicios").document(doc_id).set({
                        **datos_guardar,
                        # 👇 creador del ejercicio
                        "creado_por": correo_usuario,
                        "fecha_creacion": datetime.utcnow(),
                        # 👇 correo del entrenador que LO CREÓ (aunque sea admin, guardamos aquí)
                        "entrenador": correo_usuario,
                    }, merge=True)
                    st.success(f"✅ Ejercicio '{nombre_ej}' guardado correctamente")

                # Mensaje de visibilidad
                if datos_guardar["publico"]:
                    st.info("Este ejercicio es **público** y será visible para todos los entrenadores.")
                else:
                    st.info("Este ejercicio está **no público** (solo lo verás tú en Crear Rutina si no eres admin).")

            except Exception as e:
                st.error(f"❌ Error al guardar: {e}")

    else:
        st.info("👈 Selecciona una opción para comenzar.")

