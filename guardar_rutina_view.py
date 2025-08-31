# guardar_rutina_view.py
from firebase_admin import firestore
from datetime import timedelta
from herramientas import aplicar_progresion, normalizar_texto, to_float_or_none
import streamlit as st
import uuid

def aplicar_progresion_rango(valor_min, valor_max, cantidad, operacion):
    def operar(valor, cantidad, operacion):
        try:
            if operacion == "suma":
                return int(round(float(valor) + float(cantidad)))
            elif operacion == "resta":
                return int(round(float(valor) - float(cantidad)))
            elif operacion == "multiplicacion":
                return int(round(float(valor) * float(cantidad)))
            elif operacion == "division":
                return int(round(float(valor) / float(cantidad)))
        except:
            return valor
        return valor

    nuevo_min = operar(valor_min, cantidad, operacion) if str(valor_min) != "" else ""
    nuevo_max = operar(valor_max, cantidad, operacion) if str(valor_max) != "" else ""
    return nuevo_min, nuevo_max

def _f(v):
    """Convierte a float o None. No deja strings."""
    try:
        s = str(v).strip().replace(",", ".")
        if s == "":
            return None
        # si accidentalmente llega "8-10", toma 8
        if "-" in s:
            s = s.split("-", 1)[0].strip()
        return float(s)
    except:
        return None

def _s(v):
    """Sanea strings: None -> "", strip() y garantiza tipo str."""
    return str(v or "").strip()

def guardar_rutina(nombre_sel, correo, entrenador, fecha_inicio, semanas, dias, objetivo: str | None = None):
    db = firestore.client()
    bloque_id = str(uuid.uuid4())

    try:
        for semana in range(int(semanas)):
            fecha_semana = fecha_inicio + timedelta(weeks=semana)
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

            for i, dia_nombre in enumerate(dias):
                numero_dia = str(i + 1)
                lista_ejercicios = []

                for seccion in ["Warm Up", "Work Out"]:
                    dia_key = f"rutina_dia_{i + 1}_{seccion.replace(' ', '_')}"
                    ejercicios = st.session_state.get(dia_key, [])

                    for ejercicio in ejercicios:
                        if not _s(ejercicio.get("Ejercicio", "")):
                            continue

                        ejercicio_mod = ejercicio.copy()

                        # === APLICAR PROGRESIONES (como tenías) ===
                        campos_progresion = {
                            "peso": "Peso",
                            "rir": "RIR",
                            "tiempo": "Tiempo",
                            "velocidad": "Velocidad",
                            "repeticiones": ("RepsMin", "RepsMax")
                        }
                        for var_interna, var_real in campos_progresion.items():
                            if isinstance(var_real, tuple):
                                min_key, max_key = var_real
                                try:
                                    valor_min = int(ejercicio.get(min_key, ""))
                                except:
                                    valor_min = ""
                                try:
                                    valor_max = int(ejercicio.get(max_key, ""))
                                except:
                                    valor_max = ""
                                for p in range(1, 4):
                                    var = _s(ejercicio.get(f"Variable_{p}", "")).lower()
                                    cantidad = ejercicio.get(f"Cantidad_{p}", "")
                                    operacion = _s(ejercicio.get(f"Operacion_{p}", "")).lower()
                                    semanas_txt = ejercicio.get(f"Semanas_{p}", "")
                                    if var != var_interna or not cantidad or not operacion:
                                        continue
                                    try:
                                        semanas_aplicar = [int(s.strip()) for s in _s(semanas_txt).split(",") if s.strip().isdigit()]
                                    except:
                                        semanas_aplicar = []
                                    for s in range(2, semana + 2):
                                        if s in semanas_aplicar:
                                            valor_min, valor_max = aplicar_progresion_rango(valor_min, valor_max, float(cantidad), operacion)
                                ejercicio_mod[min_key] = valor_min
                                ejercicio_mod[max_key] = valor_max
                            else:
                                valor_original = ejercicio.get(var_real, "")
                                if valor_original != "":
                                    valor_actual = valor_original
                                    for p in range(1, 4):
                                        var = _s(ejercicio.get(f"Variable_{p}", "")).lower()
                                        cantidad = ejercicio.get(f"Cantidad_{p}", "")
                                        operacion = _s(ejercicio.get(f"Operacion_{p}", "")).lower()
                                        semanas_txt = ejercicio.get(f"Semanas_{p}", "")
                                        if var != var_interna or not cantidad or not operacion:
                                            continue
                                        try:
                                            semanas_aplicar = [int(s.strip()) for s in _s(semanas_txt).split(",") if s.strip().isdigit()]
                                        except:
                                            semanas_aplicar = []
                                        for s in range(2, semana + 2):
                                            if s in semanas_aplicar:
                                                valor_actual = aplicar_progresion(valor_actual, float(cantidad), operacion)
                                    ejercicio_mod[var_real] = valor_actual

                        # === NORMALIZAR ANTES DE GUARDAR ===
                        # Numéricos -> float o None
                        series     = _f(ejercicio_mod.get("Series", ""))
                        reps_min   = _f(ejercicio_mod.get("RepsMin", ""))
                        reps_max   = _f(ejercicio_mod.get("RepsMax", ""))
                        peso       = _f(ejercicio_mod.get("Peso", ""))
                        tiempo     = _f(ejercicio_mod.get("Tiempo", ""))
                        velocidad  = _f(ejercicio_mod.get("Velocidad", ""))
                        rir        = _f(ejercicio_mod.get("RIR", ""))

                        # Strings saneados
                        nombre_ej  = _s(ejercicio_mod.get("Ejercicio", ""))
                        detalle    = _s(ejercicio_mod.get("Detalle", ""))
                        tipo       = _s(ejercicio_mod.get("Tipo", ""))
                        circuito   = _s(ejercicio_mod.get("Circuito", ""))
                        bloque     = ejercicio_mod.get("Sección", seccion)
                        video_link = _s(ejercicio_mod.get("Video", ""))

                        lista_ejercicios.append({
                            "bloque":     bloque,
                            "circuito":   circuito,
                            "ejercicio":  nombre_ej,
                            "detalle":    detalle,
                            "series":     series,     # float | None
                            "reps_min":   reps_min,   # float | None
                            "reps_max":   reps_max,   # float | None
                            "peso":       peso,       # float | None
                            "tiempo":     tiempo,     # float | None
                            "velocidad":  velocidad,  # float | None
                            "rir":        rir,        # float | None
                            "tipo":       tipo,
                            "video":      video_link  # string limpio (o "")
                        })

                if lista_ejercicios:
                    rutina_semana["rutina"][numero_dia] = lista_ejercicios

            if rutina_semana["rutina"]:
                doc_id = f"{correo_norm}_{fecha_norm}"
                db.collection("rutinas_semanales").document(doc_id).set(rutina_semana)

        st.success(f"✅ Rutina generada correctamente para {semanas} semanas.")
    except Exception as e:
        st.error(f"❌ Error al guardar la rutina: {e}")
