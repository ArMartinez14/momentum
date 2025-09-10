# ver_rutinas.py — UI modernizada + filtro correcto por cliente + checkbox "Sesión anterior" + Reporte por circuito (reintegrado)
from __future__ import annotations

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
from datetime import datetime, timedelta, date
import json, random, re
from io import BytesIO
import matplotlib.pyplot as plt
import time
from soft_login_full import soft_login_barrier
soft_login_full = soft_login_barrier(required_roles=["entrenador", "deportista", "admin"])

# ==========================
#  PALETA / ESTILOS con soporte claro/oscuro
# ==========================
import streamlit as st

# Paleta modo oscuro (la tuya actual, con terracota)
DARK = dict(
    PRIMARY   ="#00C2FF",
    SUCCESS   ="#22C55E",
    WARNING   ="#F59E0B",
    DANGER    ="#E2725B",   # ← rojo terracota
    BG        ="#0B0F14",
    SURFACE   ="#121821",
    TEXT_MAIN ="#FFFFFF",
    TEXT_MUTED="#94A3B8",
    STROKE    ="rgba(255,255,255,.08)",
)

# Paleta modo claro (también con terracota)
LIGHT = dict(
    PRIMARY   ="#0077FF",
    SUCCESS   ="#16A34A",
    WARNING   ="#D97706",
    DANGER    ="#E2725B",   # ← rojo terracota
    BG        ="#FFFFFF",
    SURFACE   ="#F8FAFC",   
    TEXT_MAIN ="#0F172A",   
    TEXT_MUTED="#475569",   
    STROKE    ="rgba(2,6,23,.08)",  
)


with st.sidebar:
    theme_mode = st.selectbox(
        "🎨 Tema", ["Auto", "Oscuro", "Claro"],
        key="theme_mode_vista_rutinas",  # 👈 otra clave única
        help="‘Auto’ sigue el modo del sistema; ‘Oscuro/Claro’ fuerzan los colores."
    )

def _vars_block(p):
    return f"""
    --primary:{p['PRIMARY']}; --success:{p['SUCCESS']}; --warning:{p['WARNING']}; --danger:{p['DANGER']};
    --bg:{p['BG']}; --surface:{p['SURFACE']}; --muted:{p['TEXT_MUTED']}; --stroke:{p['STROKE']};
    --text-main:{p['TEXT_MAIN']};
    """

# CSS: define ambas paletas + sobrescritura según sistema + override manual
_css = f"""
<style>
/* Defaults (usaremos LIGHT por accesibilidad si no hay media query) */
:root {{ {_vars_block(LIGHT)} }}

/* Modo oscuro automático por preferencia del sistema */
@media (prefers-color-scheme: dark) {{
  :root {{ {_vars_block(DARK)} }}
}}

/* Estilos base que usan variables */
html,body,[data-testid="stAppViewContainer"]{{ background:var(--bg)!important; color:var(--text-main)!important; }}
h1,h2,h3,h4, label, p, span, div{{ color:var(--text-main); }}
.muted {{ color:var(--muted); font-size:12px; }}
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
/* Sticky CTA */
.sticky-cta {{ position:sticky; bottom:0; z-index:10; padding-top:8px;
  background:linear-gradient(180deg, rgba(0,0,0,0), rgba(0,0,0,.06)); backdrop-filter: blur(6px); }}
</style>
"""

# Override manual si el usuario lo fuerza
if theme_mode == "Oscuro":
    _css += f"<style>:root{{ {_vars_block(DARK)} }}</style>"
elif theme_mode == "Claro":
    _css += f"<style>:root{{ {_vars_block(LIGHT)} }}</style>"

st.markdown(_css, unsafe_allow_html=True)

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
    if "bloque" not in e: e["bloque"] = e.get("seccion","")
    return e

def guardar_reporte_ejercicio(db, correo_cliente_norm, semana_sel, dia_sel, ejercicio_editado):
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
    doc_ref.set({"rutina": {dia_sel: ejercicios_lista}}, merge=True); return True

