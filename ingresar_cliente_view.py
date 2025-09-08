# admin_panel_tarjetas.py — Selector por tarjetas + botón Volver (misma paleta)
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import unicodedata
import json
import re
from datetime import datetime

# 👇 servicio de catálogos (tuyo)
from servicio_catalogos import get_catalogos, add_item

# ==========================
# 🎨 PALETA / ESTILOS (solo UI)
# ==========================
PRIMARY   = "#00C2FF"
SUCCESS   = "#22C55E"
WARNING   = "#F59E0B"
DANGER    = "#EF4444"
BG_DARK   = "#0B0F14"
SURFACE   = "#121821"
TEXT_MAIN = "#FFFFFF"
TEXT_MUTED= "#94A3B8"
STROKE    = "rgba(255,255,255,.08)"

st.markdown(f"""
<style>
:root {{
  --primary:{PRIMARY}; --success:{SUCCESS}; --warning:{WARNING}; --danger:{DANGER};
  --bg:{BG_DARK}; --surface:{SURFACE}; --muted:{TEXT_MUTED}; --stroke:{STROKE};
}}
html,body,[data-testid="stAppViewContainer"]{{ background:var(--bg)!important; }}
h1,h2,h3,h4,h5 {{ color:{TEXT_MAIN}; }}
p, label, span, div {{ color:{TEXT_MAIN}; }}
small,.muted {{ color:var(--muted)!important; }}

.h-accent {{ position:relative; padding-left:10px; margin:8px 0 6px; font-weight:700; color:{TEXT_MAIN}; }}
.h-accent:before {{ content:""; position:absolute; left:0; top:2px; bottom:2px; width:4px; border-radius:3px; background:var(--primary); }}

.hr-light {{ border-bottom:1px solid var(--stroke); margin:12px 0; }}

.card {{
  background:var(--surface); border:1px solid var(--stroke);
  border-radius:12px; padding:16px; margin:10px 0;
}}

.card-click {{
  border:1px solid var(--stroke); background:linear-gradient(180deg,#0E1621,#0F1B27);
  border-radius:14px; padding:20px; text-align:center; cursor:pointer; user-select:none;
  transition:transform .06s ease, filter .12s ease;
}}
.card-click:hover {{ filter:brightness(1.05); transform:translateY(-1px); }}
.card-click h3 {{ margin:6px 0 4px; color:{TEXT_MAIN}; }}
.card-click p {{ margin:0; color:var(--muted); }}

.badge {{ display:inline-block; padding:2px 8px; border-radius:999px; font-size:12px; font-weight:700; }}
.badge--success {{ background:var(--success); color:#06210c; }}

div.stButton > button[kind="primary"], .stDownloadButton button {{
  background: var(--primary) !important; color:#001018 !important; border:none !important;
  font-weight:700 !important; border-radius:10px !important;
}}
div.stButton > button[kind="secondary"] {{
  background:#1A2431 !important; color:#E0E0E0 !important; border:1px solid var(--stroke) !important;
  border-radius:10px !important;
}}
div.stButton > button:hover {{ filter:brightness(0.93); }}

.stTextInput > div > div > input,
.stNumberInput input,
textarea, .stTextArea textarea,
.stSelectbox > div > div,
.stDateInput, .stMultiSelect > div, .stRadio > div {{
  background:#101722 !important; color:{TEXT_MAIN} !important; border:1px solid var(--stroke) !important;
}}
.stSelectbox div[data-baseweb="select"] > div {{ background:transparent!important; }}
.stRadio > label, .stCheckbox > label {{ color:{TEXT_MAIN}!important; }}

.stTabs [data-baseweb="tab-list"] button span {{ color:{TEXT_MAIN}; }}
.stTabs [data-baseweb="tab-highlight"] {{ background:var(--primary)!important; }}
</style>
""", unsafe_allow_html=True)

# === INICIALIZAR FIREBASE SOLO UNA VEZ ===
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)
db = firestore.client()

# ====== helpers de normalización ======
def normalizar_id(correo: str) -> str:
    return (correo or "").replace('@', '_').replace('.', '_')

def normalizar_texto(texto: str) -> str:
    return unicodedata.normalize('NFKD', texto).encode('ASCII', 'ignore').decode('utf-8').lower().replace(" ", "_")

