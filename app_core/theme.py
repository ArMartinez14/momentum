from __future__ import annotations

from typing import Dict, Literal, Optional

try:
    import streamlit as st
except Exception:  # pragma: no cover - streamlit no disponible en tests
    st = None  # type: ignore

ThemeMode = Literal["auto", "light", "dark"]

# ===================== 🎨 TOKENS BASE =====================
LIGHT_BASE = {
    "PRIMARY": "#D64045",
    "SUCCESS": "#2F8052",
    "WARNING": "#EFA350",
    "DANGER": "#D64045",
    "BG": "#FBF7F5",
    "SURFACE": "#FFF3EF",
    "TEXT_MAIN": "#000000",
    "TEXT_SECONDARYMAIN": "#000000",  # ← NUEVO (tono secundario oscuro)
    "TEXT_MUTED": "#000000",
    "STROKE": "rgba(120, 40, 36, 0.18)",
}

DARK_BASE = {
    "PRIMARY": "#E2554A",
    "SUCCESS": "#3C8A5A",
    "WARNING": "#EFA350",
    "DANGER": "#E2554A",
    "BG": "#070505",
    "SURFACE": "#141010",
    "TEXT_MAIN": "#FFFFFF",
    "TEXT_SECONDARYMAIN": "#E8DED7",  # ← NUEVO (blanco cálido secundario)
    "TEXT_MUTED": "#F1E6DF",
    "STROKE": "rgba(226, 94, 80, 0.22)",
}


# ===================== 🗂️ CATÁLOGO DE COLORES =====================
# Cada diccionario contiene las variaciones pedidas por el usuario
# (textos de Series/Reps/Peso/RIR, botones de video, títulos y menús).
THEME_LIBRARY: Dict[str, Dict[str, Dict[str, str]]] = {
    "light": {
        "base": LIGHT_BASE,
        "metrics": {
            "series_text": "#FF8A94",
            "series_bg": "rgba(255, 138, 148, 0.18)",
            "reps_text": "#FF7482",
            "reps_bg": "rgba(255, 116, 130, 0.18)",
            "peso_text": "#7DCAFF",
            "peso_bg": "rgba(125, 202, 255, 0.16)",
            "rir_text": "#D8A9FF",
            "rir_bg": "rgba(216, 169, 255, 0.18)",
        },
        "buttons": {
            "video_bg": "linear-gradient(130deg, #0E6B55, #1FC59D)",
            "video_text": "#041510",
            "video_border": "rgba(63, 209, 173, 0.9)",
            "video_glow": "rgba(31, 197, 157, 0.55)",
        },
        "titles": {
            "primary": "#F7F4F1",
            "accent": "#FF9B8F",
        },
        "menu": {
            "text": "#000000",
            "active": "#FF9B8F",
            "muted": "#B9ABA5",
        },
    },
    "dark": {
        "base": DARK_BASE,
        "metrics": {
            "series_text": "#FFFFFF",
            "series_bg": "rgba(255, 138, 148, 0.18)",
            "reps_text": "#FFFFFF",
            "reps_bg": "rgba(255, 116, 130, 0.18)",
            "peso_text": "#7DCAFF",
            "peso_bg": "rgba(125, 202, 255, 0.16)",
            "rir_text": "#D8A9FF",
            "rir_bg": "rgba(216, 169, 255, 0.18)",
        },
        "buttons": {
            "video_bg": "linear-gradient(130deg, #0E6B55, #1FC59D)",
            "video_text": "#041510",
            "video_border": "rgba(63, 209, 173, 0.9)",
            "video_glow": "rgba(31, 197, 157, 0.55)",
        },
        "titles": {
            "primary": "#F7F4F1",
            "accent": "#FF9B8F",
        },
        "menu": {
            "text": "#000000",
            "active": "#FF9B8F",
            "muted": "#B9ABA5",
        },
    },
}


