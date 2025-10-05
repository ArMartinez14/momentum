# crear_rutinas.py — Mismo estilo que ver_rutinas.py (solo UI/colores) + Restricción de circuitos por sección
import streamlit as st
import unicodedata
from datetime import date, timedelta, datetime, timezone
import pandas as pd
import uuid
# Catálogos para caracteristica / patrón / grupo
from servicio_catalogos import get_catalogos, add_item
from firebase_admin import firestore

from herramientas import aplicar_progresion
from guardar_rutina_view import guardar_rutina
from soft_login_full import soft_login_barrier

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


from app_core.firebase_client import get_db
from app_core.theme import inject_theme
from app_core.utils import empresa_de_usuario, EMPRESA_MOTION, EMPRESA_ASESORIA, EMPRESA_DESCONOCIDA, correo_a_doc_id

# Selector de tema (ahora en la cabecera principal)
control_bar = st.container()
with control_bar:
    control_cols = st.columns([4, 1])
    with control_cols[1]:
        theme_mode = st.selectbox(
            "🎨 Tema",
            ["Auto", "Oscuro", "Claro"],
            key="theme_mode_crear_rutinas",
            help="‘Auto’ sigue el modo del sistema; ‘Oscuro/Claro’ fuerzan los colores.",
            label_visibility="collapsed",
        )


def _vars_block(p):
    return f"""
    --primary:{p['PRIMARY']}; --success:{p['SUCCESS']}; --warning:{p['WARNING']}; --danger:{p['DANGER']};
    --bg:{p['BG']}; --surface:{p['SURFACE']}; --muted:{p['TEXT_MUTED']}; --stroke:{p['STROKE']};
    --text-main:{p['TEXT_MAIN']};
    """

# CSS/tema unificado
inject_theme()

# 👇 Aquí pegas el CSS de centrado de checkboxes
st.markdown("""
<style>
div[data-testid="stCheckbox"] {
  margin: 0 !important;
  display: flex;
  align-items: center;
  justify-content: center;
}
div[data-testid="stCheckbox"] > label {
  width: 100%;
  height: 40px;   /* ajusta 38–42px si necesitas */
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 !important;
  margin: 0 !important;
}
div[data-testid="stCheckbox"] > label p {
  margin: 0 !important;
}
</style>
""", unsafe_allow_html=True)

st.markdown("""
<style>
/* Centrar los encabezados de las columnas */
thead tr th div[data-testid="stMarkdownContainer"] {
    text-align: center !important;
    display: flex;
    justify-content: center;
    align-items: center;
}
</style>
""", unsafe_allow_html=True)


# ==========================
# Utilidades básicas
# ==========================
def proximo_lunes(base: date | None = None) -> date:
    base = base or date.today()
    dias = (7 - base.weekday()) % 7
    if dias == 0: dias = 7
    return base + timedelta(days=dias)

def normalizar_texto(texto: str) -> str:
    texto = (texto or "").lower().strip()
    texto = unicodedata.normalize("NFD", texto).encode("ascii", "ignore").decode("utf-8")
    return texto

def tiene_video(nombre_ejercicio: str, ejercicios_dict: dict[str, dict]) -> bool:
    if not nombre_ejercicio:
        return False
    data = ejercicios_dict.get(nombre_ejercicio, {}) or {}
    link = str(data.get("video", "") or "").strip()
    return bool(link)


def get_circuit_options(seccion: str) -> list[str]:
    """Devuelve circuitos válidos según sección."""
    if (seccion or "").lower().strip() == "warm up":
        return ["A", "B", "C"]
    # Work Out: D en adelante
    return list("DEFGHIJKL")

def clamp_circuito_por_seccion(circ: str, seccion: str) -> str:
    opciones = get_circuit_options(seccion)
    return circ if circ in opciones else opciones[0]

# === Helpers para detectar implemento por Marca + Máquina (mismo criterio que admin) ===
import re as _re_mod

def _norm_text_admin(s: str) -> str:
    """Normaliza para comparar: sin acentos, trim, casefold (igual a admin)."""
    import unicodedata
    s = str(s or "")
    s = unicodedata.normalize("NFKD", s).encode("ASCII", "ignore").decode("utf-8")
    s = _re_mod.sub(r"\s+", " ", s).strip().casefold()
    return s

def _resolver_id_implemento(marca: str, maquina: str) -> str:
    """
    Devuelve el id_implemento si hay match único por marca+máquina en 'implementos'.
    Si no hay o es ambiguo, retorna ''.
    """
    db = get_db()
    marca_in = (marca or "").strip()
    maquina_in = (maquina or "").strip()
    if not marca_in or not maquina_in:
        return ""

    # 1) Intento exacto
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

    # 2) Fallback normalizado (memoria)
    mkey, maqkey = _norm_text_admin(marca_in), _norm_text_admin(maquina_in)
    try:
        candidatos = []
        for d in db.collection("implementos").limit(1000).stream():
            data = d.to_dict() or {}
            if _norm_text_admin(data.get("marca")) == mkey and _norm_text_admin(data.get("maquina")) == maqkey:
                candidatos.append(d.id)
        return candidatos[0] if len(candidatos) == 1 else ""
    except Exception:
        return ""

# ==========================
# Firebase (uso centralizado)
# ==========================

ADMIN_ROLES = {"admin", "administrador", "owner", "Admin", "Administrador"}
# ===== Roles / Helpers =====
ADMIN_ROLES = {"admin", "administrador", "owner"}
# ===== Roles / Helpers =====
BORRADORES_COLLECTION = "rutinas_borrador"
def _tiene_permiso_agregar() -> bool:
    rol = (st.session_state.get("rol") or "").strip().lower()
    return rol in {"admin", "administrador", "entrenador"}

def es_admin() -> bool:
    rol = (st.session_state.get("rol") or "").strip().lower()
    return rol in {r.lower() for r in ADMIN_ROLES}

def correo_actual() -> str:
    return (st.session_state.get("correo") or "").strip().lower()

def slug_nombre(n: str) -> str:
    nn = normalizar_texto(n)
    return nn.replace(" ", "_")

def guardar_ejercicio_firestore(nombre_final: str, payload_base: dict) -> None:
    """
    Crea/actualiza el ejercicio en la colección 'ejercicios' con reglas por rol.
    - Admin: puede publicar; doc_id = slug(nombre)
    - Entrenador: privado y asignado a su correo; doc_id = slug(nombre)+'__'+correo
    """
    db = get_db()
    _es_admin = es_admin()
    _correo = correo_actual()

    # admins pueden marcar público desde el popover
    publico_flag = bool(payload_base.pop("publico_flag", False)) if _es_admin else False

    # ⚠️ Guardamos todas las claves que la UI usa aguas abajo
    meta = {
        "nombre": nombre_final,
        "video": payload_base.get("video", ""),
        "implemento": payload_base.get("implemento", ""),
        "detalle": payload_base.get("detalle", ""),
        "caracteristica": payload_base.get("caracteristica", ""),
        "patron_de_movimiento": payload_base.get("patron_de_movimiento", ""),
        "grupo_muscular_principal": payload_base.get("grupo_muscular_principal", ""),
        # alias legacy para compatibilidad con docs antiguos
        "grupo_muscular": payload_base.get("grupo_muscular_principal", ""),
        "buscable_id": slug_nombre(nombre_final),
        "publico": publico_flag,
        "entrenador": ("" if _es_admin else _correo),
        "updated_at": firestore.SERVER_TIMESTAMP,
        "created_at": firestore.SERVER_TIMESTAMP,
    }

    # si viene algo extra en payload, no lo perdemos
    meta.update(payload_base or {})

    doc_id = slug_nombre(nombre_final) if _es_admin else f"{slug_nombre(nombre_final)}__{_correo or 'sin_correo'}"
    db.collection("ejercicios").document(doc_id).set(meta, merge=True)

@st.cache_data(show_spinner=False)
def cargar_ejercicios():
    db = get_db()
    correo_usuario = (st.session_state.get("correo") or "").strip().lower()
    rol = (st.session_state.get("rol") or "").strip()
    es_admin = rol in ADMIN_ROLES

    def _store(target: dict[str, dict], data: dict) -> None:
        nombre = (data.get("nombre") or "").strip()
        if nombre:
            target[nombre] = data

    ejercicios_por_nombre: dict[str, dict] = {}
    try:
        if es_admin:
            for doc in db.collection("ejercicios").stream():
                if not doc.exists:
                    continue
                _store(ejercicios_por_nombre, doc.to_dict() or {})
        else:
            publicos: dict[str, dict] = {}
            personales: dict[str, dict] = {}
            for doc in db.collection("ejercicios").where("publico", "==", True).stream():
                if not doc.exists:
                    continue
                _store(publicos, doc.to_dict() or {})
            if correo_usuario:
                for doc in db.collection("ejercicios").where("entrenador", "==", correo_usuario).stream():
                    if not doc.exists:
                        continue
                    data = doc.to_dict() or {}
                    _store(personales, data)
                    publicos.pop((data.get("nombre") or "").strip(), None)
            ejercicios_por_nombre.update(publicos)
            ejercicios_por_nombre.update(personales)
    except Exception as e:
        st.error(f"Error cargando ejercicios: {e}")
    return ejercicios_por_nombre