import re as _re
def normalizar_correo(correo: str) -> str:
    if not correo:
        return ""
    c = str(correo)
    c = c.replace("\u00A0", "")
    c = _re.sub(r"\s+", "", c, flags=_re.UNICODE)
    c = c.casefold()
    return c

# ====== roles ======
ADMIN_ROLES = {"admin", "administrador", "owner", "Admin", "Administrador"}

def es_admin() -> bool:
    correo = (st.session_state.get("correo") or "").strip().lower()
    rol_ss = (st.session_state.get("rol") or "").strip()
    if rol_ss in ADMIN_ROLES:
        return True
    if correo:
        try:
            doc_id = normalizar_id(correo)
            snap = db.collection("usuarios").document(doc_id).get()
            if snap.exists:
                data = snap.to_dict() or {}
                rol_fb = (data.get("rol") or data.get("role") or "").strip()
                return rol_fb in ADMIN_ROLES
        except Exception:
            pass
    return False

# ====== select con “agregar nuevo” (igual) ======
def combo_con_agregar(titulo: str, opciones: list[str], key_base: str, valor_inicial: str = "") -> str:
    SENTINEL = "➕ Agregar nuevo…"

    base_opts = sorted(opciones or [])
    if valor_inicial and valor_inicial not in base_opts:
        base_opts.append(valor_inicial)

    opts = ["— Selecciona —"] + base_opts + [SENTINEL]
    index_default = 0
    if valor_inicial:
        try:
            index_default = opts.index(valor_inicial)
        except ValueError:
            index_default = 0

    sel = st.selectbox(titulo, opts, index=index_default, key=f"{key_base}_select")

    if sel == SENTINEL:
        st.markdown("<div class='card'>", unsafe_allow_html=True)
        nuevo = st.text_input(f"Ingresar nuevo valor para {titulo.lower()}:", key=f"{key_base}_nuevo")
        cols = st.columns([1, 1, 6])
        with cols[0]:
            if st.button("Guardar", key=f"{key_base}_guardar", type="primary"):
                valor_limpio = (nuevo or "").strip()
                if valor_limpio:
                    if "Característica" in titulo:
                        tipo = "caracteristicas"
                    elif "Patrón" in titulo or "Patron" in titulo:
                        tipo = "patrones_movimiento"
                    else:
                        tipo = "grupo_muscular_principal"
                    add_item(tipo, valor_limpio)
                    st.success(f"Agregado: {valor_limpio}")
                    st.rerun()
        st.markdown("</div>", unsafe_allow_html=True)
        return ""
    elif sel == "— Selecciona —":
        return ""
    else:
        return sel

# === Callback para limpiar el input en session_state ===
def _cb_normalizar_correo(key_name: str):
    raw = st.session_state.get(key_name, "")
    st.session_state[key_name] = normalizar_correo(raw)

# ==========================
# 🔁 Navegación (menu / cliente / ejercicio)
# ==========================
def _set_mode(m): 
    st.session_state["admin_panel_mode"] = m

def _get_mode() -> str:
    return st.session_state.get("admin_panel_mode", "menu")

def _btn_volver():
    cols = st.columns([1, 6])
    with cols[0]:
        if st.button("← Volver", type="secondary", use_container_width=True):
            _set_mode("menu")
            st.rerun()

# ==========================
# 🧩 Pantalla: Menú por tarjetas
# ==========================
def _render_menu():
    st.markdown("<h2 class='h-accent'>Panel de Administración</h2>", unsafe_allow_html=True)
    st.caption("Elige qué deseas gestionar.")

    colA, colB = st.columns(2, gap="large")

    with colA:
        if st.button("👤\n### Ingresar Cliente\nCrear un nuevo cliente y asignar rol.",
                     key="card_cliente", use_container_width=True):
            _set_mode("cliente"); st.rerun()

    with colB:
        if st.button("🏋️\n### Ingresar/Editar Ejercicio\nCrear uno nuevo o editar existente.",
                     key="card_ejercicio", use_container_width=True):
            _set_mode("ejercicio"); st.rerun()

    # 🔥 estilos para que parezcan tarjetas
    st.markdown(f"""
    <style>
    div.stButton > button#card_cliente,
    div.stButton > button#card_ejercicio {{
        background: var(--surface) !important;
        color: {TEXT_MAIN} !important;
        border: 1px solid {STROKE} !important;
        border-radius: 14px !important;
        padding: 28px 20px !important;
        text-align: center !important;
        font-size: 18px !important;
        font-weight: 600 !important;
        white-space: pre-line !important;  /* para saltos de línea con \n */
        transition: all .12s ease-in-out !important;
    }}
    div.stButton > button#card_cliente:hover,
    div.stButton > button#card_ejercicio:hover {{
        background: linear-gradient(180deg,#0E1621,#0F1B27) !important;
        border-color: {PRIMARY} !important;
        transform: translateY(-2px);
        filter: brightness(1.05);
    }}
    </style>
    """, unsafe_allow_html=True)

