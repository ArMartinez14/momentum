# admin_panel_tarjetas.py — Selector por tarjetas + botón Volver (misma paleta)
import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import unicodedata
import json
import re
import csv
from io import StringIO
from datetime import datetime

# 👇 servicio de catálogos (tuyo)
from servicio_catalogos import get_catalogos, add_item
from app_core.utils import empresa_de_usuario, EMPRESA_MOTION, EMPRESA_ASESORIA, EMPRESA_DESCONOCIDA
from app_core.email_notifications import enviar_correo_bienvenida

# ==========================
# 🎨 PALETA / ESTILOS (solo UI)
# ==========================
PRIMARY   = "#D64045"
SUCCESS   = "#C96B5D"
WARNING   = "#EFA350"
DANGER    = "#E2554A"
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

@st.cache_data(show_spinner=False)
def listar_entrenadores():
    coaches = []
    try:
        for snap in db.collection("usuarios").stream():
            if not snap.exists:
                continue
            data = snap.to_dict() or {}
            rol = (data.get("rol") or data.get("role") or "").strip().lower()
            if rol not in {"entrenador", "admin", "administrador"}:
                continue
            correo = (data.get("correo") or "").strip().lower()
            if not correo:
                continue
            nombre = (data.get("nombre") or correo).strip()
            coaches.append((nombre, correo))
    except Exception:
        pass
    coaches.sort(key=lambda item: item[0].lower())
    return coaches

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
                    t = titulo.lower()
                    if "característica" in t or "caracteristica" in t:
                        tipo = "caracteristicas"
                    elif "patrón" in t or "patron" in t:
                        tipo = "patrones_movimiento"
                    elif "grupo muscular secundario" in t:
                        tipo = "grupo_muscular_secundario"
                    elif "grupo muscular principal" in t:
                        tipo = "grupo_muscular_principal"
                    elif "marca" in t:
                        tipo = "marcas"
                    elif "máquina" in t or "maquina" in t:
                        tipo = "maquinas"
                    else:
                        tipo = "otros_catalogos"
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
def _norm(s: str) -> str:
    """Normaliza para comparar: sin acentos, trim, casefold."""
    import unicodedata, re
    s = str(s or "")
    s = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("utf-8")
    s = re.sub(r"\s+", " ", s).strip().casefold()
    return s

def _resolver_id_implemento(db, marca: str, maquina: str) -> str:
    """Devuelve el id_implemento si hay match único por marca+maquina; si no, ''."""
    marca_in = (marca or "").strip()
    maquina_in = (maquina or "").strip()
    if not marca_in or not maquina_in:
        return ""

    # 1) Intento exacto (si no hay índice o falla, seguimos)
    try:
        q = (db.collection("implementos")
               .where("marca", "==", marca_in)
               .where("maquina", "==", maquina_in))
        hits = list(q.stream())
        if len(hits) == 1:
            return hits[0].id
        elif len(hits) >= 2:
            return ""  # ambiguo
    except Exception:
        pass

    # 2) Fallback normalizado en memoria (colección chica/mediana)
    mkey, maqkey = _norm(marca_in), _norm(maquina_in)
    try:
        candidatos = []
        for d in db.collection("implementos").limit(1000).stream():
            data = d.to_dict() or {}
            if _norm(data.get("marca")) == mkey and _norm(data.get("maquina")) == maqkey:
                candidatos.append(d.id)
        return candidatos[0] if len(candidatos) == 1 else ""
    except Exception:
        return ""

# ==========================
# 🔁 Navegación (menu / cliente / ejercicio)
# ==========================
def _set_mode(m): 
    st.session_state["admin_panel_mode"] = m

def _get_mode() -> str:
    return st.session_state.get("admin_panel_mode", "menu")

def _panel_back_button():
    if st.button("Regresar al menú del panel", type="secondary"):
        _set_mode("menu")
        st.rerun()

