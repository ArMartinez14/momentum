from __future__ import annotations
from typing import Dict, Optional

try:
    import streamlit as st
except Exception:
    st = None  # type: ignore

# Paletas base (variables usadas recurrentemente en la app)
LIGHT = {
    "PRIMARY": "#00C2FF",
    "SUCCESS": "#22C55E",
    "WARNING": "#F59E0B",
    "DANGER": "#EF4444",
    "BG": "#FFFFFF",
    "SURFACE": "#F7FAFC",
    "TEXT_MAIN": "#0B1220",
    "TEXT_MUTED": "#64748B",
    "STROKE": "rgba(0,0,0,.08)",
}

DARK = {
    "PRIMARY": "#00C2FF",
    "SUCCESS": "#22C55E",
    "WARNING": "#F59E0B",
    "DANGER": "#EF4444",
    "BG": "#0B0F14",
    "SURFACE": "#121821",
    "TEXT_MAIN": "#FFFFFF",
    "TEXT_MUTED": "#94A3B8",
    "STROKE": "rgba(255,255,255,.08)",
}


def _vars_block(p: Dict[str, str]) -> str:
    return (
        f"--primary:{p['PRIMARY']}; --success:{p['SUCCESS']}; --warning:{p['WARNING']}; --danger:{p['DANGER']};\n"
        f"--bg:{p['BG']}; --surface:{p['SURFACE']}; --muted:{p['TEXT_MUTED']}; --stroke:{p['STROKE']};\n"
        f"--text-main:{p['TEXT_MAIN']};"
    )


def inject_base_theme(overrides: Optional[Dict[str, str]] = None) -> None:
    """Inyecta CSS base con variables LIGHT/DARK.

    - Mantiene selectores comunes usados por las páginas actuales.
    - `overrides` permite ajustar variables puntuales sin duplicar CSS.
    """
    if st is None:
        return

    light = {**LIGHT, **(overrides or {})}
    dark = {**DARK, **(overrides or {})}

    css = f"""
<style>
/* Defaults (LIGHT por accesibilidad si no hay media query) */
:root {{ {_vars_block(light)} }}

/* Modo oscuro por preferencia del sistema */
@media (prefers-color-scheme: dark) {{
  :root {{ {_vars_block(dark)} }}
}}

/* Estilos base */
html,body,[data-testid="stAppViewContainer"]{{ background:var(--bg)!important; color:var(--text-main)!important; }}
h1,h2,h3,h4, label, p, span, div{{ color:var(--text-main); }}
.small, .muted {{ color:var(--muted); font-size:12px; }}
.hr-light {{ border-bottom:1px solid var(--stroke); margin:12px 0; }}
.card {{ background:var(--surface); border:1px solid var(--stroke); border-radius:12px; padding:12px 14px; }}
.h-accent {{ position:relative; padding-left:10px; margin:8px 0 6px; font-weight:700; color:var(--text-main); }}
.h-accent:before {{ content:""; position:absolute; left:0; top:2px; bottom:2px; width:4px; border-radius:3px; background:var(--primary); }}

/* Badges */
.badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:700; }}
.badge--success {{ background:var(--success); color:#06210c; }}
.badge--pending {{ background:rgba(0,194,255,.15); color:#055160; border:1px solid rgba(0,194,255,.25); }}

/* Botones */
div.stButton > button[kind="primary"], .stDownloadButton button {{
  background: var(--primary) !important; color:#001018 !important; border:none !important;
  font-weight:700 !important; border-radius:10px !important;
}}
div.stButton > button[kind="secondary"] {{
  background: var(--surface) !important; color: var(--text-main) !important; border:1px solid var(--stroke) !important;
  border-radius:10px !important;
}}
div.stButton > button:hover {{ filter:brightness(0.93); }}

/* Inputs / selects */
[data-baseweb="input"] input, .stTextInput input, .stSelectbox div, .stSlider, textarea{{
  color:var(--text-main)!important;
}}

/* Sticky CTA (presente en algunas vistas) */
.sticky-cta {{ position:sticky; bottom:10px; z-index:10; padding:8px; background:var(--surface); border:1px solid var(--stroke); border-radius:12px; }}
</style>
"""
    st.markdown(css, unsafe_allow_html=True)


def inject_theme(overrides: Optional[Dict[str, str]] = None) -> None:
    """Alias público solicitado: usa `inject_base_theme`."""
    inject_base_theme(overrides=overrides)