@st.cache_data(show_spinner=False)
def cargar_usuarios():
    db = get_db()
    docs = db.collection("usuarios").stream()
    return [doc.to_dict() for doc in docs if doc.exists]

@st.cache_data(show_spinner=False)
def cargar_implementos():
    db = get_db()
    impl = {}
    for doc in db.collection("implementos").stream():
        d = doc.to_dict() or {}
        d["pesos"] = d.get("pesos", [])
        impl[str(doc.id)] = d
    return impl

IMPLEMENTOS = cargar_implementos()

def _ensure_len(lista: list[dict], n: int, plantilla: dict):
    if n < 0: n = 0
    while len(lista) < n: lista.append({k: "" for k in plantilla})
    while len(lista) > n: lista.pop()
    return lista
# === Helpers para cargar una rutina como base (no alteran guardado) ===
def _ejercicio_firestore_a_fila_ui_min(ej: dict) -> dict:
    """Mapea un ejercicio guardado en Firestore -> fila UI de crear_rutinas."""
    fila = {
        "Sección": "", "Circuito": "", "Ejercicio": "", "Detalle": "",
        "Series": "", "RepsMin": "", "RepsMax": "", "Peso": "", "RIR": "",
        "Tiempo": "", "Velocidad": "", "Descanso": "", "Tipo": "", "Video": "",
        # Campos que ya usa tu UI internamente
        "BuscarEjercicio": "",
        "Variable_1": "", "Cantidad_1": "", "Operacion_1": "", "Semanas_1": "",
        "Variable_2": "", "Cantidad_2": "", "Operacion_2": "", "Semanas_2": "",
        "Variable_3": "", "Cantidad_3": "", "Operacion_3": "", "Semanas_3": "",
    }

    # Sección (compatibilidad con 'bloque')
    seccion = ej.get("Sección") or ej.get("bloque") or ""
    if seccion not in ["Warm Up", "Work Out"]:
        seccion = "Warm Up" if (ej.get("circuito","") in ["A","B","C"]) else "Work Out"
    fila["Sección"] = seccion

    # Campos directos con alias
    fila["Circuito"]  = ej.get("Circuito")  or ej.get("circuito")  or ""
    fila["Ejercicio"] = ej.get("Ejercicio") or ej.get("ejercicio") or ""
    fila["Detalle"]   = ej.get("Detalle")   or ej.get("detalle")   or ""
    fila["Series"]    = ej.get("Series")    or ej.get("series")    or ""
    fila["Peso"]      = ej.get("Peso")      or ej.get("peso")      or ""
    fila["RirMin"] = ej.get("RirMin","") or ej.get("rir_min","") or ""
    fila["RirMax"] = ej.get("RirMax","") or ej.get("rir_max","") or ""
    fila["Tiempo"]    = ej.get("Tiempo")    or ej.get("tiempo")    or ""
    fila["Velocidad"] = ej.get("Velocidad") or ej.get("velocidad") or ""
    fila["Tipo"]      = ej.get("Tipo")      or ej.get("tipo")      or ""
    fila["Video"]     = ej.get("Video")     or ej.get("video")     or ""

    # Descanso: puede venir como número o string "3 min"
    # Descanso: puede venir como "", "3", "3 min", None, número, etc.
    descanso_raw = ej.get("Descanso") or ej.get("descanso") or ""

    if isinstance(descanso_raw, str):
        s = descanso_raw.strip()
        # si está vacío, deja "", si no, toma la primera "palabra" (ej. "3" de "3 min")
        fila["Descanso"] = s.split()[0] if s else ""
    elif descanso_raw is None:
        fila["Descanso"] = ""
    else:
        # números u otros tipos simples -> a string
        try:
            fila["Descanso"] = str(descanso_raw)
        except Exception:
            fila["Descanso"] = ""

    # Reps: distintas variantes guardadas
    if "RepsMin" in ej or "RepsMax" in ej:
        fila["RepsMin"] = str(ej.get("RepsMin",""))
        fila["RepsMax"] = str(ej.get("RepsMax",""))
    elif "reps_min" in ej or "reps_max" in ej:
        fila["RepsMin"] = str(ej.get("reps_min",""))
        fila["RepsMax"] = str(ej.get("reps_max",""))
    else:
        rep = str(ej.get("repeticiones","")).strip()
        if "-" in rep:
            mn, mx = rep.split("-", 1)
            fila["RepsMin"], fila["RepsMax"] = mn.strip(), mx.strip()
        else:
            fila["RepsMin"], fila["RepsMax"] = rep, ""

    # Pista + modo exacto al cargar (igual que en editar)
    if fila["Sección"] == "Work Out":
        fila["BuscarEjercicio"] = fila["Ejercicio"]
        fila["_exact_on_load"] = True  # ← forzar match exacto sólo al cargar


    # Asegurar circuito válido según sección (usas clamp_circuito_por_seccion)
    try:
        fila["Circuito"] = clamp_circuito_por_seccion(fila.get("Circuito","") or "", fila["Sección"])
    except Exception:
        pass

    return fila

def _vaciar_dias_en_session():
    """Limpia todos los días ya cargados en session_state para evitar mezclas."""
    keys = [k for k in list(st.session_state.keys()) if k.startswith("rutina_dia_")]
    for k in keys:
        st.session_state.pop(k, None)
    # también limpiamos flags/copias temporales
    for k in list(st.session_state.keys()):
        if any(p in k for p in ["_Warm_Up_", "_Work_Out_", "multiselect_", "do_copy_"]):
            st.session_state.pop(k, None)

def cargar_doc_en_session_base(rutina_dict: dict):
    """
    Carga la rutina (solo días numéricos) a las claves:
      - rutina_dia_{N}_Warm_Up
      - rutina_dia_{N}_Work_Out
    que tu UI ya usa en crear_rutinas.
    """
    _vaciar_dias_en_session()
    if not rutina_dict:
        return

    # Considera únicamente claves numéricas (tus días)
    dias_ordenados = sorted([int(d) for d in rutina_dict.keys() if str(d).isdigit()])
    for d in dias_ordenados:
        ejercicios_dia = rutina_dict.get(str(d), []) or []
        wu, wo = [], []
        for ej in ejercicios_dia:
            fila = _ejercicio_firestore_a_fila_ui_min(ej)
            if fila.get("Sección") == "Warm Up":
                wu.append(fila)
            else:
                wo.append(fila)
        st.session_state[f"rutina_dia_{int(d)}_Warm_Up"] = wu
        st.session_state[f"rutina_dia_{int(d)}_Work_Out"] = wo


def _trigger_rerun():
    """Compatibilidad con versiones nuevas/antiguas de Streamlit."""
    rerun_fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if rerun_fn:
        rerun_fn()


def _sincronizar_filas_formulario(dias_labels: list[str]):
    """Actualiza session_state con los valores más recientes de los widgets por día/sección."""
    for idx_dia, _ in enumerate(dias_labels):
        for seccion in ("Warm Up", "Work Out"):
            key_seccion = f"rutina_dia_{idx_dia + 1}_{seccion.replace(' ', '_')}"
            filas = st.session_state.get(key_seccion)
            if not isinstance(filas, list):
                continue

            filas_actualizadas: list[dict] = []
            for idx_fila, fila in enumerate(filas):
                base = dict(fila)
                key_entrenamiento = f"{idx_dia}_{seccion.replace(' ', '_')}_{idx_fila}"

                buscar_key = f"buscar_{key_entrenamiento}"
                base["BuscarEjercicio"] = st.session_state.get(buscar_key, base.get("BuscarEjercicio", ""))

                circuito_val = st.session_state.get(f"circ_{key_entrenamiento}")
                if circuito_val is not None:
                    base["Circuito"] = circuito_val

                buscar_val = st.session_state.get(f"buscar_{key_entrenamiento}")
                if buscar_val is not None:
                    base["BuscarEjercicio"] = buscar_val

                select_val = st.session_state.get(f"select_{key_entrenamiento}")
                if select_val:
                    base["Ejercicio"] = select_val if select_val != "(sin resultados)" else (buscar_val or "").strip()
                elif buscar_val is not None:
                    base["Ejercicio"] = (buscar_val or "").strip()

                for pref, campo in (
                    ("det", "Detalle"),
                    ("ser", "Series"),
                    ("rmin", "RepsMin"),
                    ("rmax", "RepsMax"),
                    ("peso", "Peso"),
                    ("tiempo", "Tiempo"),
                    ("vel", "Velocidad"),
                    ("desc", "Descanso"),
                    ("rirmin", "RirMin"),
                    ("rirmax", "RirMax"),
                ):
                    widget_val = st.session_state.get(f"{pref}_{key_entrenamiento}")
                    if widget_val is not None:
                        base[campo] = widget_val

                for p in (1, 2, 3):
                    var_key = f"var{p}_{key_entrenamiento}_{idx_fila}"
                    cant_key = f"cant{p}_{key_entrenamiento}_{idx_fila}"
                    ope_key = f"ope{p}_{key_entrenamiento}_{idx_fila}"
                    sem_key = f"sem{p}_{key_entrenamiento}_{idx_fila}"
                    cond_var_key = f"condvar{p}_{key_entrenamiento}_{idx_fila}"
                    cond_op_key = f"condop{p}_{key_entrenamiento}_{idx_fila}"
                    cond_val_key = f"condval{p}_{key_entrenamiento}_{idx_fila}"
                    if var_key in st.session_state:
                        base[f"Variable_{p}"] = st.session_state.get(var_key, base.get(f"Variable_{p}", ""))
                        base[f"Cantidad_{p}"] = st.session_state.get(cant_key, base.get(f"Cantidad_{p}", ""))
                        base[f"Operacion_{p}"] = st.session_state.get(ope_key, base.get(f"Operacion_{p}", ""))
                        base[f"Semanas_{p}"] = st.session_state.get(sem_key, base.get(f"Semanas_{p}", ""))
                        base[f"CondicionVar_{p}"] = st.session_state.get(cond_var_key, base.get(f"CondicionVar_{p}", ""))
                        base[f"CondicionOp_{p}"] = st.session_state.get(cond_op_key, base.get(f"CondicionOp_{p}", ""))
                        base[f"CondicionValor_{p}"] = st.session_state.get(cond_val_key, base.get(f"CondicionValor_{p}", ""))

                filas_actualizadas.append(base)

            st.session_state[key_seccion] = filas_actualizadas