SHARED_STYLE_TOKENS: Dict[str, str] = {
    # === Cards & generic surfaces ===
    "--card-bg": "linear-gradient(160deg, rgba(226,94,80,0.18), rgba(38,12,11,0.22))",
    "--card-border": "rgba(226,94,80,0.32)",
    "--card-shadow": "rgba(0,0,0,0.50)",
    "--session-card-bg": "linear-gradient(165deg, rgba(226,94,80,0.14), rgba(18,7,7,0.82))",
    "--session-card-border": "rgba(226,94,80,0.34)",
    "--session-card-shadow": "rgba(0,0,0,0.55)",
    "--hero-card-bg": "linear-gradient(170deg, rgba(46,14,13,0.95), rgba(20,8,8,0.82))",
    "--hero-card-border": "rgba(226,94,80,0.45)",
    "--hero-card-shadow": "rgba(0,0,0,0.58)",
    "--hero-card-label": "rgba(250,245,241,0.72)",
    "--hero-card-title": "#FFFBF9",
    "--hero-card-meta": "rgba(244,227,220,0.86)",
    "--chip-bg": "rgba(226,94,80,0.32)",
    "--chip-text": "#FFF9F6",
    "--client-sticky-bg": "linear-gradient(175deg, rgba(50,13,12,0.95), rgba(18,6,6,0.84))",
    "--client-sticky-border": "rgba(226,94,80,0.45)",
    "--client-sticky-shadow": "rgba(0,0,0,0.60)",
    "--client-sticky-label": "rgba(240,231,225,0.75)",
    "--client-sticky-value": "rgba(253,249,246,0.94)",
    "--sticky-cta-bg": "linear-gradient(160deg, rgba(45,12,11,0.9), rgba(20,8,8,0.82))",
    "--sticky-cta-border": "rgba(226,94,80,0.32)",
    # === Buttons ===
    "--btn-primary-bg": "linear-gradient(128deg, rgba(226,94,80,0.98), rgba(148,28,22,0.88))",
    "--btn-primary-text": "#FFFDFC",
    "--btn-primary-shadow": "rgba(148,28,22,0.55)",
    "--btn-secondary-bg": "rgba(20,12,11,0.60)",
    "--btn-secondary-border": "rgba(226,94,80,0.32)",
    # === Badges & chips ===
    "--badge-success-text": "#06210c",
    "--badge-pending-bg": "rgba(0,194,255,0.15)",
    "--badge-pending-text": "#055160",
    "--badge-pending-border": "rgba(0,194,255,0.25)",
}


def _build_color_catalog() -> Dict[str, Dict[str, str]]:
    catalog: Dict[str, Dict[str, str]] = {}
    for mode, profile in THEME_LIBRARY.items():
        for section_name, values in profile.items():
            catalog[f"{mode}/{section_name}"] = dict(values)
    catalog["shared/components"] = {k.lstrip("-"): v for k, v in SHARED_STYLE_TOKENS.items()}
    return catalog


def _format_color_catalog(catalog: Dict[str, Dict[str, str]]) -> str:
    lines = ["# === CATÁLOGO DE COLORES (auto-generado) ==="]
    for section in sorted(catalog.keys()):
        lines.append(f"# [{section}]")
        for key, value in catalog[section].items():
            lines.append(f"#   {key}: {value}")
    return "\n".join(lines)


COLOR_CATALOG = _build_color_catalog()
COLOR_CATALOG_DOC = _format_color_catalog(COLOR_CATALOG)


def _normalize_mode(mode: Optional[str]) -> ThemeMode:
    if not mode:
        return "auto"
    value = mode.strip().lower()
    mapping = {
        "auto": "dark",
        "system": "dark",
        "default": "dark",
        "oscuro": "dark",
        "dark": "dark",
        "night": "dark",
        "claro": "light",
        "light": "light",
        "day": "light",
    }
    return mapping.get(value, "auto")


def _clone_profile(key: str, overrides: Optional[Dict[str, str]] = None) -> Dict[str, Dict[str, str]]:
    base_profile = THEME_LIBRARY[key]
    clone = {section: dict(values) for section, values in base_profile.items()}
    if overrides:
        clone["base"] = {**clone["base"], **overrides}
    return clone


