# seccion_ejercicios.py
import re
import streamlit as st
import firebase_admin
from firebase_admin import firestore

# ======================
# Helpers de permisos
# ======================
ADMIN_ROLES = {"admin", "administrador", "owner", "Admin", "Administrador"}

def _es_admin() -> bool:
    rol = (st.session_state.get("rol") or "").strip()
    return rol in ADMIN_ROLES

def _correo_user() -> str:
    return (st.session_state.get("correo") or "").strip().lower()

def _puede_editar_video(row: dict) -> bool:
    """Admin siempre; entrenador solo si es creador/propietario."""
    if _es_admin():
        return True
    creador = (row.get("entrenador") or row.get("creado_por") or "").strip().lower()
    return creador and creador == _correo_user()

def _es_url_valida(url: str) -> bool:
    """Valida http(s) y que el dominio sea YouTube."""
    if not url:
        return False
    url = url.strip()
    patron_http = r"^https?://[^\s]+$"
    patron_yt = r"(youtube\.com|youtu\.be)"
    return bool(re.match(patron_http, url, flags=re.I)) and bool(re.search(patron_yt, url, flags=re.I))

def _formato_link(url: str) -> str:
    return f"[Ver video]({url})" if url else "-"

# ======================
# Lectura con filtros de visibilidad
# ======================
@st.cache_data(show_spinner=False, ttl=60)
def _cargar_ejercicios():
    """
    Lee colección 'ejercicios' filtrando:
      - Admin: ve TODOS.
      - No admin: ve (publico == True) + (entrenador == <su_correo>).
    Devuelve lista de dicts para UI.
    """
    db = firestore.client()  # Firebase ya debe estar inicializado en tu main
    data = []
    correo = _correo_user()
    es_admin = _es_admin()

    try:
        if es_admin:
            docs = db.collection("ejercicios").stream()
        else:
            # 1) Públicos
            pub_docs = list(db.collection("ejercicios").where("publico", "==", True).stream())
            # 2) Privados del entrenador
            priv_docs = []
            if correo:
                priv_docs = list(db.collection("ejercicios").where("entrenador", "==", correo).stream())
            # Unir (evitar duplicados por id)
            by_id = {}
            for d in pub_docs + priv_docs:
                if getattr(d, "exists", True):
                    by_id[d.id] = d
            docs = by_id.values()

        for d in docs:
            if not getattr(d, "exists", True):
                continue
            row = d.to_dict() or {}
            row["_id"] = d.id
            row["nombre"] = row.get("nombre", "")
            row["id_implemento"] = row.get("id_implemento", "")
            # Visibilidad/autor (para UI)
            row["publico"] = row.get("publico", False)
            row["entrenador"] = (row.get("entrenador") or row.get("creado_por") or "").strip().lower()

            video_raw = str(row.get("video", "") or "").strip()
            row["_tiene_video"] = bool(video_raw)
            row["_video"] = video_raw
            row["_puede_editar_video"] = _puede_editar_video(row)
            data.append(row)

        data.sort(key=lambda x: x.get("nombre", "").lower())
    except Exception as ex:
        st.error(f"Error leyendo ejercicios: {ex}")

    return data

def _guardar_video(doc_id: str, url: str):
    db = firestore.client()
    db.collection("ejercicios").document(doc_id).update({"video": url})

def _quitar_video(doc_id: str):
    db = firestore.client()
    db.collection("ejercicios").document(doc_id).update({"video": ""})

