# seguimiento_entrenamiento.py
from __future__ import annotations
import json, re
from datetime import datetime, timedelta, date

import pandas as pd
import streamlit as st

from firebase_admin import firestore
from app_core.firebase_client import get_db
from app_core.theme import inject_theme
from app_core.utils import correo_a_doc_id, usuario_activo

# =============================
#  Estilos / Constantes
# =============================
inject_theme()


# =============================
#  Helpers base
# =============================

def normalizar_id(correo: str) -> str:
    return (correo or "").strip().lower()

def safe_int(x, default=0):
    try: return int(float(x))
    except Exception: return default

def safe_float(x, default=0.0):
    try: return float(x)
    except Exception: return default

def parse_reps_min(value) -> int | None:
    """Extrae el mínimo de repeticiones desde formatos típicos."""
    if value is None: return None
    if isinstance(value, (int, float)):
        try: return int(value)
        except Exception: return None
    if isinstance(value, dict):
        for k in ("min","reps_min","rep_min","rmin"):
            if k in value:
                try: return int(value[k])
                except Exception: pass
        if "reps" in value:
            return parse_reps_min(value["reps"])
    s = str(value).strip().lower()
    m = re.match(r"^\s*(\d+)\s*[x×]\s*\d+", s)
    if m: return int(m.group(1))
    m = re.match(r"^\s*(\d+)\s*[-–—]\s*(\d+)", s)
    if m: return int(m.group(1))
    m = re.match(r"^\s*(\d+)\s*$", s)
    if m: return int(m.group(1))
    return None

def clasificar_categoria(reps_min: int | None) -> str:
    """
    Regla:
      - reps_min < 6          -> Fuerza
      - 6 <= reps_min < 12    -> Hipertrofia
      - reps_min >= 12        -> Accesorio
    """
    if reps_min is None: return "Accesorio"
    if reps_min < 6:     return "Fuerza"
    if reps_min < 12:    return "Hipertrofia"
    return "Accesorio"


# =============================
#  Lectura de datos (según tu esquema real)
# =============================
def _usuarios_por_correo(db) -> dict[str, dict]:
    mapping: dict[str, dict] = {}
    try:
        for snap in db.collection("usuarios").stream():
            if not snap.exists:
                continue
            data = snap.to_dict() or {}
            correo_u = normalizar_id(data.get("correo") or "")
            if not correo_u:
                continue
            mapping[correo_u] = data
            mapping[correo_a_doc_id(correo_u)] = data
    except Exception:
        return mapping
    return mapping


def listar_clientes_con_rutinas(db) -> list[str]:
    """Correos únicos desde 'rutinas_semanales' (campo 'correo')."""
    usuarios_map = _usuarios_por_correo(db)
    correos = set()
    for doc in db.collection("rutinas_semanales").limit(1000).stream():
        data = doc.to_dict() or {}
        email = data.get("correo")
        correo_norm = normalizar_id(email)
        if not correo_norm:
            continue
        if usuario_activo(correo_norm, usuarios_map, default_if_missing=True):
            correos.add(correo_norm)
    return sorted(correos)

def listar_evaluaciones_cliente(db, correo: str) -> list[dict]:
    """Evals (si existen). Se muestran en los select; si no, se usa fecha manual."""
    out = []
    q = db.collection("evaluaciones").where("correo", "==", normalizar_id(correo))
    for doc in q.stream():
        d = doc.to_dict() or {}
        f = d.get("fecha")
        if isinstance(f, str):
            try: d["_fecha_dt"] = datetime.fromisoformat(f)
            except Exception: d["_fecha_dt"] = None
        elif hasattr(f, "to_datetime"):
            d["_fecha_dt"] = f.to_datetime()
        elif isinstance(f, datetime):
            d["_fecha_dt"] = f
        else:
            d["_fecha_dt"] = None
        d["_id"] = doc.id
        out.append(d)
    out.sort(key=lambda x: x.get("_fecha_dt") or datetime.min)
    return out