def _vars_block(profile: Dict[str, Dict[str, str]]) -> str:
    base = profile["base"]
    metrics = profile["metrics"]
    buttons = profile["buttons"]
    titles = profile["titles"]
    menu = profile["menu"]
    tokens = {
        "--primary": base["PRIMARY"],
        "--success": base["SUCCESS"],
        "--warning": base["WARNING"],
        "--danger": base["DANGER"],
        "--bg": base["BG"],
        "--surface": base["SURFACE"],
        "--muted": base["TEXT_MUTED"],
        "--stroke": base["STROKE"],
        "--text-main": base["TEXT_MAIN"],
        "--text-secondary-main": base.get("TEXT_SECONDARYMAIN", base["TEXT_MAIN"]),
        "--metric-series-text": metrics["series_text"],
        "--metric-series-bg": metrics["series_bg"],
        "--metric-reps-text": metrics["reps_text"],
        "--metric-reps-bg": metrics["reps_bg"],
        "--metric-peso-text": metrics["peso_text"],
        "--metric-peso-bg": metrics["peso_bg"],
        "--metric-rir-text": metrics["rir_text"],
        "--metric-rir-bg": metrics["rir_bg"],
        "--video-btn-bg": buttons["video_bg"],
        "--video-btn-text": buttons["video_text"],
        "--video-btn-border": buttons["video_border"],
        "--video-btn-glow": buttons["video_glow"],
        "--title-primary": titles["primary"],
        "--title-accent": titles["accent"],
        "--menu-text": menu["text"],
        "--menu-active": menu["active"],
        "--menu-muted": menu["muted"],
    }
    tokens.update(SHARED_STYLE_TOKENS)
    return " ".join(f"{name}:{value};" for name, value in tokens.items())


def _root_block(mode: ThemeMode, overrides: Optional[Dict[str, str]]) -> str:
    light_profile = _clone_profile("light", overrides)
    dark_profile = _clone_profile("dark", overrides)
    light_vars = _vars_block(light_profile)
    dark_vars = _vars_block(dark_profile)

    if mode == "light":
        return f":root {{{light_vars}}}"
    if mode == "dark":
        return f":root {{{dark_vars}}}"
    return f":root {{{light_vars}}}\n@media (prefers-color-scheme: dark) {{ :root {{{dark_vars}}} }}"


def inject_base_theme(mode: Optional[str] = None, overrides: Optional[Dict[str, str]] = None) -> None:
    """Inyecta CSS base con variables LIGHT/DARK y tokens organizados por secciones."""
    if st is None:
        return

    resolved_mode = _normalize_mode(mode)
    root_block = _root_block(resolved_mode, overrides)

    css = f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=Space+Grotesk:wght@500;600;700&display=swap');

{root_block}

html,body,[data-testid="stAppViewContainer"]{{ background:var(--bg)!important; color:var(--text-main)!important; font-family:'Inter','SF Pro Text','Segoe UI',sans-serif; }}
h1,h2,h3,h4{{ font-family:'Space Grotesk','Inter','Segoe UI',sans-serif; color:var(--title-primary); letter-spacing:-0.01em; }}
label,p,span,div{{ color:var(--text-main); }}
.small, .muted {{ color:var(--muted); font-size:12px; }}
.hr-light {{ border-bottom:1px solid var(--stroke); margin:12px 0; }}

/* === TITULOS Y MENÚS === */
.h-accent {{ position:relative; padding-left:0; margin:8px 0 6px; font-weight:700; color:var(--title-accent); }}
.nav-section__title {{ font-weight:700; font-size:1rem; letter-spacing:0.04em; text-transform:uppercase; color:var(--menu-active); }}
.nav-section__hint {{ font-size:0.85rem; color:var(--menu-muted); }}
.nav-desktop .stButton>button,
.nav-mobile__items button {{
  color:var(--menu-text)!important;
  font-weight:700!important;
}}

