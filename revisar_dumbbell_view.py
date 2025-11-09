from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Dict, List, Tuple

import streamlit as st

from app_core.firebase_client import get_db


DUMBELL_REGEX = re.compile(r"dumbell", re.IGNORECASE)


@dataclass
class CambioDetalle:
    path: str
    antes: str
    despues: str
    coincidencias: int


@dataclass
class RutinaIncidencia:
    doc_id: str
    fecha_lunes: str | None
    reemplazos: int
    detalles: List[CambioDetalle]
    data_actualizada: Dict[str, Any]
    data_original: Dict[str, Any]
    doc_ref: Any


def _replace_preserving_case(texto: str) -> str:
    """Reemplaza manteniendo mayúsculas/minúsculas similares."""
    if not texto:
        return texto

    def _replacement(match: re.Match[str]) -> str:
        palabra = match.group(0)
        if palabra.isupper():
            return "DUMBBELL"
        if palabra[0].isupper():
            return "Dumbbell"
        return "dumbbell"

    return DUMBELL_REGEX.sub(_replacement, texto)


def _limpiar_empresa(valor: str | None) -> str:
    return (valor or "").strip().title()


@st.cache_data(ttl=180)
def _listar_deportistas() -> List[Dict[str, str]]:
    db = get_db()
    usuarios: List[Dict[str, str]] = []
    try:
        snaps = db.collection("usuarios").where("rol", "==", "deportista").stream()
        for snap in snaps:
            data = snap.to_dict() or {}
            correo = (data.get("correo") or "").strip().lower()
            if not correo:
                continue
            nombre = (
                data.get("nombre")
                or data.get("primer_nombre")
                or data.get("Nombre")
                or correo.split("@")[0]
            )
            usuarios.append(
                {
                    "correo": correo,
                    "nombre": nombre.strip() or correo,
                    "empresa": _limpiar_empresa(data.get("empresa") or data.get("empresa_id")),
                }
            )
    except Exception as exc:
        st.error(f"No se pudieron cargar los deportistas: {exc}")
        return []

    usuarios.sort(key=lambda item: (item["nombre"].lower(), item["correo"]))
    return usuarios


def _replace_in_payload(value: Any, path: str, detalles: List[CambioDetalle]) -> Tuple[Any, int]:
    """Recorrido profundo para aplicar reemplazos y registrar cada cambio."""
    if isinstance(value, dict):
        cambiado = {}
        total = 0
        for key, sub_value in value.items():
            child_path = f"{path}.{key}" if path else str(key)
            nuevo, sub_total = _replace_in_payload(sub_value, child_path, detalles)
            cambiado[key] = nuevo
            total += sub_total
        return cambiado, total

    if isinstance(value, list):
        nuevos: List[Any] = []
        total = 0
        for idx, item in enumerate(value):
            child_path = f"{path}[{idx}]" if path else f"[{idx}]"
            nuevo, sub_total = _replace_in_payload(item, child_path, detalles)
            nuevos.append(nuevo)
            total += sub_total
        return nuevos, total

    if isinstance(value, str) and value:
        if DUMBELL_REGEX.search(value):
            reemplazos = len(DUMBELL_REGEX.findall(value))
            nuevo_texto = _replace_preserving_case(value)
            detalles.append(
                CambioDetalle(
                    path=path or "(raíz)",
                    antes=value,
                    despues=nuevo_texto,
                    coincidencias=reemplazos,
                )
            )
            return nuevo_texto, reemplazos
    return value, 0


def _buscar_incidencias_en_rutinas(correo: str) -> List[RutinaIncidencia]:
    db = get_db()
    incidencias: List[RutinaIncidencia] = []

    try:
        snaps = list(db.collection("rutinas_semanales").where("correo", "==", correo).stream())
    except Exception as exc:
        st.error(f"No se pudieron consultar las rutinas de {correo}: {exc}")
        return incidencias

    for snap in snaps:
        if not snap.exists:
            continue
        data_orig = snap.to_dict() or {}
        detalles: List[CambioDetalle] = []
        data_actualizada, total = _replace_in_payload(data_orig, "", detalles)
        if total <= 0:
            continue
        incidencias.append(
            RutinaIncidencia(
                doc_id=snap.id,
                fecha_lunes=str(data_orig.get("fecha_lunes") or data_orig.get("fecha") or "Sin fecha"),
                reemplazos=total,
                detalles=detalles,
                data_actualizada=data_actualizada,
                data_original=data_orig,
                doc_ref=snap.reference,
            )
        )
    return incidencias


