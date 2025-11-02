"""Vista de administración para previsualizar correos semanales de entrenadores."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Dict, List, Optional

import streamlit as st

from app_core.email_notifications import preparar_resumen_bloques_entrenador
from app_core.firebase_client import get_db


@dataclass
class EntrenadorInfo:
    correo: str
    nombre: str


@st.cache_data(ttl=180)
def _tiene_rutinas_asignadas(correo: str) -> bool:
    correo_norm = (correo or "").strip().lower()
    if not correo_norm:
        return False
    try:
        db = get_db()
        snaps = db.collection("rutinas_semanales").where("entrenador", "==", correo_norm).limit(1).stream()
    except Exception:
        return False
    return any(getattr(snap, "exists", True) for snap in snaps)


@st.cache_data(ttl=300)
def _listar_entrenadores() -> List[EntrenadorInfo]:
    """Obtiene entrenadores o administradores con rutinas asignadas."""
    resultados: List[EntrenadorInfo] = []
    try:
        db = get_db()
        snaps = list(db.collection("usuarios").where("rol", "in", ["entrenador", "admin", "administrador"]).stream())
    except Exception:
        snaps = []
        try:
            db = get_db()
            for rol in ("entrenador", "admin", "administrador"):
                snaps.extend(db.collection("usuarios").where("rol", "==", rol).stream())
        except Exception:
            snaps = []

    seen_ids: set[str] = set()
    for snap in snaps:
        snap_id = getattr(snap, "id", None)
        if isinstance(snap_id, str):
            if snap_id in seen_ids:
                continue
            seen_ids.add(snap_id)
        try:
            if not snap.exists:
                continue
        except Exception:
            pass
        data = snap.to_dict() or {}
        correo = str(data.get("correo") or "").strip().lower()
        if not correo:
            continue
        if not _tiene_rutinas_asignadas(correo):
            continue
        nombre = str(data.get("nombre") or "").strip()
        if not nombre and "@" in correo:
            nombre = correo.split("@", 1)[0].replace(".", " ").title()
        resultados.append(EntrenadorInfo(correo=correo, nombre=nombre or correo))

    resultados.sort(key=lambda item: item.nombre.lower())
    return resultados


def _render_metadata(metadata: Dict) -> None:
    st.subheader("Datos del resumen")
    if not metadata:
        st.info("No se encontraron datos para el resumen seleccionado.")
        return

    bloques_terminados = metadata.get("bloques_terminados") or []
    bloques_proximos = metadata.get("bloques_proximos") or []
    comentarios = metadata.get("comentarios") or []

    cols = st.columns(3)
    cols[0].metric("Bloques terminan esta semana", len(bloques_terminados))
    cols[1].metric("Bloques terminan próxima semana", len(bloques_proximos))
    cols[2].metric("Comentarios capturados", len(comentarios))

    with st.expander("Bloques que terminan esta semana", expanded=False):
        if bloques_terminados:
            st.table([
                {
                    "Deportista": item.get("cliente", ""),
                    "Bloque": item.get("bloque_id", "")[:8],
                    "Semanas": item.get("total_semanas", ""),
                }
                for item in bloques_terminados
            ])
        else:
            st.caption("Sin bloques terminando esta semana.")

    with st.expander("Bloques que terminan la próxima semana", expanded=False):
        if bloques_proximos:
            st.table([
                {
                    "Deportista": item.get("cliente", ""),
                    "Bloque": item.get("bloque_id", "")[:8],
                    "Semanas": item.get("total_semanas", ""),
                }
                for item in bloques_proximos
            ])
        else:
            st.caption("Sin bloques terminando la próxima semana.")

    with st.expander("Comentarios incluidos", expanded=False):
        if comentarios:
            st.table([
                {
                    "Deportista": item.get("cliente", ""),
                    "Día": f"Día {item.get('dia')}" if item.get("dia") else "",
                    "Ejercicio": item.get("ejercicio", ""),
                    "Comentarios": "\n".join(f"- {texto}" for texto in item.get("comentarios", [])),
                }
                for item in comentarios
            ])
        else:
            st.caption("Sin comentarios registrados para la semana seleccionada.")


def ver_previsualizacion_correos() -> None:
    """Renderiza la pantalla de previsualización de correos semanales."""
    rol_actual = (st.session_state.get("rol") or "").strip().lower()
    if rol_actual not in {"admin", "administrador"}:
        st.warning("Solo los administradores pueden acceder a esta pantalla.")
        return

    st.title("📬 Previsualizador de correos semanales")
    st.caption(
        "Revisa quién recibirá el resumen dominical de bloques y cómo se verá el correo antes de enviarlo."
    )

    entrenadores = _listar_entrenadores()
    if not entrenadores:
        st.info("No se encontraron entrenadores con rutinas registradas.")
        return

    st.subheader("Destinatarios habilitados")
    dest_rows = [{"Nombre": e.nombre, "Correo": e.correo} for e in entrenadores]
    if dest_rows:
        st.dataframe(dest_rows, use_container_width=True, hide_index=True)

    fecha_referencia = st.date_input(
        "Fecha de referencia",
        value=date.today(),
        help="Se calcula el lunes de la semana seleccionada para el resumen.",
    )

    opciones = [f"{e.nombre} · {e.correo}" for e in entrenadores]
    seleccion_idx = st.selectbox(
        "Selecciona un entrenador para previsualizar",
        list(range(len(opciones))),
        format_func=lambda idx: opciones[idx],
    )

    entrenador_sel: Optional[EntrenadorInfo] = None
    if isinstance(seleccion_idx, int) and 0 <= seleccion_idx < len(entrenadores):
        entrenador_sel = entrenadores[seleccion_idx]

    if not entrenador_sel:
        st.warning("Selecciona un entrenador para ver la previsualización.")
        return

    st.divider()
    st.subheader(f"Vista previa para {entrenador_sel.nombre}")
    try:
        contenido = preparar_resumen_bloques_entrenador(
            entrenador_sel.correo,
            fecha_referencia=fecha_referencia,
        )
    except ValueError as exc:
        st.warning(str(exc))
        return
    except Exception as exc:
        st.error(f"No se pudo generar la previsualización: {exc}")
        return

    st.write(f"**Destinatario:** {entrenador_sel.nombre} `<{entrenador_sel.correo}>`")
    st.write(f"**Asunto:** {contenido.get('subject', '(sin asunto)')}")

    st.markdown("### Correo en HTML")
    st.markdown(contenido.get("html_body", ""), unsafe_allow_html=True)

    st.markdown("### Texto plano")
    st.code(contenido.get("text_body", ""), language="markdown")

    metadata = contenido.get("metadata") or {}
    _render_metadata(metadata)