/* === TARJETAS === */
.card {{
  background:var(--card-bg);
  border:1px solid var(--card-border);
  border-radius:16px;
  padding:14px 18px;
  box-shadow:0 26px 52px -32px var(--card-shadow);
}}
.hero-card {{
  background:var(--hero-card-bg);
  border:1px solid var(--hero-card-border);
  border-radius:18px;
  padding:22px 24px;
  display:flex;
  flex-direction:column;
  gap:8px;
  box-shadow:0 30px 60px -32px var(--hero-card-shadow);
}}
.hero-card__label {{ font-size:0.75rem; letter-spacing:0.12em; text-transform:uppercase; color:var(--hero-card-label); font-weight:600; }}
.hero-card__title {{ font-size:2rem; font-weight:700; letter-spacing:-0.01em; color:var(--hero-card-title); }}
.hero-card__meta {{ color:var(--hero-card-meta); font-size:0.95rem; }}
.hero-card__chip {{
  display:inline-flex;
  align-items:center;
  gap:8px;
  padding:6px 12px;
  border-radius:999px;
  background:var(--chip-bg);
  color:var(--chip-text);
  font-weight:600;
  font-size:0.85rem;
}}

.session-card {{
  background:var(--session-card-bg);
  border:1px solid var(--session-card-border);
  border-radius:16px;
  padding:18px 20px;
  display:flex;
  flex-direction:column;
  gap:6px;
  box-shadow:0 28px 56px -32px var(--session-card-shadow);
}}
.session-card__label {{ font-size:0.78rem; letter-spacing:0.08em; text-transform:uppercase; color:var(--text-secondary-main); font-weight:600; }}
.session-card__value {{ font-size:1rem; font-weight:600; word-break:break-word; }}

/* === MENÚ RESPONSIVO === */
.nav-section {{ margin:20px 0 12px; display:flex; justify-content:space-between; align-items:flex-end; }}
.nav-desktop {{ display:flex; gap:12px; margin-bottom:14px; flex-wrap:wrap; }}
.nav-desktop .stButton>button {{ min-width:150px; }}
.nav-mobile {{ margin-bottom:14px; }}
.nav-mobile__items {{ display:flex; flex-wrap:wrap; gap:12px; }}
.nav-mobile__items > div {{ flex:1 1 calc(33.333% - 12px); min-width:0; }}

/* === TABS Y BLOQUES === */
.stTabs [data-baseweb="tab-list"] {{ border-bottom:none!important; box-shadow:none!important; background:transparent!important; }}
.stTabs [data-baseweb="tab-highlight"] {{ display:none!important; }}
.editor-block {{
  background:transparent;
  border:1px solid transparent;
  border-radius:16px;
  padding:16px 18px;
  margin-bottom:16px;
  box-shadow:none;
}}

/* === BOTONES === */
div.stButton > button[kind="primary"], .stDownloadButton button {{
  background: var(--btn-primary-bg) !important;
  color:var(--btn-primary-text) !important; border:none !important;
  font-weight:700 !important; border-radius:12px !important;
  box-shadow:0 20px 36px -22px var(--btn-primary-shadow) !important;
}}
div.stButton > button[kind="secondary"] {{
  background: var(--btn-secondary-bg) !important;
  color: var(--menu-text) !important;
  border:1px solid var(--btn-secondary-border) !important;
  border-radius:10px !important;
  padding:6px 14px !important;
  font-size:0.85rem !important;
  backdrop-filter: blur(6px);
}}
button[data-testid="baseButton-secondary"] {{
  color:var(--menu-text)!important;
  font-weight:700!important;
}}
button.video-cta,
.video-legend-button {{
  display:inline-flex;
  align-items:center;
  gap:6px;
  padding:6px 16px;
  border-radius:999px;
  border:1px solid var(--video-btn-border);
  background:var(--video-btn-bg);
  color:var(--video-btn-text);
  font-weight:600;
  font-size:0.85rem;
  box-shadow:0 16px 32px -18px var(--video-btn-glow);
}}
.video-legend-button {{ cursor:default; }}
.exercise-block button[kind="primary"] {{
  color:var(--text-main)!important;
}}