def revisar_dumbbell_admin_view() -> None:
    st.header("Revisión de ejercicios con 'Dumbell'")
    st.caption("Corrige rutinas antiguas reemplazando automáticamente 'Dumbell' por 'Dumbbell'.")

    deportistas = _listar_deportistas()
    if not deportistas:
        st.info("No hay deportistas para mostrar.")
        return

    opciones = {item["correo"]: f"{item['nombre']} · {item['correo']}" for item in deportistas}
    correos = list(opciones.keys())
    select_options = [""] + correos

    def _format_option(value: str) -> str:
        if not value:
            return "— Selecciona un deportista —"
        return opciones.get(value, value)

    seleccionado = st.selectbox(
        "Elige un deportista",
        options=select_options,
        index=0,
        format_func=_format_option,
        key="revisar_dumbbell_select",
    )

    if not seleccionado:
        st.info("Selecciona un deportista para comenzar.")
        return

    atleta = next((item for item in deportistas if item["correo"] == seleccionado), None)
    if atleta:
        empresa_label = atleta.get("empresa") or "Sin empresa definida"
        st.caption(f"Empresa asignada: {empresa_label}")

    with st.spinner("Buscando coincidencias en sus rutinas..."):
        incidencias = _buscar_incidencias_en_rutinas(seleccionado)

    if not incidencias:
        st.success("✅ No se encontraron ejercicios con 'Dumbell' en sus rutinas.")
        return

    total_docs = len(incidencias)
    total_reemplazos = sum(item.reemplazos for item in incidencias)
    st.warning(f"Se encontraron {total_reemplazos} coincidencias en {total_docs} semana(s).")

    incidencias_ordenadas = sorted(incidencias, key=lambda i: i.fecha_lunes or "")

    for idx, incidencia in enumerate(incidencias_ordenadas, start=1):
        resumen = f"Semana {incidencia.fecha_lunes} · {incidencia.reemplazos} reemplazos"
        expanded = idx == 1
        with st.expander(resumen, expanded=expanded):
            st.markdown(f"- Documento: `{incidencia.doc_id}`")
            sample = incidencia.detalles[:5]
            if sample:
                st.markdown("**Cambios detectados (primeros 5):**")
                for cambio in sample:
                    st.markdown(
                        f"- `{cambio.path}`: `{cambio.antes}` → `{cambio.despues}` "
                        f"({cambio.coincidencias} coincidencia(s))"
                    )
            restantes = len(incidencia.detalles) - len(sample)
            if restantes > 0:
                st.caption(f"... y {restantes} cambios adicionales en este documento.")

    st.markdown("### Corregir una semana específica")
    opciones_semanas = [""] + [inc.doc_id for inc in incidencias_ordenadas]
    label_por_doc = {
        inc.doc_id: f"{inc.fecha_lunes} · {inc.reemplazos} coincidencia(s)" for inc in incidencias_ordenadas
    }

    def _format_semana(doc_id: str) -> str:
        if not doc_id:
            return "— Selecciona la semana —"
        return label_por_doc.get(doc_id, doc_id)

    semana_sel = st.selectbox(
        "Semana a corregir",
        options=opciones_semanas,
        index=0,
        format_func=_format_semana,
        key="revisar_dumbbell_semana_select",
    )

    if not semana_sel:
        st.info("Elige una semana y aplica la corrección para avanzar 1 a 1.")
        return

    incidencia_sel = next((inc for inc in incidencias_ordenadas if inc.doc_id == semana_sel), None)
    if incidencia_sel is None:
        st.error("No se pudo localizar la semana seleccionada.")
        return

    st.markdown(
        f"**Documento:** `{incidencia_sel.doc_id}` · Fecha: {incidencia_sel.fecha_lunes} · "
        f"{incidencia_sel.reemplazos} coincidencia(s)"
    )
    st.markdown("**Cambios detectados (primeros 10):**")
    for cambio in incidencia_sel.detalles[:10]:
        st.markdown(
            f"- `{cambio.path}`: `{cambio.antes}` → `{cambio.despues}` "
            f"({cambio.coincidencias} coincidencia(s))"
        )
    restantes = len(incidencia_sel.detalles) - min(10, len(incidencia_sel.detalles))
    if restantes > 0:
        st.caption(f"... y {restantes} cambios adicionales en esta semana.")

    if st.button("Aplicar corrección a esta semana", type="primary", key=f"aplicar_{semana_sel}"):
        try:
            incidencia_sel.doc_ref.set(incidencia_sel.data_actualizada)
            st.success("Corrección aplicada correctamente.")
            st.cache_data.clear()
            st.rerun()
        except Exception as exc:
            st.error(f"No se pudo actualizar la semana seleccionada: {exc}")