def _fila_para_borrador(fila: dict) -> dict:
    """Elimina banderas internas antes de persistir una fila como borrador."""
    limpia = {}
    for k, v in (fila or {}).items():
        if k.startswith("_"):
            continue
        limpia[k] = v
    return limpia


def _construir_datos_borrador(dias_labels: list[str]) -> dict:
    """Genera la estructura {dia: {Warm Up: [...], Work Out: [...]}} para guardar como borrador."""
    dias_data: dict[str, dict] = {}
    for idx_dia, _ in enumerate(dias_labels):
        dia_num = str(idx_dia + 1)
        dia_payload: dict[str, list] = {}
        for seccion in ("Warm Up", "Work Out"):
            key_seccion = f"rutina_dia_{idx_dia + 1}_{seccion.replace(' ', '_')}"
            if key_seccion not in st.session_state:
                continue
            filas = st.session_state.get(key_seccion, []) or []
            dia_payload[seccion] = [_fila_para_borrador(dict(fila)) for fila in filas]
        if dia_payload:
            dias_data[dia_num] = dia_payload
    return dias_data


def _cargar_borrador_en_session(borrador: dict):
    """Restaura los valores principales y los días de un borrador en session_state."""
    if not isinstance(borrador, dict):
        return

    st.session_state["crear_nombre_cliente"] = borrador.get("cliente", "")
    st.session_state["crear_correo_cliente"] = borrador.get("correo", "")
    st.session_state["objetivo"] = borrador.get("objetivo", "")
    st.session_state["crear_correo_entrenador"] = borrador.get("entrenador", st.session_state.get("correo", ""))

    fecha_str = borrador.get("fecha_inicio")
    if fecha_str:
        try:
            st.session_state["crear_fecha_inicio"] = datetime.strptime(fecha_str, "%Y-%m-%d").date()
        except Exception:
            pass

    semanas_val = borrador.get("semanas")
    if isinstance(semanas_val, int):
        st.session_state["crear_num_semanas"] = semanas_val

    dias_borrador = borrador.get("dias_data") or {}
    _vaciar_dias_en_session()
    for dia_num_str, secciones in dias_borrador.items():
        try:
            dia_idx = int(dia_num_str)
        except (TypeError, ValueError):
            continue
        for seccion in ("Warm Up", "Work Out"):
            key = f"rutina_dia_{dia_idx}_{seccion.replace(' ', '_')}"
            filas = secciones.get(seccion)
            if isinstance(filas, list):
                st.session_state[key] = filas

