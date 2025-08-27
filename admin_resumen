# admin_resumen.py
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import defaultdict

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

# ========== Firebase: inicializar solo una vez ==========
if not firebase_admin._apps:
    cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
    cred = credentials.Certificate(cred_dict)
    firebase_admin.initialize_app(cred)

db = firestore.client()


# ========== Helpers generales ==========
def _ensure_session_defaults():
    if "rol" not in st.session_state:
        st.session_state.rol = ""
    if "correo" not in st.session_state:
        st.session_state.correo = ""

def _es_admin() -> bool:
    """Admin si rol == admin o correo == ADMIN_EMAIL en secrets."""
    rol = st.session_state.get("rol", "")
    if rol == "admin":
        return True
    admin_email = st.secrets.get("ADMIN_EMAIL", "")
    correo_actual = st.session_state.get("correo", "")
    return bool(admin_email) and (correo_actual.strip().lower() == admin_email.strip().lower())

def _str_fecha(dt: Optional[datetime]) -> str:
    return dt.strftime("%Y-%m-%d") if dt else "—"

def _normalizar_id_correo(correo: str) -> str:
    return (correo or "").strip().lower().replace("@", "_").replace(".", "_")

def _parse_fecha_generic(d: Dict[str, Any]) -> Optional[datetime]:
    """Acepta fecha_lunes, fecha, fecha_inicio como datetime, iso, o Timestamp."""
    for k in ("fecha_lunes", "fecha", "fecha_inicio"):
        v = d.get(k)
        if v is None:
            continue
        # Firestore Timestamp
        try:
            if hasattr(v, "to_datetime"):
                return v.to_datetime()
        except Exception:
            pass
        # datetime ya
        if isinstance(v, datetime):
            return v
        # string ISO o yyyy-mm-dd
        try:
            return datetime.fromisoformat(str(v))
        except Exception:
            pass
    return None


# ========== Catálogos / mapas ==========
@st.cache_data(ttl=300)
def _mapear_entrenadores() -> Dict[str, str]:
    """{correo_entrenador: nombre_entrenador} desde colección 'usuarios'."""
    m: Dict[str, str] = {}
    try:
        docs = db.collection("usuarios").where("rol", "==", "entrenador").stream()
        for doc in docs:
            d = doc.to_dict() or {}
            correo = (d.get("correo") or "").strip().lower()
            nombre = (d.get("nombre") or correo).strip()
            if correo:
                m[correo] = nombre
    except Exception:
        pass
    return m

@st.cache_data(ttl=180)
def _cargar_usuarios_deportistas() -> List[Dict[str, Any]]:
    """Lista de usuarios con rol 'deportista'."""
    res: List[Dict[str, Any]] = []
    try:
        docs = db.collection("usuarios").where("rol", "==", "deportista").stream()
        for doc in docs:
            d = doc.to_dict() or {}
            d["_id"] = doc.id
            # Normaliza correo
            d["correo"] = (d.get("correo") or "").strip().lower()
            res.append(d)
    except Exception:
        pass
    return res


# ========== Buscar última rutina SIN índices compuestos ==========
def _pick_latest(docs: List[Any]) -> Optional[Dict[str, Any]]:
    """Elige el doc con fecha más reciente (en memoria)."""
    mejor = None
    mejor_f = None
    for snap in docs:
        d = snap.to_dict() or {}
        f = _parse_fecha_generic(d)
        if f and (mejor_f is None or f > mejor_f):
            mejor, mejor_f = d, f
    return mejor

def _buscar_ultima_rutina_por_correo(correo_cliente: str, max_docs: int = 150) -> Optional[Dict[str, Any]]:
    """
    Paso A: en 'rutinas' y 'rutinas_semanales' usando where('correo'==...), sin order_by.
    Ordenamos en memoria por fecha.
    """
    mejor = None
    mejor_f = None
    for col in ("rutinas", "rutinas_semanales"):
        try:
            snaps = list(
                db.collection(col)
                  .where("correo", "==", correo_cliente)
                  .limit(max_docs)
                  .stream()
            )
        except Exception:
            snaps = []
        cand = _pick_latest(snaps)
        if cand:
            f = _parse_fecha_generic(cand) or datetime.min
            if mejor is None:
                mejor, mejor_f = cand, f
            else:
                if f > (mejor_f or datetime.min):
                    mejor, mejor_f = cand, f
    return mejor

def _buscar_ultima_rutina_por_prefijo_id(correo_cliente: str) -> Optional[Dict[str, Any]]:
    """
    Paso B (fallback): en 'rutinas_semanales' por prefijo del document_id:
      <correo_normalizado>_YYYY_MM_DD  (orden lexicográfico = cronológico)
    """
    correo_norm = _normalizar_id_correo(correo_cliente)
    prefijo = f"{correo_norm}_"
    try:
        doc_id_field = firestore.FieldPath.document_id()
        q = (
            db.collection("rutinas_semanales")
              .order_by(doc_id_field)
              .start_at(prefijo)
              .end_at(prefijo + "\uf8ff")
              .limit_to_last(1)
        )
        docs = list(q.stream())
    except Exception:
        docs = []

    if not docs:
        return None

    d = docs[0].to_dict() or {}
    # Si no trae fecha, inferir desde el ID
    if _parse_fecha_generic(d) is None:
        try:
            parts = docs[0].id.split("_")
            yyyy, mm, dd = parts[-3], parts[-2], parts[-1]
            d["fecha_lunes"] = f"{yyyy}-{mm}-{dd}"
        except Exception:
            pass
    return d

