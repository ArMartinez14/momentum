# seccion_ejercicios.py
import csv
import io
import re
import streamlit as st
import firebase_admin
from firebase_admin import firestore

# ======================
# Helpers de permisos
# ======================
ADMIN_ROLES = {"admin", "administrador", "owner", "Admin", "Administrador"}
ENTRENADOR_ROLES = {"entrenador", "Entrenador", "coach", "Coach"}

def _rol_actual() -> str:
    return (st.session_state.get("rol") or "").strip()


def _es_admin() -> bool:
    return _rol_actual() in ADMIN_ROLES


def _es_entrenador() -> bool:
    return _rol_actual() in ENTRENADOR_ROLES

def _correo_user() -> str:
    return (st.session_state.get("correo") or "").strip().lower()

def _puede_editar_video(row: dict) -> bool:
    """Admin o entrenador siempre; otros solo si son creadores."""
    if _es_admin() or _es_entrenador():
        return True
    creador = (row.get("entrenador") or row.get("creado_por") or "").strip().lower()
    return creador and creador == _correo_user()

def _puede_editar_privacidad(row: dict) -> bool:
    """Usa misma regla que video: admin o creador."""
    return _puede_editar_video(row)

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

def _chunked(items: list, size: int):
    for i in range(0, len(items), size):
        yield items[i:i + size]

def _ejercicios_a_csv(rows: list[dict]) -> bytes:
    """Convierte la lista de ejercicios (sin claves internas) a CSV UTF-8 BOM."""
    visibles = []
    campos = set()
    for row in rows:
        limpio = {k: v for k, v in row.items() if not k.startswith("_")}
        visibles.append(limpio)
        campos.update(limpio.keys())

    if not campos:
        campos = {"_id", "nombre"}

    fieldnames = sorted(campos)
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for item in visibles:
        writer.writerow({k: item.get(k, "") for k in fieldnames})

    return buffer.getvalue().encode("utf-8-sig")

