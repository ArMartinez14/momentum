# guardar_rutina_view.py — progresión acumulativa + RIR min/max + soporte "descanso" + series como progresión + fallbacks
from collections import defaultdict
from datetime import timedelta
from firebase_admin import firestore
from herramientas import aplicar_progresion, normalizar_texto
import streamlit as st
import uuid
from app_core.firebase_client import get_db
from app_core.email_notifications import enviar_correo_rutina_disponible
from app_core.utils import empresa_de_usuario

# -------------------------
# Helpers de conversión
# -------------------------

def _norm(s: str) -> str:
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

    # 1) Intento exacto (requiere índice compuesto si usas ambos where ==)
    try:
        q = (db.collection("implementos")
               .where("marca", "==", marca_in)
               .where("maquina", "==", maquina_in))
        hits = list(q.stream())
        if len(hits) == 1:
            return hits[0].id
        elif len(hits) >= 2:
            return ""  # múltiples → ambiguo → vacío
    except Exception:
        pass

    # 2) Normalizado en memoria (tolerante a acentos/caso/espacios)
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


def _f(v):
    """Convierte a float o None. Tolerante con '8-10' => 8, '' => None."""
    try:
        s = str(v).strip().replace(",", ".")
        if s == "":
            return None
        if "-" in s:
            s = s.split("-", 1)[0].strip()
        return float(s)
    except:
        return None

def _s(v):
    """Sanea strings: None -> "", strip() y garantiza tipo str."""
    return str(v or "").strip()

def parsear_semanas(semanas_txt: str) -> list[int]:
    """Convierte '2,3,5' -> [2,3,5]."""
    try:
        return [int(s.strip()) for s in _s(semanas_txt).split(",") if s.strip().isdigit()]
    except:
        return []


def _default_cardio_data() -> dict:
    return {
        "tipo": "LISS",
        "modalidad": "",
        "indicaciones": "",
        "series": "",
        "intervalos": "",
        "tiempo_trabajo": "",
        "intensidad_trabajo": "",
        "tiempo_descanso": "",
        "tipo_descanso": "",
        "intensidad_descanso": "",
    }


def _normalizar_cardio_data(cardio: dict | None) -> dict:
    data = _default_cardio_data()
    if isinstance(cardio, dict):
        for key in data:
            value = cardio.get(key, data[key])
            if isinstance(value, str):
                data[key] = value.strip()
            else:
                data[key] = value
    if data["tipo"] not in {"LISS", "HIIT"}:
        data["tipo"] = "LISS"
    return data


def _cardio_tiene_datos(cardio: dict | None) -> bool:
    if not isinstance(cardio, dict):
        return False
    for campo in (
        "modalidad",
        "indicaciones",
        "series",
        "intervalos",
        "tiempo_trabajo",
        "intensidad_trabajo",
        "tiempo_descanso",
        "tipo_descanso",
        "intensidad_descanso",
    ):
        valor = cardio.get(campo, "")
        if isinstance(valor, str):
            if valor.strip():
                return True
        elif valor not in (None, ""):
            return True
    return False


def _normalizar_top_sets(data) -> list[dict]:
    """Devuelve una lista de top sets con las claves esperadas si hay datos útiles."""
    campos = ("Series", "RepsMin", "RepsMax", "Peso", "RirMin", "RirMax")
    normalizados: list[dict] = []
    if isinstance(data, dict):
        data_iterable = data.values()
    elif isinstance(data, (list, tuple)):
        data_iterable = data
    else:
        data_iterable = []

    for item in data_iterable:
        if not isinstance(item, dict):
            continue
        limpio = {}
        tiene_valor = False
        for campo in campos:
            valor = item.get(campo)
            if valor is None:
                valor = item.get(campo.lower())
            valor_str = _s(valor)
            limpio[campo] = valor_str
            if valor_str:
                tiene_valor = True
        if tiene_valor:
            normalizados.append(limpio)
    return normalizados


