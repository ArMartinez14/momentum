from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Optional, Tuple


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
