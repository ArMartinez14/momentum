"""Helpers para normalizar enlaces de video y garantizar URLs embebibles."""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlencode, urlparse

_YOUTUBE_ALLOWED_HOSTS = {
    "youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "youtube-nocookie.com",
    "www.youtube.com",
    "www.youtu.be",
    "www.youtube-nocookie.com",
}


def normalizar_link_youtube(url: str) -> str:
    """Devuelve https://www.youtube.com/watch?v=ID normalizado o '' si no aplica."""
    raw = str(url or "").strip()
    if not raw:
        return ""

    if not raw.lower().startswith(("http://", "https://")):
        raw = f"https://{raw}"

    try:
        parsed = urlparse(raw)
    except Exception:
        return ""

    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    if host not in _YOUTUBE_ALLOWED_HOSTS:
        return ""

    path = (parsed.path or "").strip()
    video_id = ""

    if host.endswith("youtu.be"):
        video_id = path.lstrip("/").split("/")[0]
    elif "/shorts/" in path:
        video_id = path.split("/shorts/", 1)[1].split("/", 1)[0]
    elif path.startswith("/embed/"):
        video_id = path.split("/embed/", 1)[1].split("/", 1)[0]
    else:
        qs = parse_qs(parsed.query or "")
        if qs.get("v"):
            video_id = qs["v"][0]
        else:
            segments = [seg for seg in path.split("/") if seg]
            if segments and segments[0] == "watch" and len(segments) > 1:
                video_id = segments[1]

    video_id = video_id.strip()
    if not video_id:
        return ""

    video_id = re.sub(r"[^0-9A-Za-z_-]", "", video_id)
    if not video_id:
        return ""

    qs_values = parse_qs(parsed.query or "")
    extra_params = {}
    for key in ("t", "start"):
        if key in qs_values and qs_values[key]:
            extra_params[key] = qs_values[key][-1]

    query = {"v": video_id}
    query.update(extra_params)
    query_str = urlencode(query)
    return f"https://www.youtube.com/watch?{query_str}"


def normalizar_video_url(url: str) -> str:
    """Devuelve un enlace apto para `st.video`, priorizando Youtube normalizado."""
    normalizado = normalizar_link_youtube(url)
    return normalizado if normalizado else (str(url or "").strip())


__all__ = ["normalizar_link_youtube", "normalizar_video_url"]
