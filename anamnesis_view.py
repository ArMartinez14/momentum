from __future__ import annotations

from contextlib import nullcontext
from datetime import date, datetime
from typing import Any, Optional
from uuid import uuid4

import streamlit as st
from firebase_admin import firestore

from app_core.firebase_client import get_db
from app_core.utils import correo_a_doc_id

COLLECTION_NAME = "anamnesis_respuestas"
FORM_COLLECTION = "anamnesis_formularios"
GESTOR_ROLES = {"entrenador", "coach", "admin", "administrador"}
QUESTION_TYPE_TEXTO = "texto"
QUESTION_TYPE_SELECCION = "seleccion"


def _doc_id(correo: str | None) -> str:
    return (correo or "").strip().lower()


def _form_doc_id(correo: str | None) -> str:
    correo = (correo or "").strip().lower()
    if not correo:
        return ""
    return correo_a_doc_id(correo)


def _parse_fecha_guardada(value: Any) -> Optional[date]:
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        try:
            return datetime.fromisoformat(value).date()
        except ValueError:
            return None
    return None


def obtener_respuestas(db: firestore.Client, correo: str) -> dict[str, Any]:
    if not correo:
        return {}
    doc = db.collection(COLLECTION_NAME).document(_doc_id(correo)).get()
    if not doc.exists:
        return {}
    data = doc.to_dict() or {}
    if "fecha_nacimiento" in data:
        data["fecha_nacimiento"] = _parse_fecha_guardada(data["fecha_nacimiento"])
    if "disponibilidad_semanal" in data:
        data["disponibilidad_semanal"] = _parse_rango_disponibilidad(
            data["disponibilidad_semanal"]
        )
    return data


def _obtener_usuario(db: firestore.Client, correo: str) -> dict[str, Any]:
    if not correo:
        return {}
    try:
        snap = db.collection("usuarios").document(correo_a_doc_id(correo)).get()
        if snap.exists:
            return snap.to_dict() or {}
    except Exception:
        return {}
    return {}


def _desactivar_requisito_anamnesis(db: firestore.Client, correo: str) -> None:
    correo = (correo or "").strip().lower()
    if not correo:
        return
    try:
        db.collection("usuarios").document(correo_a_doc_id(correo)).set(
            {"requiere_anamnesis": False},
            merge=True,
        )
    except Exception:
        pass


def _resolver_coach_para_usuario(db: firestore.Client, correo: str, rol: str) -> Optional[str]:
    rol_norm = (rol or "").strip().lower()
    if rol_norm in {"entrenador", "coach", "admin", "administrador"}:
        return correo
    data = _obtener_usuario(db, correo)
    coach = (data.get("coach_responsable") or "").strip().lower()
    return coach or None


def obtener_formulario_coach(db: firestore.Client, coach_correo: Optional[str]) -> dict[str, Any]:
    coach = (coach_correo or "").strip().lower()
    if not coach:
        return {}
    doc = db.collection(FORM_COLLECTION).document(_form_doc_id(coach)).get()
    if not doc.exists:
        return {}
    data = doc.to_dict() or {}
    preguntas = data.get("preguntas") or []
    parsed: list[dict[str, Any]] = []
    for item in preguntas:
        q_id = str(item.get("id") or item.get("key") or uuid4().hex)
        titulo = str(item.get("titulo") or item.get("pregunta") or "").strip()
        tipo = str(item.get("tipo") or QUESTION_TYPE_TEXTO).strip().lower()
        opciones_raw = item.get("opciones") or []
        if not isinstance(opciones_raw, list):
            opciones_raw = []
        opciones = [str(opt).strip() for opt in opciones_raw if str(opt).strip()]
        if not titulo:
            continue
        if tipo not in (QUESTION_TYPE_TEXTO, QUESTION_TYPE_SELECCION):
            tipo = QUESTION_TYPE_TEXTO
        parsed.append({
            "id": q_id,
            "titulo": titulo,
            "tipo": tipo,
            "opciones": opciones,
        })
    data["preguntas"] = parsed
    return data


