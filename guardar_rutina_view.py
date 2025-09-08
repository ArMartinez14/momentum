# guardar_rutina_view.py — progresión acumulativa + soporte "descanso"
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
    """
    Devuelve el valor para 'semana_objetivo' aplicando progresión ACUMULATIVA.
    Semana 1 = base. Desde la 2, aplica solo si 'wk' ∈ semanas_a_aplicar.
    """
    if _s(valor_base) == "":
        return valor_base

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

    # Si quieres enteros:
    # min_acc = None if min_acc is None or _s(min_acc)=="" else int(round(min_acc))
    # max_acc = None if max_acc is None or _s(max_acc)=="" else int(round(max_acc))
    return min_acc, max_acc

# -------------------------
# Guardado principal
# -------------------------
def guardar_rutina(nombre_sel, correo, entrenador, fecha_inicio, semanas, dias, objetivo: str | None = None):
    """
    Genera X semanas y aplica progresiones de forma ACUMULATIVA.
    Soporta variables escalares: peso, rir, tiempo, velocidad, descanso.
    Soporta rango: repeticiones (min/max).
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
                "rutina": {}
            }
            if objetivo and _s(objetivo):
                rutina_semana["objetivo"] = _s(objetivo)

            for i, _dia_nombre in enumerate(dias):
                numero_dia = str(i + 1)
                lista_ejercicios = []

                for seccion in ["Warm Up", "Work Out"]:
                    dia_key = f"rutina_dia_{i + 1}_{seccion.replace(' ', '_')}"
                    ejercicios = st.session_state.get(dia_key, []) or []

                    for ejercicio in ejercicios:
                        if not _s(ejercicio.get("Ejercicio", "")):
                            continue

                        # 1) Bases Semana 1
                        base_peso      = _f(ejercicio.get("Peso", ""))
                        base_rir       = _f(ejercicio.get("RIR", ""))
                        base_tiempo    = _f(ejercicio.get("Tiempo", ""))
                        base_velocidad = _f(ejercicio.get("Velocidad", ""))
                        base_descanso  = _f(ejercicio.get("Descanso", ""))   # 👈 NUEVO

                        base_reps_min  = _f(ejercicio.get("RepsMin", ""))
                        base_reps_max  = _f(ejercicio.get("RepsMax", ""))

                        # 2) Reglas (hasta 3)
                        reglas = []
                        for p in range(1, 4):
                            reglas.append({
                                "var": _s(ejercicio.get(f"Variable_{p}", "")).lower(),
                                "cantidad": ejercicio.get(f"Cantidad_{p}", ""),
                                "op": _s(ejercicio.get(f"Operacion_{p}", "")).lower(),
                                "semanas": parsear_semanas(ejercicio.get(f"Semanas_{p}", "")),
                            })

                        # Escalares
                        def acum_scalar(nombre_var, base_val):
                            val = base_val
                            if _s(base_val) == "":
                                return base_val
                            for r in reglas:
                                if r["var"] == nombre_var and r["cantidad"] not in (None, "") and r["op"]:
                                    val = aplicar_acumulado_escalar(
                                        val, r["cantidad"], r["op"], r["semanas"], semana_actual
                                    )
                            return val

                        peso      = acum_scalar("peso", base_peso)
                        rir       = acum_scalar("rir", base_rir)
                        tiempo    = acum_scalar("tiempo", base_tiempo)
                        velocidad = acum_scalar("velocidad", base_velocidad)
                        descanso  = acum_scalar("descanso", base_descanso)  # 👈 NUEVO

                        # Rango repeticiones
                        reps_min, reps_max = base_reps_min, base_reps_max
                        for r in reglas:
                            if r["var"] == "repeticiones" and r["cantidad"] not in (None, "") and r["op"]:
                                reps_min, reps_max = aplicar_acumulado_rango(
                                    reps_min, reps_max, r["cantidad"], r["op"], r["semanas"], semana_actual
                                )

                        # 3) Empaquetar ejercicio
                        series     = _f(ejercicio.get("Series", ""))
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
                            "descanso":   descanso,   # 👈 NUEVO (se guarda)
                            "rir":        rir,
                            "tipo":       tipo,
                            "video":      video_link
                        })

                if lista_ejercicios:
                    rutina_semana["rutina"][numero_dia] = lista_ejercicios

            if rutina_semana["rutina"]:
                doc_id = f"{correo_norm}_{fecha_norm}"
                db.collection("rutinas_semanales").document(doc_id).set(rutina_semana)

        st.success(f"✅ Rutina generada correctamente para {semanas} semanas (progresión acumulativa + descanso).")
    except Exception as e:
        st.error(f"❌ Error al guardar la rutina: {e}")