def dia_finalizado(doc_dict: dict, dia_key: str) -> bool:
    """
    Día finalizado según tu app:
      - doc["rutina"][f"{dia}_finalizado"] == True
    (Se mantiene compatibilidad con mapas alternativos si existieran).
    """
    dia_key = str(dia_key)
    rutina = doc_dict.get("rutina") or {}
    flag_key = f"{dia_key}_finalizado"
    if isinstance(rutina, dict) and flag_key in rutina:
        return bool(rutina.get(flag_key) is True)

    fin_map = doc_dict.get("finalizados")
    if isinstance(fin_map, dict):
        val = fin_map.get(dia_key)
        if isinstance(val, bool):
            return val

    estado_map = doc_dict.get("estado_por_dia")
    if isinstance(estado_map, dict):
        val = str(estado_map.get(dia_key, "")).strip().lower()
        if val in ("fin","final","finalizado","completado","done"):
            return True

    alt = doc_dict.get(f"dia_{dia_key}")
    if isinstance(alt, dict) and "finalizado" in alt:
        return bool(alt.get("finalizado"))

    return False

def obtener_lista_ejercicios(data_dia):
    """
    Normaliza el contenido del día a lista de ejercicios (dicts):
      - lista directa de dicts
      - dict con subclave 'ejercicios' (list/dict)
      - dict con claves numéricas "1","2",...
    """
    if data_dia is None: return []
    # Lista
    if isinstance(data_dia, list):
        if len(data_dia) == 1 and isinstance(data_dia[0], dict) and "ejercicios" in data_dia[0]:
            return obtener_lista_ejercicios(data_dia[0]["ejercicios"])
        return [e for e in data_dia if isinstance(e, dict)]
    # Dict
    if isinstance(data_dia, dict):
        if "ejercicios" in data_dia:
            ej = data_dia["ejercicios"]
            if isinstance(ej, list):
                return [e for e in ej if isinstance(e, dict)]
            if isinstance(ej, dict):
                try:
                    pares = sorted(ej.items(), key=lambda kv: int(kv[0]))
                    return [v for _, v in pares if isinstance(v, dict)]
                except Exception:
                    return [v for v in ej.values() if isinstance(v, dict)]
            return []
        claves_numericas = [k for k in data_dia.keys() if str(k).isdigit()]
        if claves_numericas:
            try:
                pares = sorted(((k, data_dia[k]) for k in claves_numericas), key=lambda kv: int(kv[0]))
                return [v for _, v in pares if isinstance(v, dict)]
            except Exception:
                return [data_dia[k] for k in data_dia if isinstance(data_dia[k], dict)]
        return [v for v in data_dia.values() if isinstance(v, dict)]
    return []

def _iter_dias_rutina(doc_dict: dict):
    """
    Itera días desde doc['rutina'] (dict) y devuelve (dia_key, lista_ejercicios_del_dia).
    Detecta días por claves numéricas "1","2",... y normaliza el día con obtener_lista_ejercicios().
    """
    r = doc_dict.get("rutina")
    if not isinstance(r, dict):
        return
    dia_keys = [k for k in r.keys() if str(k).isdigit()]
    dia_keys.sort(key=lambda x: int(x))
    for dia_key in dia_keys:
        ejercicios_raw = r.get(dia_key)
        lista = obtener_lista_ejercicios(ejercicios_raw)
        yield str(dia_key), lista

