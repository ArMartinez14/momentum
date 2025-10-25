import streamlit as st
from firebase_admin import credentials, firestore
import firebase_admin
import json

from app_core.utils import (
    empresa_de_usuario,
    EMPRESA_MOTION,
    EMPRESA_ASESORIA,
    EMPRESA_DESCONOCIDA,
    correo_a_doc_id,
)

# === INICIALIZAR FIREBASE con secretos ===
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()

def borrar_rutinas():
    st.title("🗑️ Borrar Rutinas por Semana")

    correo_input = st.text_input("Ingresa el correo del cliente:")

    if not correo_input:
        return

    # Preparar variantes de búsqueda
    correo_raw = correo_input.strip()
    raw_lower = correo_raw.lower()
    correo_norm = correo_raw.replace("@", "_").replace(".", "_").lower()

    # Validar permisos según empresa/coach
    correo_login = (st.session_state.get("correo") or "").strip().lower()
    rol_login = (st.session_state.get("rol") or "").strip().lower()
    empresa_login = empresa_de_usuario(correo_login) if correo_login else EMPRESA_DESCONOCIDA

    target_doc = db.collection("usuarios").document(correo_a_doc_id(raw_lower)).get()
    target_data = target_doc.to_dict() or {}
    coach_cli = (target_data.get("coach_responsable") or "").strip().lower()
    empresa_cli = empresa_de_usuario(raw_lower)

    permitido = True
    if rol_login in ("entrenador",):
        if empresa_login == EMPRESA_ASESORIA:
            permitido = coach_cli == correo_login
        elif empresa_login == EMPRESA_MOTION:
            if empresa_cli == EMPRESA_MOTION:
                permitido = True
            elif empresa_cli == EMPRESA_DESCONOCIDA:
                permitido = coach_cli == correo_login
            else:
                permitido = False
        else:
            permitido = coach_cli == correo_login
    elif rol_login not in ("admin", "administrador"):
        permitido = coach_cli == correo_login

    if not permitido:
        st.error("No tienes permisos para borrar rutinas de este cliente.")
        return

    # Buscaremos en estas colecciones
    colecciones = ["rutinas", "rutinas_semanales"]

    semanas = {}
    hallados_debug = []   # para mostrar ejemplos de IDs encontrados
    total_refs = 0

    for nombre_col in colecciones:
        try:
            col_ref = db.collection(nombre_col)
            # list_documents() obtiene referencias sin leer todo el doc (más rápido que .stream())
            for ref in col_ref.list_documents():
                total_refs += 1
                doc_id = ref.id
                did_lower = doc_id.lower()

                # 1) Prefijo exacto (correo tal cual) o normalizado
                match_prefix = did_lower.startswith(raw_lower) or did_lower.startswith(correo_norm)

                # 2) Si no hubo prefijo, intentamos contains por si el correo está en medio
                match_contains = (raw_lower in did_lower) or (correo_norm in did_lower)

                if match_prefix or match_contains:
                    hallados_debug.append((nombre_col, doc_id))

                    # Extraer fecha desde el final del ID: ..._YYYY_MM_DD
                    try:
                        base, y, m, d = doc_id.rsplit("_", 3)
                        fecha_semana = f"{y}_{m}_{d}"
                    except ValueError:
                        # No cumple patrón de fecha al final, saltamos
                        continue

                    semanas.setdefault(fecha_semana, []).append((nombre_col, doc_id))
        except Exception as e:
            st.error(f"Error leyendo colección '{nombre_col}': {e}")

    if not semanas:
        st.warning("No se encontraron rutinas para ese correo (probado: tal cual, normalizado, prefijo y contains).")
        with st.expander("Detalles de ayuda"):
            st.markdown("- **Ejemplo de ID esperado:** `correo@dominio.com_YYYY_MM_DD` o `correo_dominio_com_YYYY_MM_DD`")
            st.write(f"Correo ingresado: {correo_raw}")
            st.write(f"Correo normalizado probado: {correo_norm}")
            st.write(f"Total de refs inspeccionadas: {total_refs}")
            if hallados_debug:
                st.write("Se encontraron algunos IDs que contienen el correo, pero no tenían fecha válida al final:")
                st.write(hallados_debug[:10])
        return

    # Mostrar semanas a eliminar
    semanas_ordenadas = sorted(semanas.keys(), reverse=True)
    st.markdown("### Selecciona las semanas que deseas eliminar:")
    semanas_seleccionadas = []
    for semana in semanas_ordenadas:
        if st.checkbox(f"Semana {semana}", key=f"chk_{semana}"):
            semanas_seleccionadas.append(semana)

    # Panel de debug: primeros 10 hallados
    with st.expander("Ver IDs encontrados (debug)"):
        st.write(hallados_debug[:20])

    if semanas_seleccionadas and st.button("🗑️ Eliminar semanas seleccionadas"):
        batch = db.batch()
        total_del = 0
        for semana in semanas_seleccionadas:
            for (col_name, doc_id) in semanas[semana]:
                batch.delete(db.collection(col_name).document(doc_id))
                total_del += 1
        batch.commit()
        st.success(f"Se eliminaron {total_del} documento(s) de las semanas seleccionadas.")
