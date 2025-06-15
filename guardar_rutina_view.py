from firebase_admin import firestore
from datetime import timedelta
from herramientas import aplicar_progresion, normalizar_texto
import streamlit as st

def guardar_rutina(nombre_sel, correo, entrenador, fecha_inicio, semanas, dias):
    db = firestore.client()

    try:
        for semana in range(int(semanas)):
            fecha_semana = fecha_inicio + timedelta(weeks=semana)
            fecha_str = fecha_semana.strftime("%Y-%m-%d")
            fecha_norm = fecha_semana.strftime("%Y_%m_%d")
            correo_norm = correo.replace("@", "_").replace(".", "_")
            nombre_normalizado = normalizar_texto(nombre_sel.title())

            rutina_semana = {
                "cliente": nombre_normalizado,
                "correo": correo,
                "fecha_lunes": fecha_str,
                "entrenador": entrenador,
                "rutina": {}
            }

            for i, dia_nombre in enumerate(dias):
                dia_key = f"rutina_dia_{i + 1}"
                ejercicios = st.session_state.get(dia_key, [])
                numero_dia = str(i + 1)
                lista_ejercicios = []

                for ejercicio in ejercicios:
                    if not ejercicio.get("Ejercicio", "").strip():
                        continue  # ❌ Ignorar ejercicios vacíos

                    ejercicio_mod = ejercicio.copy()

                    # === APLICAR PROGRESIONES ===
                    for variable_objetivo in ["peso", "repeticiones", "rir", "tiempo", "velocidad"]:
                        valor_original = ejercicio.get(variable_objetivo, "")
                        if not valor_original:
                            continue

                        valor_actual = valor_original

                        for p in range(1, 4):
                            var = ejercicio.get(f"Variable_{p}", "").strip().lower()
                            cantidad = ejercicio.get(f"Cantidad_{p}", "")
                            operacion = ejercicio.get(f"Operacion_{p}", "").strip().lower()
                            semanas_txt = ejercicio.get(f"Semanas_{p}", "")

                            if var != variable_objetivo or not cantidad or not operacion:
                                continue

                            try:
                                semanas_aplicar = [int(s.strip()) for s in semanas_txt.split(",") if s.strip().isdigit()]
                            except:
                                semanas_aplicar = []

                            for s in range(2, semana + 2):
                                if s in semanas_aplicar:
                                    valor_actual = aplicar_progresion(valor_actual, float(cantidad), operacion)

                        ejercicio_mod[variable_objetivo] = valor_actual

                    lista_ejercicios.append({
                        "bloque": ejercicio_mod.get("Sección", ""),
                        "circuito": ejercicio_mod.get("Circuito", ""),
                        "ejercicio": ejercicio_mod.get("Ejercicio", ""),
                        "series": ejercicio_mod.get("Series", ""),
                        "repeticiones": ejercicio_mod.get("Repeticiones", ""),
                        "peso": ejercicio_mod.get("Peso", ""),
                        "tiempo": ejercicio_mod.get("Tiempo", ""),
                        "velocidad": ejercicio_mod.get("Velocidad", ""),
                        "rir": ejercicio_mod.get("RIR", ""),
                        "tipo": ejercicio_mod.get("Tipo", ""),
                        "video": ejercicio_mod.get("Video", "")
                    })

                if lista_ejercicios:
                    rutina_semana["rutina"][numero_dia] = lista_ejercicios

            # === GUARDAR SOLO SI TIENE DÍAS ===
            if rutina_semana["rutina"]:
                doc_id = f"{correo_norm}_{fecha_norm}"
                db.collection("rutinas_semanales").document(doc_id).set(rutina_semana)

        st.success(f"✅ Rutina generada correctamente para {semanas} semanas.")

    except Exception as e:
        st.error(f"❌ Error al guardar la rutina: {e}")