def _buscar_ultima_rutina(correo_cliente: str) -> Optional[Dict[str, Any]]:
    """
    Estrategia combinada:
    1) Buscar por campo 'correo' en ambas colecciones (sin order_by).
    2) Si nada, buscar por prefijo del ID en 'rutinas_semanales'.
    """
    d = _buscar_ultima_rutina_por_correo(correo_cliente)
    if d:
        return d
    return _buscar_ultima_rutina_por_prefijo_id(correo_cliente)


# ========== Vista principal ==========
def ver_resumen_entrenadores():
    _ensure_session_defaults()
    st.header("🔒 Resumen (solo administrador)")
    if not _es_admin():
        st.warning("No tienes permisos para ver esta sección.")
        st.stop()

    st.caption("Agrupa clientes por entrenador (correo en la rutina) y muestra su última semana planificada.")
    ver_diag = st.checkbox("🔎 Ver diagnóstico de búsquedas", value=False)

    mapa_entrenadores = _mapear_entrenadores()
    usuarios = _cargar_usuarios_deportistas()

    filas: List[Dict[str, Any]] = []   # clientes con rutina
    sin_rutina: List[Dict[str, str]] = []  # clientes sin rutina encontrada

    with st.spinner("Calculando últimas rutinas por cliente..."):
        for u in usuarios:
            nombre_cliente = u.get("nombre", "(sin nombre)")
            correo_cliente = u.get("correo", "")

            rutina = _buscar_ultima_rutina(correo_cliente)
            if not rutina:
                sin_rutina.append({"nombre": nombre_cliente, "correo": correo_cliente})
                if ver_diag:
                    st.write(f"• Debug: {nombre_cliente} ({correo_cliente}) → 0 resultados por campo 'correo' y 0 por prefijo de ID.")
                continue

            # correo de entrenador en la rutina
            correo_entrenador = (rutina.get("entrenador") or "").strip().lower()
            nombre_entrenador = mapa_entrenadores.get(correo_entrenador, correo_entrenador or "(sin entrenador)")

            filas.append({
                "cliente": nombre_cliente,
                "correo_cliente": correo_cliente,
                "entrenador_correo": correo_entrenador,
                "entrenador_nombre": nombre_entrenador,
                "ultima_fecha": _str_fecha(_parse_fecha_generic(rutina)),
            })

    # ===== Resumen por entrenador =====
    st.subheader("📊 Resumen por entrenador")
    conteo_por_ent = defaultdict(int)
    for f in filas:
        # agrupamos por CORREO del entrenador para que no se duplique por nombres iguales
        clave = f["entrenador_correo"] or "(sin entrenador)"
        conteo_por_ent[clave] += 1

    # Mostrar con nombre (si existe) y correo
    resumen_ordenado = sorted(conteo_por_ent.items(), key=lambda x: x[1], reverse=True)
    if resumen_ordenado:
        for correo_ent, cnt in resumen_ordenado:
            nombre_ent = mapa_entrenadores.get(correo_ent, correo_ent)
            etiqueta = f"{nombre_ent}" if correo_ent in ("", "(sin entrenador)") else f"{nombre_ent} ({correo_ent})"
            st.write(f"- **{etiqueta}** → {cnt} cliente(s)")
    else:
        st.write("No hay clientes con rutina asignada.")

    # ===== Detalle por entrenador =====
    st.subheader("🧑‍🏫 Detalle por entrenador")
    grupos = defaultdict(list)
    for f in filas:
        key = f["entrenador_correo"] or "(sin entrenador)"
        grupos[key].append(f)

    for correo_ent in sorted(grupos.keys()):
        nombre_ent = mapa_entrenadores.get(correo_ent, correo_ent)
        etiqueta = f"{nombre_ent}" if correo_ent in ("", "(sin entrenador)") else f"{nombre_ent} ({correo_ent})"
        data = sorted(grupos[correo_ent], key=lambda r: (r["ultima_fecha"], r["cliente"]), reverse=True)
        with st.expander(f"{etiqueta} — {len(data)} cliente(s)", expanded=False):
            for r in data:
                st.write(f"- {r['cliente']} — {r['correo_cliente']} — última rutina: {r['ultima_fecha']}")

    # ===== Deportistas sin rutina =====
    if sin_rutina:
        st.subheader("🟡 Deportistas sin ninguna rutina")
        st.caption("Están en 'usuarios' pero no se encontró rutina por campo 'correo' ni por prefijo de ID.")
        st.write("\n".join([f"- {x['nombre']} — {x['correo']}" for x in sin_rutina]))