def _actualizar_privacidad(doc_ids: list[str], publico: bool):
    if not doc_ids:
        return

    db = firestore.client()
    ref = db.collection("ejercicios")
    for lote in _chunked(doc_ids, 400):
        batch = db.batch()
        for doc_id in lote:
            batch.set(ref.document(doc_id), {"publico": publico}, merge=True)
        batch.commit()

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
            row["_puede_editar_privacidad"] = _puede_editar_privacidad(row)
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
    st.session_state.setdefault("privacidad_modo", False)

    aplicar_privacidad = False

    col_title, col_menu, col_reload = st.columns([1, 0.26, 0.12])
    with col_menu:
        with st.expander("⚙️ Opciones", expanded=False):
            st.caption("Privacidad de ejercicios")
            st.checkbox(
                "Editar privacidad masiva",
                key="privacidad_modo",
                help="Activa las casillas para seleccionar varios ejercicios a la vez.",
            )
            if st.session_state.get("privacidad_modo"):
                col_all, col_clear = st.columns(2)
                if col_all.button("Seleccionar todos", key="privacidad_select_all"):
                    st.session_state["privacidad_select_all_trigger"] = True
                if col_clear.button("Limpiar selección", key="privacidad_clear_all"):
                    st.session_state["privacidad_clear_all_trigger"] = True
            st.caption("Solo se aplicará en ejercicios propios o si eres administrador.")
            aplicar_privacidad = st.button(
                "Hacer públicos los seleccionados",
                type="primary",
                disabled=not st.session_state.get("privacidad_modo"),
            )

    with col_reload:
        if st.button("🔄 Recargar", help="Volver a leer desde Firestore", key="reload_ej"):
            st.cache_data.clear()
            st.rerun()

    ejercicios = _cargar_ejercicios()
    total = len(ejercicios)
    con_video = sum(1 for e in ejercicios if e["_tiene_video"])
    csv_bytes = _ejercicios_a_csv(ejercicios)

    col_stats, col_download = st.columns([1, 0.3])
    col_stats.caption(f"Total: **{total}** | Con video: **{con_video}** | Sin video: **{total - con_video}**")
    col_download.download_button(
        "📥 Descargar CSV",
        data=csv_bytes,
        file_name="ejercicios.csv",
        mime="text/csv",
        help="Descarga todos los ejercicios con sus campos disponibles.",
    )

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

    modo_privacidad = st.session_state.get("privacidad_modo", False)
    if not modo_privacidad:
        keys_to_remove = [k for k in list(st.session_state.keys()) if k.startswith("priv_sel_")]
        for k in keys_to_remove:
            del st.session_state[k]

    select_all_trigger = st.session_state.pop("privacidad_select_all_trigger", False)
    clear_all_trigger = st.session_state.pop("privacidad_clear_all_trigger", False)

    if modo_privacidad and (select_all_trigger or clear_all_trigger):
        for e in ejercicios:
            key = f"priv_sel_{e['_id']}"
            if clear_all_trigger:
                st.session_state[key] = False
            elif e.get("_puede_editar_privacidad", False):
                st.session_state[key] = True

    checkbox_registry: dict[str, dict] = {}

    tab_todos, tab_sin_video = st.tabs(["Todos", "Sin video"])

    # ---- Componente card + editor inline (con prefijo para evitar keys duplicadas)
    def _card_ejercicio(
        e,
        prefix: str,
        show_privacidad_checkbox: bool = False,
        registry: dict | None = None,
    ):
        with st.container(border=True):
            if show_privacidad_checkbox:
                col_sel, c1, c2, c3, c4 = st.columns([0.8, 3.0, 1.2, 2.4, 2.0])
                sel_key = f"priv_sel_{e['_id']}"
                disabled_sel = not e.get("_puede_editar_privacidad", False)
                col_sel.checkbox(
                    "Sel.",
                    key=sel_key,
                    value=st.session_state.get(sel_key, False),
                    help="Selecciona el ejercicio para cambiar su privacidad.",
                    disabled=disabled_sel,
                )
                if disabled_sel:
                    col_sel.caption("Sin permiso")
                if registry is not None:
                    registry[e["_id"]] = {
                        "key": sel_key,
                        "allowed": not disabled_sel,
                        "nombre": e.get("nombre", ""),
                    }
            else:
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
        if modo_privacidad:
            st.caption("Marca los ejercicios y luego pulsa \"Hacer públicos los seleccionados\" en Opciones.")
        for e in ejercicios:
            _card_ejercicio(
                e,
                prefix="todos",
                show_privacidad_checkbox=modo_privacidad,
                registry=checkbox_registry,
            )

    # ---- TAB: SIN VIDEO
    with tab_sin_video:
        faltantes = [e for e in ejercicios if not e["_tiene_video"]]
        if not faltantes:
            st.success("🎉 No hay ejercicios faltantes de video en este filtro.")
        else:
            st.info(f"Hay **{len(faltantes)}** ejercicios sin video.")
            for e in faltantes:
                _card_ejercicio(
                    e,
                    prefix="sinvideo",
                    show_privacidad_checkbox=modo_privacidad,
                    registry=checkbox_registry,
                )

    selected_ids = []
    if modo_privacidad and checkbox_registry:
        selected_ids = [
            doc_id
            for doc_id, info in checkbox_registry.items()
            if info.get("allowed") and st.session_state.get(info.get("key"))
        ]
        st.caption(
            f"Seleccionados: **{len(selected_ids)}** ejercicios | Acción: Hacer públicos"
        )

    if aplicar_privacidad:
        if not modo_privacidad:
            st.warning("Activa el modo de privacidad masiva para seleccionar ejercicios.")
        elif not selected_ids:
            st.warning("Selecciona al menos un ejercicio con permisos válidos.")
        else:
            try:
                _actualizar_privacidad(selected_ids, publico=True)
                st.success(f"Se actualizaron {len(selected_ids)} ejercicios a públicos.")
                for info in checkbox_registry.values():
                    st.session_state.pop(info["key"], None)
                st.cache_data.clear()
                st.rerun()
            except Exception as ex:
                st.error(f"Error actualizando privacidad: {ex}")