def guardar_formulario_coach(
    db: firestore.Client,
    coach_correo: str,
    preguntas: list[dict[str, Any]],
    actualizado_por: str,
) -> None:
    doc_id = _form_doc_id(coach_correo)
    if not doc_id:
        return
    payload = {
        "coach": coach_correo,
        "preguntas": preguntas,
        "actualizado_por": actualizado_por,
        "fecha_actualizacion": datetime.utcnow(),
    }
    db.collection(FORM_COLLECTION).document(doc_id).set(payload, merge=True)


def _nueva_pregunta() -> dict[str, Any]:
    return {
        "id": uuid4().hex,
        "titulo": "",
        "tipo": QUESTION_TYPE_TEXTO,
        "opciones": [],
    }


def _parse_rango_disponibilidad(value: Any) -> tuple[int, int]:
    """Normaliza la disponibilidad semanal a un rango (min, max)."""
    def _clip(val: int) -> int:
        return max(1, min(7, val))

    if isinstance(value, dict):
        minimo = value.get("min") or value.get("minimo") or value.get("desde") or value.get("inferior")
        maximo = value.get("max") or value.get("maximo") or value.get("hasta") or value.get("superior")
        try:
            minimo = int(minimo)
        except Exception:
            minimo = None
        try:
            maximo = int(maximo)
        except Exception:
            maximo = None
        if minimo is not None and maximo is not None:
            minimo, maximo = _clip(minimo), _clip(maximo)
            if minimo > maximo:
                minimo, maximo = maximo, minimo
            return (minimo, maximo)
        if minimo is not None:
            minimo = _clip(minimo)
            return (minimo, minimo)
        if maximo is not None:
            maximo = _clip(maximo)
            return (maximo, maximo)
    if isinstance(value, (list, tuple)) and value:
        try:
            nums = [int(v) for v in value if v is not None]
        except Exception:
            nums = []
        if nums:
            nums = [_clip(n) for n in nums]
            return (min(nums), max(nums))
    if isinstance(value, (int, float)):
        val = _clip(int(value))
        return (val, val)
    return (3, 4)


def necesita_anamnesis(db: firestore.Client, correo: str) -> bool:
    if not correo:
        return False
    user_data = _obtener_usuario(db, correo)
    rol = (user_data.get("rol") or "").strip().lower()
    requiere = bool(user_data.get("requiere_anamnesis")) and rol == "deportista"
    if not requiere:
        st.session_state["anamnesis_pendiente"] = False
        return False
    if st.session_state.get("anamnesis_completa") is True:
        return False
    data = obtener_respuestas(db, correo)
    completado = bool(data.get("completado"))
    if completado:
        st.session_state["anamnesis_completa"] = True
        st.session_state["anamnesis_pendiente"] = False
        return False
    st.session_state["anamnesis_pendiente"] = True
    return True


def _enum_index(opciones: list[str], valor: str) -> int:
    if valor in opciones:
        return opciones.index(valor)
    return 0


