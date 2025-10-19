# ver_rutinas.py — UI modernizada + filtro correcto por cliente + checkbox "Sesión anterior" + Reporte por circuito (reintegrado)
from __future__ import annotations

import streamlit as st
from streamlit.errors import StreamlitAPIException
from firebase_admin import firestore
from datetime import datetime, timedelta, date
import json, random, re, math, html
from io import BytesIO
import matplotlib.pyplot as plt
import time
from app_core.firebase_client import get_db
from app_core.theme import inject_theme
from app_core.utils import empresa_de_usuario, EMPRESA_MOTION, EMPRESA_ASESORIA, EMPRESA_DESCONOCIDA


_QUERY_API_MODE: str | None = None  # "new" | "legacy"


def _current_query_params() -> dict[str, str]:
    global _QUERY_API_MODE

    def _from_items(items):
        out: dict[str, str] = {}
        for key, value in items:
            if isinstance(value, list):
                if not value:
                    continue
                out[key] = value[0]
            elif value is not None:
                out[key] = str(value)
        return out

    if _QUERY_API_MODE == "legacy":
        try:
            return _from_items(st.experimental_get_query_params().items())
        except Exception:
            return {}

    try:
        items = st.query_params.items()
        _QUERY_API_MODE = "new"
        return _from_items(items)
    except StreamlitAPIException:
        _QUERY_API_MODE = "legacy"
        return _current_query_params()
    except Exception:
        return {}


def _replace_query_params(params: dict[str, str | None]) -> None:
    global _QUERY_API_MODE

    clean = {k: str(v) for k, v in params.items() if v is not None}
    if _current_query_params() == clean:
        return

    if _QUERY_API_MODE == "legacy":
        try:
            st.experimental_set_query_params(**clean)
        except Exception:
            pass
        return

    try:
        qp = st.query_params
        qp.clear()
        if clean:
            qp.update(clean)
        _QUERY_API_MODE = "new"
    except StreamlitAPIException:
        _QUERY_API_MODE = "legacy"
        try:
            st.experimental_set_query_params(**clean)
        except Exception:
            pass
    except Exception:
        pass


def _sync_rutinas_query_params(cliente: str | None = None, semana: str | None = None, dia: str | None = None) -> None:
    payload = {"menu": "Ver Rutinas"}
    if cliente:
        payload["cliente"] = cliente
    if semana:
        payload["semana"] = semana
    if dia:
        payload["dia"] = str(dia)
    _replace_query_params(payload)

# ==========================
#  PALETA / ESTILOS con soporte claro/oscuro
# ==========================
control_bar = st.container()
with control_bar:
    control_cols = st.columns([4, 1])
    with control_cols[1]:
        theme_mode = st.selectbox(
            "🎨 Tema",
            ["Auto", "Oscuro", "Claro"],
            key="theme_mode_vista_rutinas",
            help="'Auto' sigue el modo del sistema; 'Oscuro/Claro' fuerzan los colores.",
            label_visibility="collapsed",
        )

