from __future__ import annotations
from datetime import date, datetime, timedelta
from functools import lru_cache
from typing import Optional, Tuple, Dict, Any

from app_core.firebase_client import get_db

EMPRESA_MOTION = "motion"
EMPRESA_ASESORIA = "asesoria"
EMPRESA_DESCONOCIDA = "desconocida"


def _invalidate_usuario_cache():
    try:
        _fetch_usuario_por_doc_id.cache_clear()
    except Exception:
        pass


def normalizar_correo(correo: str) -> str:
    return (correo or "").strip().lower()


def correo_a_doc_id(correo: str) -> str:
    correo = normalizar_correo(correo)
    return correo.replace("@", "_").replace(".", "_")


def _infer_empresa_por_dominio(correo: str) -> str:
    dominio = ""
    if "@" in correo:
        dominio = correo.split("@", 1)[1].lower()
    if dominio in {"motionperformance.cl", "motion.cl"}:
        return EMPRESA_MOTION
    if dominio in {"asesoria.cl", "appasesorias.cl"}:
        return EMPRESA_ASESORIA
    return EMPRESA_DESCONOCIDA


@lru_cache(maxsize=256)
def _fetch_usuario_por_doc_id(doc_id: str) -> Optional[Dict[str, Any]]:
    if not doc_id:
        return None
    try:
        db = get_db()
        snap = db.collection("usuarios").document(doc_id).get()
        if not snap.exists:
            return None
        data = snap.to_dict() or {}
        return data
    except Exception:
        return None


def empresa_de_usuario(correo: str, usuarios_cache: Dict[str, Dict[str, Any]] | None = None) -> str:
    correo_norm = normalizar_correo(correo)
    if not correo_norm:
        return EMPRESA_DESCONOCIDA

    data = None
    lookup_keys = {correo_norm, correo_a_doc_id(correo_norm)}

    if usuarios_cache:
        for key in lookup_keys:
            if key in usuarios_cache:
                data = usuarios_cache[key]
                break

    if data is None:
        data = _fetch_usuario_por_doc_id(correo_a_doc_id(correo_norm))

    empresa = ""
    if isinstance(data, dict):
        empresa = str(data.get("empresa", "")).strip().lower()
        if not empresa:
            empresa = str(data.get("empresa_id", "")).strip().lower()

    if not empresa:
        empresa = _infer_empresa_por_dominio(correo_norm)

    return empresa or EMPRESA_DESCONOCIDA


def usuario_es_motion(correo: str, usuarios_cache: Dict[str, Dict[str, Any]] | None = None) -> bool:
    return empresa_de_usuario(correo, usuarios_cache) == EMPRESA_MOTION


def usuario_es_asesoria(correo: str, usuarios_cache: Dict[str, Dict[str, Any]] | None = None) -> bool:
    return empresa_de_usuario(correo, usuarios_cache) == EMPRESA_ASESORIA


def usuario_activo(correo: str, usuarios_cache: Dict[str, Dict[str, Any]] | None = None) -> bool:
    correo_norm = normalizar_correo(correo)
    if not correo_norm:
        return False

    data = None
    lookup_keys = {correo_norm, correo_a_doc_id(correo_norm)}

    if usuarios_cache:
        for key in lookup_keys:
            if key in usuarios_cache:
                data = usuarios_cache[key]
                break

    if data is None:
        data = _fetch_usuario_por_doc_id(correo_a_doc_id(correo_norm))

    if not isinstance(data, dict):
        return False

    activo = data.get("activo")
    return False if activo is False else True


def set_usuario_activo(correo: str, activo: bool = True) -> None:
    correo_norm = normalizar_correo(correo)
    if not correo_norm:
        return
    try:
        db = get_db()
        doc_id = correo_a_doc_id(correo_norm)
        db.collection("usuarios").document(doc_id).set({"activo": bool(activo)}, merge=True)
    finally:
        _invalidate_usuario_cache()


def safe_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        if isinstance(value, bool):
            return int(value)
        return int(str(value).strip())
    except Exception:
        return default


def safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(str(value).replace(",", ".").strip())
    except Exception:
        return default


def normalizar_texto(s: str) -> str:
    return (s or "").strip()


def parse_reps(value) -> Tuple[Optional[int], Optional[int]]:
    """Convierte "8-10" o "10" a (min,max)."""
    s = str(value or "").strip()
    if not s:
        return None, None
    if "-" in s:
        a, b = s.split("-", 1)
        return safe_int(a, None), safe_int(b, None)
    v = safe_int(s, None)
    return v, v


def parse_rir(value) -> Tuple[Optional[float], Optional[float]]:
    """Convierte "2-3" o "2" a (min,max) float."""
    s = str(value or "").strip()
    if not s:
        return None, None
    if "-" in s:
        a, b = s.split("-", 1)
        return safe_float(a, None), safe_float(b, None)
    v = safe_float(s, None)
    return v, v


def parse_semanas(s) -> list[int]:
    """Acepta formatos "1,2,4-6" → [1,2,4,5,6]."""
    raw = str(s or "").strip()
    if not raw:
        return []
    out: list[int] = []
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            a, b = part.split("-", 1)
            ai, bi = safe_int(a, 0), safe_int(b, 0)
            if ai and bi and ai <= bi:
                out.extend(list(range(ai, bi + 1)))
        else:
            v = safe_int(part, 0)
            if v:
                out.append(v)
    # sin duplicados, orden natural
    return sorted(set(out))


def lunes_actual(hoy: Optional[date] = None) -> date:
    d = hoy or date.today()
    return d - timedelta(days=d.weekday())


def iso_to_date(s: str) -> Optional[date]:
    try:
        return datetime.fromisoformat(s).date()
    except Exception:
        return None


def fecha_to_norm(d: date) -> str:
    return d.strftime("%Y_%m_%d")