def render_anamnesis(db: Optional[firestore.Client] = None) -> None:
    st.header("🩺 Anamnesis Inicial")
    if st.session_state.get("anamnesis_pendiente"):
        st.warning("Completa esta anamnesis para desbloquear el resto de la aplicación.")
    st.caption(
        "Queremos conocer mejor tu estado actual para personalizar tu experiencia. "
        "Contesta esta encuesta una sola vez; podrás actualizarla cuando cambien tus datos."
    )

    correo = (st.session_state.get("correo") or "").strip().lower()
    if not correo:
        st.warning("No detectamos un correo asociado a tu sesión. Inicia sesión nuevamente.")
        return

    db = db or get_db()
    rol_usuario = (st.session_state.get("rol") or "").strip().lower()
    doc_id = _doc_id(correo)
    doc_ref = db.collection(COLLECTION_NAME).document(doc_id)
    datos_previos = obtener_respuestas(db, correo)

    es_gestor = rol_usuario in GESTOR_ROLES
    if es_gestor:
        tab_form, tab_respuestas = st.tabs(["Cuestionario", "Respuestas de deportistas"])
    else:
        tab_form = nullcontext()
        tab_respuestas = None

    with tab_form:
        if datos_previos:
            ultima = datos_previos.get("ultima_actualizacion")
            ultima_str = ""
            if isinstance(ultima, datetime):
                ultima_str = ultima.strftime("%d/%m/%Y %H:%M")
            elif isinstance(ultima, str):
                ultima_str = ultima
            if ultima_str:
                st.info(
                    f"Tus datos fueron actualizados por última vez el {ultima_str}. Puedes modificarlos si lo necesitas."
                )

        coach_form_owner = _resolver_coach_para_usuario(db, correo, rol_usuario)
        formulario_personalizado = (
            obtener_formulario_coach(db, coach_form_owner) if coach_form_owner else {}
        )
        preguntas_personalizadas = formulario_personalizado.get("preguntas") or []
        prev_personalizadas: dict[str, str] = {}
        for item in datos_previos.get("respuestas_personalizadas", []) or []:
            qid = item.get("id")
            if qid:
                prev_personalizadas[qid] = item.get("respuesta", "")
        respuestas_personalizadas_form: dict[str, str] = {}

        disp_min, disp_max = datos_previos.get("disponibilidad_semanal", (3, 4))
        if not isinstance(disp_min, int) or not isinstance(disp_max, int):
            disp_min, disp_max = _parse_rango_disponibilidad((disp_min, disp_max))
        preseleccion = {disp_min, disp_max}
        if len(preseleccion) < 2:
            candidato = disp_min + 1 if disp_min < 7 else disp_min - 1
            if 1 <= candidato <= 7:
                preseleccion.add(candidato)
        dias_seleccionados_form: list[int] = []

        fecha_nacimiento_prev = datos_previos.get("fecha_nacimiento")
        fecha_nacimiento_texto = _format_fecha_ddmmaaaa(fecha_nacimiento_prev)
        condicion_prev = datos_previos.get("condicion_medica") or ""
        lesiones_prev = (
            datos_previos.get("lesiones_cirugias")
            or datos_previos.get("lesiones")
            or ""
        )
        suplementos_detalle_prev = (
            datos_previos.get("suplementos_med_detalle")
            or datos_previos.get("medicacion")
            or ""
        )
        suplementos_prev = datos_previos.get("suplementos_med")
        if suplementos_prev not in {"Sí", "No"}:
            suplementos_prev = "Sí" if suplementos_detalle_prev else "No"
        tiempo_sesion_prev = datos_previos.get("tiempo_sesion") or ""
        ultimo_entrenamiento_prev = (
            datos_previos.get("tiempo_ultimo_entrenamiento")
            or datos_previos.get("experiencia")
            or ""
        )
        actividad_prev = datos_previos.get("actividad_extra")
        if actividad_prev not in {"Sí", "No"}:
            actividad_prev = "Sí" if datos_previos.get("actividad_extra_detalle") else "No"
        actividad_detalle_prev = datos_previos.get("actividad_extra_detalle") or ""

        objetivo_opciones = [
            "Pérdida de grasa",
            "Aumento de masa muscular",
            "Mejorar salud / condición física",
            "Rendimiento deportivo",
            "Otro (especificar)",
        ]
        objetivo_prev = datos_previos.get("objetivo_principal") or datos_previos.get("objetivo") or ""
        objetivo_otro_prev = datos_previos.get("objetivo_principal_otro") or ""
        if objetivo_prev and objetivo_prev not in objetivo_opciones:
            objetivo_otro_prev = objetivo_otro_prev or objetivo_prev
            objetivo_prev = "Otro (especificar)"
        if not objetivo_prev:
            objetivo_prev = objetivo_opciones[0]

        expectativa_opciones = [
            "Disciplina y constancia",
            "Aprender técnica",
            "Mejorar mi salud",
            "Socializar",
            "Otro (especificar)",
        ]
        expectativa_prev = datos_previos.get("expectativa") or datos_previos.get("comentarios") or ""
        expectativa_otro_prev = datos_previos.get("expectativa_otro") or ""
        if expectativa_prev and expectativa_prev not in expectativa_opciones:
            expectativa_otro_prev = expectativa_otro_prev or expectativa_prev
            expectativa_prev = "Otro (especificar)"
        if not expectativa_prev:
            expectativa_prev = expectativa_opciones[0]

        tiempo_sesion_opciones = [
            "Menos de 1 hora",
            "1 hora",
            "Más de 1 hora",
        ]
        ultimo_entrenamiento_opciones = [
            "Actualmente entreno",
            "Hace menos de 3 meses",
            "Hace más de 3 meses",
            "Nunca he entrenado",
        ]

        with st.form("anamnesis_form"):
            st.markdown("### 🩺 Salud y antecedentes")
            fecha_nacimiento_input = st.text_input(
                "Fecha de nacimiento (DD/MM/AAAA)",
                value=fecha_nacimiento_texto,
                placeholder="DD/MM/AAAA",
                help="Ingresa la fecha siguiendo el formato Día/Mes/Año.",
            )

            condicion_medica = st.text_area(
                "¿Tienes alguna enfermedad o condición médica que debamos conocer?",
                value=condicion_prev,
                placeholder="Ej.: hipertensión, diabetes, asma, etc.",
            )

            lesiones_cirugias = st.text_area(
                "¿Tienes o has tenido alguna lesión o cirugía importante?",
                value=lesiones_prev,
                placeholder="Si la tienes actualmente, descríbela brevemente.",
            )

            suplementos_opciones = ["Sí", "No"]
            suplementos = st.radio(
                "¿Estás tomando algún suplemento o medicamento actualmente?",
                suplementos_opciones,
                index=_enum_index(suplementos_opciones, suplementos_prev),
                horizontal=True,
            )
            suplementos_detalle = ""
            if suplementos == "Sí":
                suplementos_detalle = st.text_input(
                    "Especifica cuál",
                    value=suplementos_detalle_prev,
                )
            else:
                suplementos_detalle = ""

            st.markdown("### ⚡️ Hábitos y entrenamiento")
            st.markdown("**¿Cuántos días a la semana puedes entrenar?**")
            st.caption("Selecciona exactamente dos opciones para indicar tu rango (mínimo y máximo).")
            cols_dias = st.columns(7)
            for idx, dia in enumerate(range(1, 8)):
                with cols_dias[idx]:
                    marcado = st.checkbox(
                        str(dia),
                        value=(dia in preseleccion),
                        key=f"anamnesis_dia_semana_{dia}",
                    )
                if marcado:
                    dias_seleccionados_form.append(dia)

            tiempo_sesion = st.radio(
                "¿Cuánto tiempo puedes dedicar a cada sesión?",
                tiempo_sesion_opciones,
                index=_enum_index(tiempo_sesion_opciones, tiempo_sesion_prev or tiempo_sesion_opciones[0]),
            )

            ultimo_entrenamiento = st.radio(
                "¿Hace cuánto tiempo no realizas entrenamiento con pesas?",
                ultimo_entrenamiento_opciones,
                index=_enum_index(
                    ultimo_entrenamiento_opciones,
                    ultimo_entrenamiento_prev or ultimo_entrenamiento_opciones[0],
                ),
            )

            actividad = st.radio(
                "¿Practicas algún deporte o actividad fuera del gimnasio?",
                ["Sí", "No"],
                index=_enum_index(["Sí", "No"], actividad_prev),
                horizontal=True,
            )
            actividad_detalle = ""
            if actividad == "Sí":
                actividad_detalle = st.text_input(
                    "¿Cuál?",
                    value=actividad_detalle_prev,
                )
            else:
                actividad_detalle = ""

            st.markdown("### 🎯 Objetivos y motivación")
            objetivo_principal = st.radio(
                "¿Cuál es tu principal objetivo?",
                objetivo_opciones,
                index=_enum_index(objetivo_opciones, objetivo_prev),
            )
            objetivo_principal_otro = ""
            if objetivo_principal == "Otro (especificar)":
                objetivo_principal_otro = st.text_input(
                    "Especifica tu objetivo",
                    value=objetivo_otro_prev,
                )
            else:
                objetivo_principal_otro = ""

            expectativa = st.radio(
                "¿Qué esperas lograr con la asesoría o tu experiencia en el gimnasio?",
                expectativa_opciones,
                index=_enum_index(expectativa_opciones, expectativa_prev),
            )
            expectativa_otro = ""
            if expectativa == "Otro (especificar)":
                expectativa_otro = st.text_input(
                    "Especifica qué esperas lograr",
                    value=expectativa_otro_prev,
                )
            else:
                expectativa_otro = ""

            if preguntas_personalizadas:
                st.markdown("### 📝 Preguntas adicionales de tu coach")
                for pregunta in preguntas_personalizadas:
                    qid = pregunta.get("id") or uuid4().hex
                    titulo = pregunta.get("titulo") or "Pregunta"
                    tipo = pregunta.get("tipo") or QUESTION_TYPE_TEXTO
                    tipo = tipo if tipo in (QUESTION_TYPE_TEXTO, QUESTION_TYPE_SELECCION) else QUESTION_TYPE_TEXTO
                    key_base = f"custom_{qid}"
                    if tipo == QUESTION_TYPE_SELECCION:
                        opciones = pregunta.get("opciones") or []
                        if not opciones:
                            respuesta = st.text_input(
                                titulo,
                                value=prev_personalizadas.get(qid, ""),
                                key=key_base,
                            )
                            respuestas_personalizadas_form[qid] = respuesta.strip()
                        else:
                            opciones_combo = ["— Selecciona —"] + opciones
                            valor_prev = prev_personalizadas.get(qid, "")
                            try:
                                index = opciones_combo.index(valor_prev) if valor_prev else 0
                            except ValueError:
                                index = 0
                            seleccion = st.selectbox(
                                titulo,
                                opciones_combo,
                                index=index,
                                key=key_base,
                            )
                            respuestas_personalizadas_form[qid] = "" if seleccion == "— Selecciona —" else seleccion
                    else:
                        respuesta = st.text_area(
                            titulo,
                            value=prev_personalizadas.get(qid, ""),
                            key=key_base,
                        )
                        respuestas_personalizadas_form[qid] = respuesta.strip()

            submitted = st.form_submit_button("Guardar Anamnesis", type="primary")

        dias_seleccionados = sorted(set(dias_seleccionados_form))

        if submitted:
            errores = False
            respuestas_personalizadas_guardar: list[dict[str, Any]] = []

            fecha_nacimiento_value: Optional[date] = None
            fecha_nacimiento_input_str = (fecha_nacimiento_input or "").strip()
            if fecha_nacimiento_input_str:
                try:
                    fecha_nacimiento_value = datetime.strptime(
                        fecha_nacimiento_input_str, "%d/%m/%Y"
                    ).date()
                except ValueError:
                    st.warning("Ingresa la fecha de nacimiento con formato DD/MM/AAAA.")
                    errores = True
            else:
                st.warning("La fecha de nacimiento es obligatoria.")
                errores = True

            if len(dias_seleccionados) != 2:
                st.warning("Selecciona exactamente dos días para indicar tu rango de entrenamiento semanal.")
                errores = True

            if preguntas_personalizadas:
                faltantes_personalizadas: list[str] = []
                for pregunta in preguntas_personalizadas:
                    qid = pregunta.get("id") or uuid4().hex
                    titulo = pregunta.get("titulo") or "Pregunta"
                    respuesta_val = (respuestas_personalizadas_form.get(qid) or "").strip()
                    if not respuesta_val:
                        faltantes_personalizadas.append(titulo)
                    respuestas_personalizadas_guardar.append({
                        "id": qid,
                        "pregunta": titulo,
                        "tipo": pregunta.get("tipo") or QUESTION_TYPE_TEXTO,
                        "respuesta": respuesta_val,
                    })
                if faltantes_personalizadas:
                    st.warning(
                        "Completa todas las preguntas personalizadas: " + ", ".join(faltantes_personalizadas)
                    )
                    errores = True

            if not errores:
                dias_min, dias_max = dias_seleccionados
                ahora = datetime.utcnow()
                payload = {
                    "correo": correo,
                    "fecha_nacimiento": fecha_nacimiento_value.isoformat() if fecha_nacimiento_value else None,
                    "condicion_medica": condicion_medica.strip(),
                    "lesiones_cirugias": lesiones_cirugias.strip(),
                    "suplementos_med": suplementos,
                    "suplementos_med_detalle": suplementos_detalle.strip(),
                    "tiempo_sesion": tiempo_sesion,
                    "tiempo_ultimo_entrenamiento": ultimo_entrenamiento,
                    "actividad_extra": actividad,
                    "actividad_extra_detalle": actividad_detalle.strip(),
                    "objetivo_principal": objetivo_principal,
                    "objetivo_principal_otro": objetivo_principal_otro.strip(),
                    "expectativa": expectativa,
                    "expectativa_otro": expectativa_otro.strip(),
                    "disponibilidad_semanal": {
                        "min": int(dias_min),
                        "max": int(dias_max),
                    },
                    "disponibilidad_semanal_min": int(dias_min),
                    "disponibilidad_semanal_max": int(dias_max),
                    "completado": True,
                    "ultima_actualizacion": ahora,
                    "fecha_actualizacion": ahora,
                }
                payload["objetivo"] = objetivo_principal_otro.strip() or objetivo_principal
                payload["experiencia"] = ultimo_entrenamiento
                payload["lesiones"] = lesiones_cirugias.strip()
                payload["medicacion"] = suplementos_detalle.strip() if suplementos == "Sí" else ""
                payload["habitos"] = condicion_medica.strip()
                payload["comentarios"] = expectativa_otro.strip() or expectativa

                if not datos_previos.get("creado_en"):
                    payload["creado_en"] = ahora

                if preguntas_personalizadas:
                    payload["respuestas_personalizadas"] = respuestas_personalizadas_guardar
                if coach_form_owner:
                    payload["form_coach_owner"] = coach_form_owner

                try:
                    doc_ref.set(payload, merge=True)
                    _desactivar_requisito_anamnesis(db, correo)
                    st.success("¡Gracias! Tu anamnesis fue guardada correctamente.")
                    st.session_state["anamnesis_completa"] = True
                    st.session_state["anamnesis_pendiente"] = False
                except Exception as exc:  # pragma: no cover
                    st.error(f"No se pudo guardar la anamnesis: {exc}")

        if es_gestor:
            st.markdown("---")
            _render_anamnesis_config(db, coach_form_owner or correo, formulario_personalizado)

    if tab_respuestas is not None:
        with tab_respuestas:
            coach_filter = correo if rol_usuario in {"entrenador", "coach"} else None
            _render_respuestas_deportistas(db, rol_usuario, coach_filter)