def iter_ejercicios_en_rango(db, correo: str, desde: date, hasta: date,
                             usar_real: bool, excluir_warmup: bool):
    """
    Estructura:
      - 'correo' (string)
      - 'fecha_lunes' (YYYY-MM-DD)
      - 'rutina' = dict {"1":[...], "2":[...]}
    REGLA:
      - Teórico (usar_real=False): cuenta TODOS los días.
      - Real    (usar_real=True):  SOLO días finalizados.
    Switch:
      - excluir_warmup: omite ejercicios cuyo bloque sea "Warm Up" (o seccion equivalente).
    """
    correo_norm = normalizar_id(correo)

    docs = list(
        db.collection("rutinas_semanales")
          .where("correo", "==", correo_norm)
          .stream()
    )

    for doc in docs:
        data = doc.to_dict() or {}

        # Fecha base de semana
        fecha_semana = None
        v = data.get("fecha_lunes") or data.get("semana_inicio") or data.get("fecha")
        if isinstance(v, str):
            try: fecha_semana = datetime.fromisoformat(v).date()
            except Exception: fecha_semana = None
        if not fecha_semana:
            # Fallback por ID *_YYYY_MM_DD
            try:
                tail = "_".join(doc.id.split("_")[-3:])
                fecha_semana = datetime.strptime(tail, "%Y_%m_%d").date()
            except Exception:
                continue

        # Recorremos días
        for dia_key, ejercicios in _iter_dias_rutina(data):
            try: idx = int(dia_key) - 1
            except Exception: idx = 0
            fecha_dia = fecha_semana + timedelta(days=idx)

            # Filtro por rango
            if not (desde <= fecha_dia <= hasta):
                continue

            # Real = solo finalizados
            if usar_real and (not dia_finalizado(data, dia_key)):
                continue

            if not isinstance(ejercicios, list):
                continue

            for ej in ejercicios:
                if not isinstance(ej, dict):
                    continue

                # Excluir Warm Up (bloque/seccion)
                if excluir_warmup:
                    bloque = str(ej.get("bloque", ej.get("seccion", ""))).strip().lower()
                    bloque_norm = bloque.replace("-", " ").replace("_", " ")
                    if bloque_norm == "warm up":
                        continue

                series   = safe_int(ej.get("series", 0), 0)
                reps_min = parse_reps_min(ej.get("reps_min", ej.get("reps")))
                reps_min = safe_int(reps_min or 0, 0)
                peso_plan = safe_float(ej.get("peso", 0), 0.0)
                peso_alc  = safe_float(
                    ej.get("peso_alcanzado")
                    or ej.get("Peso_alcanzado")
                    or ej.get("PesoAlcanzado"),
                    0.0,
                )

                yield {
                    "fecha": fecha_dia,
                    "ejercicio": ej.get("ejercicio"),
                    "series": series,
                    "reps_min": reps_min,
                    "peso": peso_plan,
                    "peso_alcanzado": peso_alc,
                }


# =============================
#  Agregaciones (tablas)
# =============================
def agrupar_por_semana(ej_list: list[dict]) -> pd.DataFrame:
    """Devuelve DF con columnas: semana, categoria, series, volumen, tonelaje."""
    rows = []
    for ej in ej_list:
        reps_min = ej.get("reps_min") or 0
        categoria = clasificar_categoria(reps_min)
        series = safe_int(ej.get("series"), 0)
        peso = safe_float(ej.get("peso"), 0.0)
        volumen = series * reps_min
        tonelaje = volumen * peso

        f: date = ej["fecha"]
        lunes = f - timedelta(days=f.weekday())

        rows.append({
            "semana": lunes,
            "categoria": categoria,
            "series": series,
            "volumen": volumen,
            "tonelaje": tonelaje
        })

    if not rows:
        return pd.DataFrame(columns=["semana", "categoria", "series", "volumen", "tonelaje"])

    df = pd.DataFrame(rows)
    df = df.groupby(["semana", "categoria"], as_index=False).sum(numeric_only=True)
    df = df.sort_values(["semana", "categoria"])
    return df