st.markdown(
    """
    <style>
    .status-card {
        background: #0b1018;
        border: 1px solid rgba(15, 23, 42, 0.7);
        border-radius: 18px;
        padding: 20px 22px;
        margin-bottom: 16px;
        box-shadow: 0 8px 24px rgba(8, 15, 26, 0.2);
        color: #e2e8f0;
    }
    .status-card__message {
        display: flex;
        flex-direction: column;
        gap: 6px;
        color: #e2e8f0;
    }
    .status-card__greet {
        font-size: 1rem;
        font-weight: 600;
    }
    .status-card__title {
        font-size: 1.28rem;
        font-weight: 800;
    }
    .status-card__label {
        font-size: 0.72rem;
        letter-spacing: 0.1em;
        text-transform: uppercase;
        color: rgba(148, 163, 184, 0.75);
        display: inline-block;
        margin-bottom: 4px;
    }
    .status-card__range {
        margin-top: 12px;
        font-size: 0.9rem;
        font-weight: 600;
        color: rgba(148, 163, 184, 0.75);
    }
    .summary-card {
        background: linear-gradient(135deg, rgba(52, 211, 153, 0.18), rgba(16, 185, 129, 0.22));
        border: 1px solid rgba(16, 185, 129, 0.45);
        border-radius: 16px;
        padding: 16px 20px;
        margin: 10px 0 22px;
        display: flex;
        flex-direction: column;
        gap: 8px;
        box-shadow: 0 12px 36px rgba(16, 185, 129, 0.25);
        color: #052019;
    }
    .summary-card__title {
        font-weight: 800;
        font-size: 1.05rem;
        color: #052019;
        display: flex;
        align-items: center;
        gap: 8px;
    }
    .summary-card__meta {
        font-size: 0.96rem;
        color: #064e3b;
    }
    .summary-card__meta.muted {
        color: rgba(6, 78, 59, 0.7);
    }
    .planner-card {
        background: var(--surface);
        border: 1px solid var(--stroke);
        border-radius: 18px;
        padding: 18px 22px;
        margin: 12px 0 22px;
    }
    .planner-card__body {
        display: flex;
        flex-direction: column;
        gap: 8px;
        align-items: center;
        text-align: center;
    }
    .planner-card__motivation {
        font-size: 0.95rem;
        font-weight: 600;
        color: var(--success);
    }
    .planner-card__range {
        font-size: 1.12rem;
        font-weight: 700;
    }
    .planner-card__meta {
        font-size: 0.92rem;
        color: var(--text-main);
    }
    .planner-card__meta.muted {
        color: var(--muted);
    }
    .planner-card__badge {
        display: inline-flex;
        align-items: center;
        gap: 6px;
        padding: 4px 12px;
        border-radius: 999px;
        background: rgba(0, 194, 255, 0.18);
        color: var(--primary);
        font-weight: 600;
        width: fit-content;
    }
    .planner-card__note {
        font-size: 0.84rem;
        color: var(--muted);
    }
    .planner-card__label {
        font-size: 0.75rem;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: var(--muted);
        display: block;
        margin-bottom: 6px;
    }
    .planner-card__badge.is-active {
        background: linear-gradient(135deg, rgba(0,194,255,0.2), rgba(34,197,94,0.25));
        border: 1px solid rgba(34,197,94,0.45);
        color: #10b981;
    }
    .days-subtitle {
        margin: 18px 0 12px;
        font-size: 0.92rem;
        font-weight: 600;
        color: rgba(14, 165, 233, 0.8);
        text-transform: uppercase;
        letter-spacing: 0.04em;
    }
    div[data-testid="stButton"][data-key^="daybtn_"] button {
        width: 100%;
        border-radius: 14px;
        padding: 14px 16px;
        font-weight: 600;
        letter-spacing: 0.02em;
        display: flex;
        flex-direction: column;
        align-items: flex-start;
        gap: 4px;
        white-space: pre-line;
        box-shadow: 0 8px 24px rgba(56, 189, 248, 0.18);
    }
    div[data-testid="stButton"][data-key^="daybtn_"] button[kind="secondary"] {
        background: linear-gradient(135deg, rgba(23, 37, 84, 0.85), rgba(30, 64, 175, 0.85)) !important;
        color: #f8fafc !important;
    }
    div[data-testid="stButton"][data-key^="daybtn_"] button[kind="primary"] {
        background: linear-gradient(135deg, rgba(239, 68, 68, 0.9), rgba(244, 114, 182, 0.85)) !important;
        color: #fff5f5 !important;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# CSS/tema unificado
inject_theme()
def _rirstr(e: dict) -> str:
    """
    Devuelve el RIR en formato:
      - "min–max" si existen campos de rango (RirMin/RirMax o rir_min/rir_max)
      - valor único si solo hay uno de ellos
      - valor 'legacy' si viene como texto único en e['rir'] / e['RIR'] / e['Rir']
      - "" si no hay datos
    """
    # 1) Nuevos campos con rango (preservando valores 0)
    def _pick(*valores):
        for v in valores:
            if v is None:
                continue
            if isinstance(v, str) and v.strip() == "":
                continue
            return v
        return None

    rmin = _pick(e.get("RirMin"), e.get("rir_min"), e.get("RIR_min"))
    rmax = _pick(e.get("RirMax"), e.get("rir_max"), e.get("RIR_max"))

    rmin_s = str(rmin).strip() if rmin is not None else ""
    rmax_s = str(rmax).strip() if rmax is not None else ""

    if rmin_s and rmax_s:
        return f"{rmin_s}–{rmax_s}"
    if rmin_s or rmax_s:
        return rmin_s or rmax_s

    # 2) Formato antiguo: un solo campo de texto/numero
    legacy = e.get("rir") or e.get("RIR") or e.get("Rir") or ""
    legacy_s = str(legacy).strip()
    if not legacy_s:
        return ""

    # Si venía "RIR 2" o "2 RIR", extrae número; si no, deja el texto
    m = re.search(r"-?\d+(\.\d+)?", legacy_s)
    return m.group(0) if m else legacy_s



# ==========================
#  MOTIVACIONAL
# ==========================
MENSAJES_MOTIVACIONALES = [
    "💪 ¡Éxito en tu entrenamiento de hoy, {nombre}! 🔥",
    "🚀 {nombre}, cada repetición te acerca más a tu objetivo.",
    "🏋️‍♂️ {nombre}, hoy es un gran día para superar tus límites.",
    "🔥 Vamos {nombre}, conviértete en la mejor versión de ti mismo.",
    "⚡ {nombre}, la constancia es la clave. ¡Dalo todo hoy!",
    "🥇 {nombre}, cada sesión es un paso más hacia la victoria.",
    "🌟 Nunca te detengas, {nombre}. ¡Hoy vas a brillar en tu entrenamiento!",
    "🏆 {nombre}, recuerda: disciplina > motivación. ¡Tú puedes!",
    "🙌 A disfrutar el proceso, {nombre}. ¡Confía en ti!",
    "💥 {nombre}, el esfuerzo de hoy es el resultado de mañana.",
    "🔥 {nombre}, hoy es el día perfecto para superar tu récord.",
]

def _random_mensaje(nombre: str) -> str:
    try:
        base = random.choice(MENSAJES_MOTIVACIONALES)
    except Exception:
        base = "💪 ¡Buen trabajo, {nombre}!"
    return base.format(nombre=(nombre or "Atleta").split(" ")[0])

def mensaje_motivador_del_dia(nombre: str, correo_id: str) -> str:
    hoy = date.today().isoformat()
    key = f"mot_msg_{correo_id}_{hoy}"
    if key not in st.session_state:
        st.session_state[key] = _random_mensaje(nombre)
    return st.session_state[key]

# ==========================
#  HELPERS NUM / FORMATO
# ==========================

import re

_URL_RGX = re.compile(r'(https?://\S+)', re.IGNORECASE)

def _video_y_detalle_desde_ejercicio(e: dict) -> tuple[str, str]:
    """
    Retorna (video_url, detalle_visible). Si 'detalle' contiene un link y no hay e['video'],
    usa ese link como video y oculta el detalle.
    """
    video = (e.get("video") or "").strip()
    detalle = (e.get("detalle") or "").strip()

    # Si ya hay video explícito, devolvemos tal cual y mantenemos el detalle
    if video:
        return video, detalle

    # Si no hay video pero el detalle tiene un link -> usar ese link como video y NO mostrar detalle
    if detalle:
        m = _URL_RGX.search(detalle)
        if m:
            url = m.group(1).strip()
            return url, ""  # ocultamos detalle si contenía link
    return "", detalle

def _to_float_or_none(v):
    try:
        s = str(v).strip().replace(",", ".")
        if s == "": return None
        if "-" in s: s = s.split("-", 1)[0].strip()
        return float(s)
    except: return None

def _format_minutos(v) -> str:
    f = _to_float_or_none(v)
    if f is None: return ""
    n = int(round(f))
    return f"{n} Minuto" if n == 1 else f"{n} Minutos"

def _peso_to_float(v):
    try:
        s = str(v or "").lower().replace("kg", "").replace(",", ".").strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None

def _format_peso_value(value: float) -> str:
    if value is None:
        return ""
    if not math.isfinite(value):
        return ""
    if abs(value - round(value)) < 1e-4:
        return str(int(round(value)))
    formatted = f"{value:.2f}".rstrip("0").rstrip(".")
    return formatted

# ==========================
#  NORMALIZACIÓN / LISTAS
# ==========================
def _repstr(e: dict) -> str:
    """3 × 10–12 / 3 × 12+ / 3 × ≤12 / 3 × —"""
    series = e.get("series") or e.get("series_min") or e.get("Series") or ""
    try:
        series = int(series)
    except:
        series = str(series) if str(series).strip() else "—"
    a = f"{series} × "
    rmin = e.get("reps_min") or e.get("RepsMin") or e.get("repeticiones_min")
    rmax = e.get("reps_max") or e.get("RepsMax") or e.get("repeticiones_max")
    reps = e.get("repeticiones")
    if rmin and rmax:
        return a + f"{rmin}–{rmax}"
    if rmin:
        return a + f"{rmin}+"
    if rmax:
        return a + f"≤{rmax}"
    if reps:
        return a + f"{reps}"
    return a + "—"

def _descanso_texto(e: dict) -> str:
    v = e.get("descanso") or e.get("rest") or ""
    if v in ("", None): 
        return ""
    try:
        f = float(str(v).replace(",", "."))
    except:
        return str(v)
    m = int(round(f))
    return f"{m} Minuto" if m == 1 else f"{m} Minutos"

def obtener_lista_ejercicios(data_dia):
    if data_dia is None: return []
    if isinstance(data_dia, dict):
        if "ejercicios" in data_dia:
            ejercicios = data_dia["ejercicios"]
            if isinstance(ejercicios, dict):
                try:
                    pares = sorted(ejercicios.items(), key=lambda kv: int(kv[0]))
                    return [v for _, v in pares if isinstance(v, dict)]
                except Exception:
                    return [v for v in ejercicios.values() if isinstance(v, dict)]
            elif isinstance(ejercicios, list):
                return [e for e in ejercicios if isinstance(e, dict)]
            else:
                return []
        claves_numericas = [k for k in data_dia.keys() if str(k).isdigit()]
        if claves_numericas:
            try:
                pares = sorted(((k, data_dia[k]) for k in claves_numericas), key=lambda kv: int(kv[0]))
                return [v for _, v in pares if isinstance(v, dict)]
            except Exception:
                return [data_dia[k] for k in data_dia if isinstance(data_dia[k], dict)]
        return [v for v in data_dia.values() if isinstance(v, dict)]
    if isinstance(data_dia, list):
        if len(data_dia) == 1 and isinstance(data_dia[0], dict) and "ejercicios" in data_dia[0]:
            return obtener_lista_ejercicios(data_dia[0])
        return [e for e in data_dia if isinstance(e, dict)]
    return []

def ordenar_circuito(ejercicio):
    if not isinstance(ejercicio, dict): return 99
    orden = {"A":1,"B":2,"C":3,"D":4,"E":5,"F":6,"G":7}
    return orden.get(str(ejercicio.get("circuito","")).upper(), 99)

def _num_or_empty(x):
    s = str(x).strip()
    m = re.search(r"-?\d+(\.\d+)?", s)
    return m.group(0) if m else ""

def defaults_de_ejercicio(e: dict):
    reps_def = _num_or_empty(e.get("reps_min","")) or _num_or_empty(e.get("repeticiones",""))
    peso_def = _num_or_empty(e.get("peso",""))
    rir_def  = _num_or_empty(e.get("rir",""))
    return reps_def, peso_def, rir_def

# ==========================
#  Racha por SEMANAS completas
# ==========================
def _dias_numericos(rutina_dict: dict) -> list[str]:
    if not isinstance(rutina_dict, dict): return []
    dias = [k for k in rutina_dict.keys() if str(k).isdigit()]
    return sorted(dias, key=lambda x: int(x))

def _doc_por_semana(rutinas_cliente: list[dict], semana: str) -> dict | None:
    return next((r for r in rutinas_cliente if r.get("fecha_lunes")==semana), None)

def _semana_esta_completa(doc: dict) -> bool:
    rutina = (doc.get("rutina") or {})
    dias = _dias_numericos(rutina)
    if not dias:
        return False
    return all(rutina.get(f"{d}_finalizado") is True for d in dias)

def _calcular_racha_dias(rutinas_cliente: list[dict], semana_sel: str) -> int:
    if not rutinas_cliente:
        return 0
    semanas_orden = sorted(
        (r.get("fecha_lunes") for r in rutinas_cliente if r.get("fecha_lunes")),
        reverse=True
    )
    if semana_sel not in semanas_orden:
        return 0
    start_idx = semanas_orden.index(semana_sel)
    racha = 0
    for idx in range(start_idx, len(semanas_orden)):
        semana = semanas_orden[idx]
        doc = _doc_por_semana(rutinas_cliente, semana)
        if not doc:
            break
        if _semana_esta_completa(doc):
            racha += 1
        else:
            break
    return racha

# ==========================
#  Guardado / Reportes
# ==========================
def _match_mismo_ejercicio(a: dict, b: dict) -> bool:
    if not isinstance(a, dict) or not isinstance(b, dict): return False
    return (
        (a.get("ejercicio","") == b.get("ejercicio","")) and
        (a.get("circuito","")  == b.get("circuito",""))  and
        (a.get("bloque", a.get("seccion","")) == b.get("bloque", b.get("seccion","")))
    )

def _parsear_series(series_data: list[dict]):
    pesos, reps, rirs = [], [], []
    for s in (series_data or []):
        try:
            val = str(s.get("peso","")).replace(",","." ).replace("kg","").strip()
            if val != "": pesos.append(float(val))
        except: pass
        try:
            reps_raw = str(s.get("reps","")).strip()
            if reps_raw.isdigit(): reps.append(int(reps_raw))
        except: pass
        try:
            val = str(s.get("rir","")).replace(",","." ).strip()
            if val != "": rirs.append(float(val))
        except: pass
    peso_alcanzado  = max(pesos) if pesos else None
    reps_alcanzadas = max(reps)  if reps  else None
    rir_alcanzado   = min(rirs)  if rirs  else None
    return peso_alcanzado, reps_alcanzadas, rir_alcanzado

def _series_data_con_datos(series_data: list | None) -> bool:
    if not isinstance(series_data, list) or len(series_data) == 0: return False
    for s in series_data:
        if not isinstance(s, dict): continue
        if str(s.get("reps","")).strip() or str(s.get("peso","")).strip() or str(s.get("rir","")).strip():
            return True
    return False

def _tiene_reporte_guardado(ex_guardado: dict) -> bool:
    if not isinstance(ex_guardado, dict): return False
    if _series_data_con_datos(ex_guardado.get("series_data")): return True
    if any(ex_guardado.get(k) not in (None,"",[]) for k in ["peso_alcanzado","reps_alcanzadas","rir_alcanzado"]): return True
    return False

def _preparar_ejercicio_para_guardado(e: dict, correo_actor: str) -> dict:
    try: num_series = int(e.get("series",0))
    except: num_series = 0
    reps_def, peso_def, rir_def = defaults_de_ejercicio(e)
    if "series_data" not in e or not isinstance(e["series_data"], list) or len(e["series_data"]) != num_series:
        e["series_data"] = [{"reps":reps_def, "peso":peso_def, "rir":rir_def} for _ in range(num_series)]
    else:
        for s in e["series_data"]:
            if not str(s.get("reps","")).strip(): s["reps"] = reps_def
            if not str(s.get("peso","")).strip(): s["peso"] = peso_def
            if not str(s.get("rir","")).strip():  s["rir"]  = rir_def
    peso_alc, reps_alc, rir_alc = _parsear_series(e.get("series_data", []))
    if peso_alc is not None: e["peso_alcanzado"] = peso_alc
    if reps_alc is not None: e["reps_alcanzadas"] = reps_alc
    if rir_alc  is not None: e["rir_alcanzado"]  = rir_alc
    hay_input = any([(e.get("comentario","") or "").strip(), peso_alc is not None, reps_alc is not None, rir_alc is not None])
    if hay_input: e["coach_responsable"] = correo_actor
    if "comentario" in e:
        e["comentario"] = str(e.get("comentario", "")).strip()
    if "bloque" not in e: e["bloque"] = e.get("seccion","")
    return e

def _aplicar_delta_en_dia(dia_data, ejercicio_ref, delta, peso_base_ref):
    def _actualizar_ex(ex):
        if not isinstance(ex, dict):
            return False
        if not _match_mismo_ejercicio(ex, ejercicio_ref):
            return False
        peso_actual = _peso_to_float(ex.get("peso"))
        if peso_actual is None:
            return False
        if peso_base_ref is not None and abs(peso_actual - peso_base_ref) > 1e-4:
            return False
        nuevo_peso = max(0.0, peso_actual + delta)
        ex["peso"] = _format_peso_value(nuevo_peso)
        return True

    changed = False

    if isinstance(dia_data, list):
        for ex in dia_data:
            if _actualizar_ex(ex):
                changed = True
    elif isinstance(dia_data, dict):
        ejercicios = None
        if isinstance(dia_data.get("ejercicios"), list):
            ejercicios = dia_data["ejercicios"]
        if ejercicios is not None:
            for ex in ejercicios:
                if _actualizar_ex(ex):
                    changed = True
        else:
            for key, ex in dia_data.items():
                if isinstance(ex, dict) and _actualizar_ex(ex):
                    dia_data[key] = ex
                    changed = True
    return changed

def _propagar_peso_a_futuras_semanas(db, correo_original, bloque_rutina, semana_sel, dia_sel, ejercicio_editado, delta, peso_base_ref):
    if not correo_original or not bloque_rutina:
        return
    if delta is None or abs(delta) < 1e-4:
        return
    dia_sel = str(dia_sel)
    try:
        snaps = list(
            db.collection("rutinas_semanales")
              .where("correo", "==", correo_original)
              .where("bloque_rutina", "==", bloque_rutina)
              .stream()
        )
    except Exception:
        return

    futuros = []
    for snap in snaps:
        data = snap.to_dict() or {}
        fecha = data.get("fecha_lunes")
        if not fecha or fecha <= semana_sel:
            continue
        futuros.append((fecha, snap, data))

    if not futuros:
        return

    futuros.sort(key=lambda tup: tup[0])
    for _, snap, data in futuros:
        rutina = data.get("rutina", {}) or {}
        if dia_sel not in rutina:
            continue
        dia_data = rutina[dia_sel]
        if _aplicar_delta_en_dia(dia_data, ejercicio_editado, delta, peso_base_ref):
            try:
                snap.reference.set({"rutina": {dia_sel: dia_data}}, merge=True)
            except Exception:
                continue

def guardar_reporte_ejercicio(db, correo_cliente_norm, correo_original, semana_sel, dia_sel, ejercicio_editado, bloque_rutina=None):
    fecha_norm = semana_sel.replace("-", "_")
    doc_id = f"{correo_cliente_norm}_{fecha_norm}"
    doc_ref = db.collection("rutinas_semanales").document(doc_id)
    doc = doc_ref.get()
    if not doc.exists:
        doc_ref.set({"rutina": {dia_sel: [ejercicio_editado]}}, merge=True); return True
    rutina = doc.to_dict().get("rutina", {})
    ejercicios_raw = rutina.get(dia_sel, [])
    ejercicios_lista = obtener_lista_ejercicios(ejercicios_raw)
    changed = False
    for i, ex in enumerate(ejercicios_lista):
        if _match_mismo_ejercicio(ex, ejercicio_editado):
            ejercicios_lista[i] = ejercicio_editado; changed = True; break
    if not changed: ejercicios_lista.append(ejercicio_editado)
    doc_ref.set({"rutina": {dia_sel: ejercicios_lista}}, merge=True)

    peso_base_ref = _peso_to_float(ejercicio_editado.get("peso"))
    peso_alcanzado_val = ejercicio_editado.get("peso_alcanzado")
    if peso_alcanzado_val is None:
        peso_alcanzado_val, _, _ = _parsear_series(ejercicio_editado.get("series_data", []))
    if peso_base_ref is not None and peso_alcanzado_val is not None:
        delta = float(peso_alcanzado_val) - float(peso_base_ref)
        if abs(delta) >= 1e-4:
            _propagar_peso_a_futuras_semanas(
                db=db,
                correo_original=correo_original,
                bloque_rutina=bloque_rutina,
                semana_sel=semana_sel,
                dia_sel=dia_sel,
                ejercicio_editado=ejercicio_editado,
                delta=delta,
                peso_base_ref=peso_base_ref,
            )

    return True


def marcar_dia_como_finalizado(db, correo_cliente_norm, semana_sel, dia_sel, correo_actor, rpe_valor=None):
    dia_sel = str(dia_sel)
    fecha_norm = semana_sel.replace("-", "_")
    doc_id = f"{correo_cliente_norm}_{fecha_norm}"
    doc_ref = db.collection("rutinas_semanales").document(doc_id)

    updates = {
        "rutina": {
            f"{dia_sel}_finalizado": True,
            f"{dia_sel}_finalizado_por": correo_actor,
            f"{dia_sel}_finalizado_en": firestore.SERVER_TIMESTAMP,
        }
    }
    if rpe_valor is not None:
        updates["rutina"][f"{dia_sel}_rpe"] = float(rpe_valor)

    try:
        doc_ref.set(updates, merge=True)
    except Exception:
        return False
    return True


def guardar_reportes_del_dia(db, correo_cliente_norm, correo_original, semana_sel, dia_sel, ejercicios, correo_actor, rpe_valor, bloque_rutina=None):
    dia_sel = str(dia_sel)
    fecha_norm = semana_sel.replace("-", "_")
    doc_id = f"{correo_cliente_norm}_{fecha_norm}"
    doc_ref = db.collection("rutinas_semanales").document(doc_id)
    doc = doc_ref.get()
    ejercicios_guardados = []
    if doc.exists:
        rutina = doc.to_dict().get("rutina", {})
        ejercicios_raw = rutina.get(dia_sel, [])
        ejercicios_guardados = obtener_lista_ejercicios(ejercicios_raw)
    def _key_ex(e: dict):
        return ((e.get("bloque") or e.get("seccion") or "").strip().lower(),
                (e.get("circuito") or "").strip().upper(),
                (e.get("ejercicio") or "").strip().lower())
    idx_guardados = {_key_ex(e): e for e in ejercicios_guardados if isinstance(e, dict)}
    for e in ejercicios:
        if not isinstance(e, dict): continue
        key = _key_ex(e)
        ex_prev = idx_guardados.get(key)
        if ex_prev and _tiene_reporte_guardado(ex_prev): continue
        e2 = _preparar_ejercicio_para_guardado(dict(e), correo_actor)
        ok = guardar_reporte_ejercicio(
            db=db,
            correo_cliente_norm=correo_cliente_norm,
            correo_original=correo_original,
            semana_sel=semana_sel,
            dia_sel=dia_sel,
            ejercicio_editado=e2,
            bloque_rutina=bloque_rutina,
        )
        if not ok: return False
    return marcar_dia_como_finalizado(
        db=db,
        correo_cliente_norm=correo_cliente_norm,
        semana_sel=semana_sel,
        dia_sel=dia_sel,
        correo_actor=correo_actor,
        rpe_valor=rpe_valor,
    )

# ==========================
#  PNG Resumen (no se toca)
# ==========================
def generar_tarjeta_resumen_sesion(nombre, dia_indice, ejercicios_workout, focus_tuple, gym_name="Motion Performance") -> plt.Figure:
    total_series = sum(int(e.get("series",0) or 0) for e in ejercicios_workout)
    total_reps   = sum(int(e.get("series",0) or 0)*int(e.get("reps",0) or 0) for e in ejercicios_workout)
    total_peso   = sum(int(e.get("series",0) or 0)*int(e.get("reps",0) or 0)*float(e.get("peso",0) or 0) for e in ejercicios_workout)
    fig, ax = plt.subplots(figsize=(6,8), dpi=200); ax.axis("off")
    ax.text(0.5,0.96,gym_name,ha="center",va="center",fontsize=18,fontweight="bold")
    ax.text(0.5,0.92,"Resumen de Entrenamiento",ha="center",va="center",fontsize=13)
    ax.text(0.5,0.87,f"Día {dia_indice}",ha="center",va="center",fontsize=11)
    y=0.80; ax.text(0.05,y,"Workout",fontsize=12,fontweight="bold"); y-=0.03
    if not ejercicios_workout:
        ax.text(0.07,y,"Sin ejercicios en el circuito D.",fontsize=10,ha="left"); y-=0.04
    else:
        max_lineas=9; mostrados=0
        for e in ejercicios_workout:
            if mostrados>=max_lineas: break
            linea=f"• {e['nombre']} {int(e.get('reps') or 0)}x{int(round(float(e.get('peso') or 0)))}"
            color="green" if e.get("mejoro") else "black"
            ax.text(0.07,y,linea+(" ↑" if e.get("mejoro") else ""),fontsize=10,ha="left",color=color)
            y-=0.03; mostrados+=1
        if len(ejercicios_workout)>max_lineas:
            ax.text(0.07,y,f"+ {len(ejercicios_workout)-max_lineas} ejercicio(s) más…",fontsize=10,ha="left",style="italic"); y-=0.04
    grupo,total=focus_tuple
    y-=0.01; ax.text(0.05,y,"Focus",fontsize=12,fontweight="bold"); y-=0.03
    ax.text(0.07,y,f"Grupo con más series: {grupo} ({total} series)",fontsize=11,ha="left"); y-=0.03
    y-=0.01; ax.text(0.05,y,"Totales",fontsize=12,fontweight="bold"); y-=0.035
    ax.text(0.07,y,f"• Series: {total_series}",fontsize=11,ha="left"); y-=0.028
    ax.text(0.07,y,f"• Repeticiones: {total_reps}",fontsize=11,ha="left"); y-=0.028
    ax.text(0.07,y,f"• Volumen estimado: {total_peso:g} kg",fontsize=11,ha="left"); y-=0.02
    ax.text(0.5,0.08,"¡Gran trabajo!",fontsize=10.5,ha="center",style="italic")
    ax.text(0.5,0.04,"Comparte tu progreso 📸",fontsize=9,ha="center")
    fig.tight_layout(); return fig

# ==========================
#  VISTA
# ==========================
def ver_rutinas():
    # Firebase init
    db = get_db()

    def normalizar_correo(c): return c.strip().lower().replace("@","_").replace(".","_")
    def obtener_fecha_lunes():
        hoy=datetime.now(); lunes=hoy-timedelta(days=hoy.weekday()); return lunes.strftime("%Y-%m-%d")
    def es_entrenador(rol): return rol.lower() in ["entrenador","admin","administrador"]

    @st.cache_data(show_spinner=False)
    def cargar_todas_las_rutinas():
        docs = db.collection("rutinas_semanales").stream()
        return [doc.to_dict() for doc in docs]

    # Usuario
    correo_raw = (st.session_state.get("correo","") or "").strip().lower()
    if not correo_raw: st.error("❌ No hay correo registrado."); st.stop()
    correo_norm = normalizar_correo(correo_raw)
    doc_user = db.collection("usuarios").document(correo_norm).get()
    if not doc_user.exists: st.error(f"❌ No se encontró el usuario '{correo_norm}'."); st.stop()
    datos_usuario = doc_user.to_dict()
    nombre = datos_usuario.get("nombre","Usuario")
    rol = (st.session_state.get("rol") or datos_usuario.get("rol","desconocido")).strip().lower()
    es_staff = rol in {"entrenador", "admin"}

    # Saludo en cabecera
    st.markdown(
        f"<div class='card status-card' style='margin:8px 0; padding:12px;'><b>Bienvenido {nombre.split(' ')[0]}</b></div>",
        unsafe_allow_html=True,
    )

    # Cargar todas y filtrar por cliente según rol
    rutinas_all = cargar_todas_las_rutinas()
    if not rutinas_all: st.warning("⚠️ No se encontraron rutinas."); st.stop()

    qp_values = _current_query_params()
    qp_cliente = qp_values.get("cliente")
    qp_semana = qp_values.get("semana")
    qp_dia = qp_values.get("dia")

    cliente_sel = None
    if es_entrenador(rol):
        rol_lower = rol.strip().lower()

        @st.cache_data(show_spinner=False)
        def _usuarios_por_correo():
            mapping = {}
            try:
                for snap in db.collection("usuarios").stream():
                    if not snap.exists:
                        continue
                    data = snap.to_dict() or {}
                    correo_cli = (data.get("correo") or "").strip().lower()
                    if correo_cli:
                        mapping[correo_cli] = data
                        mapping[normalizar_correo(correo_cli)] = data
            except Exception:
                pass
            return mapping

        usuarios_por_correo = _usuarios_por_correo()
        empresa_entrenador = empresa_de_usuario(correo_raw, usuarios_por_correo)
        es_motion_entrenador = empresa_entrenador == EMPRESA_MOTION
        es_asesoria_entrenador = empresa_entrenador == EMPRESA_ASESORIA

        correos_entrenador = {correo_raw}
        if correo_norm:
            correos_entrenador.add(correo_norm)
        correos_entrenador.add(normalizar_correo(correo_raw))

        def _cliente_autorizado(rutina_doc: dict) -> bool:
            if rol_lower != "entrenador":
                return True

            correo_cliente = (rutina_doc.get("correo") or "").strip().lower()
            datos_cli = usuarios_por_correo.get(correo_cliente) or usuarios_por_correo.get(normalizar_correo(correo_cliente))
            responsable = (datos_cli.get("coach_responsable") or "").strip().lower() if datos_cli else ""
            entrenador_reg = (rutina_doc.get("entrenador") or "").strip().lower()
            entrenador_reg_norm = normalizar_correo(rutina_doc.get("entrenador") or "")
            empresa_cli = empresa_de_usuario(correo_cliente, usuarios_por_correo) if correo_cliente else ""

            if es_asesoria_entrenador:
                return responsable == correo_raw

            if es_motion_entrenador:
                if entrenador_reg in correos_entrenador or entrenador_reg_norm in correos_entrenador:
                    return True
                if correo_cliente and empresa_cli in {EMPRESA_MOTION, EMPRESA_DESCONOCIDA}:
                    return True
                if responsable and responsable == correo_raw:
                    return True
                return False

            if responsable and responsable == correo_raw:
                return True
            if entrenador_reg and entrenador_reg in correos_entrenador:
                return True
            if entrenador_reg_norm in correos_entrenador:
                return True
            return False

        clientes_empresa_info: dict[str, set[str]] = {}
        for r in rutinas_all:
            nombre_cli = (r.get("cliente") or "").strip()
            if not nombre_cli:
                continue
            correo_cli = (r.get("correo") or "").strip().lower()
            permitido = _cliente_autorizado(r)
            if rol_lower == "entrenador":
                if es_asesoria_entrenador:
                    permitido = permitido and ((usuarios_por_correo.get(correo_cli) or {}).get("coach_responsable", "").strip().lower() == correo_raw)
                elif es_motion_entrenador:
                    empresa_cli = empresa_de_usuario(correo_cli, usuarios_por_correo) if correo_cli else ""
                    permitido = permitido or (
                        correo_cli
                        and empresa_cli in {EMPRESA_MOTION, EMPRESA_DESCONOCIDA}
                    )
            if permitido:
                clientes_empresa_info.setdefault(nombre_cli, set())
                if correo_cli:
                    clientes_empresa_info[nombre_cli].add(correo_cli)
                else:
                    clientes_empresa_info[nombre_cli].add("__no_email__")

        if rol_lower == "entrenador":
            if es_asesoria_entrenador:
                clientes_tarjetas = []
                for r in rutinas_all:
                    nombre_cli = (r.get("cliente") or "").strip()
                    if not nombre_cli:
                        continue
                    correo_cli = (r.get("correo") or "").strip().lower()
                    datos_cli = usuarios_por_correo.get(correo_cli) or usuarios_por_correo.get(normalizar_correo(correo_cli)) or {}
                    coach_resp_cli = (datos_cli.get("coach_responsable") or "").strip().lower()
                    if coach_resp_cli == correo_raw:
                        clientes_tarjetas.append(nombre_cli)
                clientes_tarjetas = sorted(set(clientes_tarjetas))
            else:
                clientes_tarjetas = []
                for r in rutinas_all:
                    nombre_cli = (r.get("cliente") or "").strip()
                    if not nombre_cli:
                        continue
                    entrenador_reg = (r.get("entrenador") or "").strip().lower()
                    entrenador_reg_norm = normalizar_correo(r.get("entrenador") or "")
                    correo_cli = (r.get("correo") or "").strip().lower()
                    datos_cli = usuarios_por_correo.get(correo_cli) or usuarios_por_correo.get(normalizar_correo(correo_cli)) or {}
                    coach_resp_cli = (datos_cli.get("coach_responsable") or "").strip().lower()
                    empresa_cli = empresa_de_usuario(correo_cli, usuarios_por_correo) if correo_cli else ""
                    if es_motion_entrenador:
                        if (
                            entrenador_reg in correos_entrenador
                            or entrenador_reg_norm in correos_entrenador
                            or coach_resp_cli == correo_raw
                            or empresa_cli in {EMPRESA_MOTION, EMPRESA_DESCONOCIDA}
                        ):
                            clientes_tarjetas.append(nombre_cli)
                    else:
                        if (
                            entrenador_reg in correos_entrenador
                            or entrenador_reg_norm in correos_entrenador
                            or coach_resp_cli == correo_raw
                        ):
                            clientes_tarjetas.append(nombre_cli)
                clientes_tarjetas = sorted(set(clientes_tarjetas))
        else:
            clientes_tarjetas = sorted(clientes_empresa_info.keys())

        if not clientes_empresa_info:
            st.info("No hay clientes registrados aún."); st.stop()

        busqueda = st.text_input("Busca deportista", key="cliente_input", placeholder="Escribe un nombre…")
        busqueda_lower = busqueda.lower()
        clientes_asignados = clientes_tarjetas

        base_lista = clientes_tarjetas if clientes_tarjetas else sorted(clientes_empresa_info.keys())

        if busqueda_lower:
            candidatos = [
                nombre_cli
                for nombre_cli, correos_cli in clientes_empresa_info.items()
                if busqueda_lower in nombre_cli.lower() or any(busqueda_lower in c for c in correos_cli)
            ]
        else:
            candidatos = base_lista

        if "_mostrar_lista_clientes" not in st.session_state:
            st.session_state["_mostrar_lista_clientes"] = True

        if st.session_state.get("_cliente_sel") not in clientes_empresa_info:
            st.session_state.pop("_cliente_sel", None)
            st.session_state["_mostrar_lista_clientes"] = True

        if busqueda:
            st.session_state["_mostrar_lista_clientes"] = True

        if not st.session_state.get("_cliente_sel") and qp_cliente and qp_cliente in clientes_empresa_info:
            st.session_state["_cliente_sel"] = qp_cliente
            st.session_state["_mostrar_lista_clientes"] = False

        mostrar_lista = st.session_state.get("_mostrar_lista_clientes", True)
        cliente_sel = st.session_state.get("_cliente_sel")

        if mostrar_lista or not cliente_sel:
            if not candidatos:
                mensaje_sin_resultados = (
                    "No tienes deportistas asignados. Usa la búsqueda para consultar otros." if (not clientes_asignados and not busqueda_lower)
                    else "No se encontraron coincidencias para esa búsqueda."
                )
                st.info(mensaje_sin_resultados)
            else:
                grid_cols = st.columns(min(3, len(candidatos)))
                for idx, cliente_nombre in enumerate(candidatos):
                    col = grid_cols[idx % len(grid_cols)]
                    with col:
                        activo = cliente_nombre == cliente_sel
                        estilo = "border: 1.5px solid var(--primary);" if activo else "border: 1px solid var(--stroke);"
                        st.markdown(
                            f"""
                            <div class='card' style='{estilo} padding:14px; display:flex; flex-direction:column; gap:6px;'>
                              <div style='font-weight:700; font-size:1.05rem;'>{cliente_nombre}</div>
                            </div>
                            """,
                            unsafe_allow_html=True,
                        )
                        if st.button("Ver rutina", key=f"cliente_card_{cliente_nombre}", use_container_width=True, type="secondary"):
                            st.session_state["_cliente_sel"] = cliente_nombre
                            st.session_state["_mostrar_lista_clientes"] = False
                            st.session_state.pop("semana_sel", None)
                            st.session_state.pop("dia_sel", None)
                            _sync_rutinas_query_params(cliente_nombre)
                            st.rerun()
        else:
            if rol in ("entrenador", "admin", "administrador"):
                st.markdown(
                    f"""
                    <div class='client-sticky'>
                      <div class='client-sticky__label'>Deportista seleccionado</div>
                      <div class='client-sticky__value'>
                        {cliente_sel}
                        <span class='client-sticky__badge'>Rutina activa</span>
                      </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f"""
                    <div class='card' style='border: 1.5px solid var(--primary); padding:14px; display:flex; flex-direction:column; gap:6px;'>
                      <div style='font-weight:700; font-size:1.05rem;'>{cliente_sel}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            if st.button("Cambiar deportista", key="volver_lista_clientes", type="secondary", use_container_width=True):
                st.session_state["_mostrar_lista_clientes"] = True
                st.session_state.pop("dia_sel", None)
                _sync_rutinas_query_params()
                st.rerun()

        cliente_sel = st.session_state.get("_cliente_sel")
        if not cliente_sel:
            st.info("Selecciona un deportista y haz clic en \"Ver rutina\" para cargar su rutina.")
            st.stop()

        correos_permitidos = clientes_empresa_info.get(cliente_sel, set())
        rutinas_cliente = [
            r for r in rutinas_all
            if r.get("cliente") == cliente_sel
            and (
                not correos_permitidos
                or "__no_email__" in correos_permitidos
                or (r.get("correo") or "").strip().lower() in correos_permitidos
            )
        ]
    else:
        rutinas_cliente = [r for r in rutinas_all if (r.get("correo","") or "").strip().lower()==correo_raw]
        cliente_sel = nombre

    if not rutinas_cliente:
        st.warning("⚠️ No se encontraron rutinas para ese cliente.")
        st.stop()

    # --- Antes de construir el selectbox de Semana, lee los query params ---
    seeded_from_qs = False

    # Semana (desde rutinas_cliente)
    semanas = sorted({r["fecha_lunes"] for r in rutinas_cliente if r.get("fecha_lunes")}, reverse=True)
    semana_actual = obtener_fecha_lunes()

    # Si viene por URL, úsala; si no, usa lo previamente seleccionado, o la actual
    pre_semana = qp_semana or st.session_state.get("semana_sel")
    if pre_semana not in semanas:
        pre_semana = semana_actual if semana_actual in semanas else (semanas[0] if semanas else None)

    index_semana = semanas.index(pre_semana) if pre_semana in semanas else 0
    # ── Barra superior: mensaje + semana + refrescar ─────────────────────────────
    motivacional_msg = mensaje_motivador_del_dia(nombre, correo_norm) if not es_staff else None
    status_card = st.container()
    with status_card:
        st.markdown("<div class='planner-card'>", unsafe_allow_html=True)
        planner_cols = st.columns([3, 2], gap="large")
        left_summary = planner_cols[0].empty()
        with planner_cols[1]:
            st.markdown("<span class='planner-card__label'>Semana</span>", unsafe_allow_html=True)
            semana_sel = st.selectbox(
                "Semana",
                semanas,
                index=index_semana,
                key="semana_sel",
                label_visibility="collapsed",
            )
            planner_actions = st.container()
        st.markdown("</div>", unsafe_allow_html=True)

    try:
        week_start = datetime.strptime(semana_sel, "%Y-%m-%d").date()
        week_end = week_start + timedelta(days=6)
        rango_texto = f"{week_start.strftime('%d %b')} – {week_end.strftime('%d %b %Y')}"
    except Exception:
        rango_texto = "Semana sin rango definido"

    # Si venimos por query param la primera vez, SEMBRAMOS el día y marcamos bandera
    if qp_semana and qp_dia and "dia_sel" not in st.session_state:
        st.session_state["dia_sel"] = str(qp_dia)
        seeded_from_qs = True

    # Reset día solo si el usuario CAMBIA la semana manualmente (no al seed inicial)
    _prev = st.session_state.get("_prev_semana_sel")
    if _prev != semana_sel:
        st.session_state["_prev_semana_sel"] = semana_sel
        if not seeded_from_qs:  # ← evita borrar el día que vino desde Inicio / URL
            st.session_state.pop("dia_sel", None)

    # Documento de rutina (cliente + semana)
    if es_entrenador(rol):
        rutina_doc = next((r for r in rutinas_cliente if r.get("fecha_lunes")==semana_sel and r.get("cliente")==cliente_sel), None)
    else:
        rutina_doc = next((r for r in rutinas_cliente if r.get("fecha_lunes")==semana_sel), None)

    if not rutina_doc:
        st.warning("⚠️ No hay rutina para esa semana y cliente.")
        st.stop()

    # Banner motivacional (solo deportista) con racha de SEMANAS
    if rol == "deportista":
        racha_actual = _calcular_racha_dias(rutinas_cliente, semana_sel)
        extra = (
            f"Llevas {racha_actual} semana{'s' if racha_actual!=1 else ''} seguidas COMPLETAS. ¡No rompas la cadena! 🔥"
            if racha_actual > 0 else None
        )
        if extra: st.caption(f"🔥 {extra}")

    rutina_semana = rutina_doc.get("rutina", {}) or {}
    dias_dash = _dias_numericos(rutina_semana)
    sesiones_completadas = sum(1 for d in dias_dash if rutina_semana.get(f"{d}_finalizado") is True)
    total_sesiones = len(dias_dash)

    bloque_id = rutina_doc.get("bloque_rutina")
    bloque_meta = "Sin identificador"
    if bloque_id:
        mismas = [r for r in rutinas_cliente if r.get("bloque_rutina")==bloque_id]
        fechas_bloque = sorted([r["fecha_lunes"] for r in mismas if r.get("fecha_lunes")])
        try:
            semana_actual_idx = fechas_bloque.index(semana_sel)+1
            total_semanas_bloque = len(fechas_bloque)
            bloque_meta = f"Semana {semana_actual_idx} de {total_semanas_bloque}"
        except ValueError:
            bloque_meta = "Sin identificador"

    sesiones_texto = (
        f"{sesiones_completadas}/{total_sesiones} sesiones completadas"
        if total_sesiones else "Sin sesiones registradas"
    )

    dia_actual = st.session_state.get("dia_sel") or (str(qp_dia) if qp_dia else None)

    left_blocks = ["<div class='planner-card__body'>"]
    if motivacional_msg:
        left_blocks.append(f"<div class='planner-card__motivation'>{motivacional_msg}</div>")
    left_blocks.append(f"<div class='planner-card__meta'>Bloque de rutina · {bloque_meta}</div>")
    left_blocks.append(f"<div class='planner-card__meta muted'>{sesiones_texto}</div>")
    if dia_actual:
        left_blocks.append(f"<div class='planner-card__badge is-active'>Día {dia_actual}</div>")
    else:
        left_blocks.append("<div class='planner-card__note'>Selecciona un día para revisar la sesión detallada.</div>")
    left_blocks.append("</div>")
    left_summary.markdown("".join(left_blocks), unsafe_allow_html=True)

    with planner_actions:
        if dia_actual:
            st.markdown("<div style='display:flex; justify-content:flex-end;'>", unsafe_allow_html=True)
            if st.button("Cambiar día", key=f"cambiar_{semana_sel}_{dia_actual}", type="secondary"):
                st.session_state.pop("dia_sel", None)
                _sync_rutinas_query_params(cliente_sel, semana_sel)
                st.rerun()
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown("<div class='planner-card__note'>Selecciona un día en las tarjetas inferiores para ver la rutina.</div>", unsafe_allow_html=True)

    # Aún no hay día seleccionado → mostrar progreso + tarjetas
    if not dia_actual:
        if dias_dash:
            progreso_valor = sesiones_completadas/len(dias_dash)
            progreso_texto = None if es_staff else f"{sesiones_completadas}/{len(dias_dash)} sesiones completadas"

            if progreso_texto is not None:
                st.progress(progreso_valor, text=progreso_texto)
            else:
                st.progress(progreso_valor)

            st.markdown(
                "<p class='days-subtitle'>Elige un día para revisar la rutina detallada.</p>",
                unsafe_allow_html=True,
            )

            cols = st.columns(len(dias_dash), gap="medium")
            for i, dia in enumerate(dias_dash):
                finalizado = bool(rutina_doc["rutina"].get(f"{dia}_finalizado") is True)
                estado_texto = "Completado" if finalizado else "Pendiente"
                btn_label = f"{'✅' if finalizado else '⚡'} Día {dia}\n{estado_texto}"
                btn_key   = f"daybtn_{semana_sel}_{cliente_sel}_{dia}"
                with cols[i]:
                    if st.button(btn_label, key=btn_key, type=("secondary" if finalizado else "primary"),
                                use_container_width=True, help=f"Ver rutina del día {dia}"):
                        st.session_state["dia_sel"] = str(dia)
                        # sincroniza la URL para persistencia (sobrevive reload/bloqueo)
                        _sync_rutinas_query_params(cliente_sel, semana_sel, str(dia))
                        st.rerun()


    st.markdown("<div class='hr-light'></div>", unsafe_allow_html=True)

    # Mostrar rutina solo cuando haya día seleccionado
    dia_sel = st.session_state.get("dia_sel")
    # Si llegó por URL (Inicio) y aún no hay día en session_state, siembra desde query param
    if not dia_sel and qp_dia:
        dia_sel = str(qp_dia)
        st.session_state["dia_sel"] = dia_sel

    _sync_rutinas_query_params(cliente_sel, semana_sel, dia_sel)

    if not dia_sel:
        st.info("Selecciona un día en las tarjetas superiores para ver tu rutina.")
        st.stop()
    # Checkbox global de Sesión anterior
    mostrar_prev = st.checkbox(
        "📅 Mostrar sesión anterior",
        value=False,
        help="Muestra reps/peso/RIR de la semana anterior (si existen coincidencias por ejercicio)."
    )

    # Mapa de sesión previa
    ejercicios_prev_map = {}
    if mostrar_prev:
        semana_prev = (datetime.strptime(semana_sel, "%Y-%m-%d") - timedelta(days=7)).strftime("%Y-%m-%d")
        rutina_prev_doc = next((r for r in rutinas_cliente if r.get("fecha_lunes")==semana_prev), None)
        if rutina_prev_doc and str(dia_sel) in (rutina_prev_doc.get("rutina", {}) or {}):
            ejercicios_prev = obtener_lista_ejercicios(rutina_prev_doc["rutina"][str(dia_sel)])
            for ex in ejercicios_prev:
                key_prev = ((ex.get("bloque") or ex.get("seccion") or "").strip().lower(),
                            (ex.get("circuito") or "").strip().upper(),
                            (ex.get("ejercicio") or "").strip().lower())
                ejercicios_prev_map[key_prev] = ex

    # Ejercicios del día
    st.markdown(f"<h3 class='h-accent'>Ejercicios del día {dia_sel}</h3>", unsafe_allow_html=True)
    ejercicios = obtener_lista_ejercicios(rutina_doc["rutina"][dia_sel])
    ejercicios.sort(key=ordenar_circuito)

    ejercicios_por_circuito = {}
    for e in ejercicios:
        circuito = (e.get("circuito","Z") or "Z").upper()
        ejercicios_por_circuito.setdefault(circuito, []).append(e)

    for circuito, lista in sorted(ejercicios_por_circuito.items()):
        titulo = "Warm-Up" if circuito=="A" else ("Workout" if circuito=="D" else f"Circuito {circuito}")
        st.markdown(f"<h4 class='h-accent'>{titulo}</h4>", unsafe_allow_html=True)

        # === Render de ejercicios (nombre como botón si hay video; 'detalle' puede traer link) ===
        for idx, e in enumerate(lista):
            nombre    = e.get("ejercicio", f"Ejercicio {idx+1}")
            peso      = e.get("peso","")
            tiempo    = e.get("tiempo","")
            velocidad = e.get("velocidad","")

            # 1) Video (puede venir en e['video'] o dentro de 'detalle' como link)
            video_url, detalle_visible = _video_y_detalle_desde_ejercicio(e)

            # 2) Línea secundaria: reps/peso/tiempo/descanso/velocidad/RIR
            partes = [f"{_repstr(e)}"]
            if peso:      partes.append(f"{peso} kg")
            if tiempo:    partes.append(f"{tiempo} seg")
            if velocidad: partes.append(f"{velocidad} m/s")
            dsc = _descanso_texto(e)
            if dsc:       partes.append(f"{dsc}")

            rir_text = _rirstr(e)           # ← usa la nueva función
            if rir_text:
                partes.append(f"RIR {rir_text}")

            info_str = " · ".join(partes)

            # 3) Contenedor visual
            st.markdown("<div style='margin:12px 0;'>", unsafe_allow_html=True)

            # 3.a) Título (si hay video -> el nombre es botón; si no -> texto)
            video_btn_key = f"video_btn_{cliente_sel}_{semana_sel}_{circuito}_{idx}"
            mostrar_video_key = f"mostrar_video_{cliente_sel}_{semana_sel}_{circuito}_{idx}"

            if video_url:
                titulo_btn = nombre if not detalle_visible else f"{nombre} — {detalle_visible}"
                btn_clicked = st.button(
                    titulo_btn,
                    key=video_btn_key,
                    type="primary",
                    help="Click para mostrar/ocultar video",
                )
                if btn_clicked:
                    st.session_state[mostrar_video_key] = not st.session_state.get(mostrar_video_key, False)
            else:
                titulo_linea = nombre + (f" — {detalle_visible}" if detalle_visible else "")
                st.markdown(
                    f"<div style='font-weight:800;font-size:1.05rem;color:var(--text-main);'>{titulo_linea}</div>",
                    unsafe_allow_html=True
                )

            # 3.b) Línea de detalles (incluye ahora también el RIR)
            st.markdown(f"<div class='muted' style='margin-top:2px;'>{info_str}</div>", unsafe_allow_html=True)

            comentario_cliente = (e.get("comentario", "") or "").strip()
            if comentario_cliente:
                st.markdown(
                    f"<div style='margin-top:6px; padding:10px 12px; border-left:3px solid var(--primary); background:rgba(15,23,42,0.35); border-radius:8px;'>"
                    f"<div style='font-size:0.85rem; color:var(--muted); text-transform:uppercase; letter-spacing:0.08em;'>Comentario del deportista</div>"
                    f"<div style='font-size:0.96rem; color:var(--text-main); margin-top:4px;'>{html.escape(comentario_cliente)}</div>"
                    f"</div>",
                    unsafe_allow_html=True,
                )

            # 3.c) Mostrar video embebido si está activo
            if video_url and st.session_state.get(mostrar_video_key, False):
                url = video_url
                if "youtube.com/shorts/" in url:
                    try:
                        video_id = url.split("shorts/")[1].split("?")[0]
                        url = f"https://www.youtube.com/watch?v={video_id}"
                    except:
                        pass
                st.video(url)

            st.markdown("</div>", unsafe_allow_html=True)

            # 4) Sesión anterior (misma lógica de siempre)
            if mostrar_prev:
                key_prev = ((e.get("bloque") or e.get("seccion") or "").strip().lower(),
                            (e.get("circuito") or "").strip().upper(),
                            (e.get("ejercicio") or "").strip().lower())
                ex_prev = ejercicios_prev_map.get(key_prev)
                if ex_prev:
                    peso_alc, reps_alc, rir_alc = _parsear_series(ex_prev.get("series_data", []))
                    peso_prev = peso_alc if peso_alc is not None else ex_prev.get("peso_alcanzado","")
                    reps_prev = reps_alc if reps_alc is not None else ex_prev.get("reps_alcanzadas","")
                    rir_prev  = rir_alc  if rir_alc  is not None else ex_prev.get("rir_alcanzado","")
                    info_prev=[]
                    if reps_prev not in ("",None): info_prev.append(f"Reps: {reps_prev}")
                    if peso_prev not in ("",None): info_prev.append(f"Peso: {peso_prev}")
                    if rir_prev  not in ("",None): info_prev.append(f"RIR: {rir_prev}")
                    st.caption(" | ".join(info_prev) if info_prev else "Sin datos guardados.")
                else:
                    st.caption("Sin coincidencias para este ejercicio.")

        # ==========================
        #  🔁 BOTÓN "📝 Reporte {circuito}" (REINTEGRADO)
        # ==========================
        # Alineado a la izquierda con columnas
        rc_cols = st.columns([1, 6])
        with rc_cols[0]:
            toggle_key = f"mostrar_reporte_{cliente_sel}_{semana_sel}_{circuito}"
            if toggle_key not in st.session_state:
                st.session_state[toggle_key] = False
            if st.button(f"📝 Reporte {circuito}", key=f"btn_reporte_{cliente_sel}_{semana_sel}_{circuito}", type="secondary"):
                st.session_state[toggle_key] = not st.session_state[toggle_key]

        if st.session_state.get(toggle_key, False):
            st.markdown(f"### 📋 Registro del circuito {circuito}")
            for idx, e in enumerate(lista):
                ejercicio_nombre = e.get("ejercicio", f"Ejercicio {idx+1}")
                ejercicio_id = f"{cliente_sel}_{semana_sel}_{circuito}_{ejercicio_nombre}_{idx}".lower()
                st.markdown(f"#### {ejercicio_nombre}")

                # Inicializa/asegura series_data con defaults
                try:
                    num_series = int(e.get("series", 0))
                except:
                    num_series = 0

                reps_def, peso_def, rir_def = defaults_de_ejercicio(e)
                if "series_data" not in e or not isinstance(e["series_data"], list) or len(e["series_data"]) != num_series:
                    e["series_data"] = [{"reps": reps_def, "peso": peso_def, "rir": rir_def} for _ in range(num_series)]
                else:
                    for s in e["series_data"]:
                        if not str(s.get("reps", "")).strip():
                            s["reps"] = reps_def
                        if not str(s.get("peso", "")).strip():
                            s["peso"] = peso_def
                        if not str(s.get("rir", "")).strip():
                            s["rir"] = rir_def

                # Inputs por serie
                for s_idx in range(num_series):
                    st.markdown(f"**Serie {s_idx + 1}**")
                    s_cols = st.columns(3)
                    e["series_data"][s_idx]["reps"] = s_cols[0].text_input(
                        "Reps", value=e["series_data"][s_idx].get("reps", ""),
                        placeholder="Reps", key=f"rep_{ejercicio_id}_{s_idx}", label_visibility="collapsed"
                    )
                    e["series_data"][s_idx]["peso"] = s_cols[1].text_input(
                        "Peso", value=e["series_data"][s_idx].get("peso", ""),
                        placeholder="Kg", key=f"peso_{ejercicio_id}_{s_idx}", label_visibility="collapsed"
                    )
                    e["series_data"][s_idx]["rir"] = s_cols[2].text_input(
                        "RIR", value=e["series_data"][s_idx].get("rir", ""),
                        placeholder="RIR", key=f"rir_{ejercicio_id}_{s_idx}", label_visibility="collapsed"
                    )

                # Comentario general
                e["comentario"] = st.text_input(
                    "Comentario general", value=e.get("comentario", ""),
                    placeholder="Comentario", key=f"coment_{ejercicio_id}"
                )

                # Guardar SOLO este ejercicio
                btn_guardar_key = f"guardar_reporte_{ejercicio_id}"
                if st.button("💾 Guardar este reporte", key=btn_guardar_key):
                    with st.spinner("Guardando reporte del ejercicio..."):
                        peso_alc, reps_alc, rir_alc = _parsear_series(e.get("series_data", []))
                        if peso_alc is not None: e["peso_alcanzado"] = peso_alc
                        if reps_alc is not None: e["reps_alcanzadas"] = reps_alc
                        if rir_alc  is not None: e["rir_alcanzado"]  = rir_alc

                        tiene_metricas = any([
                            peso_alc is not None,
                            reps_alc is not None,
                            rir_alc  is not None,
                        ])

                        hay_input = any([
                            (e.get("comentario", "") or "").strip(),
                            peso_alc is not None,
                            reps_alc is not None,
                            rir_alc  is not None
                        ])
                        if hay_input:
                            e["coach_responsable"] = st.session_state.get("correo","")

                        if "bloque" not in e:
                            e["bloque"] = e.get("seccion", "")

                        ok = guardar_reporte_ejercicio(
                            db=db,
                            correo_cliente_norm=normalizar_correo(rutina_doc.get("correo","")),
                            correo_original=rutina_doc.get("correo",""),
                            semana_sel=semana_sel,
                            dia_sel=str(dia_sel),
                            ejercicio_editado=e,
                            bloque_rutina=rutina_doc.get("bloque_rutina"),
                        )
                        if ok:
                            if tiene_metricas:
                                marcar_dia_como_finalizado(
                                    db=db,
                                    correo_cliente_norm=normalizar_correo(rutina_doc.get("correo","")),
                                    semana_sel=semana_sel,
                                    dia_sel=str(dia_sel),
                                    correo_actor=st.session_state.get("correo", ""),
                                    rpe_valor=None,
                                )
                            st.success("✅ Reporte guardado.")
                            st.cache_data.clear()
                            st.rerun()
                        else:
                            st.error("❌ No se pudo guardar el reporte.")

    # RPE + CTA
    st.markdown("<div class='hr-light'></div>", unsafe_allow_html=True)
    valor_rpe_inicial = rutina_doc["rutina"].get(str(dia_sel) + "_rpe","")
    rpe_valor = st.slider("RPE del día", 0.0, 10.0,
                          value=float(valor_rpe_inicial) if valor_rpe_inicial!="" else 0.0,
                          step=0.5, key=f"rpe_{semana_sel}_{dia_sel}")
    st.markdown("""
    <div style="height:6px;border-radius:999px;background:
    linear-gradient(90deg,#00C2FF 0%,#22C55E 40%,#F59E0B 75%,#EF4444 100%); margin-top:-8px;"></div>
    """, unsafe_allow_html=True)

    with st.container():
        st.markdown("<div class='sticky-cta'></div>", unsafe_allow_html=True)
        cols = st.columns([3,2])
        with cols[0]: st.caption("Cuando termines, registra tu sesión")
        with cols[1]:
            if st.button("✅ Finalizar día", key=f"finalizar_{cliente_sel}_{semana_sel}_{dia_sel}",
                         type="primary", use_container_width=True):
                with st.spinner("Guardando reportes (solo faltantes) y marcando el día como realizado..."):
                    try:
                        ok_all = guardar_reportes_del_dia(
                            db=db,
                            correo_cliente_norm=normalizar_correo(rutina_doc.get("correo","")),
                            correo_original=rutina_doc.get("correo",""),
                            semana_sel=semana_sel,
                            dia_sel=str(dia_sel),
                            ejercicios=ejercicios,
                            correo_actor=st.session_state.get("correo",""),
                            rpe_valor=rpe_valor,
                            bloque_rutina=rutina_doc.get("bloque_rutina"),
                        )
                        if ok_all:
                            st.cache_data.clear()
                            st.success("✅ Día finalizado y registrado correctamente. ¡Gran trabajo! 💪")
                            time.sleep(2.5)  
                            st.rerun()
                        else:
                            st.error("❌ No se pudieron guardar todos los reportes del día.")
                    except Exception as e:
                        st.error("❌ Error durante el guardado masivo del día.")
                        st.exception(e)

# Run
if __name__ == "__main__":
    ver_rutinas()