# ==========================
# 🧩 Pantalla: Menú por tarjetas
# ==========================
def _render_menu():
    st.markdown("<h2 class='h-accent'>Panel de Administración</h2>", unsafe_allow_html=True)
    st.caption("Elige qué deseas gestionar.")

    colA, colB, colC = st.columns(3, gap="large")

    with colA:
        if st.button("👤\n### Ingresar Cliente\nCrear un nuevo cliente y asignar rol.",
                     key="card_cliente", use_container_width=True):
            _set_mode("cliente"); st.rerun()

    with colB:
        if st.button("🏋️\n### Ingresar/Editar Ejercicio\nCrear uno nuevo o editar existente.",
                     key="card_ejercicio", use_container_width=True):
            _set_mode("ejercicio"); st.rerun()

    with colC:
        if es_admin():
            if st.button(
                "📤\n### Importar Ejercicios\nCarga un archivo CSV para crear ejercicios.",
                key="card_carga",
                use_container_width=True,
            ):
                _set_mode("carga_csv"); st.rerun()

    # 🔥 estilos para que parezcan tarjetas
    st.markdown(f"""
    <style>
    div.stButton > button#card_cliente,
    div.stButton > button#card_ejercicio,
    div.stButton > button#card_carga {{
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
    div.stButton > button#card_ejercicio:hover,
    div.stButton > button#card_carga:hover {{
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
    _panel_back_button()
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h4 class='h-accent'>👤 Cliente Nuevo</h4>", unsafe_allow_html=True)

    st.markdown("<div class='muted'>Completa los datos básicos del cliente. El nombre y correo son obligatorios.</div>", unsafe_allow_html=True)

    col_nombre, col_apellido = st.columns(2, gap="small")
    with col_nombre:
        nombre_cliente = st.text_input("Nombre", placeholder="Ej.: María")
    with col_apellido:
        apellido_cliente = st.text_input("Apellido", placeholder="Ej.: Fernández")

    if "correo_cliente_nuevo" in st.session_state:
        st.session_state["correo_cliente_nuevo"] = normalizar_correo(st.session_state["correo_cliente_nuevo"])

    correo_input = st.text_input(
        "Correo",
        key="correo_cliente_nuevo",
        on_change=_cb_normalizar_correo,
        args=("correo_cliente_nuevo",),
        placeholder="nombre@dominio.com"
    )
    correo_limpio = st.session_state.get("correo_cliente_nuevo", "")

    if correo_input:
        st.caption(f"Se guardará como: **{correo_limpio or '—'}**")

    correo_usuario = (st.session_state.get("correo") or "").strip().lower()
    coach_responsable = correo_usuario

    if es_admin():
        entrenadores = listar_entrenadores()
        if entrenadores:
            labels = [f"{nombre} ({correo})" for nombre, correo in entrenadores]
            try:
                default_idx = next(idx for idx, (_, c) in enumerate(entrenadores) if c == correo_usuario)
            except StopIteration:
                default_idx = 0
            elegido = st.selectbox(
                "Entrenador responsable",
                labels,
                index=default_idx,
                help="El coach que verá y gestionará a este cliente."
            )
            coach_responsable = entrenadores[labels.index(elegido)][1]
        else:
            st.info("No se encontraron entrenadores registrados; se asignará a tu correo por defecto.")

    empresa_preferida = empresa_de_usuario(coach_responsable)

    if st.session_state.get("rol") == "admin":
        opciones_rol = ["deportista", "entrenador", "admin"]
    else:
        opciones_rol = ["deportista"]

    st.markdown("<hr class='hr-light'>", unsafe_allow_html=True)

    rol = st.selectbox("Rol en la plataforma", opciones_rol, help="Define los permisos por defecto del cliente.")

    empresa_seleccionada = empresa_preferida or EMPRESA_DESCONOCIDA
    if es_admin():
        opciones_empresa = {
            "Motion": EMPRESA_MOTION,
            "Asesoría": EMPRESA_ASESORIA,
        }
        default_label = next(
            (label for label, valor in opciones_empresa.items() if valor == empresa_seleccionada),
            "Motion",
        )
        empresa_label = st.selectbox(
            "Empresa",
            list(opciones_empresa.keys()),
            index=list(opciones_empresa.keys()).index(default_label) if default_label in opciones_empresa else 0,
            help="Selecciona la empresa asociada a este usuario."
        )
        empresa_seleccionada = opciones_empresa[empresa_label]
    else:
        if empresa_seleccionada == EMPRESA_MOTION:
            st.caption("Empresa asignada automáticamente: Motion")
        elif empresa_seleccionada == EMPRESA_ASESORIA:
            st.caption("Empresa asignada automáticamente: Asesoría")
        else:
            st.caption("Este usuario se registrará sin empresa asignada.")

    solicitar_anamnesis = False
    if rol == "deportista":
        solicitar_anamnesis = st.checkbox(
            "Solicitar anamnesis inicial",
            value=True,
            help="Si está activo, el deportista deberá completar la anamnesis antes de usar la app."
        )

    st.markdown("<hr class='hr-light'>", unsafe_allow_html=True)

    cols_btn = st.columns([1,3])
    with cols_btn[0]:
        if st.button("Guardar Cliente", type="primary", use_container_width=True):
            nombre_clean = nombre_cliente.strip()
            apellido_clean = apellido_cliente.strip()
            if not nombre_clean:
                st.warning("⚠️ Ingresa el nombre.")
                st.markdown("</div>", unsafe_allow_html=True)
                return
            if not apellido_clean:
                st.warning("⚠️ Ingresa el apellido.")
                st.markdown("</div>", unsafe_allow_html=True)
                return

            correo_limpio = normalizar_correo(correo_input)
            if not correo_limpio:
                st.warning("⚠️ Ingresa un correo válido.")
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

            if rol == "entrenador" and not es_admin():
                st.warning("⚠️ Solo un administrador puede crear entrenadores.")
                st.markdown("</div>", unsafe_allow_html=True)
                return

            doc_id = normalizar_id(correo_limpio)
            nombre_completo = " ".join(part for part in [nombre_clean, apellido_clean] if part)

            data = {
                "nombre": nombre_completo,
                "correo": correo_limpio,
                "rol": rol,
                "creado_en": datetime.utcnow(),
                "empresa": empresa_seleccionada or EMPRESA_DESCONOCIDA,
                "requiere_anamnesis": bool(solicitar_anamnesis) if rol == "deportista" else False,
            }

            if rol == "deportista":
                data["coach_responsable"] = coach_responsable
            elif es_admin():
                data["coach_responsable"] = coach_responsable if coach_responsable else ""
            else:
                data["coach_responsable"] = coach_responsable

            try:
                db.collection("usuarios").document(doc_id).set(data)
                st.success(f"✅ Cliente '{nombre_completo}' guardado correctamente")
                try:
                    empresa_coach = empresa_de_usuario(coach_responsable)
                    if not (empresa_seleccionada == EMPRESA_MOTION and empresa_coach == EMPRESA_MOTION):
                        envio_ok = enviar_correo_bienvenida(
                            correo=correo_limpio,
                            nombre=nombre_completo,
                            empresa=empresa_seleccionada,
                            rol=rol,
                        )
                        if envio_ok:
                            st.caption("Se envió un correo de bienvenida con instrucciones de acceso.")
                        else:
                            st.caption("No se pudo enviar el correo de bienvenida; revisa la configuración de notificaciones.")
                    else:
                        st.caption("Cliente creado sin correo de bienvenida (política Motion).")
                except Exception as exc_envio:
                    st.caption(f"Cliente creado, pero falló el envío de bienvenida: {exc_envio}")
            except Exception as e:
                st.error(f"❌ Error al guardar: {e}")
    st.markdown("</div>", unsafe_allow_html=True)

# ==========================
# 🏋️ Formulario: Ejercicio
# ==========================
def _render_ejercicio():
    _panel_back_button()
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h4 class='h-accent'>📌 Crear o Editar Ejercicio</h4>", unsafe_allow_html=True)
    st.markdown("<div class='muted'>Usa este formulario para registrar ejercicios con su clasificación. Los campos marcados son obligatorios.</div>", unsafe_allow_html=True)

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
    catalogo_carac   = cat.get("caracteristicas", [])
    catalogo_patron  = cat.get("patrones_movimiento", [])
    catalogo_grupo_p = cat.get("grupo_muscular_principal", [])
    catalogo_grupo_s = cat.get("grupo_muscular_secundario", [])
    catalogo_marcas  = cat.get("marcas", [])
    catalogo_maquinas= cat.get("maquinas", [])

    # === # === FORMULARIO ===
    st.markdown("<hr class='hr-light'>", unsafe_allow_html=True)

    col1, col2 = st.columns(2)
    with col1:
        marca = st.text_input("Marca", value=datos.get("marca", ""), key="marca", placeholder="Ej.: TRX", help="Opcional: identifica el implemento o fabricante").strip()
    with col2:
        maquina = st.text_input("Máquina", value=datos.get("maquina", ""), key="maquina", placeholder="Ej.: Remo sentado", help="Opcional: nombre del equipo").strip()

    detalle = st.text_input("Detalle *", value=datos.get("detalle", ""), key="detalle", placeholder="Descripción breve del ejercicio")

    col3, col4 = st.columns(2)
    with col3:
        caracteristica = combo_con_agregar(
            "Característica",
            catalogo_carac,
            key_base="caracteristica",
            valor_inicial=datos.get("caracteristica", "")
        )
    with col4:
        patron = combo_con_agregar(
            "Patrón de Movimiento",
            catalogo_patron,
            key_base="patron",
            valor_inicial=datos.get("patron_de_movimiento", "")
        )

    col5, col6 = st.columns(2)
    with col5:
        grupo_p = combo_con_agregar(
            "Grupo Muscular Principal",
            catalogo_grupo_p,
            key_base="grupo_p",
            valor_inicial=datos.get("grupo_muscular_principal", "")
        )
    with col6:
        grupo_s = combo_con_agregar(
            "Grupo Muscular Secundario",
            catalogo_grupo_s,
            key_base="grupo_s",
            valor_inicial=datos.get("grupo_muscular_secundario", "")
        )
    # Preview de implemento/pesos si hay marca+máquina
    if marca and maquina:
        _id_prev = _resolver_id_implemento(db, marca, maquina)
        if _id_prev:
            snap_impl = db.collection("implementos").document(str(_id_prev)).get()
            if snap_impl.exists:
                data_impl = snap_impl.to_dict() or {}
                st.success(f"Implemento detectado: ID **{_id_prev}** · {data_impl.get('marca','')} – {data_impl.get('maquina','')}")
                pesos = data_impl.get("pesos", [])
                if isinstance(pesos, dict):
                    pesos_list = [v for _, v in sorted(pesos.items(), key=lambda kv: int(kv[0]))]
                elif isinstance(pesos, list):
                    pesos_list = pesos
                else:
                    pesos_list = []
                if pesos_list:
                    st.caption("Pesos disponibles (preview): " + ", ".join(str(p) for p in pesos_list))

    # Nombre visible
    nombre_ej = " ".join([x for x in [marca, maquina, detalle] if x]).strip()
    st.text_input("Nombre completo", value=nombre_ej, key="nombre", disabled=True, help="Se compone automáticamente con Marca, Máquina y Detalle; modifícalo al guardar si lo requieres.")

    publico_default = True if admin else False
    publico_check = st.checkbox("Hacer público (visible para todos los entrenadores)", value=publico_default)

    cols_btn2 = st.columns([1,3])
    with cols_btn2[0]:
        if st.button("💾 Guardar Ejercicio", key="btn_guardar_ejercicio", type="primary"):
            # Validaciones mínimas
            faltantes = [etq for etq, val in {
                "Detalle": detalle,
                "Característica": caracteristica,
                "Patrón de Movimiento": patron,
                "Grupo Muscular Principal": grupo_p
            }.items() if not (val or "").strip()]


            if faltantes:
                st.warning("⚠️ Completa: " + ", ".join(faltantes))
                st.markdown("</div>", unsafe_allow_html=True)
                return

            nombre_final = (nombre_ej or datos.get("nombre") or detalle or maquina or marca or "").strip()
            if not nombre_final:
                st.warning("⚠️ El campo 'nombre' es obligatorio (usa al menos Detalle/Máquina/Marca).")
                st.markdown("</div>", unsafe_allow_html=True)
                return

            # === Resolver id_implemento SOLO AL GUARDAR ===
            id_impl_resuelto = _resolver_id_implemento(db, marca, maquina)

            # Si estás editando: conserva el id previo si Marca/Máquina no cambiaron
            if modo == "Editar ejercicio existente" and doc_id_sel:
                marca_prev   = (datos.get("marca") or "").strip()
                maquina_prev = (datos.get("maquina") or "").strip()
                if _norm(marca_prev) == _norm(marca) and _norm(maquina_prev) == _norm(maquina):
                    id_impl_final = (datos.get("id_implemento") or "")
                else:
                    id_impl_final = id_impl_resuelto  # recalculado por cambio
            else:
                id_impl_final = id_impl_resuelto  # nuevo ejercicio

            datos_guardar = {
                "nombre": nombre_final,
                "marca": marca,
                "maquina": maquina,
                "detalle": detalle,
                "caracteristica": caracteristica,
                "patron_de_movimiento": patron,
                "grupo_muscular_principal": grupo_p,
                "grupo_muscular_secundario": grupo_s or "",
                "id_implemento": id_impl_final,   # ← requerido
                "actualizado_por": correo_usuario,
                "fecha_actualizacion": datetime.utcnow(),
                "publico": bool(publico_check),
            }

            try:
                if modo == "Editar ejercicio existente" and doc_id_sel:
                    if not datos.get("entrenador"):
                        datos_guardar["entrenador"] = correo_usuario  # backfill si faltaba
                    db.collection("ejercicios").document(doc_id_sel).update(datos_guardar)
                    st.success(f"✅ Ejercicio '{datos.get('nombre', doc_id_sel)}' actualizado correctamente")
                else:
                    doc_id = normalizar_texto(nombre_final)
                    db.collection("ejercicios").document(doc_id).set({
                        **datos_guardar,
                        "creado_por": correo_usuario,
                        "fecha_creacion": datetime.utcnow(),
                        "entrenador": correo_usuario,
                    }, merge=True)
                    st.success(f"✅ Ejercicio '{nombre_final}' guardado correctamente")

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
def _render_carga_csv():
    _panel_back_button()
    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h4 class='h-accent'>📤 Importar ejercicios desde archivo</h4>", unsafe_allow_html=True)
    st.caption(
        "El CSV puede incluir columnas como **Detalle**, **Caracteristica**, **Patron de Movimiento**,"
        " **Marca**, **Maquina**, **Grupo Muscular Principal/Secundario**, `Publico`, entre otras."
        " Cualquier columna faltante se dejará vacía automáticamente."
    )

    archivo = st.file_uploader("Archivo CSV", type=["csv"], help="Usa codificación UTF-8. Cada fila crea o actualiza un ejercicio.")
    if not archivo:
        st.markdown("</div>", unsafe_allow_html=True)
        return

    try:
        contenido = archivo.getvalue().decode("utf-8-sig")
        reader = csv.DictReader(StringIO(contenido))
        filas = [row for row in reader if any((row.get(col) or "").strip() for col in reader.fieldnames or [])]
    except Exception as exc:
        st.error(f"No se pudo leer el archivo: {exc}")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    if not filas:
        st.warning("El archivo no contiene filas válidas.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    st.dataframe(filas[:10])

    correo_usuario = (st.session_state.get("correo") or "").strip().lower()
    if not correo_usuario:
        st.error("No se detectó un usuario autenticado. Inicia sesión nuevamente.")
        st.markdown("</div>", unsafe_allow_html=True)
        return

    admin = es_admin()
    headers_norm = { (h or "").strip().lower(): h for h in (reader.fieldnames or []) }

    if st.button("Importar ejercicios", type="primary", key="btn_importar_csv"):
        guardados = 0
        errores = []
        for idx, row in enumerate(filas, start=1):
            try:
                def _val(nombre, *aliases):
                    for alias in (nombre, *aliases):
                        if alias in headers_norm:
                            return (row.get(headers_norm[alias]) or "").strip()
                    return ""

                marca = _val("marca")
                maquina = _val("maquina")
                detalle = _val("detalle")
                caracteristica = _val("caracteristica")
                patron = _val("patron de movimiento", "patron_de_movimiento", "patron")
                grupo_p = _val("grupo muscular principal", "grupo_muscular_principal")
                grupo_s = _val("grupo muscular secundario", "grupo_muscular_secundario")
                video = _val("video", "link_video", "url_video", "youtube", "link")
                entrenador_csv = _val("entrenador", "coach")
                creado_por_csv = _val("creado_por", "creado por", "created_by")

                nombre = _val("nombre")
                if not nombre:
                    nombre = " ".join(filter(None, [marca, maquina, detalle])).strip()
                if not nombre:
                    nombre = f"ejercicio_{idx}"

                if not detalle:
                    detalle = nombre
                if not caracteristica:
                    caracteristica = "Sin especificar"
                if not patron:
                    patron = "Sin especificar"

                publico_raw = _val("publico", "publico_flag")
                publico_raw = publico_raw.lower()
                publico = publico_raw in {"1", "true", "si", "sí", "publico", "public", "yes"}
                if not admin:
                    publico = False

                id_impl = _resolver_id_implemento(db, marca, maquina)
                doc_id = normalizar_texto(nombre)

                entrenador_final = (entrenador_csv or creado_por_csv or correo_usuario).strip().lower()
                if not entrenador_final:
                    entrenador_final = correo_usuario
                creado_por_final = (creado_por_csv or entrenador_final or correo_usuario).strip().lower()

                payload = {
                    "nombre": nombre,
                    "marca": marca,
                    "maquina": maquina,
                    "detalle": detalle,
                    "caracteristica": caracteristica,
                    "patron_de_movimiento": patron,
                    "grupo_muscular_principal": grupo_p,
                    "grupo_muscular_secundario": grupo_s,
                    "id_implemento": id_impl,
                    "publico": bool(publico),
                    "actualizado_por": correo_usuario,
                    "fecha_actualizacion": datetime.utcnow(),
                    "entrenador": entrenador_final,
                }
                if video:
                    payload["video"] = video

                db.collection("ejercicios").document(doc_id).set({
                    **payload,
                    "creado_por": creado_por_final,
                    "fecha_creacion": datetime.utcnow(),
                }, merge=True)
                guardados += 1
            except Exception as exc:
                errores.append((idx, str(exc)))

        if guardados:
            st.success(f"✅ Ejercicios guardados: {guardados}")
        if errores:
            st.warning("Se encontraron errores en algunas filas:")
            for fila, err in errores:
                st.write(f"- Fila {fila}: {err}")

    st.markdown("</div>", unsafe_allow_html=True)


def ingresar_cliente_o_video_o_ejercicio():
    mode = _get_mode()
    if mode == "menu":
        _render_menu()
    elif mode == "cliente":
        _render_cliente()
    elif mode == "ejercicio":
        _render_ejercicio()
    elif mode == "carga_csv":
        if es_admin():
            _render_carga_csv()
        else:
            st.error("Solo los administradores pueden importar ejercicios masivamente.")
            _set_mode("menu")
    else:
        _set_mode("menu"); _render_menu()

# Llamada directa si usas multipage
if __name__ == "__main__":
    ingresar_cliente_o_video_o_ejercicio()