def _render_anamnesis_config(
    db: firestore.Client,
    coach_correo: str,
    formulario_actual: Optional[dict[str, Any]] = None,
) -> None:
    st.subheader("⚙️ Configura tu anamnesis personalizada")
    st.caption(
        "Agrega preguntas de texto o selección múltiple. Tus clientes verán estas preguntas "
        "cuando ingresen a su formulario de anamnesis."
    )

    if not coach_correo:
        st.info("No se detectó un coach responsable para configurar este formulario.")
        return

    data_form = formulario_actual or obtener_formulario_coach(db, coach_correo)
    preguntas_iniciales = data_form.get("preguntas") or []
    state_key = f"anamnesis_builder_{_doc_id(coach_correo)}"

    if state_key not in st.session_state:
        st.session_state[state_key] = [dict(p) for p in preguntas_iniciales] or []

    preguntas_state: list[dict[str, Any]] = st.session_state[state_key]

    col_add, col_reset, _ = st.columns([1, 1, 6])
    with col_add:
        if st.button("Agregar pregunta", key=f"btn_add_question_{state_key}"):
            preguntas_state.append(_nueva_pregunta())
            st.rerun()
    with col_reset:
        if st.button("Restablecer cambios", key=f"btn_reset_question_{state_key}"):
            st.session_state[state_key] = [dict(p) for p in preguntas_iniciales] or []
            st.rerun()

    if not preguntas_state:
        st.info("Aún no tienes preguntas configuradas.")

    for idx, pregunta in enumerate(preguntas_state):
        pregunta.setdefault("id", uuid4().hex)
        pregunta.setdefault("tipo", QUESTION_TYPE_TEXTO)
        pregunta.setdefault("opciones", [])
        with st.container():
            st.markdown(f"**Pregunta {idx + 1}**")
            texto = st.text_input(
                "Texto de la pregunta",
                value=pregunta.get("titulo", ""),
                key=f"{pregunta['id']}_titulo",
            )
            pregunta["titulo"] = texto
            tipo_label = st.selectbox(
                "Tipo de respuesta",
                ["Texto libre", "Selección múltiple"],
                index=0 if pregunta["tipo"] == QUESTION_TYPE_TEXTO else 1,
                key=f"{pregunta['id']}_tipo",
            )
            pregunta["tipo"] = QUESTION_TYPE_TEXTO if tipo_label == "Texto libre" else QUESTION_TYPE_SELECCION
            if pregunta["tipo"] == QUESTION_TYPE_SELECCION:
                opciones_value = "\n".join(pregunta.get("opciones") or [])
                opciones_input = st.text_area(
                    "Opciones (una por línea)",
                    value=opciones_value,
                    key=f"{pregunta['id']}_opciones",
                )
                pregunta["opciones"] = [opt.strip() for opt in opciones_input.splitlines() if opt.strip()]
            else:
                pregunta["opciones"] = []
            if st.button("Eliminar", key=f"del_{pregunta['id']}"):
                preguntas_state.pop(idx)
                st.rerun()
        st.divider()

    if st.button("Guardar formulario personalizado", type="primary", key=f"save_form_{state_key}"):
        errores = []
        preguntas_guardar: list[dict[str, Any]] = []
        for idx, pregunta in enumerate(preguntas_state):
            titulo = (pregunta.get("titulo") or "").strip()
            tipo = pregunta.get("tipo") or QUESTION_TYPE_TEXTO
            opciones = pregunta.get("opciones") or []
            if not titulo:
                errores.append(f"La pregunta #{idx + 1} no tiene texto.")
                continue
            if tipo == QUESTION_TYPE_SELECCION and len(opciones) < 2:
                errores.append(f"La pregunta '{titulo}' necesita al menos dos opciones.")
            preguntas_guardar.append({
                "id": pregunta.get("id") or uuid4().hex,
                "titulo": titulo,
                "tipo": tipo,
                "opciones": opciones,
            })

        if errores:
            st.warning("No se pudo guardar el formulario: " + " ".join(errores))
            return
        if not preguntas_guardar:
            st.warning("Agrega al menos una pregunta antes de guardar.")
            return

        guardar_formulario_coach(db, coach_correo, preguntas_guardar, actualizado_por=coach_correo)
        st.success("Formulario de anamnesis guardado correctamente.")
        st.session_state.pop(state_key, None)
        st.rerun()


