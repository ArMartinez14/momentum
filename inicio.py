# inicio_deportista.py — Inicio para deportista o entrenador (vista dual)

from __future__ import annotations
import streamlit as st
from datetime import datetime, timedelta
from collections import defaultdict
from functools import partial

from motivacional import mensaje_motivador_del_dia
from app_core.firebase_client import get_db
from app_core.theme import inject_theme

# ======== Estilos (tema unificado) ========
inject_theme()
st.markdown(
    """
    <style>
    .progress-bar {
        margin-top: 10px;
        width: 100%;
        height: 10px;
        background: rgba(148, 163, 184, 0.25);
        border-radius: 999px;
        overflow: hidden;
    }
    .progress-fill {
        height: 100%;
        background: linear-gradient(90deg, #D64045 0%, #C96B5D 100%);
    }
    div[data-testid="stButton"][data-key^="accion_"] button {
        background: rgba(32, 12, 11, 0.95) !important;
        border: 1px solid rgba(226, 94, 80, 0.45) !important;
        color: #FFEDEA !important;
        font-weight: 700 !important;
        border-radius: 12px !important;
        box-shadow: 0 10px 25px rgba(226, 94, 80, 0.22);
        transition: transform 0.15s ease, box-shadow 0.15s ease;
    }
    div[data-testid="stButton"][data-key^="accion_"] button:hover {
        transform: translateY(-1px);
        box-shadow: 0 14px 30px rgba(226, 94, 80, 0.28);
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# ========= Helpers =========
def _norm_mail(c: str) -> str:
    return (c or "").strip().lower().replace("@","_").replace(".","_")


from datetime import datetime, timedelta, date

def _lunes_hoy() -> date:
    h = date.today()
    return h - timedelta(days=h.weekday())

def _parse_lunes(fecha_lunes_str: str) -> date:
    # 'fecha_lunes' viene como 'YYYY-MM-DD'
    return datetime.strptime(fecha_lunes_str, "%Y-%m-%d").date()

def semana_actual_en_bloque(fechas_lunes: list[str]) -> tuple[int, int, str]:
    """
    Dado el listado de 'fecha_lunes' de un bloque (todas las semanas planificadas),
    devuelve (semana_actual, total_semanas, ultima_semana_str).

    - semana_actual se calcula con el lunes de hoy relativo al primer lunes del bloque.
    - Se acota al rango [1, total].
    """
    if not fechas_lunes:
        return (0, 0, "")

    fechas = sorted(_parse_lunes(f) for f in fechas_lunes)
    total = len(fechas)
    inicio = fechas[0]
    hoy_lunes = _lunes_hoy()

    # semanas transcurridas desde el inicio (1-indexed)
    idx = ((hoy_lunes - inicio).days // 7) + 1
    idx = max(1, min(idx, total))  # acotar a [1, total]

    ultima = fechas[-1].strftime("%Y-%m-%d")
    return (idx, total, ultima)


def _dia_finalizado(doc_dict: dict, dia_key: str) -> bool:
    dia_key = str(dia_key)
    rutina = doc_dict.get("rutina") or {}
    if not isinstance(rutina, dict):
        return False

    flag_key = f"{dia_key}_finalizado"
    if flag_key in rutina and rutina.get(flag_key) is True:
        return True

    fin_map = doc_dict.get("finalizados")
    if isinstance(fin_map, dict):
        val = fin_map.get(dia_key)
        if isinstance(val, bool):
            return val

    estado_map = doc_dict.get("estado_por_dia")
    if isinstance(estado_map, dict):
        estado = str(estado_map.get(dia_key, "")).strip().lower()
        if estado in {"fin", "final", "finalizado", "completado", "done"}:
            return True

    alt = doc_dict.get(f"dia_{dia_key}")
    if isinstance(alt, dict) and bool(alt.get("finalizado")):
        return True

    return False


def _contar_dias_semana(doc_dict: dict) -> tuple[int, int]:
    rutina = doc_dict.get("rutina")
    if not isinstance(rutina, dict):
        return (0, 0)
    dias = [k for k in rutina.keys() if str(k).isdigit()]
    total = len(dias)
    completados = sum(1 for k in dias if _dia_finalizado(doc_dict, k))
    return (completados, total)

def _fecha_lunes_hoy() -> str:
    hoy = datetime.now()
    lunes = hoy - timedelta(days=hoy.weekday())
    return lunes.strftime("%Y-%m-%d")

@st.cache_data(show_spinner=False, ttl=120, max_entries=256)
def _rutinas_cliente_semana(_db, correo_raw: str):
    docs = _db.collection("rutinas_semanales").where("correo", "==", correo_raw).stream()
    out = []
    for d in docs:
        try: out.append(d.to_dict())
        except: pass
    return out

@st.cache_data(show_spinner=False, ttl=120, max_entries=256)
def _rutinas_asignadas_a_entrenador(_db, correo_entrenador: str):
    """Todas las rutinas donde el campo 'entrenador' coincide con el correo del entrenador."""
    docs = _db.collection("rutinas_semanales").where("entrenador", "==", correo_entrenador).stream()
    out = []
    for d in docs:
        try: out.append(d.to_dict())
        except: pass
    return out

def _doc_id_from_mail(mail: str) -> str:
    return mail.replace('@','_').replace('.','_')

def _iter_ejercicios_en_doc(doc: dict):
    rutina = doc.get("rutina") or {}
    for dia_key, data_dia in rutina.items():
        if not str(dia_key).isdigit():
            continue
        items = []
        if isinstance(data_dia, list):
            items = [e for e in data_dia if isinstance(e, dict)]
        elif isinstance(data_dia, dict):
            if isinstance(data_dia.get("ejercicios"), list):
                items = [e for e in data_dia["ejercicios"] if isinstance(e, dict)]
            else:
                items = [e for e in data_dia.values() if isinstance(e, dict)]
        for item in items:
            yield item

def _comentarios_recientes_por_cliente(rutinas: list[dict], ack_map: dict[str, str] | None = None) -> dict[str, dict]:
    """Devuelve mapping correo_cliente -> {'cliente': str, 'fecha': str, 'comentarios': [str]} considerando la semana más reciente con comentarios no vistos."""
    ack_map = ack_map or {}
    resultado: dict[str, dict] = {}
    for doc in rutinas:
        cliente = (doc.get("cliente") or "").strip()
        fecha = doc.get("fecha_lunes") or ""
        correo_cliente = (doc.get("correo") or "").strip().lower()
        if not cliente or not fecha:
            continue
        comentarios = []
        for ejercicio in _iter_ejercicios_en_doc(doc):
            comentario = (ejercicio.get("comentario") or "").strip()
            if comentario:
                comentarios.append(comentario)
        if not comentarios:
            continue
        ack_fecha = ack_map.get(correo_cliente)
        if ack_fecha and ack_fecha >= fecha:
            continue
        stored = resultado.get(correo_cliente)
        if stored is None or fecha > stored.get("fecha", ""):
            resultado[correo_cliente] = {
                "cliente": cliente,
                "fecha": fecha,
                "comentarios": comentarios,
            }
    return resultado

def _comentarios_ack_map(_db, correo_entrenador: str) -> dict[str, str]:
    try:
        doc_id = _doc_id_from_mail(correo_entrenador)
        snap = _db.collection("comentarios_ack").document(doc_id).get()
        data = snap.to_dict() if snap.exists else {}
        if not isinstance(data, dict):
            return {}
        return {str(k).strip().lower(): str(v) for k, v in data.items() if isinstance(k, str) and v}
    except Exception:
        return {}

def _dias_numericos(rutina_dict: dict) -> list[str]:
    if not isinstance(rutina_dict, dict): return []
    dias = [k for k in rutina_dict.keys() if str(k).isdigit()]
    return sorted(dias, key=lambda x: int(x))

def _primero_pendiente(doc: dict) -> str | None:
    r = (doc.get("rutina") or {})
    for d in _dias_numericos(r):
        if not (r.get(f"{d}_finalizado") is True):
            return d
    return None

def _set_query_params(**params: str | None):
    """Actualiza los query params usando la API moderna de Streamlit."""
    try:
        qp = st.query_params
        qp.clear()
        clean = {k: v for k, v in params.items() if v is not None}
        if clean:
            qp.update(clean)
    except Exception:
        pass

def _go_menu(menu_label: str, *, clear_dia: bool = False, clear_params: bool = False):
    """Utilidad centralizada para movernos entre secciones usando el menú lateral."""
    if clear_dia:
        st.session_state.pop("dia_sel", None)
    if clear_params:
        _set_query_params()
    st.session_state["_menu_target"] = menu_label
    st.rerun()

def _go_ver_rutinas(semana: str | None = None, dia: str | None = None):
    """Navega a Ver Rutinas desde el Inicio; si recibo semana/día, los siembro."""
    if semana:
        st.session_state["semana_sel"] = semana
    if dia:
        st.session_state["dia_sel"] = str(dia)
    _set_query_params(
        semana=semana,
        dia=str(dia) if dia is not None else None,
    )
    _go_menu("Ver Rutinas")

def _go_ver_rutinas_sin_prefijar():
    """Entrenador: ir a Ver Rutinas sin sembrar nada."""
    _go_menu("Ver Rutinas", clear_dia=True, clear_params=True)

def _bloque_progress_para_cliente(r_docs: list[dict]) -> tuple[int | None, int | None, str | None]:
    """
    Dado el conjunto de docs de rutinas de un cliente, devuelve:
    (semana_actual_en_bloque, total_en_bloque, fecha_lunes_ultima_semana_del_bloque)

    - La semana actual se calcula respecto al lunes de HOY y el primer lunes del bloque.
    - Se acota al rango [1, total].
    """
    if not r_docs:
        return None, None, None

    # Docs con fecha válida
    validos = [r for r in r_docs if r.get("fecha_lunes")]
    if not validos:
        return None, None, None

    # Tomamos el bloque "activo" según el doc más reciente (por fecha_lunes)
    ult_doc = max(validos, key=lambda x: x["fecha_lunes"])
    bloque_id = ult_doc.get("bloque_rutina")

    # Todas las semanas (fechas_lunes) de ese mismo bloque
    if bloque_id:
        fechas_bloque = [
            r["fecha_lunes"] for r in r_docs
            if r.get("bloque_rutina") == bloque_id and r.get("fecha_lunes")
        ]
    else:
        # No hay bloque_rutina: usamos igual todas las fechas que tenga el cliente
        fechas_bloque = [r["fecha_lunes"] for r in validos]

    fechas_bloque = sorted(set(fechas_bloque))
    if not fechas_bloque:
        return None, None, None

    sem_act, total, ultima = semana_actual_en_bloque(fechas_bloque)
    return sem_act, total, ultima

SEGUIMIENTO_LABEL = "Seguimiento (Entre Evaluaciones)"

_ACCIONES_INICIO = [
    {
        "id": "ver_rutinas",
        "label": "Ver Rutinas",
        "help": "Revisa y actualiza las semanas de entrenamiento de tus deportistas.",
        "roles": {"entrenador", "admin", "administrador"},
        "callback": _go_ver_rutinas_sin_prefijar,
    },
    {
        "id": "crear_rutinas",
        "label": "Crear Rutinas",
        "help": "Genera o asigna nuevas planificaciones semanales.",
        "roles": {"entrenador", "admin", "administrador"},
        "callback": partial(_go_menu, "Crear Rutinas", clear_params=True),
    },
    {
        "id": "ingresar_deportista",
        "label": "Ingresar Deportista o Ejercicio",
        "help": "Registra nuevos deportistas, videos o ejercicios en la base.",
        "roles": {"entrenador", "admin", "administrador"},
        "callback": partial(_go_menu, "Ingresar Deportista o Ejercicio", clear_params=True),
    },
    {
        "id": "borrar_rutinas",
        "label": "Borrar Rutinas",

        "help": "Elimina planificaciones que ya no necesitas.",
        "roles": {"entrenador", "admin", "administrador"},
        "callback": partial(_go_menu, "Borrar Rutinas", clear_params=True),
    },
    {
        "id": "editar_rutinas",
        "label": "Editar Rutinas",
        "help": "Ajusta rutinas existentes día por día.",
        "roles": {"entrenador", "admin", "administrador"},
        "callback": partial(_go_menu, "Editar Rutinas", clear_params=True),
    },
    {
        "id": "ejercicios",
        "label": "Ejercicios",
        "help": "Consulta el catálogo de ejercicios disponibles.",
        "roles": {"entrenador", "admin", "administrador"},
        "callback": partial(_go_menu, "Ejercicios", clear_params=True),
    },
    {
        "id": "crear_descarga",
        "label": "Crear Descarga",
        "help": "Genera un archivo descargable con la rutina seleccionada.",
        "roles": {"entrenador", "admin", "administrador"},
        "callback": partial(_go_menu, "Crear Descarga", clear_params=True),
    },
    {
        "id": "reportes",
        "label": "Reportes",
        "help": "Visualiza indicadores clave del desempeño.",
        "roles": {"entrenador", "admin", "administrador"},
        "callback": partial(_go_menu, "Reportes", clear_params=True),
    },
    {
        "id": "seguimiento",
        "label": SEGUIMIENTO_LABEL,
        "help": "Registra avances entre evaluaciones formales.",
        "roles": {"admin", "administrador"},
        "callback": partial(_go_menu, SEGUIMIENTO_LABEL, clear_params=True),
    },
    {
        "id": "resumen_admin",
        "label": "Resumen (Admin)",
        "help": "Panel ejecutivo con el estado de cada entrenador.",
        "roles": {"admin", "administrador"},
        "callback": partial(_go_menu, "Resumen (Admin)", clear_params=True),
    },
]

def _acciones_para_rol(rol: str) -> list[dict]:
    rol = (rol or "").strip().lower()
    return [a for a in _ACCIONES_INICIO if rol in a["roles"]]

# ========= Vista =========
def inicio_deportista():
    db = get_db()

    correo_raw = (st.session_state.get("correo","") or "").strip().lower()
    if not correo_raw:
        st.error("❌ No hay correo activo."); st.stop()

    correo_norm = _norm_mail(correo_raw)
    user_doc = db.collection("usuarios").document(correo_norm).get()
    datos_usuario = user_doc.to_dict() if user_doc.exists else {}
    nombre = (datos_usuario.get("nombre") or st.session_state.get("primer_nombre") or correo_raw.split("@")[0] or "Usuario").split(" ")[0]
    rol = (st.session_state.get("rol") or datos_usuario.get("rol","deportista")).strip().lower()

    # ====== VISTA ENTRENADOR / ADMIN ======
    if rol in ("entrenador", "admin", "administrador"):
        # 1) Mensaje de bienvenida
        st.markdown(
            f"""
            <div class='banner'>
              👋 Hola, <b>{nombre}</b><br>
              <span style='color:var(--muted)'>Panel de entrenador — aquí verás tus deportistas y el estado de sus bloques.</span>
            </div>
            """,
            unsafe_allow_html=True
        )

        st.markdown("---")

        # 3) Deportistas a mi cargo (entrenador == mi correo)
        asignadas = _rutinas_asignadas_a_entrenador(db, correo_raw)
        if not asignadas:
            st.info("No tienes deportistas asignados aún.")
        else:
            ack_map = _comentarios_ack_map(db, correo_raw)
            comentarios_recientes = _comentarios_recientes_por_cliente(asignadas, ack_map)
            if comentarios_recientes:
                avisos = []
                for correo_cli, payload in comentarios_recientes.items():
                    cliente_nombre = payload.get("cliente") or correo_cli
                    total = len(payload.get("comentarios", []))
                    texto = "un comentario" if total == 1 else f"{total} comentarios"
                    avisos.append(f"{cliente_nombre} dejó {texto}")
                st.info("🗨️ " + " · ".join(avisos))

            # agrupar por correo de cliente
            por_cliente = defaultdict(list)
            for r in asignadas:
                key = (r.get("correo") or "").strip().lower()
                por_cliente[key].append(r)

            st.markdown("### 🧑‍🤝‍🧑 Tus deportistas")
            def _fecha_val(doc):
                try:
                    return datetime.strptime(doc["fecha_lunes"], "%Y-%m-%d")
                except Exception:
                    return datetime.min

            ordenados = []
            hoy_lunes_str = _fecha_lunes_hoy()

            for correo_cli, docs_cli in por_cliente.items():
                nombre_cli = (docs_cli[-1].get("cliente") or correo_cli.split("@")[0] or "Cliente").strip()
                sem_idx, sem_total, fecha_ult = _bloque_progress_para_cliente(docs_cli)
                doc_semana_actual = max(
                    (
                        doc for doc in docs_cli
                        if doc.get("fecha_lunes") and doc.get("fecha_lunes") <= hoy_lunes_str
                    ),
                    default=None,
                    key=lambda d: d.get("fecha_lunes"),
                )
                if doc_semana_actual is None:
                    doc_semana_actual = max(
                        (doc for doc in docs_cli if doc.get("fecha_lunes")),
                        default=None,
                        key=lambda d: d.get("fecha_lunes"),
                    )
                dias_comp, dias_total = _contar_dias_semana(doc_semana_actual or {})
                try:
                    fecha_dt = datetime.strptime(fecha_ult, "%Y-%m-%d") if fecha_ult else datetime.min
                except Exception:
                    fecha_dt = datetime.min
                ordenados.append((
                    correo_cli,
                    docs_cli,
                    nombre_cli,
                    sem_idx,
                    sem_total,
                    fecha_ult,
                    fecha_dt,
                    dias_comp,
                    dias_total,
                ))

            ordenados.sort(key=lambda item: item[6])

            cols = st.columns(2, gap="medium")
            for idx, (correo_cli, docs_cli, nombre_cli, sem_idx, sem_total, fecha_ult, _, dias_comp, dias_total) in enumerate(ordenados):
                with cols[idx % 2]:
                    badge_html = ""
                    info_comentario = comentarios_recientes.get(correo_cli)
                    if info_comentario:
                        total_c = len(info_comentario.get("comentarios", []))
                        badge_html = (
                            "<div style='margin-top:10px;'>"
                            "<span style='display:inline-flex;align-items:center;padding:4px 12px;border-radius:14px;gap:6px;"
                            "background:linear-gradient(135deg, rgba(226,94,80,0.22), rgba(148,34,28,0.28));"
                            "color:#FFE4DE;font-weight:600;font-size:0.82rem;'>"
                            "💬 Comentarios recientes"
                            f"<span style='background:rgba(226,94,80,0.32); color:#FFD4CB; border-radius:999px; padding:2px 8px; font-size:0.72rem;'>{total_c}</span>"
                            "</span></div>"
                        )
                    fecha_badge = (
                        f"<span style='display:inline-flex;align-items:center;padding:4px 12px;border-radius:12px;gap:8px;"
                        "background:linear-gradient(135deg, rgba(226,94,80,0.24), rgba(120,24,20,0.28));"
                        "color:#FFDCD6;font-weight:600;font-size:0.82rem;letter-spacing:0.01em;'>"
                        "<span style='background:rgba(226,94,80,0.35);padding:2px 8px;border-radius:999px;font-size:0.7rem;color:#FFEDEA;'>Última rutina</span>"
                        f"<span>🗓️ {fecha_ult or '—'}</span>"
                        "</span>"
                    )
                    dias_label = "—/—"
                    if dias_total:
                        dias_label = f"{dias_comp}/{dias_total}"
                    st.markdown(
                        f"""
                        <div class="card">
                          <div style="font-weight:800; font-size:1.05rem;">{nombre_cli}</div>
                          <div class='muted' style='margin-top:6px;'>Bloque: Semana {sem_idx or '—'} de {sem_total or '—'}</div>
                          <div class='muted' style='margin-top:2px;'>Días completados: {dias_label}</div>
                          <div style='margin-top:8px;'>{fecha_badge}</div>
                          {badge_html}
                        </div>
                        """,
                        unsafe_allow_html=True,
                    )

        return  # ⬅️ no renderizamos la vista de deportista

    # ====== VISTA DEPORTISTA ======
    # Rutinas del cliente
    rutinas = _rutinas_cliente_semana(db, correo_raw)
    if not rutinas:
        st.warning("⚠️ Aún no hay rutinas asignadas."); st.stop()

    semanas = sorted({r.get("fecha_lunes") for r in rutinas if r.get("fecha_lunes")}, reverse=True)
    semana_actual = _fecha_lunes_hoy()
    qs_semana = st.query_params.get("semana", [None])
    qs_semana = qs_semana[0] if isinstance(qs_semana, list) else qs_semana
    pre_semana = st.session_state.get("semana_sel") or qs_semana or (semana_actual if semana_actual in semanas else (semanas[0] if semanas else None))
    if not pre_semana: st.warning("⚠️ No hay semanas válidas."); st.stop()

    # ── Top bar: mensaje + semana + refrescar ─────────────────────
    top_cols = st.columns([6, 2], gap="small")
    with top_cols[0]:
        msg = mensaje_motivador_del_dia(nombre, correo_norm)
        st.markdown(
            f"""
            <div class='banner'>
              {msg}<br>
              👋 Hola, <b>{nombre}</b><br>
              <span style='color:var(--muted)'>Aquí tienes tu semana de entrenamiento. Elige un día para comenzar.</span>
            </div>
            """,
            unsafe_allow_html=True
        )
    with top_cols[1]:
        semana_sel = st.selectbox(
            "Semana",
            semanas,
            index=semanas.index(pre_semana),
            key="inicio_semana_sel",
            label_visibility="collapsed",
        )
    # Documento de la semana
    doc_semana = next((r for r in rutinas if r.get("fecha_lunes")==semana_sel), None)
    if not doc_semana or not isinstance(doc_semana.get("rutina"), dict):
        st.warning("⚠️ No hay detalles de rutina en esta semana."); st.stop()

    # Tarjetas por día
    dias = _dias_numericos(doc_semana["rutina"])
    if not dias: st.info("No hay días configurados en esta semana."); st.stop()

    st.markdown("### 🗓️ Tus días")
    cols = st.columns(min(len(dias), 5), gap="small")
    for i, d in enumerate(dias):
        fin = bool(doc_semana["rutina"].get(f"{d}_finalizado") is True)
        label = f"{'✅' if fin else '⚡'} Día {d}"
        with cols[i % len(cols)]:
            if st.button(label, key=f"inicio_day_{semana_sel}_{d}",
                         type=("secondary" if fin else "primary"), use_container_width=True):
                _go_ver_rutinas(semana_sel, d)

    # Continuar donde quedó
    st.markdown("<hr style='border-color:var(--stroke);'>", unsafe_allow_html=True)
    sugerido = _primero_pendiente(doc_semana) or (dias[0] if dias else None)
    if sugerido and st.button(f"▶️ Continuar: Día {sugerido}", use_container_width=True):
        _go_ver_rutinas(semana_sel, sugerido)

if __name__ == "__main__":
    inicio_deportista()
