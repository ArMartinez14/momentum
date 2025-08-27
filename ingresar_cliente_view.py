import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import unicodedata
import json
import re  # 👈 NUEVO: para validar correo

# 👇 NUEVO: importar el servicio de catálogos
from servicio_catalogos import get_catalogos, add_item

# === INICIALIZAR FIREBASE SOLO UNA VEZ ===
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

def normalizar_id(correo):
    return correo.replace('@', '_').replace('.', '_')

def normalizar_texto(texto):
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower().replace(" ", "_")

# 👇 NUEVO: limpia espacios (inicio, fin y también intermedios)
def limpiar_correo(correo: str) -> str:
    if not correo:
        return ""
    # quita espacios al inicio/fin y también espacios internos
    return ''.join(correo.strip().split())

# 👇 NUEVO: helper para selectbox con opción "➕ Agregar nuevo…"
def combo_con_agregar(titulo: str, opciones: list[str], key_base: str, valor_inicial: str = "") -> str:
    """
    Renderiza un selectbox con opciones + '➕ Agregar nuevo…'.
    Si se elige 'Agregar nuevo…', muestra un text_input y botón Guardar que
    escribe el valor en Firestore y hace st.rerun().
    Retorna el valor seleccionado (o "" si no hay selección válida).
    """
    SENTINEL = "➕ Agregar nuevo…"

    # Copia/ordena y asegura que el valor inicial (al editar) esté incluido
    base_opts = sorted(opciones or [])
    if valor_inicial and valor_inicial not in base_opts:
        base_opts.append(valor_inicial)

    opts = ["— Selecciona —"] + base_opts + [SENTINEL]

    # Índice por defecto cuando hay valor inicial
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
                    # Mapa del título a la clave en Firestore
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
        correo_input = st.text_input("Correo del cliente:")
        correo_limpio = limpiar_correo(correo_input)  # 👈 NUEVO

        # Vista previa del correo que se guardará
        if correo_input:
            st.caption(f"Se guardará como: **{correo_limpio or '—'}**")

        # Rol según el usuario logueado
        if st.session_state.get("rol") == "admin":
            opciones_rol = ["deportista", "entrenador", "admin"]
        else:
            opciones_rol = ["deportista"]

        rol = st.selectbox("Rol:", opciones_rol)

        if st.button("Guardar Cliente"):
            # Validaciones
            if not nombre:
                st.warning("⚠️ Ingresa el nombre.")
                return

            if not correo_limpio:
                st.warning("⚠️ Ingresa el correo.")
                return

            # Validación simple de correo (sin espacios y con @ y dominio)
            patron_correo = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
            if not re.match(patron_correo, correo_limpio):
                st.warning("⚠️ El correo no parece válido. Revisa el formato (ej: nombre@dominio.com).")
                return

            if not rol:
                st.warning("⚠️ Selecciona el rol.")
                return

            # Guardar usando SIEMPRE el correo limpio
            doc_id = normalizar_id(correo_limpio)
            data = {"nombre": nombre, "correo": correo_limpio, "rol": rol}

            try:
                db.collection("usuarios").document(doc_id).set(data)
                st.success(f"✅ Cliente '{nombre}' guardado correctamente")
            except Exception as e:
                st.error(f"❌ Error al guardar: {e}")

    # ================= EJERCICIO NUEVO O EDITAR =================
    elif opcion == "Ejercicio Nuevo o Editar":
        st.subheader("📌 Crear o Editar Ejercicio")

        # Cargar ejercicios ya existentes
        docs = db.collection("ejercicios").stream()
        ejercicios_disponibles = {doc.id: doc.to_dict().get("nombre", doc.id) for doc in docs}

        modo = st.radio("¿Qué quieres hacer?", ["Nuevo ejercicio", "Editar ejercicio existente"], horizontal=True)

        if modo == "Editar ejercicio existente":
            seleccion = st.selectbox("Selecciona un ejercicio:", list(ejercicios_disponibles.values()))
            doc_id_sel = [k for k, v in ejercicios_disponibles.items() if v == seleccion][0]
            doc_ref = db.collection("ejercicios").document(doc_id_sel).get()
            datos = doc_ref.to_dict() if doc_ref.exists else {}
        else:
            datos = {}

        # === NUEVO: cargar catálogos centralizados desde Firestore ===
        cat = get_catalogos()
        catalogo_carac  = cat.get("caracteristicas", [])
        catalogo_patron = cat.get("patrones_movimiento", [])
        catalogo_grupo  = cat.get("grupo_muscular_principal", [])

        # === FORMULARIO ORDENADO Y CON AUTO-NOMBRE ===
        col1, col2 = st.columns(2)
        with col1:
            implemento = st.text_input("Implemento:", value=datos.get("implemento", ""), key="implemento")
        with col2:
            detalle = st.text_input("Detalle:", value=datos.get("detalle", ""), key="detalle")

        # 👇 Reemplazo de text_input por listas desplegables basadas en catálogos
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

        # === NOMBRE AUTOCOMPLETADO ===
        nombre_ej = f"{implemento.strip()} {detalle.strip()}".strip()
        st.text_input("Nombre completo del ejercicio:", value=nombre_ej, key="nombre", disabled=True)

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
                "patron_de_movimiento": patron
            }

            # Validaciones mínimas: no guardar si catálogos vacíos
            faltantes = [k for k, v in {
                "Característica": caracteristica,
                "Grupo muscular principal": grupo,
                "Patrón de movimiento": patron
            }.items() if not (v or "").strip()]

            if faltantes:
                st.warning("⚠️ Completa: " + ", ".join(faltantes))
                return

            try:
                doc_id = normalizar_texto(nombre_ej)
                db.collection("ejercicios").document(doc_id).set(datos_guardar)
                st.success(f"✅ Ejercicio '{nombre_ej}' guardado correctamente")
            except Exception as e:
                st.error(f"❌ Error al guardar: {e}")

    else:
        st.info("👈 Selecciona una opción para comenzar.")