def _format_datetime_display(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%d/%m/%Y %H:%M")
    if isinstance(value, date):
        return value.strftime("%d/%m/%Y")
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value)
            return dt.strftime("%d/%m/%Y %H:%M")
        except Exception:
            return value
    return ""


def _format_fecha_display(value: Any) -> str:
    parsed = _parse_fecha_guardada(value)
    if parsed:
        return parsed.strftime("%d/%m/%Y")
    if isinstance(value, str):
        return value
    return "—"


def _format_fecha_ddmmaaaa(value: Any) -> str:
    parsed = _parse_fecha_guardada(value)
    if parsed:
        return parsed.strftime("%d/%m/%Y")
    if isinstance(value, str) and value:
        try:
            # Intento directo por si ya viene en el formato esperado
            datetime.strptime(value, "%d/%m/%Y")
            return value
        except Exception:
            pass
    return ""


def _format_disponibilidad_texto(datos: dict[str, Any]) -> str:
    disp = datos.get("disponibilidad_semanal")
    minimo = None
    maximo = None
    if isinstance(disp, dict):
        minimo = disp.get("min") or disp.get("minimo")
        maximo = disp.get("max") or disp.get("maximo")
    if minimo is None:
        minimo = datos.get("disponibilidad_semanal_min")
    if maximo is None:
        maximo = datos.get("disponibilidad_semanal_max")
    try:
        minimo = int(minimo) if minimo is not None else None
    except Exception:
        minimo = None
    try:
        maximo = int(maximo) if maximo is not None else None
    except Exception:
        maximo = None
    if minimo and maximo:
        if minimo == maximo:
            return f"{minimo} día(s) por semana"
        return f"{minimo} a {maximo} días por semana"
    if minimo:
        return f"{minimo} día(s) por semana"
    if maximo:
        return f"{maximo} día(s) por semana"
    return "—"