def _listar_ejercicios_de_dia(data):
    if isinstance(data, list):
        return [e for e in data if isinstance(e, dict)]
    if isinstance(data, dict):
        ejercicios = data.get("ejercicios")
        if isinstance(ejercicios, list):
            return [e for e in ejercicios if isinstance(e, dict)]
        return [v for v in data.values() if isinstance(v, dict)]
    return []


def _ejercicio_clave(e: dict) -> tuple[str, str, str]:
    nombre = _norm(e.get("ejercicio") or e.get("Ejercicio") or e.get("nombre") or "")
    circuito = (_s(e.get("circuito") or e.get("Circuito") or "")).upper()
    bloque = _norm(e.get("bloque") or e.get("Sección") or e.get("seccion") or "")
    return (nombre, circuito, bloque)


def _indice_ejercicios_por_nombre(ejercicios_meta: dict[str, dict]) -> dict[str, dict]:
    """Devuelve un índice nombre_normalizado -> metadata."""
    idx: dict[str, dict] = {}
    for clave, data in (ejercicios_meta or {}).items():
        candidatos = [
            clave,
            (data or {}).get("nombre"),
            (data or {}).get("Nombre"),
            (data or {}).get("ejercicio"),
        ]
        for candidato in candidatos:
            key_norm = _norm(candidato)
            if key_norm and key_norm not in idx:
                idx[key_norm] = data or {}
    return idx


@st.cache_data(show_spinner=False)
def _cargar_ejercicios_metadata_para_guardado() -> dict[str, dict]:
    """
    Recupera metadata mínima de ejercicios (solo campos requeridos para clasificar series).
    Sirve como fallback cuando la UI no entrega el catálogo completo.
    """
    resultado: dict[str, dict] = {}
    try:
        db = get_db()
        for doc in db.collection("ejercicios").stream():
            if not doc.exists:
                continue
            data = doc.to_dict() or {}
            nombre = (data.get("nombre") or data.get("Nombre") or "").strip()
            if not nombre:
                continue
            resultado[nombre] = {
                "nombre": nombre,
                "grupo_muscular_principal": data.get("grupo_muscular_principal")
                    or data.get("grupo_muscular")
                    or "",
                "patron_de_movimiento": data.get("patron_de_movimiento") or "",
            }
    except Exception:
        return {}
    return resultado


def _actualizar_series_categoria(
    acumuladores: dict[str, defaultdict[str, float]],
    nombre_ejercicio: str,
    series_valor,
    ejercicios_idx: dict[str, dict],
) -> None:
    """Suma las series del ejercicio a cada clasificación configurada."""
    nombre_norm = _norm(nombre_ejercicio)
    if not nombre_norm:
        return
    series_float = _f(series_valor)
    if series_float is None or series_float <= 0:
        return

    data = ejercicios_idx.get(nombre_norm)
    if not data:
        for campo in acumuladores:
            acumuladores[campo]["(no encontrado)"] += series_float
        return

    for campo in acumuladores:
        categoria_val = _s(data.get(campo))
        if not categoria_val:
            categoria_val = "(sin dato)"
        acumuladores[campo][categoria_val] += series_float


def _extraer_rir_valores(e: dict) -> list[float]:
    valores: list[float] = []
    series = e.get("series_data")
    if isinstance(series, list):
        for s in series:
            if not isinstance(s, dict):
                continue
            val = _f(s.get("rir") or s.get("RIR"))
            if val is not None:
                valores.append(val)
    for key in ("rir_alcanzado", "RirAlcanzado", "RIR_alcanzado"):
        val = _f(e.get(key))
        if val is not None:
            valores.append(val)
    return valores


def _cargar_doc_semana(db, cache: dict, correo_norm: str, fecha_iso: str):
    key = (correo_norm, fecha_iso)
    if key not in cache:
        doc_id = f"{correo_norm}_{fecha_iso.replace('-', '_')}"
        snap = db.collection("rutinas_semanales").document(doc_id).get()
        cache[key] = snap.to_dict() if snap.exists else None
    return cache[key]


