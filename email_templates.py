from __future__ import annotations

import html
import re
from dataclasses import dataclass
from datetime import date
from typing import Any, Dict, List, Optional

DEFAULT_PORTAL_URL = "https://momentum-bclfppzmx8zykyrlkhfmr2.streamlit.app/"


@dataclass
class EmailContent:
    subject: str
    html_body: str
    text_body: Optional[str] = None


def _strip_html(value: str) -> str:
    text = re.sub(r"<\s*br\s*/?\s*>", "\n", value, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _formatear_fecha_es(fecha_obj: date) -> str:
    return fecha_obj.strftime("%d/%m/%Y")


def build_bienvenida_email(
    nombre: str,
    empresa_txt: str,
    es_coach: bool,
    portal_url: Optional[str],
    anamnesis_url: Optional[str],
    instrucciones_extra: Optional[str] = None,
) -> EmailContent:
    nombre = (nombre or "").strip()
    portal_destino = (portal_url or "").strip() or DEFAULT_PORTAL_URL

    if nombre:
        saludo = f"Hola {nombre},"
    else:
        saludo = "Hola,"

    if es_coach:
        instrucciones_html = (
            "A continuación encontrarás el botón para ingresar a la webapp. "
            "Tu correo de acceso es el mismo al que te llegó este mensaje."
        )
        bienvenida_html = (
            "¡Bienvenido a Momentum! Gracias por unirte a nuestra App. Tu cuenta ya está activa en nuestra plataforma."
        )
    else:
        instrucciones_html = (
            "Ingresa con tu correo desde el botón siguiente y, si es tu primer acceso, abre el menú "
            "<strong>Atleta</strong> y selecciona el submenú <strong>Anamnesis</strong> para completar la encuesta inicial."
        )
        bienvenida_html = f"¡Bienvenido a Momentum! Tu cuenta ya está activa en nuestra plataforma."

    if instrucciones_extra:
        instrucciones_html = f"{instrucciones_html} {instrucciones_extra.strip()}"

    boton_html = (
        "<table role='presentation' cellspacing='0' cellpadding='0'>"
        "<tr>"
        "<td style='border-radius:8px;background:#D64045;text-align:center;'>"
        f"<a href=\"{portal_destino}\" target=\"_blank\" "
        "style='display:inline-block;padding:12px 22px;color:#ffffff;font-weight:600;"
        "text-decoration:none;font-family:Helvetica,Arial,sans-serif;border-radius:8px;'>"
        "Ir a la app</a>"
        "</td>"
        "</tr>"
        "</table>"
    )

    html_parts = [
        "<html><body style='font-family:Helvetica,Arial,sans-serif;font-size:15px;color:#1f2933;'>",
        f"<p>{saludo}</p>",
        f"<p>{bienvenida_html}</p>",
        f"<p>{instrucciones_html}</p>",
        f"<div style='margin:24px 0;text-align:center;'>{boton_html}</div>",
    ]

    if not es_coach and anamnesis_url:
        html_parts.append(
            f"<p>Te pedimos completar la <strong>encuesta de anamnesis</strong> cuanto antes. "
            f"Accede desde <a href=\"{anamnesis_url}\" target=\"_blank\">este enlace</a> "
            "o entra al portal, abre el menú <strong>Atleta</strong> y selecciona el submenú <strong>Anamnesis</strong>. "
            "Recuerda usar el mismo correo con el que te registramos.</p>"
        )

    html_parts.extend(
        [
            "<p>Si necesitas apoyo, responde a este correo y tu entrenador te ayudará a resolver cualquier duda.</p>",
            (
                "<div style='margin-top:32px;border-top:1px solid #e2e8f0;padding-top:16px;font-size:14px;color:#64748b;'>"
                "<strong>Equipo Momentum</strong><br>"
                "Coaching y planificación personalizada<br>"
                f"<a href=\"{portal_destino}\" target=\"_blank\" style='color:#D64045;text-decoration:none;'>Visita la app</a>"
                "</div>"
            ),
            "</body></html>",
        ]
    )

    text_lines = [
        saludo.strip(","),
        bienvenida_html,
        _strip_html(instrucciones_html),
        f"Link de acceso: {portal_destino}",
    ]

    if not es_coach:
        if anamnesis_url:
            text_lines.append(f"Encuesta de anamnesis: {anamnesis_url}")
        else:
            text_lines.append(
                "Completa la anamnesis ingresando a la app (Menú Atleta > Anamnesis)."
            )

    text_lines.append(
        "Si necesitas apoyo, responde a este correo y tu entrenador te ayudará a resolver cualquier duda."
    )
    text_lines.append("Equipo Momentum - Coaching y planificación personalizada.")

    subject = "Bienvenido a Momentum" if es_coach else f"Bienvenido a {empresa_txt}"

    return EmailContent(
        subject=subject,
        html_body="\n".join(html_parts),
        text_body="\n\n".join(text_lines),
    )


def build_resumen_bloques_email(
    nombre_destino: str,
    lunes_actual: date,
    domingo_actual: date,
    bloques_terminados: List[Dict[str, Any]],
    bloques_proximos: List[Dict[str, Any]],
    comentarios_agrupados: List[Dict[str, Any]],
) -> EmailContent:
    nombre_destino = (nombre_destino or "").strip() or "Entrenador"
    rango_semana = f"{_formatear_fecha_es(lunes_actual)} al {_formatear_fecha_es(domingo_actual)}"
    subject = f"Resumen semanal de bloques | Semana del {_formatear_fecha_es(lunes_actual)}"

    html_parts = [
        "<html><body style='font-family:Helvetica,Arial,sans-serif;font-size:15px;color:#1f2933;line-height:1.6;'>",
        f"<p>Hola {html.escape(nombre_destino)},</p>",
        f"<p>Este es el resumen semanal de tus bloques correspondiente a la semana del {html.escape(rango_semana)}.</p>",
    ]

    text_lines = [
        f"Hola {nombre_destino},",
        "",
        f"Resumen semanal de tus bloques ({rango_semana}).",
    ]

    def _render_bloques_section(
        titulo: str,
        items: List[Dict[str, Any]],
        empty_msg: str,
    ) -> None:
        html_parts.append(
            f"<h2 style='margin-top:24px;font-size:18px;color:#0f172a;'>{html.escape(titulo)}</h2>"
        )
        text_lines.append("")
        text_lines.append(f"{titulo}:")
        if items:
            html_parts.append("<ul style='padding-left:18px;margin:8px 0 0;'>")
            for item in items:
                ultima_semana = item.get("ultima_semana")
                ultima_txt = (
                    _formatear_fecha_es(ultima_semana)
                    if isinstance(ultima_semana, date)
                    else str(ultima_semana)
                )
                total = item.get("total_semanas", "")
                semana_idx = item.get("semana_actual") or total
                cliente = item.get("cliente", "")
                html_parts.append(
                    "<li style='margin-bottom:6px;'>"
                    f"<strong>{html.escape(str(cliente))}</strong> — "
                    f"Semana {semana_idx} de {total} · última semana programada {html.escape(ultima_txt)}"
                    "</li>"
                )
                text_lines.append(
                    f"- {cliente} — Semana {semana_idx} de {total} · última semana programada {ultima_txt}"
                )
            html_parts.append("</ul>")
        else:
            html_parts.append(f"<p style='margin:6px 0;'>{html.escape(empty_msg)}</p>")
            text_lines.append(f"- {empty_msg}")

    _render_bloques_section(
        "Bloques Terminados",
        bloques_terminados,
        "No hay bloques que finalicen esta semana.",
    )
    _render_bloques_section(
        "Bloques próximos a terminar",
        bloques_proximos,
        "No hay bloques cuya última semana sea la próxima semana.",
    )

    html_parts.append("<h2 style='margin-top:24px;font-size:18px;color:#0f172a;'>Comentarios</h2>")
    text_lines.append("")
    text_lines.append("Comentarios de la semana:")

    if comentarios_agrupados:
        html_parts.append("<ul style='padding-left:18px;margin:8px 0 0;'>")
        for comentario in comentarios_agrupados:
            cliente = comentario.get("cliente", "")
            dia_lbl = comentario.get("dia")
            dia_txt = f"Día {dia_lbl}" if dia_lbl else "Día"
            ejercicio_txt = comentario.get("ejercicio") or "Ejercicio"
            comentarios_html = "".join(
                "<li style='margin-bottom:4px;'>"
                f"{html.escape(texto).replace('\r\n', '<br>').replace('\n', '<br>')}"
                "</li>"
                for texto in comentario.get("comentarios", [])
            )
            html_parts.append(
                "<li style='margin-bottom:8px;'>"
                f"<strong>{html.escape(str(cliente))}</strong> — {html.escape(dia_txt)} · {html.escape(ejercicio_txt)}"
                f"<ul style='margin-top:4px;padding-left:18px;color:#475569;'>{comentarios_html}</ul>"
                "</li>"
            )
            text_lines.append(f"- {cliente} — {dia_txt} — {ejercicio_txt}:")
            for texto in comentario.get("comentarios", []):
                text_lines.append(f"    • {texto}")
            text_lines.append("")
        html_parts.append("</ul>")
    else:
        mensaje = "No se registraron comentarios en los reportes de esta semana."
        html_parts.append(f"<p style='margin:6px 0;'>{html.escape(mensaje)}</p>")
        text_lines.append(f"- {mensaje}")

    html_parts.extend(
        [
            "<p style='margin-top:12px;'>Buen trabajo y cualquier duda responde a este correo.</p>",
            "<p style='margin-top:16px;color:#475569;'>Equipo Momentum</p>",
            "</body></html>",
        ]
    )

    text_lines.extend(
        [
            "",
            "Equipo Momentum",
        ]
    )

    return EmailContent(
        subject=subject,
        html_body="\n".join(html_parts),
        text_body="\n".join(text_lines),
    )


def build_rutina_disponible_email(
    nombre: str,
    portal_url: Optional[str],
    semanas: int,
    fecha_inicio: Any,
    coach_label: Optional[str],
) -> EmailContent:
    nombre = (nombre or "").strip()
    portal_url = (portal_url or "").strip()

    if nombre:
        saludo = f"Hola {nombre},"
    else:
        saludo = "Hola,"

    if coach_label:
        coach_line = (
            f"Tu entrenador {coach_label} ya dejó listo tu siguiente bloque de entrenamiento."
        )
    else:
        coach_line = "Tu siguiente bloque de entrenamiento ya está disponible."

    fecha_txt = ""
    if hasattr(fecha_inicio, "strftime"):
        try:
            fecha_txt = fecha_inicio.strftime("%d/%m/%Y")
        except Exception:
            fecha_txt = ""

    detalle_line = ""
    if semanas:
        detalle_line = (
            f"Incluye {semanas} semana(s) planificadas empezando el {fecha_txt or 'próximo bloque'}."
        )
    elif fecha_txt:
        detalle_line = f"Comienza el {fecha_txt}."

    html_parts = [
        f"<p>{saludo}</p>",
        f"<p>{coach_line}</p>",
    ]
    if detalle_line:
        html_parts.append(f"<p>{detalle_line}</p>")
    if portal_url:
        html_parts.append(
            f"<p>Revisa la rutina en <a href=\"{portal_url}\" target=\"_blank\">{portal_url}</a> usando tu correo.</p>"
        )
    else:
        html_parts.append("<p>Ingresa a la app con tu correo para revisarla.</p>")

    html_parts.append("<p>¡Éxitos en tus próximas sesiones!</p>")

    return EmailContent(
        subject="Tu siguiente bloque de entrenamiento ya está disponible",
        html_body="\n".join(html_parts),
        text_body=None,
    )
