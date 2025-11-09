# admin_resumen.py
import json
from datetime import datetime
from typing import Optional, Dict, Any, List
from collections import defaultdict

import pandas as pd

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore

from app_core.utils import (
    set_usuario_activo,
    empresa_de_usuario,
    usuario_activo,
    EMPRESA_DESCONOCIDA,
    _invalidate_usuario_cache,
)

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


def _trigger_rerun():
    rerun_fn = getattr(st, "rerun", None) or getattr(st, "experimental_rerun", None)
    if rerun_fn:
        rerun_fn()

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


def _set_empresa_usuario(correo: str, empresa: str) -> bool:
    correo_norm = (correo or "").strip().lower()
    if not correo_norm:
        return False

    doc_id = _normalizar_id_correo(correo_norm)
    empresa_clean = (empresa or "").strip()

    try:
        if empresa_clean:
            empresa_value = empresa_clean.lower()
            payload = {
                "empresa": empresa_value,
                "empresa_id": empresa_value,
            }
        else:
            payload = {
                "empresa": firestore.DELETE_FIELD,
                "empresa_id": firestore.DELETE_FIELD,
            }

        db.collection("usuarios").document(doc_id).set(payload, merge=True)
        _invalidate_usuario_cache()
        st.cache_data.clear()
        return True
    except Exception as exc:
        st.error(f"No se pudo actualizar la empresa: {exc}")
        return False


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