def resumen_semanal(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Retorna (df_totales, df_promedio_por_categoria)."""
    if df.empty:
        empty_cols = ["categoria", "series", "volumen", "tonelaje"]
        return (pd.DataFrame(columns=["semana"] + empty_cols),
                pd.DataFrame(columns=empty_cols))
    df_totales = df.copy()
    semanas_count = df["semana"].nunique()
    df_prom = (df.groupby("categoria", as_index=False)[["series","volumen","tonelaje"]]
                 .sum(numeric_only=True))
    if semanas_count > 0:
        df_prom[["series","volumen","tonelaje"]] = df_prom[["series","volumen","tonelaje"]] / semanas_count
    df_prom = df_prom.sort_values("categoria")
    return df_totales, df_prom


# =============================
#  Diagnóstico
# =============================
def diagnosticar_estructura(db, correo: str, desde: date, hasta: date,
                             usar_real: bool, excluir_warmup: bool):
    correo_norm = normalizar_id(correo)
    rows = []

    docs = list(db.collection("rutinas_semanales")
                  .where("correo", "==", correo_norm).stream())

    for d in docs:
        data = d.to_dict() or {}

        # Fecha semana
        fecha_semana = None
        v = data.get("fecha_lunes") or data.get("semana_inicio") or data.get("fecha")
        if isinstance(v, str):
            try: fecha_semana = datetime.fromisoformat(v).date()
            except Exception: pass
        if not fecha_semana:
            try:
                tail = "_".join(d.id.split("_")[-3:])
                fecha_semana = datetime.strptime(tail, "%Y_%m_%d").date()
            except Exception:
                pass

        rutina = data.get("rutina")
        if not isinstance(rutina, dict):
            rows.append({"doc_id": d.id, "comentario": "Sin 'rutina' dict"})
            continue

        dia_keys = [k for k in rutina.keys() if str(k).isdigit()]
        dia_keys.sort(key=lambda x: int(x) if str(x).isdigit() else 999)

        for dia_key in dia_keys:
            try: idx = int(dia_key) - 1
            except Exception: idx = 0
            fecha_dia = fecha_semana + timedelta(days=idx) if fecha_semana else None

            en_rango = bool(fecha_dia and (desde <= fecha_dia <= hasta))
            fin = dia_finalizado(data, dia_key)
            motivo = "OK"
            if not en_rango:
                motivo = "Fuera de rango"
            elif usar_real and not fin:
                motivo = "No finalizado (modo REAL)"

            ejercicios = obtener_lista_ejercicios(rutina.get(dia_key))
            # Conteos robustos (saltando no-dicts)
            n_total = sum(1 for e in ejercicios if isinstance(e, dict))
            if excluir_warmup:
                n_post = sum(
                    1
                    for e in ejercicios
                    if isinstance(e, dict)
                    and str(e.get("bloque", e.get("seccion", ""))).strip().lower().replace("-", " ").replace("_", " ") != "warm up"
                )
            else:
                n_post = n_total

            rows.append({
                "doc_id": d.id,
                "fecha_semana": (fecha_semana.isoformat() if fecha_semana else None),
                "dia": dia_key,
                "fecha_dia": (fecha_dia.isoformat() if fecha_dia else None),
                "finalizado": fin,
                "en_rango": en_rango,
                "n_ejercicios_total(dicts)": n_total,
                "n_ejercicios_despues_filtro(dicts)": n_post,
                "incluido?": (motivo == "OK"),
                "motivo": motivo,
            })

    df = pd.DataFrame(rows)
    if df.empty:
        st.warning("No se encontraron documentos para ese correo.")
    else:
        st.dataframe(df, use_container_width=True)


# =============================
#  UI principal (solo muestra; no guarda)
# =============================
def app():

    db = get_db()

    # ---------- Controles ----------
    st.markdown("### Configuración")

    colA, colB, colC = st.columns([1, 1, 1])
    with colA:
        clientes = listar_clientes_con_rutinas(db)
        correo_sel = st.selectbox("Cliente (correo)", options=clientes, index=0 if clientes else None)

    with colB:
        usar_real = st.toggle("Usar **Real (solo días finalizados)**", value=False)

    with colC:
        excluir_warmup = st.toggle("Excluir **Warm Up**", value=True,
                                   help="Si está activo, no contabiliza ejercicios cuyo bloque/sección sea Warm Up.")

    vista_opciones = ["Resumen general", "Ejercicio específico"]
    modo_vista = st.radio(
        "Modo de análisis",
        vista_opciones,
        index=st.session_state.get("_seg_modo_vista", 0),
        horizontal=True,
        key="_seg_radio_modo"
    )
    st.session_state["_seg_modo_vista"] = vista_opciones.index(modo_vista)

    colD, colE = st.columns(2)
    with colD:
        evals = listar_evaluaciones_cliente(db, correo_sel) if correo_sel else []
        nombres_eval = [f"{(e.get('_fecha_dt') or datetime.min).date()} — {e.get('nombre','Evaluación')}" for e in evals]
        e1 = st.selectbox("Evaluación inicial", options=["(usar fecha manual)"] + nombres_eval, index=0)
    with colE:
        e2 = st.selectbox("Evaluación final", options=["(usar fecha manual)"] + nombres_eval, index=0)

    def _fecha_from_eval_label(lbl: str) -> date | None:
        try: return datetime.fromisoformat(lbl.split(" — ")[0].strip()).date()
        except Exception: return None

    hoy = date.today()
    colF, colG = st.columns(2)
    with colF:
        fecha_ini = st.date_input("Desde (incl.)", value=hoy - timedelta(days=28))
    with colG:
        fecha_fin = st.date_input("Hasta (incl.)", value=hoy)

    if e1 != "(usar fecha manual)":
        f = _fecha_from_eval_label(e1)
        if f: fecha_ini = f
    if e2 != "(usar fecha manual)":
        f = _fecha_from_eval_label(e2)
        if f: fecha_fin = f

    # ---------- Diagnóstico ----------
    with st.expander("🔎 Diagnóstico de búsqueda"):
        st.caption("Muestra qué días/ejercicios entra según tu selección.")
        if st.button("Ejecutar diagnóstico", use_container_width=True):
            diagnosticar_estructura(db, correo_sel, fecha_ini, fecha_fin, usar_real, excluir_warmup)

    st.divider()

    # ---------- Ejecutar (solo visual) ----------
    disabled = (not correo_sel) or (fecha_ini is None) or (fecha_fin is None) or (fecha_ini > fecha_fin)
    if st.button("Calcular seguimiento", type="primary", disabled=disabled, use_container_width=True):
        with st.spinner("Calculando…"):
            ejercicios = list(iter_ejercicios_en_rango(
                db, correo_sel, fecha_ini, fecha_fin,
                usar_real=usar_real, excluir_warmup=excluir_warmup
            ))
            df_raw = pd.DataFrame(ejercicios)
            if not df_raw.empty:
                df_raw["peso"] = df_raw["peso"].apply(lambda x: safe_float(x, 0.0))
                if "peso_alcanzado" in df_raw.columns:
                    df_raw["peso_alcanzado"] = df_raw["peso_alcanzado"].apply(lambda x: safe_float(x, 0.0))
                else:
                    df_raw["peso_alcanzado"] = 0.0
                df_raw["fecha"] = pd.to_datetime(df_raw["fecha"]).dt.date
            df = agrupar_por_semana(ejercicios)
            df_totales, df_prom = resumen_semanal(df)

        st.session_state["_seg_df_raw"] = df_raw
        st.session_state["_seg_df_totales"] = df_totales
        st.session_state["_seg_df_prom"] = df_prom
        st.session_state["_seg_modo_vista_last"] = modo_vista

    df_raw = st.session_state.get("_seg_df_raw", pd.DataFrame())
    df_totales = st.session_state.get("_seg_df_totales", pd.DataFrame())
    df_prom = st.session_state.get("_seg_df_prom", pd.DataFrame())
    modo_vista_last = st.session_state.get("_seg_modo_vista_last", modo_vista)

    if df_raw.empty:
        st.info("Carga un cálculo para ver resultados.")
        return

    st.success("✅ Resumen generado (solo visual, no se guarda).")
    import matplotlib.pyplot as plt

    if modo_vista == "Resumen general" or modo_vista_last == "Resumen general":
        if modo_vista != "Resumen general":
            st.info("El resumen general se calculó, cambia a ese modo si quieres verlo.")

    if modo_vista == "Resumen general":
        categorias_disponibles = []
        if not df_totales.empty and "categoria" in df_totales.columns:
            categorias_disponibles = sorted(df_totales["categoria"].dropna().unique())

        if categorias_disponibles:
            default_categorias = st.session_state.get("_seg_categories", categorias_disponibles)
            default_categorias = [c for c in default_categorias if c in categorias_disponibles]
            if not default_categorias:
                default_categorias = categorias_disponibles
            categorias_sel = st.multiselect(
                "Clasificaciones a incluir",
                options=categorias_disponibles,
                default=default_categorias,
                help="Elige qué tipos de ejercicios quieres visualizar en el resumen.",
            )
            st.session_state["_seg_categories"] = categorias_sel
            categorias_filtradas = categorias_sel or categorias_disponibles
        else:
            categorias_filtradas = categorias_disponibles

        if categorias_filtradas:
            df_totales_filtrado = df_totales[df_totales["categoria"].isin(categorias_filtradas)].copy()
            df_prom_filtrado = df_prom[df_prom["categoria"].isin(categorias_filtradas)].copy()
        else:
            df_totales_filtrado = df_totales.copy()
            df_prom_filtrado = df_prom.copy()

        if df_totales_filtrado.empty:
            st.warning("No hay datos para las categorías seleccionadas.")
        else:
            st.markdown("### Totales por **Semana × Categoría**")
            st.dataframe(df_totales_filtrado, use_container_width=True)

            st.markdown("### Promedio **semanal** por Categoría")
            st.dataframe(df_prom_filtrado, use_container_width=True)

            semanas_disponibles = []
            if not df_totales_filtrado.empty:
                semanas_series = pd.to_datetime(df_totales_filtrado["semana"], errors="coerce")
                semanas_disponibles = sorted({d.date() for d in semanas_series.dropna()})

            semana_map = {s.isoformat(): s for s in semanas_disponibles}
            if semana_map:
                opciones_semanas = list(semana_map.keys())
                default_labels = st.session_state.get("_seg_weeks_labels", opciones_semanas)
                default_labels = [lbl for lbl in default_labels if lbl in semana_map]
                if not default_labels:
                    default_labels = opciones_semanas
                selected_labels = st.multiselect(
                    "Semanas a graficar (fecha lunes)",
                    options=opciones_semanas,
                    default=default_labels,
                    help="Selecciona las semanas (por la fecha de lunes) que quieres incluir en el gráfico.",
                )
                st.session_state["_seg_weeks_labels"] = selected_labels
                selected_weeks = [semana_map[lbl] for lbl in selected_labels] or list(semana_map.values())
            else:
                selected_weeks = []

            if selected_weeks:
                df_semanal = df_totales_filtrado[df_totales_filtrado["semana"].isin(selected_weeks)].copy()
            else:
                df_semanal = df_totales_filtrado.copy()

            if df_semanal.empty:
                st.warning("No hay datos para las semanas seleccionadas.")
            else:
                tonelaje_por_semana = (
                    df_semanal.groupby("semana", as_index=True)["tonelaje"].sum().sort_index()
                )
                reps_por_semana = (
                    df_semanal.groupby("semana", as_index=True)["volumen"].sum().sort_index()
                )
                intensidad_media = tonelaje_por_semana / reps_por_semana.replace(0, pd.NA)
                intensidad_media = intensidad_media.fillna(0)

                semanas_plot = pd.to_datetime(tonelaje_por_semana.index)

                st.markdown("#### Volumen total e intensidad media por semana")
                fig_vol_int, ax_vol = plt.subplots()
                ax_int = ax_vol.twinx()
                from matplotlib.patches import Patch

                vol_color = "#2563eb"
                int_color = "#f59e0b"
                vol_band_handles: list[Patch] = []
                vol_series = tonelaje_por_semana.dropna()
                if vol_series.nunique() > 1:
                    vol_min = float(vol_series.min())
                    vol_low = float(vol_series.quantile(1/3))
                    vol_high = float(vol_series.quantile(2/3))
                    vol_max = float(vol_series.max())
                    vol_bands = [
                        ("Volumen bajo", vol_min, vol_low, "#dbeafe"),
                        ("Volumen moderado", vol_low, vol_high, "#bfdbfe"),
                        ("Volumen alto", vol_high, vol_max, "#93c5fd"),
                    ]
                    for label, y0, y1, color in vol_bands:
                        if not (y1 > y0):
                            continue
                        ax_vol.axhspan(y0, y1, facecolor=color, alpha=0.25, zorder=0)
                        vol_band_handles.append(Patch(facecolor=color, alpha=0.25, label=label))
                    for bound in (vol_low, vol_high):
                        ax_vol.axhline(
                            bound,
                            color=vol_color,
                            linestyle="--",
                            linewidth=1,
                            alpha=0.6,
                            zorder=1,
                        )

                int_band_handles: list[Patch] = []
                int_series = intensidad_media.dropna()
                if int_series.nunique() > 1:
                    int_min = float(int_series.min())
                    int_low = float(int_series.quantile(1/3))
                    int_high = float(int_series.quantile(2/3))
                    int_max = float(int_series.max())
                    int_bands = [
                        ("Intensidad baja", int_min, int_low, "#fef3c7"),
                        ("Intensidad moderada", int_low, int_high, "#fde68a"),
                        ("Intensidad alta", int_high, int_max, "#fbbf24"),
                    ]
                    for label, y0, y1, color in int_bands:
                        if not (y1 > y0):
                            continue
                        ax_int.axhspan(y0, y1, facecolor=color, alpha=0.2, zorder=0)
                        int_band_handles.append(Patch(facecolor=color, alpha=0.2, label=label))
                    for bound in (int_low, int_high):
                        ax_int.axhline(
                            bound,
                            color=int_color,
                            linestyle="--",
                            linewidth=1,
                            alpha=0.6,
                            zorder=1,
                        )

                linea_vol = ax_vol.plot(
                    semanas_plot,
                    tonelaje_por_semana.values,
                    marker="o",
                    color=vol_color,
                    linewidth=2,
                    label="Volumen total (kg levantados)",
                )[0]
                linea_int = ax_int.plot(
                    semanas_plot,
                    intensidad_media.values,
                    marker="o",
                    color=int_color,
                    linewidth=2,
                    label="Intensidad media (kg/rep)",
                )[0]
                ax_vol.set_title("Volumen vs Intensidad por semana")
                ax_vol.set_xlabel("Semana (lunes)")
                ax_vol.set_ylabel("Volumen total (kg levantados)", color=vol_color)
                ax_int.set_ylabel("Intensidad media (kg/rep)", color=int_color)
                ax_vol.tick_params(axis="y", labelcolor=vol_color)
                ax_int.tick_params(axis="y", labelcolor=int_color)
                ax_vol.grid(True, axis="y", alpha=0.3, linestyle="--")
                plt.setp(ax_vol.get_xticklabels(), rotation=45, ha="right")
                line_handles = [linea_vol, linea_int]
                legend_lines = ax_vol.legend(
                    line_handles, [h.get_label() for h in line_handles], loc="upper left"
                )
                if vol_band_handles:
                    ax_vol.add_artist(legend_lines)
                    ax_vol.legend(
                        vol_band_handles,
                        [h.get_label() for h in vol_band_handles],
                        loc="lower left",
                        title="Zonas volumen",
                        frameon=False,
                    )
                if int_band_handles:
                    ax_int.legend(
                        int_band_handles,
                        [h.get_label() for h in int_band_handles],
                        loc="upper right",
                        title="Zonas intensidad",
                        frameon=False,
                    )
                st.pyplot(fig_vol_int)

                # --- Tonelaje: área apilada ---
                st.markdown("#### Tonelaje por semana (área apilada)")
                pivot_ton = df_totales_filtrado.pivot_table(
                    index="semana", columns="categoria", values="tonelaje", aggfunc="sum"
                ).fillna(0)
                fig1, ax1 = plt.subplots()
                pivot_ton.plot(kind="area", stacked=True, ax=ax1, alpha=0.7)
                ax1.set_xlabel("Semana")
                ax1.set_ylabel("Tonelaje (kg)")
                ax1.set_title("Tonelaje total acumulado")
                st.pyplot(fig1)

                # --- Volumen: líneas comparativas ---
                st.markdown("#### Volumen por semana (líneas)")
                pivot_vol = df_totales_filtrado.pivot_table(
                    index="semana", columns="categoria", values="volumen", aggfunc="sum"
                ).fillna(0)
                fig2, ax2 = plt.subplots()
                pivot_vol.plot(ax=ax2, marker="o")
                ax2.set_xlabel("Semana")
                ax2.set_ylabel("Volumen (series × reps)")
                ax2.set_title("Evolución del volumen por categoría")
                st.pyplot(fig2)

                # --- Series: barras agrupadas ---
                st.markdown("#### Series por semana (barras agrupadas)")
                pivot_ser = df_totales_filtrado.pivot_table(
                    index="semana", columns="categoria", values="series", aggfunc="sum"
                ).fillna(0)
                fig3, ax3 = plt.subplots()
                pivot_ser.plot(kind="bar", ax=ax3)
                ax3.set_xlabel("Semana")
                ax3.set_ylabel("Series")
                ax3.set_title("Series por semana y categoría")
                st.pyplot(fig3)

                # --- Distribución porcentual promedio ---
                st.markdown("#### Distribución porcentual promedio (torta)")
                fig4, ax4 = plt.subplots()
                df_prom_filtrado.set_index("categoria")["series"].plot(
                    kind="pie", ax=ax4, autopct="%1.1f%%", startangle=90
                )
                ax4.set_ylabel("")
                ax4.set_title("Proporción de series por categoría (promedio)")
                st.pyplot(fig4)

                # --- Volumen vs Intensidad ---
                st.markdown("#### Volumen vs Intensidad (comparación en una misma escala)")
                vol_semana = df_totales_filtrado.groupby("semana", as_index=True)["volumen"].sum().sort_index()
                ton_semana = df_totales_filtrado.groupby("semana", as_index=True)["tonelaje"].sum().sort_index()
                int_semana = ton_semana / vol_semana.replace(0, pd.NA)
                df_norm = pd.DataFrame({
                    "Volumen (reps totales)": vol_semana,
                    "Intensidad media (kg/rep)": int_semana
                })
                df_norm = df_norm / df_norm.max()
                fig, ax = plt.subplots()
                df_norm.plot(ax=ax, marker="o")
                ax.set_title("Volumen vs Intensidad (normalizado)")
                ax.set_xlabel("Semana")
                ax.set_ylabel("Valor normalizado (0–1)")
                ax.legend(loc="best")
                st.pyplot(fig)
                st.caption("👉 Los valores están normalizados para comparar tendencias; no representan cantidades absolutas.")

    if modo_vista == "Ejercicio específico":
        opciones_ej = sorted(set(str(e).strip() for e in df_raw["ejercicio"].dropna()))
        if not opciones_ej:
            st.warning("No se encontraron nombres de ejercicio para este rango.")
            return
        if "_seg_select_ejercicio" not in st.session_state or st.session_state["_seg_select_ejercicio"] not in opciones_ej:
            st.session_state["_seg_select_ejercicio"] = opciones_ej[0]
        ejercicio_sel = st.selectbox(
            "Ejercicio",
            opciones_ej,
            key="_seg_select_ejercicio"
        )
        df_ej = df_raw[df_raw["ejercicio"] == ejercicio_sel].copy()
        df_ej["peso_util"] = df_ej.apply(
            lambda row: row["peso_alcanzado"] if safe_float(row.get("peso_alcanzado"), 0.0) > 0 else row["peso"],
            axis=1,
        )
        df_ej = df_ej[df_ej["peso_util"].apply(lambda x: safe_float(x, 0.0) > 0)]

        if df_ej.empty:
            st.info("Ese ejercicio no tiene registros de peso en el rango seleccionado.")
            return

        df_ej["semana"] = df_ej["fecha"].apply(lambda f: f - timedelta(days=f.weekday()))
        df_sem = df_ej.groupby("semana", as_index=False)["peso_util"].max().sort_values("semana")

        st.markdown(f"### 📈 Progresión de peso — {ejercicio_sel}")
        fig_ej, ax_ej = plt.subplots()
        ax_ej.plot(df_sem["semana"], df_sem["peso_util"], marker="o", color="#0ea5e9")
        ax_ej.set_xlabel("Semana")
        ax_ej.set_ylabel("Peso máximo reportado (kg)")
        ax_ej.set_title("Evolución del peso planificado/registrado")
        ax_ej.grid(alpha=0.2)
        st.pyplot(fig_ej)

        st.markdown("#### Detalle de registros")
        st.dataframe(
            df_ej.sort_values("fecha")[["fecha", "series", "reps_min", "peso", "peso_alcanzado", "peso_util"]].rename(columns={
                "fecha": "Fecha",
                "series": "Series",
                "reps_min": "Reps mín",
                "peso": "Peso plan (kg)",
                "peso_alcanzado": "Peso alcanzado (kg)",
                "peso_util": "Peso usado en gráfico (kg)"
            }),
            use_container_width=True,
        )

# Ejecutable standalone (opcional)
if __name__ == "__main__":
    app()