def _condicion_rir_cumplida(db, cache, correo_norm: str, fecha_prev: str, numero_dia: int, ejercicio_ref: dict, operador: str, umbral: float) -> bool:
    doc_prev = _cargar_doc_semana(db, cache, correo_norm, fecha_prev)
    if not doc_prev:
        return False
    rutina_prev = doc_prev.get("rutina", {}) or {}
    dia_data = rutina_prev.get(str(numero_dia))
    if not dia_data:
        return False

    ejercicios_prev = _listar_ejercicios_de_dia(dia_data)
    ref_clave = _ejercicio_clave(ejercicio_ref)

    def _compare(valor: float) -> bool:
        if operador == ">":
            return valor > umbral
        if operador == "<":
            return valor < umbral
        if operador == ">=":
            return valor >= umbral
        if operador == "<=":
            return valor <= umbral
        return False

    for e_prev in ejercicios_prev:
        if _ejercicio_clave(e_prev) != ref_clave:
            continue

        plan_peso = _f(e_prev.get("peso") or e_prev.get("Peso"))
        series = e_prev.get("series_data") if isinstance(e_prev.get("series_data"), list) else []

        encontro_condicion = False
        salto_por_progresion = False

        for serie in series:
            if not isinstance(serie, dict):
                continue
            rir_val = _f(serie.get("rir") or serie.get("RIR"))
            peso_val = _f(serie.get("peso") or serie.get("Peso"))

            if rir_val is not None and _compare(rir_val):
                encontro_condicion = True

            if (
                plan_peso is not None
                and peso_val is not None
                and peso_val > plan_peso
                and (rir_val is None or not _compare(rir_val))
            ):
                salto_por_progresion = True

        if salto_por_progresion:
            return False
        if encontro_condicion:
            return True

    return False

# -------------------------
# Progresión acumulativa
# -------------------------
def aplicar_acumulado_escalar(valor_base, cantidad, operacion, semanas_a_aplicar, semana_objetivo: int):
    """Aplica acumulado semana a semana desde la semana 2 hasta la semana objetivo (incluida si corresponde)."""
    acumulado = valor_base
    for wk in range(2, semana_objetivo + 1):
        if wk in semanas_a_aplicar:
            try:
                acumulado = aplicar_progresion(acumulado, float(cantidad), operacion)
            except Exception:
                pass
    return acumulado

def aplicar_acumulado_rango(min_base, max_base, cantidad, operacion, semanas_a_aplicar, semana_objetivo: int):
    """Versión acumulativa para (min, max). Trabaja con float; puedes castear a int si lo prefieres."""
    def operar(v, cant, op):
        if v is None or _s(v) == "":
            return v
        try:
            v = float(v); cant = float(cant)
            if op == "suma":
                return v + cant
            elif op == "resta":
                return v - cant
            elif op == "multiplicacion":
                return v * cant
            elif op == "division":
                return v / cant if cant != 0 else v
        except:
            return v
        return v

    min_acc, max_acc = min_base, max_base
    for wk in range(2, semana_objetivo + 1):
        if wk in semanas_a_aplicar:
            min_acc = operar(min_acc, cantidad, operacion)
            max_acc = operar(max_acc, cantidad, operacion)

    return min_acc, max_acc