# ==========================
# 👤 Formulario: Cliente
# ==========================
def _render_cliente():
    _btn_volver()
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h4 class='h-accent'>👤 Cliente Nuevo</h4>", unsafe_allow_html=True)

    nombre = st.text_input("Nombre del cliente:")

    if "correo_cliente_nuevo" in st.session_state:
        st.session_state["correo_cliente_nuevo"] = normalizar_correo(st.session_state["correo_cliente_nuevo"])

    correo_input = st.text_input(
        "Correo del cliente:",
        key="correo_cliente_nuevo",
        on_change=_cb_normalizar_correo,
        args=("correo_cliente_nuevo",)
    )
    correo_limpio = st.session_state.get("correo_cliente_nuevo", "")

    if correo_input:
        st.caption(f"Se guardará como: **{correo_limpio or '—'}**")

    if st.session_state.get("rol") == "admin":
        opciones_rol = ["deportista", "entrenador", "admin"]
    else:
        opciones_rol = ["deportista"]

    rol = st.selectbox("Rol:", opciones_rol)

    cols_btn = st.columns([1,3])
    with cols_btn[0]:
        if st.button("Guardar Cliente", type="primary"):
            if not nombre:
                st.warning("⚠️ Ingresa el nombre.")
                st.markdown("</div>", unsafe_allow_html=True)
                return

            correo_limpio = normalizar_correo(correo_input)
            if not correo_limpio:
                st.warning("⚠️ Ingresa el correo.")
                st.markdown("</div>", unsafe_allow_html=True)
                return

            patron_correo = r"^[^\s@]+@[^\s@]+\.[^\s@]+$"
            if not re.match(patron_correo, correo_limpio):
                st.warning("⚠️ El correo no parece válido. Revisa el formato (ej: nombre@dominio.com).")
                st.markdown("</div>", unsafe_allow_html=True)
                return

            if not rol:
                st.warning("⚠️ Selecciona el rol.")
                st.markdown("</div>", unsafe_allow_html=True)
                return

            doc_id = normalizar_id(correo_limpio)
            data = {"nombre": nombre, "correo": correo_limpio, "rol": rol}

            try:
                db.collection("usuarios").document(doc_id).set(data)
                st.success(f"✅ Cliente '{nombre}' guardado correctamente con correo: {correo_limpio}")
            except Exception as e:
                st.error(f"❌ Error al guardar: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

# ==========================
# 🏋️ Formulario: Ejercicio
# ==========================
def _render_ejercicio():
    _btn_volver()
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h4 class='h-accent'>📌 Crear o Editar Ejercicio</h4>", unsafe_allow_html=True)

    correo_usuario = (st.session_state.get("correo") or "").strip().lower()
    if not correo_usuario:
        st.warning("Primero ingresa tu correo en la app (st.session_state['correo']).")
        st.markdown("</div>", unsafe_allow_html=True)
        st.stop()

    admin = es_admin()

    # Cargar ejercicios ya existentes
    docs = db.collection("ejercicios").stream()
    ejercicios_disponibles = {doc.id: doc.to_dict().get("nombre", doc.id) for doc in docs}

    modo = st.radio("¿Qué quieres hacer?", ["Nuevo ejercicio", "Editar ejercicio existente"], horizontal=True)

    doc_id_sel = None
    datos = {}
    if modo == "Editar ejercicio existente" and ejercicios_disponibles:
        seleccion = st.selectbox("Selecciona un ejercicio:", list(ejercicios_disponibles.values()))
        doc_id_sel = [k for k, v in ejercicios_disponibles.items() if v == seleccion][0]
        snap = db.collection("ejercicios").document(doc_id_sel).get()
        datos = snap.to_dict() if snap.exists else {}

    # === catálogos ===
    cat = get_catalogos()
    catalogo_carac  = cat.get("caracteristicas", [])
    catalogo_patron = cat.get("patrones_movimiento", [])
    catalogo_grupo  = cat.get("grupo_muscular_principal", [])

    # === FORMULARIO ===
    col1, col2 = st.columns(2)
    with col1:
        implemento = st.text_input("Implemento:", value=datos.get("implemento", ""), key="implemento")
    with col2:
        detalle = st.text_input("Detalle:", value=datos.get("detalle", ""), key="detalle")

    col3, col4 = st.columns(2)
    with col3:
        caracteristica = combo_con_agregar(
            "Característica",
            catalogo_carac,
            key_base="caracteristica",
            valor_inicial=datos.get("caracteristica", "")
        )
    with col4:
        grupo = combo_con_agregar(
            "Grupo muscular principal",
            catalogo_grupo,
            key_base="grupo",
            valor_inicial=datos.get("grupo_muscular_principal", "")
        )

    patron = combo_con_agregar(
        "Patrón de movimiento",
        catalogo_patron,
        key_base="patron",
        valor_inicial=datos.get("patron_de_movimiento", "")
    )

    nombre_ej = f"{implemento.strip()} {detalle.strip()}".strip()
    st.text_input("Nombre completo del ejercicio:", value=nombre_ej, key="nombre", disabled=True)

    publico_default = True if admin else False
    publico_check = st.checkbox("Hacer público (visible para todos los entrenadores)", value=publico_default)

    cols_btn2 = st.columns([1,3])
    with cols_btn2[0]:
        if st.button("💾 Guardar Ejercicio", key="btn_guardar_ejercicio", type="primary"):
            if not nombre_ej:
                st.warning("⚠️ El campo 'nombre' es obligatorio.")
                st.markdown("</div>", unsafe_allow_html=True)
                return

            datos_guardar = {
                "nombre": nombre_ej,
                "caracteristica": caracteristica,
                "detalle": detalle,
                "grupo_muscular_principal": grupo,
                "implemento": implemento,
                "patron_de_movimiento": patron,
                "actualizado_por": correo_usuario,
                "fecha_actualizacion": datetime.utcnow(),
                "publico": bool(publico_check),
            }

            faltantes = [k for k, v in {
                "Característica": caracteristica,
                "Grupo muscular principal": grupo,
                "Patrón de movimiento": patron
            }.items() if not (v or "").strip()]

            if faltantes:
                st.warning("⚠️ Completa: " + ", ".join(faltantes))
                st.markdown("</div>", unsafe_allow_html=True)
                return

            try:
                if modo == "Editar ejercicio existente" and doc_id_sel:
                    entrenador_original = datos.get("entrenador")
                    if not entrenador_original:
                        datos_guardar["entrenador"] = correo_usuario  # backfill si faltaba
                    db.collection("ejercicios").document(doc_id_sel).update(datos_guardar)
                    st.success(f"✅ Ejercicio '{datos.get('nombre', doc_id_sel)}' actualizado correctamente")
                else:
                    doc_id = normalizar_texto(nombre_ej)
                    db.collection("ejercicios").document(doc_id).set({
                        **datos_guardar,
                        "creado_por": correo_usuario,
                        "fecha_creacion": datetime.utcnow(),
                        "entrenador": correo_usuario,
                    }, merge=True)
                    st.success(f"✅ Ejercicio '{nombre_ej}' guardado correctamente")

                if datos_guardar["publico"]:
                    st.info("Este ejercicio es **público** y será visible para todos los entrenadores.")
                else:
                    st.info("Este ejercicio está **no público** (solo lo verás tú en Crear Rutina si no eres admin).")

            except Exception as e:
                st.error(f"❌ Error al guardar: {e}")

    st.markdown("</div>", unsafe_allow_html=True)

# ==========================
# 🚀 Punto de entrada
# ==========================
def ingresar_cliente_o_video_o_ejercicio():
    mode = _get_mode()
    if mode == "menu":
        _render_menu()
    elif mode == "cliente":
        _render_cliente()
    elif mode == "ejercicio":
        _render_ejercicio()
    else:
        _set_mode("menu"); _render_menu()

# Llamada directa si usas multipage
if __name__ == "__main__":
    ingresar_cliente_o_video_o_ejercicio()