def _render_resumen_respuestas(datos: dict[str, Any]) -> None:
    base_fields = [
        ("Fecha de nacimiento", _format_fecha_display(datos.get("fecha_nacimiento"))),
        ("Condición médica", datos.get("condicion_medica") or "—"),
        ("Lesiones o cirugías", datos.get("lesiones_cirugias") or datos.get("lesiones") or "—"),
        (
            "Suplementos/medicación",
            (datos.get("suplementos_med") or "No")
            + (
                f" – {datos.get('suplementos_med_detalle')}"
                if datos.get("suplementos_med_detalle")
                else ""
            ),
        ),
        ("Disponibilidad semanal", _format_disponibilidad_texto(datos)),
        ("Tiempo por sesión", datos.get("tiempo_sesion") or "—"),
        ("Último entrenamiento", datos.get("tiempo_ultimo_entrenamiento") or datos.get("experiencia") or "—"),
        (
            "Actividad extra",
            (datos.get("actividad_extra") or "No")
            + (f" – {datos.get('actividad_extra_detalle')}" if datos.get("actividad_extra_detalle") else ""),
        ),
        ("Objetivo principal", datos.get("objetivo_principal") or datos.get("objetivo") or "—"),
        ("Expectativa", datos.get("expectativa") or datos.get("comentarios") or "—"),
    ]

    st.markdown("**Datos principales**")
    for label, value in base_fields:
        st.markdown(f"- **{label}:** {value if value else '—'}")

    personalizados = datos.get("respuestas_personalizadas") or []
    if personalizados:
        st.markdown("**Preguntas personalizadas**")
        for item in personalizados:
            pregunta = item.get("pregunta") or item.get("titulo") or "Pregunta"
            respuesta = item.get("respuesta") or "—"
            st.markdown(f"• {pregunta}: {respuesta}")


