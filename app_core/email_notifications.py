from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
import smtplib
from typing import Dict, Optional

import requests

try:
    import streamlit as st  # type: ignore
except Exception:  # pragma: no cover - streamlit no disponible en algunos contextos
    st = None  # type: ignore

from app_core.firebase_client import get_db
from app_core.utils import (
    EMPRESA_ASESORIA,
    EMPRESA_DESCONOCIDA,
    EMPRESA_MOTION,
    correo_a_doc_id,
    normalizar_correo,
)

logger = logging.getLogger(__name__)


@dataclass
class EmailSettings:
    api_key: str = ""
    from_email: str = ""
    from_name: str = ""
    reply_to: Optional[str] = None
    program_urls: Dict[str, str] | None = None
    login_url: Optional[str] = None
    anamnesis_urls: Dict[str, str] | None = None
    anamnesis_url_default: Optional[str] = None
    enabled: bool = False
    smtp_host: str = ""
    smtp_port: int = 0
    smtp_user: str = ""
    smtp_password: str = ""
    use_ssl: bool = True
    use_starttls: bool = False


def _secret_dict() -> Dict:
    """Unifica posibles nodos en st.secrets y los expone como dict llano."""
    candidates: list[Dict] = []
    if st is not None:
        for key in ("email", "EMAIL", "email_notifications", "EMAIL_NOTIFICATIONS"):
            try:
                value = st.secrets.get(key)  # type: ignore[attr-defined]
            except Exception:
                value = None
            if value:
                try:
                    candidates.append(dict(value))
                except Exception:
                    candidates.append(value)
    # Prefiere el primer dict no vacío
    for candidate in candidates:
        if isinstance(candidate, dict) and candidate:
            return candidate
    return {}


def _load_settings() -> EmailSettings:
    raw = _secret_dict()

    def _from_raw(key: str, default: Optional[str] = None) -> Optional[str]:
        val = raw.get(key)
        if val is None:
            return default
        if isinstance(val, str):
            return val.strip()
        return default

    api_key = (
        _from_raw("sendgrid_api_key")
        or _from_raw("api_key")
        or os.getenv("SENDGRID_API_KEY", "").strip()
    )
    from_email = _from_raw("from_email") or os.getenv("EMAIL_FROM", "").strip()
    from_name = _from_raw("from_name") or os.getenv("EMAIL_FROM_NAME", "").strip()
    reply_to = _from_raw("reply_to") or os.getenv("EMAIL_REPLY_TO", "").strip() or None

    program_urls = raw.get("program_urls") if isinstance(raw.get("program_urls"), dict) else {}
    anamnesis_urls = raw.get("anamnesis_urls") if isinstance(raw.get("anamnesis_urls"), dict) else {}
    anamnesis_url_default = _from_raw("anamnesis_url") or os.getenv("ANAMNESIS_URL", "").strip()
    login_url = (
        _from_raw("login_url")
        or _from_raw("portal_url")
        or os.getenv("APP_PORTAL_URL", "").strip()
    )

    smtp_host = _from_raw("smtp_host") or os.getenv("SMTP_HOST", "").strip()
    smtp_port_raw = raw.get("smtp_port") or os.getenv("SMTP_PORT")
    smtp_port = 0
    try:
        smtp_port = int(smtp_port_raw) if smtp_port_raw else 0
    except Exception:
        smtp_port = 0
    smtp_user = _from_raw("smtp_user") or os.getenv("SMTP_USER", "").strip()
    smtp_password = _from_raw("smtp_password") or os.getenv("SMTP_PASSWORD", "").strip()
    use_ssl = raw.get("use_ssl", True)
    use_starttls = raw.get("use_starttls", False)
    try:
        use_ssl = bool(use_ssl)
    except Exception:
        use_ssl = True
    try:
        use_starttls = bool(use_starttls)
    except Exception:
        use_starttls = False

    if not from_email and smtp_user:
        from_email = smtp_user

    enabled_flag = raw.get("enabled", True)
    try:
        enabled_flag = bool(enabled_flag)
    except Exception:
        enabled_flag = True

    enabled = enabled_flag and (
        (api_key and from_email)
        or (smtp_host and smtp_port and smtp_user and smtp_password)
    )

    return EmailSettings(
        api_key=api_key,
        from_email=from_email,
        from_name=from_name or "",
        reply_to=reply_to,
        program_urls=program_urls or {},
        login_url=login_url or None,
        anamnesis_urls=anamnesis_urls or {},
        anamnesis_url_default=anamnesis_url_default or None,
        enabled=enabled,
        smtp_host=smtp_host or "",
        smtp_port=smtp_port,
        smtp_user=smtp_user or "",
        smtp_password=smtp_password or "",
        use_ssl=use_ssl,
        use_starttls=use_starttls,
    )


