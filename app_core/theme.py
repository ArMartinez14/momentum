from __future__ import annotations
from typing import Dict, Optional

try:
    import streamlit as st
except Exception:
    st = None  # type: ignore

# Paletas base (variables usadas recurrentemente en la app)
LIGHT = {
    "PRIMARY": "#D64045",
    "SUCCESS": "#2F8052",
    "WARNING": "#EFA350",
    "DANGER": "#D64045",
    "BG": "#FBF7F5",
    "SURFACE": "#FFF3EF",
    "TEXT_MAIN": "#1B1919",
    "TEXT_MUTED": "#7B6E6A",
    "STROKE": "rgba(120, 40, 36, 0.18)",
}

DARK = {
    "PRIMARY": "#E2554A",
    "SUCCESS": "#3C8A5A",
    "WARNING": "#EFA350",
    "DANGER": "#E2554A",
    "BG": "#070505",
    "SURFACE": "#141010",
    "TEXT_MAIN": "#F7F4F1",
    "TEXT_MUTED": "#B9ABA5",
    "STROKE": "rgba(226, 94, 80, 0.22)",
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
.card {{
  background:linear-gradient(160deg, rgba(226,94,80,0.18), rgba(38,12,11,0.22));
  border:1px solid rgba(226,94,80,0.32);
  border-radius:16px;
  padding:14px 18px;
  box-shadow:0 26px 52px -32px rgba(0,0,0,0.5);
}}
.h-accent {{ position:relative; padding-left:10px; margin:8px 0 6px; font-weight:700; color:var(--text-main); }}
.h-accent:before {{ content:""; position:absolute; left:0; top:2px; bottom:2px; width:4px; border-radius:3px; background:var(--primary); }}

/* Hero / session layouts */
.hero-card {{
  background:linear-gradient(170deg, rgba(46,14,13,0.95), rgba(20,8,8,0.82));
  border:1px solid rgba(226,94,80,0.45);
  border-radius:18px;
  padding:22px 24px;
  display:flex;
  flex-direction:column;
  gap:8px;
  box-shadow:0 30px 60px -32px rgba(0,0,0,0.58);
}}
.hero-card__label {{ font-size:0.75rem; letter-spacing:0.12em; text-transform:uppercase; color:rgba(250,245,241,0.72); font-weight:600; }}
.hero-card__title {{ font-size:2rem; font-weight:700; letter-spacing:-0.01em; color:#FFFBF9; }}
.hero-card__meta {{ color:rgba(244,227,220,0.86); font-size:0.95rem; }}
.hero-card__chip {{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:6px 12px;
  border-radius:999px;
  background:rgba(226,94,80,0.32);
  color:#FFF9F6;
  font-weight:600;
  font-size:0.85rem;
}}

.session-card {{
  background:linear-gradient(165deg, rgba(226,94,80,0.14), rgba(18,7,7,0.82));
  border:1px solid rgba(226,94,80,0.34);
  border-radius:16px;
  padding:18px 20px;
  display:flex;
  flex-direction:column;
  gap:6px;
  box-shadow:0 28px 56px -32px rgba(0,0,0,0.55);
}}
.session-card__label {{ font-size:0.78rem; letter-spacing:0.08em; text-transform:uppercase; color:var(--muted); font-weight:600; }}
.session-card__value {{ font-size:1rem; font-weight:600; word-break:break-word; }}

.nav-section {{ margin:20px 0 12px; display:flex; justify-content:space-between; align-items:flex-end; }}
.nav-section__title {{ font-weight:700; font-size:1rem; letter-spacing:0.04em; text-transform:uppercase; color:rgba(226,94,80,0.96); }}
.nav-section__hint {{ font-size:0.85rem; color:rgba(239,230,224,0.66); }}

.nav-scroll-wrapper {{ position:relative; margin-bottom:12px; }}
.nav-scroll {{
  display:flex;
  gap:12px;
  overflow-x:auto;
  padding:4px 2px 12px;
  scroll-snap-type:x mandatory;
  scrollbar-width:none;
}}
.nav-scroll::-webkit-scrollbar {{ display:none; }}
.nav-scroll__item {{ scroll-snap-align:center; min-width:160px; flex:0 0 auto; }}
.nav-scroll__item .stButton>button {{ width:100%; }}
.nav-arrow {{
  position:absolute;
  top:50%;
  transform:translateY(-50%);
  width:34px;
  height:34px;
  border-radius:999px;
  display:flex;
  align-items:center;
  justify-content:center;
  background:rgba(18,10,9,0.82);
  border:1px solid rgba(226,94,80,0.32);
  color:#F8F2EE;
  cursor:pointer;
  transition:background .2s ease;
  box-shadow:0 12px 24px -16px rgba(0,0,0,0.5);
}}
.nav-arrow:hover {{ background:rgba(226,94,80,0.3); }}
.nav-arrow--left {{ left:-12px; }}
.nav-arrow--right {{ right:-12px; }}

.client-sticky {{
  position:-webkit-sticky;
  position:sticky;
  top:12px;
  z-index:60;
  width:100%;
  box-sizing:border-box;
  background:linear-gradient(175deg, rgba(50,13,12,0.95), rgba(18,6,6,0.84));
  border:1px solid rgba(226,94,80,0.45);
  border-radius:18px;
  padding:16px 20px;
  margin-bottom:14px;
  box-shadow:0 32px 62px -32px rgba(0,0,0,0.6);
  backdrop-filter:blur(14px);
}}
.client-sticky__label {{
  font-size:0.72rem;
  letter-spacing:0.1em;
  text-transform:uppercase;
  color:rgba(240,231,225,0.75);
  font-weight:600;
}}
.client-sticky__value {{
  font-size:1.35rem;
  font-family:'Space Grotesk','Inter','Segoe UI',sans-serif;
  font-weight:600;
  color:rgba(253,249,246,0.94);
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
  background:rgba(226,94,80,0.32);
  color:#FFF9F6;
  font-size:0.8rem;
  font-weight:600;
}}

/* Badges */
.badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:700; }}
.badge--success {{ background:var(--success); color:#06210c; }}
.badge--pending {{ background:rgba(0,194,255,.15); color:#055160; border:1px solid rgba(0,194,255,.25); }}

/* Botones */
div.stButton > button[kind="primary"], .stDownloadButton button {{
  background: linear-gradient(128deg, rgba(226,94,80,0.98), rgba(148,28,22,0.88)) !important;
  color:#FFFDFC !important; border:none !important;
  font-weight:700 !important; border-radius:12px !important;
  box-shadow:0 20px 36px -22px rgba(148,28,22,0.55) !important;
}}
div.stButton > button[kind="secondary"] {{
  background: rgba(20,12,11,0.6) !important;
  color: rgba(248,242,238,0.9) !important;
  border:1px solid rgba(226,94,80,0.32) !important;
  border-radius:10px !important;
  padding:6px 14px !important;
  font-size:0.85rem !important;
  backdrop-filter: blur(6px);
}}
div.stButton > button:hover {{ filter:brightness(0.93); }}

/* Inputs / selects */
[data-baseweb="input"] input, .stTextInput input, .stSelectbox div, .stSlider, textarea{{
  color:var(--text-main)!important;
}}

/* Sticky CTA (presente en algunas vistas) */
.sticky-cta {{ position:sticky; bottom:10px; z-index:10; padding:8px; background:linear-gradient(160deg, rgba(45,12,11,0.9), rgba(20,8,8,0.82)); border:1px solid rgba(226,94,80,0.32); border-radius:12px; }}
</style>
"""
    st.markdown(css, unsafe_allow_html=True)


def inject_theme(overrides: Optional[Dict[str, str]] = None) -> None:
    """Alias público solicitado: usa `inject_base_theme`."""
    inject_base_theme(overrides=overrides)