/* === METRICAS SERIES / REPS / PESO / RIR === */
.metric-legend {{
  display:none !important;
}}
.metric-chip {{
  display:inline-flex;
  align-items:center;
  padding:4px 12px;
  border-radius:999px;
  font-size:0.8rem;
  font-weight:600;
  border:1px solid transparent;
  background:transparent;
}}
.metric-chip--series {{
  color:var(--metric-series-text);
  border-color:var(--metric-series-text);
  background:var(--metric-series-bg);
}}
.metric-chip--reps {{
  color:var(--metric-reps-text);
  border-color:var(--metric-reps-text);
  background:var(--metric-reps-bg);
}}
.metric-chip--peso {{
  color:var(--metric-peso-text);
  border-color:var(--metric-peso-text);
  background:var(--metric-peso-bg);
}}
.metric-chip--rir {{
  color:var(--metric-rir-text);
  border-color:var(--metric-rir-text);
  background:var(--metric-rir-bg);
}}
.header-center--series {{ color:var(--metric-series-text); }}
.header-center--repeticiones {{ color:var(--metric-reps-text); }}
.header-center--peso {{ color:var(--metric-peso-text); }}
.header-center--rir-min-max {{ color:var(--metric-rir-text); }}

/* === Inputs / selects === */
[data-baseweb="input"] input, .stTextInput input, .stSelectbox div, .stSlider, textarea{{
  color:var(--text-main)!important;
}}

/* === Sticky sections === */
.top-actions button[data-testid="baseButton-secondary"] {{
  color:var(--text-main) !important;
  font-weight:600 !important;
}}
.client-sticky {{
  position:-webkit-sticky;
  position:sticky;
  top:12px;
  z-index:60;
  width:100%;
  box-sizing:border-box;
  background:var(--client-sticky-bg);
  border:1px solid var(--client-sticky-border);
  border-radius:18px;
  padding:16px 20px;
  margin-bottom:14px;
  box-shadow:0 32px 62px -32px var(--client-sticky-shadow);
  backdrop-filter:blur(14px);
}}
.client-sticky__label {{
  font-size:0.72rem;
  letter-spacing:0.1em;
  text-transform:uppercase;
  color:var(--client-sticky-label);
  font-weight:600;
}}
.client-sticky__value {{
  font-size:1.35rem;
  font-family:'Space Grotesk','Inter','Segoe UI',sans-serif;
  font-weight:600;
  color:var(--client-sticky-value);
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
  background:var(--chip-bg);
  color:var(--chip-text);
  font-size:0.8rem;
  font-weight:600;
}}

/* === Badges / CTA === */
.badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:700; }}
.badge--success {{ background:var(--success); color:var(--badge-success-text); }}
.badge--pending {{ background:var(--badge-pending-bg); color:var(--badge-pending-text); border:1px solid var(--badge-pending-border); }}
.sticky-cta {{ position:sticky; bottom:10px; z-index:10; padding:8px; background:var(--sticky-cta-bg); border:1px solid var(--sticky-cta-border); border-radius:12px; }}

@media (min-width: 1024px) {{
  .nav-mobile {{ display:none; }}
}}

@media (max-width: 1023px) {{
  .nav-desktop {{ display:none; }}
}}

/* === TOP SET BLOCK === */
.topset-card {{
  text-align: center;
  margin: 12px auto 0;
  width: min(520px, 100%);
}}
.topset-card__title {{
  text-align: center;
  font-weight: 700;
  margin-bottom: 4px;
}}
.topset-line {{
  text-align: center;
  margin: 2px 0;
}}
</style>
"""
    st.markdown(css, unsafe_allow_html=True)


def inject_theme(mode: Optional[str] = None, overrides: Optional[Dict[str, str]] = None) -> None:
    """Alias público solicitado: usa `inject_base_theme`."""
    inject_base_theme(mode=mode, overrides=overrides)


if __name__ == "__main__":
    print(COLOR_CATALOG_DOC)