# -------------------------
# Guardado principal
# -------------------------
def guardar_rutina(
    nombre_sel,
    correo,
    entrenador,
    fecha_inicio,
    semanas,
    dias,
    notificar_correo: bool = False,
    objetivo: str | None = None,
    ejercicios_meta: dict[str, dict] | None = None,
):
    """
    Genera X semanas y aplica progresiones de forma ACUMULATIVA.
    Escalares: peso, tiempo, velocidad, descanso, series.
    Rangos: repeticiones (min/max) y RIR (min/max).
    Además, clasifica las series por categoría (grupo muscular y patrón).
    """
    db = get_db()
    bloque_id = str(uuid.uuid4())

    docs_prev_cache: dict[tuple[str, str], dict | None] = {}
    ejercicios_meta = ejercicios_meta or _cargar_ejercicios_metadata_para_guardado()
    ejercicios_idx = _indice_ejercicios_por_nombre(ejercicios_meta)
    campos_series_categoria = ("grupo_muscular_principal", "patron_de_movimiento")

    try:
        for semana_idx in range(int(semanas)):  # 0..(N-1)
            semana_actual = semana_idx + 1      # 1..N
            fecha_semana = fecha_inicio + timedelta(weeks=semana_idx)
            fecha_str = fecha_semana.strftime("%Y-%m-%d")
            fecha_norm = fecha_semana.strftime("%Y_%m_%d")
            correo_norm = _s(correo).lower().replace("@", "_").replace(".", "_")
            nombre_normalizado = normalizar_texto(_s(nombre_sel).title())

            rutina_semana = {
                "cliente": nombre_normalizado,
                "correo": _s(correo),
                "fecha_lunes": fecha_str,
                "entrenador": _s(entrenador),
                "bloque_rutina": bloque_id,
                "objetivo": _s(objetivo or ""),
                "rutina": {}
            }
            series_por_categoria_semana: dict[str, defaultdict[str, float]] = {
                campo: defaultdict(float) for campo in campos_series_categoria
            }
            cardio_semana: dict[str, dict] = {}

            # Recorre los días definidos en la UI (Día 1..5)
            for i, _dia_label in enumerate(dias):
                numero_dia = i + 1
                lista_ejercicios = []
                cardio_key = f"rutina_dia_{i + 1}_Cardio"
                cardio_info = None
                if cardio_key in st.session_state:
                    cardio_tmp = _normalizar_cardio_data(st.session_state.get(cardio_key))
                    if _cardio_tiene_datos(cardio_tmp):
                        cardio_info = cardio_tmp

                for seccion in ["Warm Up", "Work Out"]:
                    dia_key = f"rutina_dia_{i + 1}_{seccion.replace(' ', '_')}"
                    ejercicios = st.session_state.get(dia_key, []) or []

                    for ejercicio in ejercicios:
                        if not _s(ejercicio.get("Ejercicio", "")):
                            continue

                        ejercicio_ref = {
                            "Ejercicio": ejercicio.get("Ejercicio", ""),
                            "ejercicio": ejercicio.get("Ejercicio", ""),
                            "Circuito": ejercicio.get("Circuito", ""),
                            "circuito": ejercicio.get("Circuito", ""),
                            "Sección": ejercicio.get("Sección", seccion),
                            "bloque": ejercicio.get("Sección", seccion),
                        }

                        # 1) Bases Semana 1
                        base_peso       = _f(ejercicio.get("Peso", ""))
                        base_tiempo     = _f(ejercicio.get("Tiempo", ""))
                        base_velocidad  = _f(ejercicio.get("Velocidad", ""))
                        base_descanso   = _f(ejercicio.get("Descanso", ""))
                        base_reps_min   = _f(ejercicio.get("RepsMin", ""))
                        base_reps_max   = _f(ejercicio.get("RepsMax", ""))
                        base_rir_min    = _f(ejercicio.get("RirMin", ""))
                        base_rir_max    = _f(ejercicio.get("RirMax", ""))

                        # Fallbacks por compatibilidad (formatos antiguos):
                        # - Si viene 'Repeticiones' como '8-10' o '10', parsea a RepsMin/RepsMax
                        rep_raw = _s(ejercicio.get("Repeticiones", ""))
                        if (base_reps_min is None and base_reps_max is None) and rep_raw:
                            if "-" in rep_raw:
                                try:
                                    mn, mx = rep_raw.split("-", 1)
                                    base_reps_min = _f(mn)
                                    base_reps_max = _f(mx)
                                except Exception:
                                    pass
                            else:
                                v = _f(rep_raw)
                                base_reps_min = v
                                base_reps_max = v

                        # - Si viene 'RIR' como '2-3' o '3', parsea a RirMin/RirMax
                        rir_raw = _s(ejercicio.get("RIR", ""))
                        if (base_rir_min is None and base_rir_max is None) and rir_raw:
                            if "-" in rir_raw:
                                try:
                                    mn, mx = rir_raw.split("-", 1)
                                    base_rir_min = _f(mn)
                                    base_rir_max = _f(mx)
                                except Exception:
                                    pass
                            else:
                                v = _f(rir_raw)
                                base_rir_min = v
                                base_rir_max = v

                        # 2) Reglas (hasta 3)
                        reglas = []
                        for p in range(1, 4):
                            reglas.append({
                                "var": _s(ejercicio.get(f"Variable_{p}", "")).lower(),
                                "cantidad": ejercicio.get(f"Cantidad_{p}", ""),
                                "op": _s(ejercicio.get(f"Operacion_{p}", "")).lower(),
                                "semanas": parsear_semanas(ejercicio.get(f"Semanas_{p}", "")),
                                "cond_var": _s(ejercicio.get(f"CondicionVar_{p}", "")),
                                "cond_op": _s(ejercicio.get(f"CondicionOp_{p}", "")),
                                "cond_val": _f(ejercicio.get(f"CondicionValor_{p}", "")),
                            })

                        fecha_prev_iso = (fecha_semana - timedelta(weeks=1)).strftime("%Y-%m-%d")

                        def _regla_habilitada(regla) -> bool:
                            cond_var = (regla.get("cond_var") or "").lower()
                            cond_op = regla.get("cond_op")
                            cond_val = regla.get("cond_val")
                            if not cond_var or cond_op not in {">", "<", ">=", "<="} or cond_val in (None, ""):
                                return True
                            if semana_actual <= 1:
                                return False
                            if cond_var == "rir":
                                return _condicion_rir_cumplida(
                                    db,
                                    docs_prev_cache,
                                    correo_norm,
                                    fecha_prev_iso,
                                    numero_dia,
                                    ejercicio_ref,
                                    cond_op,
                                    cond_val,
                                )
                            return True

                        def acum_scalar(nombre_var, base_val):
                            """Aplica progresión acumulativa para un escalar si hay una regla que lo afecta."""
                            val = base_val
                            for r in reglas:
                                if r["var"] == nombre_var and r["cantidad"] not in (None, "") and r["op"]:
                                    if not _regla_habilitada(r):
                                        continue
                                    val = aplicar_acumulado_escalar(val, r["cantidad"], r["op"], r["semanas"], semana_actual)
                            return val

                        # Escalares
                        peso      = acum_scalar("peso", base_peso)
                        tiempo    = acum_scalar("tiempo", base_tiempo)
                        velocidad = acum_scalar("velocidad", base_velocidad)
                        descanso  = acum_scalar("descanso", base_descanso)

                        # Series como escalar (opcional)
                        try:
                            base_series_val = _f(ejercicio.get("Series", ""))
                        except Exception:
                            base_series_val = None
                        series_val = base_series_val
                        for r in reglas:
                            if r["var"] == "series" and r["cantidad"] not in (None, "") and r["op"]:
                                series_val = aplicar_acumulado_escalar(series_val, r["cantidad"], r["op"], r["semanas"], semana_actual)

                        # Rangos: RIR y Repeticiones
                        rir_min, rir_max = base_rir_min, base_rir_max
                        for r in reglas:
                            if r["var"] == "rir" and r["cantidad"] not in (None, "") and r["op"]:
                                if not _regla_habilitada(r):
                                    continue
                                rir_min, rir_max = aplicar_acumulado_rango(
                                    rir_min, rir_max, r["cantidad"], r["op"], r["semanas"], semana_actual
                                )

                        reps_min, reps_max = base_reps_min, base_reps_max
                        for r in reglas:
                            if r["var"] == "repeticiones" and r["cantidad"] not in (None, "") and r["op"]:
                                if not _regla_habilitada(r):
                                    continue
                                reps_min, reps_max = aplicar_acumulado_rango(
                                    reps_min, reps_max, r["cantidad"], r["op"], r["semanas"], semana_actual
                                )

                        # 3) Empaquetar ejercicio
                        series     = series_val if series_val is not None else _f(ejercicio.get("Series", ""))
                        nombre_ej  = _s(ejercicio.get("Ejercicio", ""))
                        detalle    = _s(ejercicio.get("Detalle", ""))
                        tipo       = _s(ejercicio.get("Tipo", ""))
                        circuito   = _s(ejercicio.get("Circuito", ""))
                        bloque     = ejercicio.get("Sección", seccion)
                        video_link = _s(ejercicio.get("Video", ""))

                        top_sets_clean = _normalizar_top_sets(
                            ejercicio.get("TopSetData") or ejercicio.get("top_sets")
                        )

                        registro_ejercicio = {
                            "bloque":     bloque,
                            "circuito":   circuito,
                            "ejercicio":  nombre_ej,
                            "detalle":    detalle,
                            "series":     series,
                            "reps_min":   reps_min,
                            "reps_max":   reps_max,
                            "peso":       peso,
                            "tiempo":     tiempo,
                            "velocidad":  velocidad,
                            "descanso":   descanso,
                            "rir_min":    rir_min,
                            "rir_max":    rir_max,
                            "tipo":       tipo,
                            "video":      video_link
                        }
                        if top_sets_clean:
                            registro_ejercicio["TopSetData"] = top_sets_clean

                        lista_ejercicios.append(registro_ejercicio)

                        if seccion.strip().lower() == "work out":
                            _actualizar_series_categoria(
                                series_por_categoria_semana,
                                nombre_ej,
                                series,
                                ejercicios_idx,
                            )

                if lista_ejercicios:
                    # Firestore solo acepta claves string en mapas, por eso guardamos el número de día como texto
                    rutina_semana["rutina"][str(numero_dia)] = lista_ejercicios
                if cardio_info:
                    cardio_semana[str(numero_dia)] = cardio_info

            series_por_categoria_payload = {
                campo: [
                    {"categoria": categoria, "series": valor}
                    for categoria, valor in sorted(
                        mapa.items(),
                        key=lambda item: (-item[1], item[0])
                    )
                ]
                for campo, mapa in series_por_categoria_semana.items()
                if mapa
            }
            if series_por_categoria_payload:
                rutina_semana["series_por_categoria"] = series_por_categoria_payload
            if cardio_semana:
                rutina_semana["cardio"] = cardio_semana

            if rutina_semana["rutina"]:
                doc_id = f"{correo_norm}_{fecha_norm}"
                db.collection("rutinas_semanales").document(doc_id).set(rutina_semana)

        st.success(f"✅ Rutina generada correctamente para {semanas} semanas (progresión acumulativa + descanso + RIR min/max + series).")
        if notificar_correo:
            empresa_cliente = empresa_de_usuario(correo)
            envio_ok = enviar_correo_rutina_disponible(
                correo=correo,
                nombre=nombre_sel,
                fecha_inicio=fecha_inicio,
                semanas=semanas,
                empresa=empresa_cliente,
                coach=entrenador,
            )
            if envio_ok:
                st.caption("El cliente fue notificado por correo con su bloque actualizado.")
            else:
                st.caption("No se pudo enviar el aviso por correo; revisa la configuración de notificaciones.")
        else:
            st.caption("No se envió correo porque la notificación está desactivada.")
    except Exception as e:
        st.error(f"❌ Error al guardar la rutina: {e}")