@st.cache_data(ttl=120)
def _cargar_todos_usuarios() -> List[Dict[str, Any]]:
    usuarios: List[Dict[str, Any]] = []
    try:
        for snap in db.collection("usuarios").stream():
            if not snap.exists:
                continue
            data = snap.to_dict() or {}
            data["_id"] = snap.id
            data["correo"] = (data.get("correo") or "").strip().lower()
            usuarios.append(data)
    except Exception:
        pass
    return usuarios


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

    mapa_entrenadores = _mapear_entrenadores()
    if mapa_entrenadores:
        lista_entrenadores = pd.DataFrame(
            sorted(
                (
                    {"Nombre": nombre or correo, "Correo": correo}
                    for correo, nombre in mapa_entrenadores.items()
                ),
                key=lambda r: r["Nombre"].lower()
            )
        )
        st.markdown("#### Entrenadores registrados")
        st.dataframe(lista_entrenadores, use_container_width=True)
    else:
        st.caption("No hay usuarios con rol entrenador registrados.")

    st.markdown("<div class='card'>", unsafe_allow_html=True)
    st.markdown("<h4 class='h-accent'>🛑 Dar de baja / reactivar usuarios</h4>", unsafe_allow_html=True)
    usuarios_totales = _cargar_todos_usuarios()
    if not usuarios_totales:
        st.info("No se encontraron usuarios en la colección.")
    else:
        usuarios_map: Dict[str, Dict[str, Any]] = {}
        for u in usuarios_totales:
            correo_u = (u.get("correo") or "").strip().lower()
            doc_id_u = u.get("_id")
            if correo_u:
                usuarios_map[correo_u] = u
                usuarios_map[_normalizar_id_correo(correo_u)] = u
            if doc_id_u:
                usuarios_map[doc_id_u] = u

        df_usuarios = pd.DataFrame([
            {
                "Nombre": (u.get("nombre") or u.get("correo") or "").strip(),
                "Correo": (u.get("correo") or "").strip().lower(),
                "Rol": (u.get("rol") or u.get("role") or "").strip().lower(),
                "Empresa": empresa_de_usuario(u.get("correo", ""), usuarios_map),
                "Activo": usuario_activo(u.get("correo", ""), usuarios_map),
            }
            for u in usuarios_totales
        ])

        st.caption("Usuarios con estado ‘Inactivo’ no podrán autenticarse con su correo hasta ser reactivados.")

        estado_msg = st.session_state.pop("_admin_baja_msg", None)
        empresa_msg = st.session_state.pop("_admin_empresa_msg", None)
        for msg in (estado_msg, empresa_msg):
            if msg:
                st.success(msg)

        roles_disponibles = sorted({row["Rol"] for row in df_usuarios.to_dict("records")})
        rol_filtro = st.selectbox(
            "Filtrar por rol",
            ["todos"] + roles_disponibles,
            format_func=lambda r: "Todos" if r == "todos" else r.title(),
        )

        busqueda = st.text_input("Buscar por nombre o correo", placeholder="Ej: juan@motion.cl")
        solo_inactivos = st.checkbox("Mostrar solo usuarios inactivos", value=False)

        registros = df_usuarios.to_dict("records")
        empresas_existentes = sorted(
            {
                row["Empresa"]
                for row in registros
                if isinstance(row.get("Empresa"), str)
                and row["Empresa"].strip()
                and row["Empresa"] != EMPRESA_DESCONOCIDA
            }
        )
        registros_filtrados: List[Dict[str, Any]] = []
        for row in registros:
            if rol_filtro != "todos" and row["Rol"] != rol_filtro:
                continue
            if solo_inactivos and row["Activo"]:
                continue
            if busqueda:
                busc = busqueda.strip().lower()
                if busc not in (row["Nombre"] or "").lower() and busc not in (row["Correo"] or "").lower():
                    continue
            registros_filtrados.append(row)

        if not registros_filtrados:
            st.info("No se encontraron usuarios para los filtros seleccionados.")
        else:
            for idx, row in enumerate(registros_filtrados):
                correo_sel = row["Correo"]
                activo_actual = usuario_activo(correo_sel, usuarios_map)
                empresa_usr = empresa_de_usuario(correo_sel, usuarios_map)
                empresa_actual = (
                    "" if not empresa_usr or empresa_usr == EMPRESA_DESCONOCIDA else empresa_usr
                )

                cols = st.columns([4, 2, 1])
                with cols[0]:
                    st.markdown(
                        f"**{row['Nombre']}**\n\n"
                        f"`{correo_sel}`  ·  Rol: {row['Rol'].title()}  ·  Empresa: {empresa_usr.title() if empresa_usr else '—'}"
                    )

                    option_new = "__empresa_nueva__"
                    opciones_empresa = [""]
                    opciones_empresa.extend(
                        sorted(e for e in empresas_existentes if e != empresa_actual)
                    )
                    if empresa_actual and empresa_actual not in opciones_empresa:
                        opciones_empresa.append(empresa_actual)
                    opciones_empresa = sorted(set(opciones_empresa), key=lambda x: (x != "", x))
                    opciones_empresa.append(option_new)

                    def _fmt_empresa(val: str) -> str:
                        if val == option_new:
                            return "Agregar nueva…"
                        if not val:
                            return "Sin empresa"
                        return val.title()

                    indice = 0
                    if empresa_actual and empresa_actual in opciones_empresa:
                        indice = opciones_empresa.index(empresa_actual)

                    select_key = f"empresa_sel_{correo_sel}_{idx}"
                    empresa_select = st.selectbox(
                        "Empresa",
                        opciones_empresa,
                        index=indice,
                        format_func=_fmt_empresa,
                        key=select_key,
                    )

                    if empresa_select == option_new:
                        nueva_empresa = st.text_input(
                            "Nueva empresa",
                            key=f"empresa_new_{correo_sel}_{idx}",
                            placeholder="Nombre de la empresa",
                        )
                        guardar_disabled = not nueva_empresa.strip()
                        if st.button(
                            "Guardar nueva empresa",
                            key=f"empresa_save_new_{correo_sel}_{idx}",
                            disabled=guardar_disabled,
                        ):
                            if _set_empresa_usuario(correo_sel, nueva_empresa.strip()):
                                st.session_state["_admin_empresa_msg"] = "Empresa actualizada correctamente."
                                _trigger_rerun()
                    else:
                        empresa_objetivo = empresa_select
                        if empresa_objetivo != empresa_actual:
                            etiqueta_btn = (
                                "Asignar empresa" if empresa_objetivo else "Quitar empresa"
                            )
                            if st.button(
                                etiqueta_btn,
                                key=f"empresa_apply_{correo_sel}_{idx}",
                            ):
                                if _set_empresa_usuario(correo_sel, empresa_objetivo):
                                    st.session_state["_admin_empresa_msg"] = "Empresa actualizada correctamente."
                                    _trigger_rerun()
                with cols[1]:
                    estado_badge = "✅ Activo" if activo_actual else "⛔️ Inactivo"
                    st.markdown(f"<div class='badge'>{estado_badge}</div>", unsafe_allow_html=True)
                with cols[2]:
                    accion = "Reactivar" if not activo_actual else "Dar de baja"
                    if st.button(accion, key=f"toggle_{correo_sel}_{idx}"):
                        set_usuario_activo(correo_sel, not activo_actual)
                        st.session_state["_admin_baja_msg"] = (
                            f"Usuario {'reactivado' if not activo_actual else 'dado de baja'} correctamente."
                        )
                        st.cache_data.clear()
                        _trigger_rerun()

    st.markdown("</div>", unsafe_allow_html=True)

    st.caption("Agrupa clientes por entrenador (correo en la rutina) y muestra su última semana planificada.")
    ver_diag = st.checkbox("🔎 Ver diagnóstico de búsquedas", value=False)
    usuarios = _cargar_usuarios_deportistas()

    filas: List[Dict[str, Any]] = []   # clientes con rutina
    sin_rutina: List[Dict[str, str]] = []  # clientes sin rutina encontrada

    with st.spinner("Calculando últimas rutinas por cliente..."):
        for u in usuarios:
            nombre_cliente = u.get("nombre", "(sin nombre)")
            correo_cliente = u.get("correo", "")

            activo_flag = u.get("activo")
            if activo_flag is False or (
                isinstance(activo_flag, str)
                and activo_flag.strip().lower() in {"false", "0", "no"}
            ):
                if ver_diag:
                    st.write(f"• Debug: {nombre_cliente} ({correo_cliente}) omitido por estar inactivo.")
                continue

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