def _emit_info(msg: str) -> None:
    logger.info(msg)


def _emit_warning(msg: str) -> None:
    logger.warning(msg)
    if st is not None:
        try:
            st.toast(msg, icon="⚠️")  # type: ignore[attr-defined]
        except Exception:
            pass


def _emit_error(msg: str) -> None:
    logger.error(msg)
    if st is not None:
        try:
            st.toast(msg, icon="❌")  # type: ignore[attr-defined]
        except Exception:
            pass


def _send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str] = None,
    to_name: Optional[str] = None,
) -> bool:
    settings = _load_settings()
    if not settings.enabled:
        _emit_info("Notificaciones por correo deshabilitadas o sin credenciales.")
        return False

    if settings.api_key:
        return _send_email_sendgrid(settings, to_email, subject, html_body, text_body, to_name)

    if settings.smtp_host and settings.smtp_user and settings.smtp_password and settings.smtp_port:
        return _send_email_smtp(settings, to_email, subject, html_body, text_body, to_name)

    _emit_warning("No hay configuración válida de correo (SendGrid o SMTP).")
    return False


def _send_email_smtp(
    settings: EmailSettings,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str],
    to_name: Optional[str],
) -> bool:
    mensaje = MIMEMultipart("alternative")
    remitente_nombre = settings.from_name or settings.smtp_user
    remitente_address = settings.from_email or settings.smtp_user
    mensaje["Subject"] = subject
    mensaje["From"] = formataddr((remitente_nombre, remitente_address))
    mensaje["To"] = formataddr((to_name or "", to_email))
    if settings.reply_to:
        mensaje["Reply-To"] = settings.reply_to

    text_part = MIMEText(text_body or _strip_html(html_body), "plain", "utf-8")
    html_part = MIMEText(html_body, "html", "utf-8")
    mensaje.attach(text_part)
    mensaje.attach(html_part)

    try:
        if settings.use_ssl:
            smtp = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=10)
        else:
            smtp = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10)
        with smtp:
            if settings.use_starttls and not settings.use_ssl:
                smtp.starttls()
            smtp.login(settings.smtp_user, settings.smtp_password)
            smtp.sendmail(remitente_address, [to_email], mensaje.as_string())
        _emit_info(f"Correo enviado a {to_email} con asunto '{subject}'.")
        return True
    except Exception as exc:
        _emit_error(f"No se pudo enviar el correo a {to_email} vía SMTP: {exc}")
        return False


def _send_email_sendgrid(
    settings: EmailSettings,
    to_email: str,
    subject: str,
    html_body: str,
    text_body: Optional[str],
    to_name: Optional[str],
) -> bool:

    payload = {
        "personalizations": [
            {
                "to": [{"email": to_email, **({"name": to_name} if to_name else {})}],
            }
        ],
        "from": {
            "email": settings.from_email,
            **({"name": settings.from_name} if settings.from_name else {}),
        },
        "subject": subject,
        "content": [
            {
                "type": "text/plain",
                "value": text_body or _strip_html(html_body),
            },
            {
                "type": "text/html",
                "value": html_body,
            },
        ],
    }

    if settings.reply_to:
        payload["reply_to"] = {"email": settings.reply_to}

    headers = {
        "Authorization": f"Bearer {settings.api_key}",
        "Content-Type": "application/json",
    }

    try:
        response = requests.post(
            "https://api.sendgrid.com/v3/mail/send",
            headers=headers,
            json=payload,
            timeout=10,
        )
        response.raise_for_status()
        _emit_info(f"Correo enviado a {to_email} con asunto '{subject}'.")
        return True
    except Exception as exc:
        _emit_error(f"No se pudo enviar el correo a {to_email}: {exc}")
        return False


