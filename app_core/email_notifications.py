from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr
import smtplib
from typing import Any, Dict, Iterable, List, Optional, Tuple

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
    empresa_de_usuario,
    normalizar_correo,
)
from app_core.email_templates import (
    EmailContent,
    build_bienvenida_email,
    build_resumen_bloques_email,
    build_rutina_disponible_email,
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


def _lunes_de(fecha_ref: Optional[date] = None) -> date:
    base = fecha_ref or date.today()
    return base - timedelta(days=base.weekday())


def _parse_fecha_lunes(value: Any) -> Optional[date]:
    if not value:
        return None
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except Exception:
        return None


def _iter_ejercicios_en_doc(doc: dict) -> Iterable[Tuple[str, dict]]:
    rutina = doc.get("rutina")
    if not isinstance(rutina, dict):
        return []
    for dia_key, dia_node in rutina.items():
        dia_str = str(dia_key)
        if not dia_str.isdigit():
            continue
        ejercicios: List[dict] = []
        if isinstance(dia_node, list):
            ejercicios = [e for e in dia_node if isinstance(e, dict)]
        elif isinstance(dia_node, dict):
            if isinstance(dia_node.get("ejercicios"), list):
                ejercicios = [e for e in dia_node["ejercicios"] if isinstance(e, dict)]
            else:
                ejercicios = [v for v in dia_node.values() if isinstance(v, dict)]
        for ejercicio in ejercicios:
            yield (dia_str, ejercicio)


def _extraer_comentarios_doc(doc: dict) -> List[Dict[str, str]]:
    comentarios: List[Dict[str, str]] = []
    for dia_str, ejercicio in _iter_ejercicios_en_doc(doc):
        comentario_raw = ejercicio.get("comentario")
        if comentario_raw is None:
            continue
        comentario = str(comentario_raw).strip()
        if not comentario:
            continue
        nombre_ej = (
            ejercicio.get("ejercicio")
            or ejercicio.get("Ejercicio")
            or ejercicio.get("nombre")
            or ejercicio.get("id_ejercicio")
            or "Ejercicio sin nombre"
        )
        comentarios.append(
            {
                "dia": dia_str,
                "ejercicio": str(nombre_ej),
                "comentario": comentario,
            }
        )
    return comentarios


def _bloque_resumen_label(info: Dict[str, Any]) -> str:
    objetivo = str(info.get("objetivo") or "").strip()
    bloque_id = str(info.get("bloque_id") or "").strip()
    bloque_short = bloque_id[:8] if bloque_id else ""
    if objetivo and bloque_short:
        return f"{objetivo} (ID {bloque_short})"
    if objetivo:
        return objetivo
    if bloque_short:
        return f"Bloque {bloque_short}"
    return "Bloque sin nombre"


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


def _empresa_destino(empresa: Optional[str], correo: str) -> str:
    empresa_norm = (empresa or "").strip().lower()
    if empresa_norm:
        return empresa_norm
    try:
        return empresa_de_usuario(correo)
    except Exception:
        return ""


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

    empresa_norm = _empresa_destino(empresa, correo_norm)

    rol_norm = (rol or "").strip().lower()
    es_coach = rol_norm in {"entrenador", "coach", "admin", "administrador"}

    if empresa_norm == EMPRESA_MOTION and not es_coach:
        _emit_info("Correo de bienvenida omitido para cliente Motion.")
        return False

    portal_url = _resolve_portal_url(empresa_norm)
    anamnesis_url = _resolve_anamnesis_url(empresa_norm)

    empresa_txt = _nombre_empresa(empresa_norm)

    contenido: EmailContent = build_bienvenida_email(
        nombre=nombre or "",
        empresa_txt=empresa_txt,
        es_coach=es_coach,
        portal_url=portal_url,
        anamnesis_url=anamnesis_url,
        instrucciones_extra=instrucciones_extra,
    )

    return _send_email(
        to_email=correo_norm,
        subject=contenido.subject,
        html_body=contenido.html_body,
        text_body=contenido.text_body,
        to_name=nombre or None,
    )


def preparar_resumen_bloques_entrenador(
    correo_entrenador: str,
    fecha_referencia: Optional[date] = None,
) -> Dict[str, Any]:
    correo_norm = (correo_entrenador or "").strip().lower()
    if not correo_norm:
        raise ValueError("correo_entrenador es obligatorio.")

    fecha_base = fecha_referencia or date.today()
    lunes_actual = _lunes_de(fecha_base)
    domingo_actual = lunes_actual + timedelta(days=6)
    lunes_siguiente = lunes_actual + timedelta(days=7)

    db = get_db()

    rol_destino = ""
    try:
        snaps_usuario = db.collection("usuarios").where("correo", "==", correo_norm).limit(1).stream()
        for snap in snaps_usuario:
            data_usuario = snap.to_dict() or {}
            rol_destino = str(data_usuario.get("rol") or "").strip().lower()
            break
    except Exception:
        rol_destino = ""

    if rol_destino and rol_destino not in {"entrenador", "admin", "administrador"}:
        raise ValueError("Solo se generan resúmenes para entrenadores o administradores.")

    col = db.collection("rutinas_semanales")
    try:
        snaps = list(col.where("entrenador", "==", correo_norm).stream())
    except Exception as exc:
        _emit_warning(f"No se pudo filtrar rutinas por entrenador '{correo_norm}': {exc}")
        try:
            snaps = list(col.stream())
        except Exception:
            snaps = []

    docs: List[Dict[str, Any]] = []
    for snap in snaps:
        try:
            if not snap.exists:
                continue
        except Exception:
            pass
        data = snap.to_dict() or {}
        entrenador_val = str(data.get("entrenador") or "").strip().lower()
        if entrenador_val != correo_norm:
            continue
        data["_doc_id"] = snap.id
        docs.append(data)

    if not docs:
        raise ValueError("El entrenador no tiene rutinas registradas.")

    bloques: Dict[Tuple[str, str], Dict[str, Any]] = {}
    comentarios_semana: List[Dict[str, Any]] = []

    for data in docs:
        fecha_lunes_dt = _parse_fecha_lunes(data.get("fecha_lunes"))
        if not fecha_lunes_dt:
            continue

        correo_cliente = str(data.get("correo") or "").strip().lower()
        if not correo_cliente:
            continue

        bloque_id_raw = str(data.get("bloque_rutina") or "").strip()
        if not bloque_id_raw:
            continue

        cliente_nombre = str(data.get("cliente") or data.get("nombre") or "").strip()
        if not cliente_nombre:
            if "@" in correo_cliente:
                cliente_nombre = correo_cliente.split("@", 1)[0]
            else:
                cliente_nombre = correo_cliente
        objetivo_txt = str(data.get("objetivo") or "").strip()

        key = (correo_cliente, bloque_id_raw)
        info = bloques.get(key)
        if info is None:
            info = {
                "cliente": cliente_nombre,
                "bloque_id": bloque_id_raw,
                "objetivo": objetivo_txt,
                "fechas": set(),
            }
            bloques[key] = info
        else:
            if not info.get("cliente"):
                info["cliente"] = cliente_nombre
            if not info.get("objetivo") and objetivo_txt:
                info["objetivo"] = objetivo_txt

        info["fechas"].add(fecha_lunes_dt)

        if fecha_lunes_dt == lunes_actual:
            comentarios_doc = _extraer_comentarios_doc(data)
            for comentario in comentarios_doc:
                dia_val = comentario.get("dia", "")
                try:
                    dia_int = int(dia_val)
                except Exception:
                    dia_int = None
                comentarios_semana.append(
                    {
                        "cliente": info["cliente"],
                        "dia": dia_val,
                        "dia_int": dia_int,
                        "ejercicio": comentario.get("ejercicio", ""),
                        "comentario": comentario.get("comentario", ""),
                    }
                )

    bloques_terminados: List[Dict[str, Any]] = []
    bloques_proximos: List[Dict[str, Any]] = []

    for info in bloques.values():
        fechas: List[date] = sorted(info["fechas"])
        if not fechas:
            continue
        fecha_inicio = fechas[0]
        ultima_fecha = fechas[-1]
        total_semanas = len(fechas)

        diff_sem = ((lunes_actual - fecha_inicio).days // 7) + 1
        semana_actual_idx = max(1, min(diff_sem, total_semanas))

        entry_base = {
            "cliente": info["cliente"],
            "bloque_id": info["bloque_id"],
            "objetivo": info.get("objetivo") or "",
            "ultima_semana": ultima_fecha,
            "total_semanas": total_semanas,
            "semana_actual": semana_actual_idx,
            "fecha_inicio": fecha_inicio,
        }

        if ultima_fecha == lunes_actual:
            bloques_terminados.append(entry_base)
        elif ultima_fecha == lunes_siguiente:
            bloques_proximos.append(entry_base)

    bloques_terminados.sort(key=lambda x: x["cliente"].lower())
    bloques_proximos.sort(key=lambda x: x["cliente"].lower())
    comentarios_semana.sort(
        key=lambda x: (x["cliente"].lower(), x.get("dia_int") or 99, x.get("ejercicio", "").lower())
    )

    comentarios_agrupados_map: Dict[Tuple[str, str, str], Dict[str, Any]] = {}
    for comentario in comentarios_semana:
        cliente = comentario.get("cliente", "")
        dia_lbl = comentario.get("dia") or ""
        ejercicio_txt = comentario.get("ejercicio") or ""
        key = (cliente, dia_lbl, ejercicio_txt)
        if key not in comentarios_agrupados_map:
            comentarios_agrupados_map[key] = {
                "cliente": cliente,
                "dia": dia_lbl,
                "dia_int": comentario.get("dia_int"),
                "ejercicio": ejercicio_txt,
                "comentarios": [],
            }
        texto = (comentario.get("comentario") or "").strip()
        if texto:
            comentarios_agrupados_map[key]["comentarios"].append(texto)

    comentarios_agrupados = [
        value for value in comentarios_agrupados_map.values() if value.get("comentarios")
    ]

    if not bloques_terminados and not bloques_proximos and not comentarios_agrupados:
        raise ValueError("No hay rutinas por terminar ni comentarios nuevos para esta semana.")

    nombre_destino = _buscar_nombre_usuario(correo_norm) or ""
    if not nombre_destino:
        local = correo_norm.split("@", 1)[0] if "@" in correo_norm else correo_norm
        nombre_destino = local.replace(".", " ").replace("_", " ").title()

    contenido: EmailContent = build_resumen_bloques_email(
        nombre_destino=nombre_destino,
        lunes_actual=lunes_actual,
        domingo_actual=domingo_actual,
        bloques_terminados=bloques_terminados,
        bloques_proximos=bloques_proximos,
        comentarios_agrupados=comentarios_agrupados,
    )

    metadata = {
        "lunes_actual": lunes_actual,
        "domingo_actual": domingo_actual,
        "lunes_siguiente": lunes_siguiente,
        "destinatario": correo_norm,
        "bloques_terminados": bloques_terminados,
        "bloques_proximos": bloques_proximos,
        "comentarios": comentarios_agrupados,
    }

    return {
        "subject": contenido.subject,
        "html_body": contenido.html_body,
        "text_body": contenido.text_body,
        "destinatario": correo_norm,
        "nombre_destinatario": nombre_destino,
        "metadata": metadata,
    }


def enviar_resumen_bloques_entrenador(
    correo_entrenador: str,
    enviar: bool = False,
    fecha_referencia: Optional[date] = None,
) -> Dict[str, Any]:
    try:
        contenido = preparar_resumen_bloques_entrenador(correo_entrenador, fecha_referencia)
    except ValueError as exc:
        return {
            "enviado": False,
            "error": str(exc),
            "destinatario": (correo_entrenador or "").strip().lower(),
        }

    resultado = dict(contenido)

    if not enviar:
        resultado["enviado"] = False
        return resultado

    enviado = _send_email(
        to_email=contenido["destinatario"],
        subject=contenido["subject"],
        html_body=contenido["html_body"],
        text_body=contenido["text_body"],
        to_name=contenido.get("nombre_destinatario"),
    )

    if "metadata" in resultado:
        resultado["metadata"] = dict(resultado["metadata"])
        resultado["metadata"]["enviado"] = enviado

    resultado["enviado"] = enviado
    return resultado


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

    empresa_norm = _empresa_destino(empresa, correo_norm)

    if empresa_norm == EMPRESA_MOTION:
        _emit_info("Correo de rutina omitido para cliente Motion.")
        return False

    portal_url = _resolve_portal_url(empresa_norm)

    coach_label = None
    if coach:
        coach_label = coach
        if "@" in coach:
            coach_label = _buscar_nombre_usuario(coach) or coach
    contenido: EmailContent = build_rutina_disponible_email(
        nombre=nombre or "",
        portal_url=portal_url,
        semanas=semanas,
        fecha_inicio=fecha_inicio,
        coach_label=coach_label,
    )

    return _send_email(
        to_email=correo_norm,
        subject=contenido.subject,
        html_body=contenido.html_body,
        text_body=contenido.text_body,
        to_name=nombre or None,
    )
