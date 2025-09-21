# guardar_rutina_view.py — progresión acumulativa + RIR min/max + soporte "descanso" + series como progresión + fallbacks
from firebase_admin import firestore
from datetime import timedelta
from herramientas import aplicar_progresion, normalizar_texto
import streamlit as st
import uuid

# -------------------------
# Helpers de conversión
# -------------------------
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
def guardar_rutina(nombre_sel, correo, entrenador, fecha_inicio, semanas, dias, objetivo: str | None = None):
    """
    Genera X semanas y aplica progresiones de forma ACUMULATIVA.
    Escalares: peso, tiempo, velocidad, descanso, series.
    Rangos: repeticiones (min/max) y RIR (min/max).
    """
    db = firestore.client()
    bloque_id = str(uuid.uuid4())

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

            # Recorre los días definidos en la UI (Día 1..5)
            for i, _dia_label in enumerate(dias):
                numero_dia = i + 1
                lista_ejercicios = []

                for seccion in ["Warm Up", "Work Out"]:
                    dia_key = f"rutina_dia_{i + 1}_{seccion.replace(' ', '_')}"
                    ejercicios = st.session_state.get(dia_key, []) or []

                    for ejercicio in ejercicios:
                        if not _s(ejercicio.get("Ejercicio", "")):
                            continue

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
                            })

                        def acum_scalar(nombre_var, base_val):
                            """Aplica progresión acumulativa para un escalar si hay una regla que lo afecta."""
                            val = base_val
                            for r in reglas:
                                if r["var"] == nombre_var and r["cantidad"] not in (None, "") and r["op"]:
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
                                rir_min, rir_max = aplicar_acumulado_rango(
                                    rir_min, rir_max, r["cantidad"], r["op"], r["semanas"], semana_actual
                                )

                        reps_min, reps_max = base_reps_min, base_reps_max
                        for r in reglas:
                            if r["var"] == "repeticiones" and r["cantidad"] not in (None, "") and r["op"]:
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

                        lista_ejercicios.append({
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
                        })

                if lista_ejercicios:
                    rutina_semana["rutina"][str(numero_dia)] = lista_ejercicios

            if rutina_semana["rutina"]:
                doc_id = f"{correo_norm}_{fecha_norm}"
                db.collection("rutinas_semanales").document(doc_id).set(rutina_semana)

        st.success(f"✅ Rutina generada correctamente para {semanas} semanas (progresión acumulativa + descanso + RIR min/max + series).")
    except Exception as e:
        st.error(f"❌ Error al guardar la rutina: {e}")
