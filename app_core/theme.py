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
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

/* Defaults (LIGHT por accesibilidad si no hay media query) */
:root {{ {_vars_block(light)} }}

/* Modo oscuro por preferencia del sistema */
@media (prefers-color-scheme: dark) {{
  :root {{ {_vars_block(dark)} }}
}}

/* Estilos base */
html,body,[data-testid="stAppViewContainer"]{{ background:var(--bg)!important; color:var(--text-main)!important; font-family:'Inter','SF Pro Text','Segoe UI',sans-serif; }}
h1,h2,h3,h4{{ font-family:'Space Grotesk','Inter','Segoe UI',sans-serif; color:var(--text-main); letter-spacing:-0.01em; }}
label,p,span,div{{ color:var(--text-main); }}
.small, .muted {{ color:var(--muted); font-size:12px; }}
.hr-light {{ border-bottom:1px solid var(--stroke); margin:12px 0; }}
.card {{ background:var(--surface); border:1px solid var(--stroke); border-radius:12px; padding:12px 14px; }}
.h-accent {{ position:relative; padding-left:10px; margin:8px 0 6px; font-weight:700; color:var(--text-main); }}
.h-accent:before {{ content:""; position:absolute; left:0; top:2px; bottom:2px; width:4px; border-radius:3px; background:var(--primary); }}

/* Hero / session layouts */
.hero-card {{
  background:linear-gradient(135deg, rgba(0,194,255,0.18), rgba(56,189,248,0.12));
  border:1px solid rgba(56,189,248,0.35);
  border-radius:18px;
  padding:22px 24px;
  display:flex;
  flex-direction:column;
  gap:8px;
  box-shadow:0 18px 46px -24px rgba(0,194,255,0.35);
}}
.hero-card__label {{ font-size:0.75rem; letter-spacing:0.12em; text-transform:uppercase; color:rgba(148,163,184,0.85); font-weight:600; }}
.hero-card__title {{ font-size:2rem; font-weight:700; letter-spacing:-0.01em; }}
.hero-card__meta {{ color:rgba(148,163,184,0.9); font-size:0.95rem; }}
.hero-card__chip {{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:6px 12px;
  border-radius:999px;
  background:rgba(0,194,255,0.22);
  color:#0f172a;
  font-weight:600;
  font-size:0.85rem;
}}

.session-card {{
  background:var(--surface);
  border:1px solid var(--stroke);
  border-radius:16px;
  padding:18px 20px;
  display:flex;
  flex-direction:column;
  gap:6px;
  box-shadow:0 16px 40px -26px rgba(15,23,42,0.45);
}}
.session-card__label {{ font-size:0.78rem; letter-spacing:0.08em; text-transform:uppercase; color:var(--muted); font-weight:600; }}
.session-card__value {{ font-size:1rem; font-weight:600; word-break:break-word; }}

.nav-section {{ margin:20px 0 12px; display:flex; justify-content:space-between; align-items:flex-end; }}
.nav-section__title {{ font-weight:700; font-size:1rem; letter-spacing:0.04em; text-transform:uppercase; color:var(--muted); }}
.nav-section__hint {{ font-size:0.85rem; color:rgba(148,163,184,0.85); }}

.nav-row {{ display:flex; flex-wrap:wrap; gap:10px; margin-bottom:12px; }}
.nav-row .stButton>button {{
  min-width:150px;
}}

.client-sticky {{
  position:-webkit-sticky;
  position:sticky;
  top:12px;
  z-index:60;
  width:100%;
  box-sizing:border-box;
  background:linear-gradient(135deg, rgba(15,23,42,0.96), rgba(15,23,42,0.82));
  border:1px solid rgba(148,163,184,0.28);
  border-radius:18px;
  padding:16px 20px;
  margin-bottom:14px;
  box-shadow:0 22px 48px -30px rgba(15,23,42,0.65);
  backdrop-filter:blur(14px);
}}
.client-sticky__label {{
  font-size:0.72rem;
  letter-spacing:0.1em;
  text-transform:uppercase;
  color:rgba(148,163,184,0.82);
  font-weight:600;
}}
.client-sticky__value {{
  font-size:1.35rem;
  font-family:'Space Grotesk','Inter','Segoe UI',sans-serif;
  font-weight:600;
  color:rgba(226,232,240,0.95);
  display:flex;
  align-items:center;
  gap:10px;
}}
.client-sticky__badge {{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:4px 10px;
  border-radius:999px;
  background:rgba(34,197,94,0.16);
  color:#4ade80;
  font-size:0.8rem;
  font-weight:600;
}}

/* Badges */
.badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:700; }}
.badge--success {{ background:var(--success); color:#06210c; }}
.badge--pending {{ background:rgba(0,194,255,.15); color:#055160; border:1px solid rgba(0,194,255,.25); }}

/* Botones */
div.stButton > button[kind="primary"], .stDownloadButton button {{
  background: linear-gradient(135deg, var(--primary), rgba(0,194,255,0.72)) !important;
  color:#001018 !important; border:none !important;
  font-weight:700 !important; border-radius:12px !important;
  box-shadow:0 12px 28px -16px rgba(0,194,255,0.65) !important;
}}
div.stButton > button[kind="secondary"] {{
  background: rgba(15,23,42,0.35) !important;
  color: rgba(226,232,240,0.95) !important;
  border:1px solid rgba(148,163,184,0.24) !important;
  border-radius:12px !important;
  backdrop-filter: blur(6px);
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