def _render_respuestas_deportistas(
    db: firestore.Client,
    rol_usuario: str,
    coach_correo: Optional[str],
) -> None:
    st.subheader("📂 Respuestas de deportistas")
    coach_norm = (coach_correo or "").strip().lower()
    try:
        snapshots = list(db.collection(COLLECTION_NAME).stream())
    except Exception as exc:
        st.error(f"No se pudieron leer las respuestas: {exc}")
        return

    registros: list[dict[str, Any]] = []
    for snap in snapshots:
        data = snap.to_dict() or {}
        correo_dep = (data.get("correo") or snap.id or "").strip().lower()
        if not correo_dep:
            continue
        usuario_meta = _obtener_usuario(db, correo_dep)
        coach_resp = (usuario_meta.get("coach_responsable") or data.get("form_coach_owner") or "").strip().lower()
        if coach_norm and rol_usuario not in {"admin", "administrador"}:
            if coach_resp and coach_resp != coach_norm:
                continue
            if not coach_resp and coach_norm != correo_dep:
                continue
        registros.append({
            "correo": correo_dep,
            "nombre": usuario_meta.get("nombre")
            or usuario_meta.get("primer_nombre")
            or data.get("nombre")
            or correo_dep.split("@")[0].title(),
            "coach": coach_resp,
            "ultima_actualizacion": data.get("ultima_actualizacion") or data.get("fecha_actualizacion"),
            "datos": data,
        })

    if not registros:
        st.info("Aún no hay respuestas registradas.")
        return

    registros.sort(key=lambda r: r.get("ultima_actualizacion") or datetime.min, reverse=True)

    busqueda = st.text_input("Buscar deportista", placeholder="Correo o nombre")
    if busqueda:
        q = busqueda.strip().lower()
        registros = [r for r in registros if q in r["correo"] or q in (r["nombre"] or "").lower()]
        if not registros:
            st.info("No se encontraron coincidencias con esa búsqueda.")
            return

    for registro in registros:
        header = f"{registro['nombre']} · {registro['correo']}"
        if registro.get("coach"):
            header += f" — Coach: {registro['coach']}"
        ultima_txt = _format_datetime_display(registro.get("ultima_actualizacion"))
        with st.expander(header, expanded=False):
            if ultima_txt:
                st.caption(f"Última actualización: {ultima_txt}")
            _render_resumen_respuestas(registro["datos"])