# ======================
# UI
# ======================
def base_ejercicios():
    st.header("📚 Base de ejercicios")

    # Estado del editor inline
    st.session_state.setdefault("edit_video_id", None)
    st.session_state.setdefault("edit_video_default", "")

    col_title, col_reload = st.columns([1, 0.12])
    with col_reload:
        if st.button("🔄 Recargar", help="Volver a leer desde Firestore", key="reload_ej"):
            st.cache_data.clear()
            st.rerun()

    ejercicios = _cargar_ejercicios()
    total = len(ejercicios)
    con_video = sum(1 for e in ejercicios if e["_tiene_video"])
    st.caption(f"Total: **{total}** | Con video: **{con_video}** | Sin video: **{total - con_video}**")

    q = st.text_input(
        "🔎 Buscar por nombre o ID de implemento",
        placeholder="Ej: sentadilla, polea, db-20…",
        key="search_ej",
    )
    if q:
        qn = q.strip().lower()
        ejercicios = [
            e for e in ejercicios
            if qn in e["nombre"].lower() or qn in str(e["id_implemento"]).lower()
        ]

    tab_todos, tab_sin_video = st.tabs(["Todos", "Sin video"])

    # ---- Componente card + editor inline (con prefijo para evitar keys duplicadas)
    def _card_ejercicio(e, prefix: str):
        with st.container(border=True):
            c1, c2, c3, c4 = st.columns([3.0, 1.2, 2.4, 2.0])
            c1.markdown(f"**{e['nombre']}**  \n`{e['_id']}`")
            c4.markdown(
                f"**Implemento:**  \n`{e.get('id_implemento','') or '-'}`  \n"
                f"**Visibilidad:** {'Público' if e.get('publico') else 'Privado'}  \n"
                f"**Creador:** `{e.get('entrenador') or '-'}`"
            )

            # Info de video + botones según permiso
            if e["_tiene_video"]:
                c2.markdown("**Video:** ✅")
                c3.markdown(_formato_link(e["_video"]))
                b1, b2 = c3.columns([1, 1])
                editar_disabled = not e["_puede_editar_video"]
                quitar_disabled = not e["_puede_editar_video"]
                if b1.button("Editar", key=f"{prefix}_edit_{e['_id']}", disabled=editar_disabled):
                    st.session_state.edit_video_id = e["_id"]
                    st.session_state.edit_video_default = e["_video"]
                    st.rerun()
                if b2.button("Quitar", key=f"{prefix}_del_{e['_id']}", disabled=quitar_disabled):
                    if e["_puede_editar_video"]:
                        try:
                            _quitar_video(e["_id"])
                            st.success("Video eliminado.")
                            st.cache_data.clear()
                            st.rerun()
                        except Exception as ex:
                            st.error(f"Error al eliminar: {ex}")
                    else:
                        st.warning("No tienes permiso para quitar el video de este ejercicio.")
            else:
                c2.markdown("**Video:** ❌")
                agregar_disabled = not e["_puede_editar_video"]
                if c3.button("Agregar", key=f"{prefix}_add_{e['_id']}", disabled=agregar_disabled):
                    st.session_state.edit_video_id = e["_id"]
                    st.session_state.edit_video_default = ""

            # Editor inline para el ejercicio activo
            if st.session_state.edit_video_id == e["_id"]:
                st.divider()
                puede_editar = e["_puede_editar_video"]
                with st.form(key=f"{prefix}_form_video_{e['_id']}", clear_on_submit=False):
                    url = st.text_input(
                        "Pega el link de YouTube",
                        value=st.session_state.edit_video_default,
                        placeholder="https://www.youtube.com/watch?v=...",
                        key=f"{prefix}_inp_url_{e['_id']}",
                        disabled=not puede_editar
                    )
                    colf1, colf2 = st.columns([1, 1])
                    guardar = colf1.form_submit_button("💾 Guardar", disabled=not puede_editar)
                    cancelar = colf2.form_submit_button("Cancelar")

                    if guardar:
                        if not puede_editar:
                            st.warning("No tienes permiso para editar el video de este ejercicio.")
                        elif not _es_url_valida(url):
                            st.error("Por favor ingresa un link válido de YouTube (http/https).")
                        else:
                            try:
                                _guardar_video(e["_id"], url.strip())
                                st.success("¡Video guardado!")
                                st.session_state.edit_video_id = None
                                st.session_state.edit_video_default = ""
                                st.cache_data.clear()
                                st.rerun()
                            except Exception as ex:
                                st.error(f"Error guardando: {ex}")

                    if cancelar:
                        st.session_state.edit_video_id = None
                        st.session_state.edit_video_default = ""
                        st.rerun()

    # ---- TAB: TODOS
    with tab_todos:
        for e in ejercicios:
            _card_ejercicio(e, prefix="todos")

    # ---- TAB: SIN VIDEO
    with tab_sin_video:
        faltantes = [e for e in ejercicios if not e["_tiene_video"]]
        if not faltantes:
            st.success("🎉 No hay ejercicios faltantes de video en este filtro.")
        else:
            st.info(f"Hay **{len(faltantes)}** ejercicios sin video.")
            for e in faltantes:
                _card_ejercicio(e, prefix="sinvideo")