def guardar_reportes_del_dia(db, correo_cliente_norm, semana_sel, dia_sel, ejercicios, correo_actor, rpe_valor):
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
        ok = guardar_reporte_ejercicio(db=db, correo_cliente_norm=correo_cliente_norm,
                                       semana_sel=semana_sel, dia_sel=dia_sel, ejercicio_editado=e2)
        if not ok: return False
    updates = {"rutina": {f"{dia_sel}_finalizado": True,
                          f"{dia_sel}_finalizado_por": correo_actor,
                          f"{dia_sel}_finalizado_en": firestore.SERVER_TIMESTAMP}}
    if rpe_valor is not None:
        updates["rutina"][f"{dia_sel}_rpe"] = float(rpe_valor)
    doc_ref.set(updates, merge=True); return True

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
    if not firebase_admin._apps:
        cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    db = firestore.client()

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

    # Sidebar saludo
    with st.sidebar:
        st.markdown(f"<div class='card'><b>Bienvenido {nombre.split(' ')[0]}</b></div>", unsafe_allow_html=True)

    # Cargar todas y filtrar por cliente según rol
    rutinas_all = cargar_todas_las_rutinas()
    if not rutinas_all: st.warning("⚠️ No se encontraron rutinas."); st.stop()

    cliente_sel = None
    if es_entrenador(rol):
        clientes = sorted({r.get("cliente","") for r in rutinas_all if r.get("cliente")})
        prev_cliente = st.session_state.get("_cliente_sel")
        # Botón pequeño alineado a la derecha (actualizar lista)
        col_void, col_btn = st.columns([6, 1], gap="small")
        with col_btn:
            if st.button("🔄", key="refresh_clientes", type="secondary", help="Actualizar rutina"):
                st.cache_data.clear()
                st.rerun()

        cliente_input = st.text_input("👤 Escribe el nombre del cliente:", key="cliente_input")
        candidatos = [c for c in clientes if cliente_input.lower() in c.lower()] or clientes
        cliente_sel = st.selectbox("Selecciona cliente:", candidatos, key="cliente_sel_ui")
        if prev_cliente != cliente_sel:
            st.session_state["_cliente_sel"] = cliente_sel
            st.session_state.pop("semana_sel", None)
            st.session_state.pop("dia_sel", None)
        rutinas_cliente = [r for r in rutinas_all if r.get("cliente")==cliente_sel]
    else:
        rutinas_cliente = [r for r in rutinas_all if (r.get("correo","") or "").strip().lower()==correo_raw]
        cliente_sel = nombre

    if not rutinas_cliente:
        st.warning("⚠️ No se encontraron rutinas para ese cliente.")
        st.stop()

    # Semana (desde rutinas_cliente)
    semanas = sorted({r["fecha_lunes"] for r in rutinas_cliente if r.get("fecha_lunes")}, reverse=True)
    semana_actual = obtener_fecha_lunes()
    pre_semana = st.session_state.get("semana_sel")
    index_semana = semanas.index(pre_semana) if pre_semana in semanas else (semanas.index(semana_actual) if semana_actual in semanas else 0)
    semana_sel = st.selectbox("📆 Semana", semanas, index=index_semana, key="semana_sel")

    # Reset día si cambia semana
    if st.session_state.get("_prev_semana_sel") != semana_sel:
        st.session_state["_prev_semana_sel"] = semana_sel
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
        msg = mensaje_motivador_del_dia(nombre, correo_norm)
        extra = (
            f"Llevas {racha_actual} semana{'s' if racha_actual!=1 else ''} seguidas COMPLETAS. ¡No rompas la cadena! 🔥"
            if racha_actual > 0 else None
        )
        st.markdown(f"<div class='banner-mot'>{msg}</div>", unsafe_allow_html=True)
        if extra: st.caption(f"🔥 {extra}")

    # Bloque rutina
    bloque_id = rutina_doc.get("bloque_rutina")
    if bloque_id:
        mismas = [r for r in rutinas_cliente if r.get("bloque_rutina")==bloque_id]
        fechas_bloque = sorted([r["fecha_lunes"] for r in mismas if r.get("fecha_lunes")])
        try:
            semana_actual_idx = fechas_bloque.index(semana_sel)+1
            total_semanas_bloque = len(fechas_bloque)
            st.markdown(f"<div class='card'>📦 <b>Bloque de rutina:</b> Semana {semana_actual_idx} de {total_semanas_bloque}</div>", unsafe_allow_html=True)
        except ValueError:
            st.info("ℹ️ Semana no encontrada en bloque de rutina.")
    else:
        st.markdown(f"<div class='card'>📦 <b>Bloque de rutina:</b> <span class='muted'>Sin identificador</span></div>", unsafe_allow_html=True)

    # Dashboard de días (tarjetas)
    st.markdown("<h3 class='h-accent'>🗓️ Elige tu día</h3>", unsafe_allow_html=True)
    dias_dash = _dias_numericos(rutina_doc.get("rutina", {}))

    if dias_dash:
        completados = sum(1 for d in dias_dash if rutina_doc["rutina"].get(f"{d}_finalizado") is True)
        st.progress(completados/len(dias_dash), text=f"{completados}/{len(dias_dash)} sesiones completadas")

        cols = st.columns(len(dias_dash), gap="small")
        for i, dia in enumerate(dias_dash):
            finalizado = bool(rutina_doc["rutina"].get(f"{dia}_finalizado") is True)
            btn_label = f"{'✅' if finalizado else '⚡'} Día {dia}"
            btn_key   = f"daybtn_{semana_sel}_{cliente_sel}_{dia}"
            with cols[i]:
                if st.button(btn_label, key=btn_key, type=("secondary" if finalizado else "primary"),
                             use_container_width=True, help=("Completado" if finalizado else "Pendiente")):
                    st.session_state["dia_sel"] = str(dia)
                    st.rerun()
                st.markdown(
                    "<span class='badge {cls}'></span>".format(
                        cls=("badge--success" if finalizado else "badge--pending"),
                    ),
                    unsafe_allow_html=True
                )

    st.markdown("<div class='hr-light'></div>", unsafe_allow_html=True)

    # Mostrar rutina solo cuando haya día seleccionado
    dia_sel = st.session_state.get("dia_sel")
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
            rir_val   = e.get("rir")

            # 1) Video (puede venir en e['video'] o dentro de 'detalle' como link)
            video_url, detalle_visible = _video_y_detalle_desde_ejercicio(e)

            # 2) Línea secundaria: reps/peso/tiempo/descanso/velocidad (SIN RIR)
            partes = [f"{_repstr(e)}"]
            if peso:      partes.append(f"{peso} kg")
            if tiempo:    partes.append(f"{tiempo} seg")
            if velocidad: partes.append(f"{velocidad} m/s")
            dsc = _descanso_texto(e)
            if dsc:       partes.append(f"{dsc}")
            info_str = " · ".join(partes)

            # 3) Contenedor visual
            st.markdown("<div style='margin:12px 0;'>", unsafe_allow_html=True)

            # 3.a) Título (si hay video -> el nombre es botón; si no -> texto)
            video_btn_key = f"video_btn_{cliente_sel}_{semana_sel}_{circuito}_{idx}"
            mostrar_video_key = f"mostrar_video_{cliente_sel}_{semana_sel}_{circuito}_{idx}"

            if video_url:
                # nombre como botón (ajustado al texto, no ocupa todo el ancho)
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
                # nombre como texto (si no hay link en detalle, lo mostramos normal)
                titulo_linea = nombre + (f" — {detalle_visible}" if detalle_visible else "")
                st.markdown(
                    f"<div style='font-weight:800;font-size:1.05rem;color:var(--text-main);'>{titulo_linea}</div>",
                    unsafe_allow_html=True
                )

            # 3.b) Línea de detalles (reps/peso/descanso/velocidad)
            st.markdown(f"<div class='muted' style='margin-top:2px;'>{info_str}</div>", unsafe_allow_html=True)

            # 3.c) RIR en una fila aparte
            if rir_val:
                st.markdown(f"<div class='muted' style='margin-top:2px;'>RIR {rir_val}</div>", unsafe_allow_html=True)

            # 3.d) Mostrar video embebido si está activo
            if video_url and st.session_state.get(mostrar_video_key, False):
                url = video_url
                # Normalizar Shorts de YouTube
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
                            semana_sel=semana_sel,
                            dia_sel=str(dia_sel),
                            ejercicio_editado=e,
                        )
                        if ok:
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
                            semana_sel=semana_sel,
                            dia_sel=str(dia_sel),
                            ejercicios=ejercicios,
                            correo_actor=st.session_state.get("correo",""),
                            rpe_valor=rpe_valor,
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