# ==========================
#   PÁGINA: CREAR RUTINAS
# ==========================
def crear_rutinas():
    rol = (st.session_state.get("rol") or "").lower()
    if rol not in ("entrenador", "admin", "administrador"):
        st.warning("No tienes permisos para crear rutinas.")
        return

    st.markdown("<h2 class='h-accent'>Crear nueva rutina</h2>", unsafe_allow_html=True)

    status_msg = st.session_state.pop("borrador_status_msg", None)
    if status_msg:
        status_type = st.session_state.pop("borrador_status_type", "success")
        if status_type == "success":
            st.success(status_msg)
        elif status_type == "warning":
            st.warning(status_msg)
        elif status_type == "error":
            st.error(status_msg)
        else:
            st.info(status_msg)

    borrador_activo_id = st.session_state.get("rutina_borrador_activo_id")
    if borrador_activo_id:
        borrador_label = (
            st.session_state.get("rutina_borrador_activo_cliente")
            or st.session_state.get("crear_correo_cliente")
            or ""
        )
        st.caption(f"📝 Editando borrador: {borrador_label} (ID {borrador_activo_id[:8]})")

    # --- Tarjeta de filtros principales ---
    st.markdown("<div class='card'>", unsafe_allow_html=True)

    ejercicios_dict = cargar_ejercicios()
    usuarios = cargar_usuarios()

    correo_login = (st.session_state.get("correo") or "").strip().lower()
    usuarios_map: dict[str, dict] = {}
    for u in usuarios:
        correo_u = (u.get("correo") or "").strip().lower()
        if correo_u:
            usuarios_map[correo_u] = u
            usuarios_map[correo_a_doc_id(correo_u)] = u

    if rol == "entrenador" and correo_login:
        empresa_entrenador = empresa_de_usuario(correo_login, usuarios_map)
        if empresa_entrenador == EMPRESA_ASESORIA:
            usuarios = [
                u for u in usuarios
                if (u.get("coach_responsable") or "").strip().lower() == correo_login
            ]
        elif empresa_entrenador == EMPRESA_MOTION:
            usuarios_filtrados = []
            for u in usuarios:
                correo_cli = (u.get("correo") or "").strip().lower()
                empresa_cli = empresa_de_usuario(correo_cli, usuarios_map)
                if empresa_cli == EMPRESA_MOTION:
                    usuarios_filtrados.append(u)
                elif empresa_cli == EMPRESA_DESCONOCIDA and (u.get("coach_responsable") or "").strip().lower() == correo_login:
                    usuarios_filtrados.append(u)
            usuarios = usuarios_filtrados
        else:
            usuarios = [
                u for u in usuarios
                if (u.get("coach_responsable") or "").strip().lower() == correo_login
            ]

    nombres = sorted(set(u.get("nombre", "") for u in usuarios))
    correos_entrenadores = sorted([
        u.get("correo", "") for u in usuarios if (u.get("rol", "") or "").lower() in ["entrenador", "admin", "administrador"]
    ])

    # === Selección de cliente/semana ===
    nombre_input = st.text_input("Escribe el nombre del cliente:", key="crear_nombre_cliente")
    coincidencias = [n for n in nombres if nombre_input.lower() in (n or "").lower()]
    nombre_sel = st.selectbox("Selecciona de la lista:", coincidencias) if coincidencias else ""

    correo_auto = next((u.get("correo", "") for u in usuarios if u.get("nombre") == nombre_sel), "")
    correo = st.text_input("Correo del cliente:", value=correo_auto, key="crear_correo_cliente")

    valor_defecto = proximo_lunes()
    sel = st.date_input(
        "Fecha de inicio de rutina:",
        value=valor_defecto,
        help="Solo se usan lunes. Si eliges otro día, se ajustará automáticamente al lunes de esa semana.",
        key="crear_fecha_inicio",
    )
    fecha_inicio = sel - timedelta(days=sel.weekday()) if sel.weekday() != 0 else sel
    if sel.weekday() != 0:
        st.markdown("<span class='badge badge--warn'>Ajustado automáticamente al lunes seleccionado</span>", unsafe_allow_html=True)

    semanas = st.number_input("Semanas de duración:", min_value=1, max_value=12, value=4, key="crear_num_semanas")

    objetivo = st.text_area("🎯 Objetivo de la rutina (opcional)", value=st.session_state.get("objetivo", ""))
    st.session_state["objetivo"] = objetivo

    entrenador = st.text_input(
        "Correo del entrenador responsable:",
        value=correo_login,
        disabled=True,
        key="crear_correo_entrenador",
    )
    # === 📥 Cargar rutina previa del MISMO cliente como base (opcional) ===
    with st.expander("📥 Cargar rutina previa como base", expanded=False):
        correo_base = (correo or "").strip().lower()
        if not correo_base:
            st.info("Primero selecciona el **nombre** (para autocompletar) y el **correo** del cliente.")
        else:
            db = get_db()
            # Trae semanas disponibles para este correo
            semanas_dict = {}
            try:
                for doc in db.collection("rutinas_semanales").where("correo", "==", correo_base).stream():
                    data = doc.to_dict() or {}
                    f = data.get("fecha_lunes")
                    if f:
                        semanas_dict[f] = doc.id
            except Exception as e:
                st.error(f"Error leyendo semanas: {e}")

            if not semanas_dict:
                st.info("Este cliente aún no tiene semanas guardadas en 'rutinas_semanales'.")
            else:
                semanas_ordenadas = sorted(semanas_dict.keys())

                # índice por defecto = última semana, acotado al rango válido
                default_idx = (len(semanas_ordenadas) - 1) if semanas_ordenadas else 0
                default_idx = max(0, min(default_idx, len(semanas_ordenadas) - 1)) if semanas_ordenadas else 0

                semana_base = st.selectbox(
                    "Semana a usar como base:",
                    semanas_ordenadas,
                    index=default_idx,
                    key="sel_semana_base_crear",   # clave única
                )

                if st.button("📥 Cargar como base (no guarda nada)", type="secondary", key="btn_cargar_base_crear"):
                    try:
                        doc_id = semanas_dict.get(semana_base)
                        if not doc_id:
                            st.warning("No se encontró el documento de esa semana.")
                        else:
                            doc_data = db.collection("rutinas_semanales").document(doc_id).get().to_dict() or {}
                            rutina_raw = doc_data.get("rutina", {}) or {}
                            # Solo días numéricos
                            rutina_base = {k: v for k, v in rutina_raw.items() if str(k).isdigit()}

                            # Carga en session_state
                            cargar_doc_en_session_base(rutina_base)

                            st.success(f"Rutina de la semana {semana_base} cargada como base ✅")

                            # 🔁 Importante: forzar un rerun inmediato para evitar desincronización
                            # de índices en selectboxes (causa típica de 'list index out of range').
                            st.rerun()
                    except Exception as e:
                        import traceback
                        st.error(f"No se pudo cargar la rutina base: {e}")
                        st.code("".join(traceback.format_exc()))

    with st.expander("📝 Borradores en progreso", expanded=False):
        correo_borrador = (st.session_state.get("crear_correo_cliente") or correo or "").strip().lower()
        usuario_actual = (st.session_state.get("correo") or "").strip().lower()

        if not correo_borrador:
            st.info("Ingresa el nombre y correo del cliente para ver borradores guardados.")
        else:
            try:
                db = get_db()
                query = db.collection(BORRADORES_COLLECTION).where("correo", "==", correo_borrador)
                borradores_raw = []
                for doc in query.stream():
                    data = doc.to_dict() or {}
                    creador_doc = (data.get("creado_por") or "").strip().lower()
                    if usuario_actual and creador_doc and creador_doc != usuario_actual:
                        continue
                    data["_id"] = doc.id
                    borradores_raw.append(data)
            except Exception as e:
                st.error(f"Error al leer borradores: {e}")
                borradores_raw = []

            if not borradores_raw:
                st.info("No hay borradores guardados para este cliente.")
            else:
                def _timestamp_to_dt(value):
                    if hasattr(value, "to_datetime"):
                        value = value.to_datetime()
                    if isinstance(value, datetime):
                        if value.tzinfo is not None:
                            return value.astimezone(timezone.utc).replace(tzinfo=None)
                        return value
                    return None

                def _formato_borrador(idx: int) -> str:
                    borrador = borradores_raw[idx]
                    fecha_inicio_lbl = borrador.get("fecha_inicio") or "Sin fecha"
                    ts = _timestamp_to_dt(borrador.get("updated_at") or borrador.get("created_at"))
                    updated_lbl = ts.strftime("%Y-%m-%d %H:%M") if ts else "Sin actualización"

                    dias_data = borrador.get("dias_data") or {}
                    dias_contenido = 0
                    total_ejercicios = 0
                    for secciones in dias_data.values():
                        dia_tiene_datos = False
                        if isinstance(secciones, dict):
                            for lista in secciones.values():
                                if not isinstance(lista, list):
                                    continue
                                for fila in lista:
                                    if isinstance(fila, dict) and (
                                        (fila.get("Ejercicio") or "").strip()
                                        or (fila.get("BuscarEjercicio") or "").strip()
                                    ):
                                        dia_tiene_datos = True
                                        total_ejercicios += 1
                        if dia_tiene_datos:
                            dias_contenido += 1

                    return (
                        f"Inicio {fecha_inicio_lbl} · {dias_contenido} día(s) · "
                        f"{total_ejercicios} ejercicio(s) · Última ed. {updated_lbl}"
                    )

                borradores_raw.sort(
                    key=lambda d: _timestamp_to_dt(d.get("updated_at") or d.get("created_at")) or datetime.min,
                    reverse=True,
                )
                opciones = list(range(len(borradores_raw)))
                idx_sel = st.selectbox(
                    "Selecciona un borrador:",
                    opciones,
                    format_func=_formato_borrador,
                    key="seleccion_borrador_crear",
                )

                cols_borradores = st.columns([1, 1], gap="small")
                if cols_borradores[0].button("Cargar borrador", key="btn_cargar_borrador"):
                    _cargar_borrador_en_session(borradores_raw[idx_sel])
                    st.session_state["rutina_borrador_activo_id"] = borradores_raw[idx_sel]["_id"]
                    st.session_state["rutina_borrador_activo_cliente"] = (
                        borradores_raw[idx_sel].get("cliente")
                        or borradores_raw[idx_sel].get("correo")
                        or ""
                    )
                    st.session_state["borrador_status_msg"] = "Borrador cargado en el editor."
                    st.session_state["borrador_status_type"] = "success"
                    _trigger_rerun()

                if cols_borradores[1].button("Eliminar borrador", key="btn_eliminar_borrador"):
                    doc_id = borradores_raw[idx_sel]["_id"]
                    try:
                        db.collection(BORRADORES_COLLECTION).document(doc_id).delete()
                        if st.session_state.get("rutina_borrador_activo_id") == doc_id:
                            st.session_state.pop("rutina_borrador_activo_id", None)
                            st.session_state.pop("rutina_borrador_activo_cliente", None)
                        st.session_state["borrador_status_msg"] = "Borrador eliminado."
                        st.session_state["borrador_status_type"] = "success"
                    except Exception as e:
                        st.session_state["borrador_status_msg"] = f"No se pudo eliminar el borrador: {e}"
                        st.session_state["borrador_status_type"] = "error"
                    _trigger_rerun()

    st.markdown("</div>", unsafe_allow_html=True)  # /card
    st.markdown("<div class='hr-light'></div>", unsafe_allow_html=True)

    st.markdown("<h3 class='h-accent'>Días de entrenamiento</h3>", unsafe_allow_html=True)

    dias_labels = ["Día 1", "Día 2", "Día 3", "Día 4", "Día 5"]
    tabs = st.tabs(dias_labels)
    dias = dias_labels  # alias

    BASE_HEADERS = [
    "Circuito", "Buscar Ejercicio", "Ejercicio", "Detalle",
    "Series", "Repeticiones", "Peso", "RIR (Min/Max)", "Progresión", "Copiar", "Video?"
    ]
    BASE_SIZES = [1, 2.5, 2.5, 2.0, 0.7, 1.4, 1.0, 1.4, 1.0, 0.6, 0.6]  
    # 👆 aquí puse 1.6 en RIR para que quepan dos casillas

    columnas_tabla = [
        "Circuito", "Sección", "Ejercicio", "Detalle", "Series", "Repeticiones",
        "Peso", "Tiempo", "Velocidad", "Descanso", "RIR", "Tipo", "Video"
    ]

    progresion_activa = st.radio("Progresión activa", ["Progresión 1", "Progresión 2", "Progresión 3"],
                                 horizontal=True, index=0)

    for i, tab in enumerate(tabs):
        with tab:
            dia_key = f"rutina_dia_{i+1}"

            for seccion in ["Warm Up", "Work Out"]:
                key_seccion = f"{dia_key}_{seccion.replace(' ', '_')}"
                if key_seccion not in st.session_state:
                    st.session_state[key_seccion] = [{k: "" for k in columnas_tabla} for _ in range(6)]
                    for f in st.session_state[key_seccion]:
                        f["Sección"] = seccion
                        # normalizar circuito inicial según sección
                        f["Circuito"] = clamp_circuito_por_seccion(f.get("Circuito","") or "", seccion)

                # --- Encabezado de sección con toggles ---
                st.markdown("<div class='card'>", unsafe_allow_html=True)
                # +1 columna a la derecha para el botón "Crear ejercicio"
                head_cols = st.columns([6.9, 1.1, 1.2, 1.2, 1.6], gap="small")

                with head_cols[0]:
                    st.markdown(f"<h4 class='h-accent' style='margin-top:2px'>{seccion}</h4>", unsafe_allow_html=True)
                with head_cols[1]:
                    show_tiempo_sec = st.toggle(
                        "Tiempo",
                        key=f"show_tiempo_{key_seccion}",
                        value=st.session_state.get(f"show_tiempo_{key_seccion}", False),
                    )
                with head_cols[2]:
                    show_vel_sec = st.toggle(
                        "Velocidad",
                        key=f"show_vel_{key_seccion}",
                        value=st.session_state.get(f"show_vel_{key_seccion}", False),
                    )
                with head_cols[3]:
                    show_descanso_sec = st.toggle(
                        "Descanso",
                        key=f"show_desc_{key_seccion}",
                        value=st.session_state.get(f"show_desc_{key_seccion}", False),
                    )
                
                # --- Botón/Popover: "＋" Crear ejercicio (encabezado de sección) con permisos ---
                if _tiene_permiso_agregar():
                    pop = head_cols[4].popover("＋", use_container_width=True)  # ← sin key (tu Streamlit no lo soporta)
                    with pop:
                        st.markdown("**📌 Crear o Editar Ejercicio (rápido)**")

                        # === Catálogos (mismos que admin) ===
                        try:
                            cat = get_catalogos()
                        except Exception as e:
                            st.error(f"No pude cargar catálogos: {e}")
                            cat = {}
                        catalogo_carac   = cat.get("caracteristicas", []) or []
                        catalogo_patron  = cat.get("patrones_movimiento", []) or []
                        catalogo_grupo_p = cat.get("grupo_muscular_principal", []) or []
                        catalogo_grupo_s = cat.get("grupo_muscular_secundario", []) or []

                        # === Select con opción “➕ Agregar nuevo …”
                        def _combo_con_agregar(label: str, opciones: list[str], key_base: str, valor_inicial: str = "") -> str:
                            SENT = "➕ Agregar nuevo…"
                            base_opts = sorted(opciones or [])
                            if valor_inicial and valor_inicial not in base_opts:
                                base_opts.append(valor_inicial)
                            opts = ["— Selecciona —"] + base_opts + [SENT]
                            index_default = 0
                            if valor_inicial:
                                try:
                                    index_default = opts.index(valor_inicial)
                                except ValueError:
                                    index_default = 0

                            sel = st.selectbox(label, opts, index=index_default, key=f"{key_base}_sel_{key_seccion}")
                            if sel == SENT:
                                st.markdown("<div class='card'>", unsafe_allow_html=True)
                                nuevo = st.text_input(f"Ingresar nuevo valor para {label.lower()}:", key=f"{key_base}_nuevo_{key_seccion}")
                                cols_add = st.columns([1, 1, 6])
                                with cols_add[0]:
                                    if st.button("Guardar", key=f"{key_base}_guardar_{key_seccion}", type="primary"):
                                        valor_limpio = (nuevo or "").strip()
                                        if valor_limpio:
                                            t = label.lower()
                                            if "característica" in t or "caracteristica" in t:
                                                tipo = "caracteristicas"
                                            elif "patrón" in t or "patron" in t:
                                                tipo = "patrones_movimiento"
                                            elif "grupo muscular secundario" in t:
                                                tipo = "grupo_muscular_secundario"
                                            elif "grupo muscular principal" in t:
                                                tipo = "grupo_muscular_principal"
                                            else:
                                                tipo = "otros_catalogos"
                                            add_item(tipo, valor_limpio)
                                            st.success(f"Agregado: {valor_limpio}")
                                            st.cache_data.clear()
                                            st.rerun()
                                st.markdown("</div>", unsafe_allow_html=True)
                                return ""
                            elif sel == "— Selecciona —":
                                return ""
                            else:
                                return sel

                        # === Prefill con la última búsqueda de ESTA sección ===
                        _prefill_detalle = ""
                        _prefix_busca = f"buscar_{i}_{seccion.replace(' ','_')}_"
                        try:
                            for kss, vss in st.session_state.items():
                                if isinstance(vss, str) and kss.startswith(_prefix_busca) and vss.strip():
                                    _prefill_detalle = vss.strip()
                                    break
                        except Exception:
                            pass

                        # === FORMULARIO (igual que admin) ===
                        c1, c2 = st.columns(2)
                        with c1:
                            marca = st.text_input("Marca (opcional):", key=f"marca_top_{key_seccion}").strip()
                        with c2:
                            maquina = st.text_input("Máquina (opcional):", key=f"maquina_top_{key_seccion}").strip()

                        detalle = st.text_input("Detalle:", value=_prefill_detalle, key=f"detalle_top_{key_seccion}")

                        c3, c4 = st.columns(2)
                        with c3:
                            caracteristica = _combo_con_agregar("Característica",        catalogo_carac,   key_base=f"carac_top_{i}_{seccion}")
                        with c4:
                            patron         = _combo_con_agregar("Patrón de Movimiento",  catalogo_patron,  key_base=f"patron_top_{i}_{seccion}")

                        c5, c6 = st.columns(2)
                        with c5:
                            grupo_p        = _combo_con_agregar("Grupo Muscular Principal",  catalogo_grupo_p, key_base=f"grupoP_top_{i}_{seccion}")
                        with c6:
                            grupo_s        = _combo_con_agregar("Grupo Muscular Secundario", catalogo_grupo_s, key_base=f"grupoS_top_{i}_{seccion}")

                        # Link de video (opcional) — NUEVO
                        video_url = st.text_input(
                            "URL del video (opcional):",
                            key=f"video_top_{key_seccion}",
                            placeholder="https://youtu.be/…"
                        )

                        # Preview de implemento/pesos si hay Marca + Máquina
                        id_impl_preview = ""
                        if marca and maquina:
                            try:
                                # usa tu helper si lo tienes; si no, pega el helper del bloque 2
                                id_impl_preview = _resolver_id_implemento(marca, maquina)
                                if id_impl_preview:
                                    snap_impl = get_db().collection("implementos").document(str(id_impl_preview)).get()
                                    if snap_impl.exists:
                                        data_impl = snap_impl.to_dict() or {}
                                        st.success(f"Implemento detectado: ID **{id_impl_preview}** · {data_impl.get('marca','')} – {data_impl.get('maquina','')}")
                                        pesos = data_impl.get("pesos", [])
                                        if isinstance(pesos, dict):
                                            pesos_list = [v for _, v in sorted(pesos.items(), key=lambda kv: int(kv[0]))]
                                        elif isinstance(pesos, list):
                                            pesos_list = pesos
                                        else:
                                            pesos_list = []
                                        if pesos_list:
                                            st.caption("Pesos disponibles (preview): " + ", ".join(str(p) for p in pesos_list))
                            except Exception:
                                pass

                        # Nombre compuesto (solo lectura)
                        nombre_ej = " ".join([x for x in [marca, maquina, detalle] if x]).strip()
                        st.text_input("Nombre completo del ejercicio:", value=nombre_ej, key=f"nombre_top_{key_seccion}", disabled=True)

                        publico_default = True if es_admin() else False
                        publico_check   = st.checkbox("Hacer público (visible para todos los entrenadores)", value=publico_default, key=f"pub_chk_{key_seccion}")

                        # Guardar
                        cols_btn_save = st.columns([1,3])
                        with cols_btn_save[0]:
                            if st.button("💾 Guardar Ejercicio", key=f"btn_guardar_top_{key_seccion}", type="primary", use_container_width=True):
                                faltantes = [etq for etq, val in {
                                    "Característica": caracteristica,
                                    "Patrón de Movimiento": patron,
                                    "Grupo Muscular Principal": grupo_p
                                }.items() if not (val or "").strip()]
                                if faltantes:
                                    st.warning("⚠️ Completa: " + ", ".join(faltantes))
                                else:
                                    nombre_final = (nombre_ej or detalle or maquina or marca or "").strip()
                                    if not nombre_final:
                                        st.warning("⚠️ El campo 'nombre' es obligatorio (usa al menos Detalle/Máquina/Marca).")
                                    else:
                                        id_impl_final = _resolver_id_implemento(marca, maquina) if (marca and maquina) else ""

                                        payload = {
                                            "nombre": nombre_final,
                                            "marca":  marca,
                                            "maquina": maquina,
                                            "detalle": detalle,
                                            "caracteristica": caracteristica,
                                            "patron_de_movimiento": patron,
                                            "grupo_muscular_principal":  grupo_p,
                                            "grupo_muscular_secundario": grupo_s or "",
                                            "id_implemento": id_impl_final,
                                            "video": (video_url or "").strip(),          # ← guarda el link de video
                                            "publico_flag": bool(publico_check),
                                        }
                                        try:
                                            guardar_ejercicio_firestore(nombre_final, payload)

                                            # refresca cache local para búsquedas/pesos/video inmediato
                                            ejercicios_dict[nombre_final] = {
                                                "nombre": nombre_final,
                                                "marca":  marca,
                                                "maquina": maquina,
                                                "detalle": detalle,
                                                "caracteristica": caracteristica,
                                                "patron_de_movimiento": patron,
                                                "grupo_muscular_principal":  grupo_p,
                                                "grupo_muscular_secundario": grupo_s or "",
                                                "id_implemento": id_impl_final if id_impl_final else "",
                                                "publico": bool(publico_check),
                                                "video": (video_url or "").strip(),
                                            }
                                            st.success(f"✅ Ejercicio '{nombre_final}' guardado correctamente")
                                            st.cache_data.clear()
                                            st.rerun()
                                        except Exception as e:
                                            st.error(f"❌ Error al guardar: {e}")
                else:
                    head_cols[4].button("＋", use_container_width=True, disabled=True)
                    st.caption("Solo *Administrador* o *Entrenador* pueden crear ejercicios.")

                # ======= Construcción dinámica de columnas =======
                headers = BASE_HEADERS.copy()
                sizes = BASE_SIZES.copy()

                # antes
                # rir_idx = headers.index("RIR")

                # después
                rir_idx = headers.index("RIR (Min/Max)")


                if show_tiempo_sec:
                    headers.insert(rir_idx, "Tiempo")
                    sizes.insert(rir_idx, 0.9)
                    rir_idx += 1
                if show_vel_sec:
                    headers.insert(rir_idx, "Velocidad")
                    sizes.insert(rir_idx, 1.0)
                    rir_idx += 1
                if show_descanso_sec:
                    headers.insert(rir_idx, "Descanso")
                    sizes.insert(rir_idx, 0.9)

                # ---------- FORM por sección ----------
                with st.form(f"form_{key_seccion}", clear_on_submit=False):
                    n_filas = st.number_input(
                        "Filas", key=f"num_{key_seccion}", min_value=0, max_value=30,
                        value=len(st.session_state[key_seccion]), step=1
                    )
                    _ensure_len(st.session_state[key_seccion], n_filas, {k: "" for k in columnas_tabla})
                    st.markdown("")

                    # Encabezados centrados
                    header_cols = st.columns(sizes)
                    for c, title in zip(header_cols, headers):
                        c.markdown(f"<div class='header-center'>{title}</div>", unsafe_allow_html=True)

                    # ------ Render filas ------
                    for idx, fila in enumerate(st.session_state[key_seccion]):
                        key_entrenamiento = f"{i}_{seccion.replace(' ','_')}_{idx}"
                        cols = st.columns(sizes)
                        pos = {h: k for k, h in enumerate(headers)}

                        # === Circuito (RESTRINGIDO POR SECCIÓN) ===
                        opciones_circuito = get_circuit_options(seccion)
                        # normalizar si el valor actual no es válido
                        circ_actual = fila.get("Circuito") or ""
                        if circ_actual not in opciones_circuito:
                            circ_actual = opciones_circuito[0]
                            fila["Circuito"] = circ_actual

                        fila["Circuito"] = cols[pos["Circuito"]].selectbox(
                            "", opciones_circuito,
                            index=(opciones_circuito.index(circ_actual) if circ_actual in opciones_circuito else 0),
                            key=f"circ_{key_entrenamiento}",
                            label_visibility="collapsed"
                        )

                        # =======================
                        # Buscar + Ejercicio (INLINE con alta si no existe)
                        # =======================
                        # --- Buscador de ejercicios (Warm Up y Work Out)
                        buscar_key = f"buscar_{key_entrenamiento}"
                        if buscar_key not in st.session_state:
                            st.session_state[buscar_key] = fila.get("BuscarEjercicio", "")
                        previo_buscar = fila.get("BuscarEjercicio", "")
                        palabra = cols[pos["Buscar Ejercicio"]].text_input(
                            "",
                            value=st.session_state[buscar_key],
                            key=buscar_key,
                            label_visibility="collapsed", placeholder="Buscar ejercicio…"
                        )
                        if normalizar_texto(palabra) != normalizar_texto(previo_buscar):
                            st.session_state.pop(f"select_{key_entrenamiento}", None)
                            fila["_exact_on_load"] = False
                        fila["BuscarEjercicio"] = palabra

                        nombre_original = (fila.get("Ejercicio","") or "").strip()
                        exact_on_load = bool(fila.get("_exact_on_load", False))

                        def _buscar_fuzzy_local(q: str) -> list[str]:
                            if not q.strip():
                                return []
                            tokens = normalizar_texto(q).split()
                            res = []
                            for n in ejercicios_dict.keys():
                                nn = normalizar_texto(n)
                                if all(t in nn for t in tokens):
                                    res.append(n)
                            return res

                        if exact_on_load:
                            if (not palabra.strip()) or (normalizar_texto(palabra) == normalizar_texto(nombre_original)):
                                ejercicios_encontrados = [nombre_original] if nombre_original else []
                            else:
                                ejercicios_encontrados = _buscar_fuzzy_local(palabra)
                                fila["_exact_on_load"] = False
                        else:
                            ejercicios_encontrados = _buscar_fuzzy_local(palabra)

                        if not ejercicios_encontrados and nombre_original:
                            ejercicios_encontrados = [nombre_original]

                        vistos = set()
                        ejercicios_encontrados = [e for e in ejercicios_encontrados if not (e in vistos or vistos.add(e))]

                        if not ejercicios_encontrados and palabra.strip():
                            ejercicios_encontrados = [palabra.strip()]
                        elif not ejercicios_encontrados:
                            ejercicios_encontrados = ["(sin resultados)"]

                        seleccionado = cols[pos["Ejercicio"]].selectbox(
                            "",
                            ejercicios_encontrados,
                            key=f"select_{key_entrenamiento}",
                            index=0,
                            label_visibility="collapsed"
                        )

                        if seleccionado == "(sin resultados)":
                            fila["Ejercicio"] = palabra.strip()
                            fila["Video"] = (ejercicios_dict.get(fila["Ejercicio"], {}) or {}).get("video", "").strip()
                        else:
                            fila["Ejercicio"] = seleccionado
                            fila["Video"] = (ejercicios_dict.get(seleccionado, {}) or {}).get("video", "").strip()
                        
                        
                        # Detalle
                        fila["Detalle"] = cols[pos["Detalle"]].text_input(
                            "", value=fila.get("Detalle",""),
                            key=f"det_{key_entrenamiento}", label_visibility="collapsed", placeholder="Notas (opcional)"
                        )
                        # Series
                        fila["Series"] = cols[pos["Series"]].text_input(
                            "", value=fila.get("Series",""),
                            key=f"ser_{key_entrenamiento}", label_visibility="collapsed", placeholder="N°"
                        )
                        # Reps min/max en una celda
                        cmin, cmax = cols[pos["Repeticiones"]].columns(2)
                        fila["RepsMin"] = cmin.text_input(
                            "", value=str(fila.get("RepsMin","")),
                            key=f"rmin_{key_entrenamiento}", label_visibility="collapsed", placeholder="Min"
                        )
                        fila["RepsMax"] = cmax.text_input(
                            "", value=str(fila.get("RepsMax","")),
                            key=f"rmax_{key_entrenamiento}", label_visibility="collapsed", placeholder="Max"
                        )

                        # Peso (select si implemento tiene pesos)
                        peso_widget_key = f"peso_{key_entrenamiento}"
                        peso_value = fila.get("Peso","")
                        pesos_disponibles = []
                        usar_text_input = True
                        try:
                            nombre_ej = fila.get("Ejercicio","")
                            ej_doc = ejercicios_dict.get(nombre_ej, {}) or {}
                            id_impl = str(ej_doc.get("id_implemento","") or "")
                            if id_impl and id_impl != "1" and id_impl in IMPLEMENTOS:
                                pesos_disponibles = IMPLEMENTOS[id_impl].get("pesos", []) or []
                                usar_text_input = not bool(pesos_disponibles)
                        except Exception:
                            usar_text_input = True

                        if not usar_text_input and pesos_disponibles:
                            opciones_peso = [str(p) for p in pesos_disponibles]
                            # Normaliza el valor actual al set de opciones
                            if str(peso_value) not in opciones_peso and opciones_peso:
                                peso_value = opciones_peso[0]
                            # Índice seguro (0 si no está)
                            idx_peso = opciones_peso.index(str(peso_value)) if str(peso_value) in opciones_peso else 0

                            fila["Peso"] = cols[pos["Peso"]].selectbox(
                                "",
                                options=opciones_peso,
                                index=idx_peso,                  # ← evita index out of range
                                key=peso_widget_key,
                                label_visibility="collapsed"
                            )
                        else:
                            fila["Peso"] = cols[pos["Peso"]].text_input(
                                "", value=str(peso_value),
                                key=peso_widget_key, label_visibility="collapsed", placeholder="Kg"
                            )


                        # Tiempo / Velocidad / Descanso dinámicos
                        if "Tiempo" in pos:
                            fila["Tiempo"] = cols[pos["Tiempo"]].text_input(
                                "", value=str(fila.get("Tiempo","")),
                                key=f"tiempo_{key_entrenamiento}", label_visibility="collapsed", placeholder="Seg"
                            )
                        else:
                            fila.setdefault("Tiempo","")

                        if "Velocidad" in pos:
                            fila["Velocidad"] = cols[pos["Velocidad"]].text_input(
                                "", value=str(fila.get("Velocidad","")),
                                key=f"vel_{key_entrenamiento}", label_visibility="collapsed", placeholder="m/s"
                            )
                        else:
                            fila.setdefault("Velocidad","")

                        if "Descanso" in pos:
                            opciones_descanso = ["", "1", "2", "3", "4", "5"]
                            valor_actual_desc = str(fila.get("Descanso", "")).strip()
                            if " " in valor_actual_desc:
                                valor_actual_desc = valor_actual_desc.split()[0]
                            idx_desc = opciones_descanso.index(valor_actual_desc) if valor_actual_desc in opciones_descanso else 0
                            fila["Descanso"] = cols[pos["Descanso"]].selectbox(
                                "",
                                options=opciones_descanso,
                                index=idx_desc,
                                key=f"desc_{key_entrenamiento}",
                                label_visibility="collapsed",
                                help="Minutos de descanso (1–5). Deja vacío si no aplica."
                            )
                        else:
                            fila.setdefault("Descanso","")

                        # RIR
                        cmin_rir, cmax_rir = cols[pos["RIR (Min/Max)"]].columns(2)
                        fila["RirMin"] = cmin_rir.text_input(
                            "", value=str(fila.get("RirMin","")),
                            key=f"rirmin_{key_entrenamiento}", label_visibility="collapsed", placeholder="Min"
                        )
                        fila["RirMax"] = cmax_rir.text_input(
                            "", value=str(fila.get("RirMax","")),
                            key=f"rirmax_{key_entrenamiento}", label_visibility="collapsed", placeholder="Max"
                        )


                        # Progresiones
                        prog_cell = cols[pos["Progresión"]].columns([1, 1, 1])
                        mostrar_progresion = prog_cell[1].checkbox("", key=f"prog_check_{key_entrenamiento}_{idx}")

                        copy_cell = cols[pos["Copiar"]].columns([1, 1, 1])
                        mostrar_copia = copy_cell[1].checkbox("", key=f"copy_check_{key_entrenamiento}_{idx}")

                        # ===== Indicador de Video (✅ / ❌) al final =====
                        # ===== Indicador de Video (checkbox deshabilitado) =====
                        # esto va dentro del loop de filas, DESPUÉS de actualizar fila["Ejercicio"] / fila["Video"]
                        if "Video?" in pos:   # 👈 nombre EXACTO del header
                            nombre_ej = str(fila.get("Ejercicio", "")).strip()
                            has_video = bool((fila.get("Video") or "").strip()) or tiene_video(nombre_ej, ejercicios_dict)

                            cols[pos["Video?"]].checkbox(
                                "",
                                value=has_video,
                                key=f"video_flag_{i}_{seccion}_{idx}",   # 👈 key 100% única
                                disabled=True
                            )



                        if mostrar_progresion:
                            st.markdown("<div class='hr-light'></div>", unsafe_allow_html=True)
                            st.markdown("<div class='h-accent'>Progresiones activas</div>", unsafe_allow_html=True)
                            p = int(progresion_activa.split()[-1])
                            pcols = st.columns(4)

                            variable_key = f"Variable_{p}"
                            cantidad_key = f"Cantidad_{p}"
                            operacion_key = f"Operacion_{p}"
                            semanas_key = f"Semanas_{p}"

                            opciones_var = ["", "peso", "velocidad", "tiempo", "descanso", "rir", "series", "repeticiones"]
                            opciones_ope = ["", "multiplicacion", "division", "suma", "resta"]

                            fila[variable_key] = pcols[0].selectbox(
                                f"Variable {p}",
                                opciones_var,
                                index=(opciones_var.index(fila.get(variable_key, "")) if fila.get(variable_key, "") in opciones_var else 0),
                                key=f"var{p}_{key_entrenamiento}_{idx}"
                            )
                            fila[operacion_key] = pcols[1].selectbox(
                                f"Operación {p}", opciones_ope,
                                index=(opciones_ope.index(fila.get(operacion_key, "")) if fila.get(operacion_key, "") in opciones_ope else 0),
                                key=f"ope{p}_{key_entrenamiento}_{idx}"
                            )
                            fila[cantidad_key] = pcols[2].text_input(
                                f"Cantidad {p}", value=fila.get(cantidad_key, ""), key=f"cant{p}_{key_entrenamiento}_{idx}"
                            )
                            fila[semanas_key] = pcols[3].text_input(
                                f"Semanas {p}", value=fila.get(semanas_key, ""), key=f"sem{p}_{key_entrenamiento}_{idx}"
                            )

                            cond_cols = st.columns([1.2, 1.2, 1])
                            cond_cols[0].markdown("<small>Condición</small>", unsafe_allow_html=True)
                            cond_var_key = f"condvar{p}_{key_entrenamiento}_{idx}"
                            cond_op_key = f"condop{p}_{key_entrenamiento}_{idx}"
                            cond_val_key = f"condval{p}_{key_entrenamiento}_{idx}"
                            opciones_cond_var = ["", "rir"]
                            opciones_cond_op = ["", ">", "<", ">=", "<="]
                            fila[f"CondicionVar_{p}"] = cond_cols[0].selectbox(
                                "Variable condición",
                                opciones_cond_var,
                                index=(opciones_cond_var.index(fila.get(f"CondicionVar_{p}", "")) if fila.get(f"CondicionVar_{p}", "") in opciones_cond_var else 0),
                                key=cond_var_key,
                                label_visibility="collapsed"
                            )
                            fila[f"CondicionOp_{p}"] = cond_cols[1].selectbox(
                                "Operador condición",
                                opciones_cond_op,
                                index=(opciones_cond_op.index(fila.get(f"CondicionOp_{p}", "")) if fila.get(f"CondicionOp_{p}", "") in opciones_cond_op else 0),
                                key=cond_op_key,
                                label_visibility="collapsed"
                            )
                            fila[f"CondicionValor_{p}"] = cond_cols[2].text_input(
                                "", value=str(fila.get(f"CondicionValor_{p}", "") or ""), key=cond_val_key, label_visibility="collapsed"
                            )

                        # Copia entre días
                        if mostrar_copia:
                            copiar_cols = st.columns([1, 3])
                            st.caption("Selecciona día(s) y presiona **Actualizar sección** para copiar.")
                            dias_copia = copiar_cols[1].multiselect(
                                "Días destino", dias,
                                key=f"multiselect_{key_entrenamiento}_{idx}"
                            )
                            st.session_state[f"do_copy_{key_entrenamiento}_{idx}"] = True
                        else:
                            st.session_state.pop(f"multiselect_{key_entrenamiento}_{idx}", None)
                            st.session_state.pop(f"do_copy_{key_entrenamiento}_{idx}", None)

                    action_cols = st.columns([1,5,1], gap="small")
                    with action_cols[0]:
                        submitted = st.form_submit_button("Actualizar sección", type="primary")
                    with action_cols[2]:
                        limpiar_clicked = st.form_submit_button("Limpiar sección", type="secondary")

                    pending_key = f"pending_clear_{key_seccion}"

                    if limpiar_clicked:
                        if st.session_state.get(pending_key):
                            fila_vacia = {k: "" for k in columnas_tabla}
                            fila_vacia["Sección"] = seccion
                            fila_vacia["Circuito"] = clamp_circuito_por_seccion(fila_vacia.get("Circuito","") or "", seccion)
                            fila_vacia["BuscarEjercicio"] = ""
                            fila_vacia["Ejercicio"] = ""
                            st.session_state[key_seccion] = [fila_vacia]

                            prefix = f"{i}_{seccion.replace(' ','_')}_"
                            for key in list(st.session_state.keys()):
                                if key.startswith(f"multiselect_{prefix}") or key.startswith(f"do_copy_{prefix}"):
                                    st.session_state.pop(key, None)
                            st.session_state.pop(pending_key, None)
                            st.success("Sección limpiada ✅")
                            st.rerun()
                        else:
                            st.session_state[pending_key] = True

                    if st.session_state.get(pending_key):
                        st.warning("Vuelve a presionar **Limpiar sección** para confirmar el borrado.")

                    if submitted:
                        st.session_state.pop(pending_key, None)
                        # Normalización final de circuitos y copia
                        for idx, fila in enumerate(st.session_state[key_seccion]):
                            # Clamp circuito según sección por si entró algo viejo en session_state
                            fila["Circuito"] = clamp_circuito_por_seccion(fila.get("Circuito","") or "", seccion)

                            key_entrenamiento = f"{i}_{seccion.replace(' ','_')}_{idx}"
                            do_copy_key = f"do_copy_{key_entrenamiento}_{idx}"
                            multisel_key = f"multiselect_{key_entrenamiento}_{idx}"
                            if st.session_state.get(do_copy_key):
                                dias_copia = st.session_state.get(multisel_key, [])
                                if dias_copia:
                                    for dia_destino in dias_copia:
                                        idx_dia = dias.index(dia_destino)
                                        key_destino = f"rutina_dia_{idx_dia + 1}_{seccion.replace(' ', '_')}"
                                        if key_destino not in st.session_state:
                                            st.session_state[key_destino] = []
                                        nuevo_ejercicio = {k: v for k, v in fila.items()}
                                        # asegurar tamaño
                                        while len(st.session_state[key_destino]) <= idx:
                                            fila_vacia = {k: "" for k in columnas_tabla}
                                            fila_vacia["Sección"] = seccion
                                            # clamp circuito también en destino
                                            fila_vacia["Circuito"] = clamp_circuito_por_seccion(fila_vacia.get("Circuito","") or "", seccion)
                                            st.session_state[key_destino].append(fila_vacia)
                                        # clamp destino
                                        nuevo_ejercicio["Circuito"] = clamp_circuito_por_seccion(nuevo_ejercicio.get("Circuito","") or "", seccion)
                                        st.session_state[key_destino][idx] = nuevo_ejercicio
                        st.success("Sección actualizada ✅")
                st.markdown("</div>", unsafe_allow_html=True)  # /card

            st.markdown("<div class='hr-light'></div>", unsafe_allow_html=True)

    # ======= Panel de análisis =======
    analysis_controls = st.container()
    with analysis_controls:
        st.markdown("<div class='sidebar-card'>", unsafe_allow_html=True)
        st.markdown("### 🧮 Series por categoría")
        opcion_categoria = st.selectbox("Categoría para análisis:", ["grupo_muscular_principal", "patron_de_movimiento"])
        st.markdown("</div>", unsafe_allow_html=True)

    ejercicios_dict = cargar_ejercicios()  # asegurar en scope
    contador = {}
    nombres_originales = {}
    dias_keys = [k for k in st.session_state if k.startswith("rutina_dia_") and "_Work_Out" in k]
    for key_dia in dias_keys:
        ejercicios = st.session_state.get(key_dia, [])
        for ejercicio in ejercicios:
            nombre_raw = str(ejercicio.get("Ejercicio", "")).strip()
            nombre_norm = normalizar_texto(nombre_raw)
            try:
                series = int(ejercicio.get("Series", 0))
            except:
                series = 0
            if not nombre_norm: continue
            coincidencias = [
                data for nombre, data in ejercicios_dict.items()
                if normalizar_texto(nombre) == nombre_norm
            ]
            data = coincidencias[0] if coincidencias else None
            if not data:
                categoria_valor = "(no encontrado)"
            else:
                try:
                    categoria_valor = data.get(opcion_categoria, "(sin dato)")
                except:
                    categoria_valor = "(error)"
            categoria_norm = normalizar_texto(str(categoria_valor))
            if categoria_norm in contador:
                contador[categoria_norm] += series
                nombres_originales[categoria_norm].add(categoria_valor)
            else:
                contador[categoria_norm] = series
                nombres_originales[categoria_norm] = {categoria_valor}

    analysis_results = st.container()
    with analysis_results:
        st.markdown("<div class='sidebar-card'>", unsafe_allow_html=True)
        if contador:
            df = pd.DataFrame({
                "Categoría": [
                    ", ".join(sorted(cat.replace("_", " ").capitalize() for cat in nombres_originales[k]))
                    for k in contador
                ],
                "Series": [contador[k] for k in contador]
            }).sort_values("Series", ascending=False)
            st.dataframe(df, use_container_width=True, hide_index=True)
        else:
            st.info("No hay datos de series aún.")
        st.markdown("</div>", unsafe_allow_html=True)

    # ======= Previsualización =======
    def _f(v):
        try:
            s = str(v).strip().replace(",", ".")
            if s == "": return None
            if "-" in s: s = s.split("-", 1)[0].strip()
            return float(s)
        except: return None

    if st.button("🔍 Previsualizar rutina", type="secondary"):
        st.markdown("<h3 class='h-accent'>📅 Previsualización de todas las semanas con progresiones aplicadas</h3>", unsafe_allow_html=True)
        for semana_idx in range(1, int(semanas) + 1):
            with st.expander(f"Semana {semana_idx}"):
                for i, dia_nombre in enumerate(dias):
                    wu_key = f"rutina_dia_{i + 1}_Warm_Up"
                    wo_key = f"rutina_dia_{i + 1}_Work_Out"
                    ejercicios = (st.session_state.get(wu_key, []) or []) + (st.session_state.get(wo_key, []) or [])
                    if not ejercicios:
                        continue

                    st.write(f"**{dia_nombre}**")
                    tabla = []
                    for ej in ejercicios:
                        ejv = ej.copy()
                        for p in range(1, 3+1):
                            variable = str(ej.get(f"Variable_{p}", "")).strip().lower()
                            cantidad = ej.get(f"Cantidad_{p}", "")
                            operacion = str(ej.get(f"Operacion_{p}", "")).strip().lower()
                            semanas_txt = str(ej.get(f"Semanas_{p}", ""))
                            if not (variable and operacion and cantidad):
                                continue
                            try:
                                semanas_aplicar = [int(s.strip()) for s in semanas_txt.split(",") if s.strip().isdigit()]
                            except:
                                semanas_aplicar = []
                            if semana_idx in semanas_aplicar:
                                if variable == "repeticiones":
                                    try:
                                        mn = _f(ejv.get("RepsMin","")); mx = _f(ejv.get("RepsMax",""))
                                        def op(v, cant, o):
                                            if v is None: return v
                                            v=float(v); cant=float(cant)
                                            return v+cant if o=="suma" else v-cant if o=="resta" else v*cant if o=="multiplicacion" else (v/cant if cant!=0 else v)
                                        ejv["RepsMin"] = op(mn, cantidad, operacion)
                                        ejv["RepsMax"] = op(mx, cantidad, operacion)
                                    except: pass
                                else:
                                    key_cap = variable.capitalize()
                                    val = ejv.get(key_cap, "")
                                    if val != "":
                                        try:
                                            ejv[key_cap] = aplicar_progresion(val, float(cantidad), operacion)
                                        except:
                                            pass

                        rep_str = ""
                        mn, mx = ejv.get("RepsMin",""), ejv.get("RepsMax","")
                        if mn != "" and mx != "":
                            rep_str = f"{mn}–{mx}"
                        elif mn != "" or mx != "":
                            rep_str = str(mn or mx)
                        
                        rir_str = ""
                        mn_rir, mx_rir = ejv.get("RirMin",""), ejv.get("RirMax","")
                        if mn_rir != "" and mx_rir != "":
                            rir_str = f"{mn_rir}–{mx_rir}"
                        elif mn_rir != "" or mx_rir != "":
                            rir_str = str(mn_rir or mx_rir)

                    
                        # El bloque se respeta por "Sección" y circuitos ya están validados por sección
                        tabla.append({
                            "bloque": ejv.get("Sección") or ("Warm Up" if ejv.get("Circuito","") in ["A","B","C"] else "Work Out"),
                            "circuito": ejv.get("Circuito",""),
                            "ejercicio": ejv.get("Ejercicio",""),
                            "series": ejv.get("Series",""),
                            "repeticiones": rep_str,
                            "peso": ejv.get("Peso",""),
                            "tiempo": ejv.get("Tiempo",""),
                            "velocidad": ejv.get("Velocidad",""),
                            "descanso": ejv.get("Descanso",""),
                            "rir": rir_str,
                            "tipo": ejv.get("Tipo",""),
                        })

                    st.dataframe(pd.DataFrame(tabla), use_container_width=True, hide_index=True)

    # ======= Guardar =======
    botones_guardado = st.columns([1, 1], gap="medium")
    guardar_borrador_click = botones_guardado[0].button(
        "💾 Guardar borrador", type="secondary", use_container_width=True
    )
    guardar_rutina_click = botones_guardado[1].button(
        "Guardar Rutina", type="primary", use_container_width=True
    )

    if guardar_borrador_click:
        correo_ingresado = str(correo).strip()
        if not correo_ingresado:
            st.warning("⚠️ Ingresa el correo del cliente antes de guardar un borrador.")
        else:
            _sincronizar_filas_formulario(dias_labels)
            dias_data = _construir_datos_borrador(dias_labels)

            correo_norm = correo_ingresado.lower()
            nombre_cliente = str(nombre_sel or nombre_input).strip()
            entrenador_val = str(entrenador).strip()
            objetivo_val = st.session_state.get("objetivo", "")
            fecha_iso = fecha_inicio.strftime("%Y-%m-%d") if isinstance(fecha_inicio, date) else ""
            semanas_val = int(semanas)
            creador_val = (st.session_state.get("correo") or "").strip().lower() or entrenador_val.strip().lower()

            payload = {
                "cliente": nombre_cliente,
                "correo": correo_norm,
                "entrenador": entrenador_val,
                "objetivo": objetivo_val,
                "fecha_inicio": fecha_iso,
                "semanas": semanas_val,
                "dias_labels": dias_labels,
                "dias_data": dias_data,
                "creado_por": creador_val,
                "updated_at": firestore.SERVER_TIMESTAMP,
            }

            draft_id = st.session_state.get("rutina_borrador_activo_id")
            try:
                db = get_db()
                if draft_id:
                    db.collection(BORRADORES_COLLECTION).document(draft_id).set(payload, merge=True)
                else:
                    draft_id = uuid.uuid4().hex
                    payload["created_at"] = firestore.SERVER_TIMESTAMP
                    db.collection(BORRADORES_COLLECTION).document(draft_id).set(payload)

                st.session_state["rutina_borrador_activo_id"] = draft_id
                st.session_state["rutina_borrador_activo_cliente"] = nombre_cliente or correo_norm
                st.session_state["borrador_status_msg"] = "Borrador guardado correctamente."
                st.session_state["borrador_status_type"] = "success"
            except Exception as e:
                st.session_state["borrador_status_msg"] = f"No se pudo guardar el borrador: {e}"
                st.session_state["borrador_status_type"] = "error"

            _trigger_rerun()

    if guardar_rutina_click:
        if all([str(nombre_sel).strip(), str(correo).strip(), str(entrenador).strip()]):
            objetivo_val = st.session_state.get("objetivo", "")
            _sincronizar_filas_formulario(dias_labels)
            guardar_rutina(
                nombre_sel.strip(),
                correo.strip(),
                entrenador.strip(),
                fecha_inicio,
                int(semanas),
                dias_labels,
                objetivo=objetivo_val,
            )
            st.session_state.pop("rutina_borrador_activo_id", None)
            st.session_state.pop("rutina_borrador_activo_cliente", None)
        else:
            st.warning("⚠️ Completa nombre, correo y entrenador antes de guardar.")