def _strip_html(html: str) -> str:
    import re

    text = re.sub(r"<\s*br\s*/?\s*>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _resolve_portal_url(empresa: str | None = None) -> Optional[str]:
    empresa_norm = (empresa or "").strip().lower()
    settings = _load_settings()
    urls = settings.program_urls or {}
    for key in (empresa_norm, "default"):
        if key and key in urls and urls[key]:
            return urls[key]
    return settings.login_url


def _resolve_anamnesis_url(empresa: str | None = None) -> Optional[str]:
    settings = _load_settings()
    urls = settings.anamnesis_urls or {}
    empresa_norm = (empresa or "").strip().lower()
    for key in (empresa_norm, "default"):
        url = urls.get(key)
        if url:
            return url
    return settings.anamnesis_url_default


def _nombre_empresa(empresa: str | None) -> str:
    empresa_norm = (empresa or EMPRESA_DESCONOCIDA).strip().lower()
    if empresa_norm == EMPRESA_MOTION:
        return "Motion"
    if empresa_norm == EMPRESA_ASESORIA:
        return "Asesoría"
    return "nuestro programa"


def _buscar_nombre_usuario(correo: str) -> Optional[str]:
    correo_norm = normalizar_correo(correo)
    if not correo_norm:
        return None
    try:
        db = get_db()
        snap = db.collection("usuarios").document(correo_a_doc_id(correo_norm)).get()
        if snap.exists:
            data = snap.to_dict() or {}
            nombre = str(data.get("nombre") or "").strip()
            return nombre or None
    except Exception:
        return None
    return None


def enviar_correo_bienvenida(
    correo: str,
    nombre: Optional[str] = None,
    empresa: Optional[str] = None,
    instrucciones_extra: Optional[str] = None,
    rol: Optional[str] = None,
) -> bool:
    correo_norm = normalizar_correo(correo)
    if not correo_norm:
        _emit_warning("No se pudo enviar correo de bienvenida: correo vacío.")
        return False

    if not nombre:
        nombre = _buscar_nombre_usuario(correo_norm) or ""

    portal_url = _resolve_portal_url(empresa)
    anamnesis_url = _resolve_anamnesis_url(empresa)

    empresa_txt = _nombre_empresa(empresa)
    saludo_nombre = nombre or "!"
    if saludo_nombre != "!":
        saludo = f"Hola {saludo_nombre},"
    else:
        saludo = "Hola,"

    rol_norm = (rol or "").strip().lower()
    es_coach = rol_norm in {"entrenador", "coach", "admin", "administrador"}

    def _render_boton(url: str) -> str:
        return (
            "<table role='presentation' cellspacing='0' cellpadding='0'>"
            "<tr>"
            "<td style='border-radius:8px;background:#D64045;text-align:center;'>"
            f"<a href=\"{url}\" target=\"_blank\" "
            "style='display:inline-block;padding:12px 22px;color:#ffffff;font-weight:600;"
            "text-decoration:none;font-family:Helvetica,Arial,sans-serif;border-radius:8px;'>"
            "Ir a la app</a>"
            "</td>"
            "</tr>"
            "</table>"
        )

    boton_html = ""
    portal_destino = portal_url or DEFAULT_PORTAL_URL
    boton_html = _render_boton(portal_destino)

    if es_coach:
        instrucciones_html = (
            "A continuación encontrarás el botón para ingresar a la webapp. "
            "Tu correo de acceso es el mismo al que te llegó este mensaje."
        )
    else:
        instrucciones_html = (
            "Ingresa con tu correo desde el botón siguiente y, si es tu primer acceso, abre el menú "
            "<strong>Atleta</strong> y selecciona el submenú <strong>Anamnesis</strong> para completar la encuesta inicial."
        )

    if instrucciones_extra:
        instrucciones_html = f"{instrucciones_html} {instrucciones_extra.strip()}"

    html_parts = [f"<p>{saludo}</p>"]

    if es_coach:
        bienvenida_html = "¡Bienvenido a Momentum! Gracias por unirte a nuestra App. Tu cuenta ya está activa en nuestra plataforma."
    else:
        bienvenida_html = f"¡Bienvenido a {empresa_txt}! Tu cuenta ya está activa en nuestra plataforma."

    html_parts.append(f"<p>{bienvenida_html}</p>")
    html_parts.append(f"<p>{instrucciones_html}</p>")
    html_parts.append(f"<div style='margin:24px 0;text-align:center;'>{boton_html}</div>")

    if not es_coach:
        if anamnesis_url:
            html_parts.append(
                f"<p>Te pedimos completar la <strong>encuesta de anamnesis</strong> cuanto antes. "
                f"Accede desde <a href=\"{anamnesis_url}\" target=\"_blank\">este enlace</a> "
                "o entra al portal, abre el menú <strong>Atleta</strong> y selecciona el submenú <strong>Anamnesis</strong>. "
                "Recuerda usar el mismo correo con el que te registramos.</p>"
            )
        

    html_parts.append(
        "<p>Si necesitas apoyo, responde a este correo y tu entrenador te ayudará a resolver cualquier duda.</p>"
    )

    html_parts.append(
        "<div style='margin-top:32px;border-top:1px solid #e2e8f0;padding-top:16px;font-size:14px;color:#64748b;'>"
        "<strong>Equipo Momentum</strong><br>"
        "Coaching y planificación personalizada<br>"
        f"<a href=\"{portal_destino}\" target=\"_blank\" style='color:#D64045;text-decoration:none;'>Visita la app</a>"
        "</div>"
    )

    html_body = "<html><body style='font-family:Helvetica,Arial,sans-serif;font-size:15px;color:#1f2933;'>"
    html_body += "\n".join(html_parts)
    html_body += "</body></html>"

    text_body_override = [
        saludo.strip(","),
        bienvenida_html,
        _strip_html(instrucciones_html),
        f"Link de acceso: {portal_destino}",
    ]

    if not es_coach:
        if anamnesis_url:
            text_body_override.append(f"Encuesta de anamnesis: {anamnesis_url}")
        else:
            text_body_override.append("Completa la anamnesis ingresando a la app (Menú Atleta > Anamnesis).")

    text_body_override.append("Si necesitas apoyo, responde a este correo y tu entrenador te ayudará a resolver cualquier duda.")
    text_body_override.append("Equipo Momentum - Coaching y planificación personalizada.")

    text_body = "\n\n".join(text_body_override)
    subject = "Bienvenido a Momentum" if es_coach else f"Bienvenido a {empresa_txt}"

    return _send_email(
        to_email=correo_norm,
        subject=subject,
        html_body=html_body,
        text_body=text_body,
        to_name=nombre or None,
    )


def enviar_correo_rutina_disponible(
    correo: str,
    nombre: Optional[str],
    fecha_inicio,
    semanas: int,
    empresa: Optional[str] = None,
    coach: Optional[str] = None,
) -> bool:
    correo_norm = normalizar_correo(correo)
    if not correo_norm:
        _emit_warning("No se pudo enviar correo de rutina: correo vacío.")
        return False

    if not nombre:
        nombre = _buscar_nombre_usuario(correo_norm) or ""

    portal_url = _resolve_portal_url(empresa)
    empresa_txt = _nombre_empresa(empresa)

    saludo_nombre = nombre or "!"
    if saludo_nombre != "!":
        saludo = f"Hola {saludo_nombre},"
    else:
        saludo = "Hola,"

    fecha_txt = ""
    try:
        if hasattr(fecha_inicio, "strftime"):
            fecha_txt = fecha_inicio.strftime("%d/%m/%Y")
    except Exception:
        fecha_txt = ""

    coach_line = ""
    if coach:
        coach_label = coach
        if "@" in coach:
            coach_label = _buscar_nombre_usuario(coach) or coach
        coach_line = f"Tu entrenador {coach_label} ya dejó listo tu siguiente bloque de entrenamiento."
    else:
        coach_line = "Tu siguiente bloque de entrenamiento ya está disponible."

    detalle_line = ""
    if semanas:
        detalle_line = f"Incluye {semanas} semana(s) planificadas empezando el {fecha_txt or 'próximo bloque'}."
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

    html_body = "\n".join(html_parts)
    subject = "Tu siguiente bloque de entrenamiento ya está disponible"

    return _send_email(
        to_email=correo_norm,
        subject=subject,
        html_body=html_body,
        to_name=nombre or None,
    )
DEFAULT_PORTAL_URL = "https://momentum-bclfppzmx8zykyrlkhfmr2.streamlit.app/"
