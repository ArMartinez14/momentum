# dashboard.py — Tablero según rol.
# Deportista: muestra tarjetas/botones por día (Día 1, Día 2, ...) con color
# según estado {dia}_finalizado. Al hacer clic, abre ver_rutinas() directo en ese día.

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore, initialize_app
from datetime import datetime, timedelta, date
import json

# Importa la vista de rutina para navegar dentro del mismo flujo
from vista_rutinas import ver_rutinas

# ---------- Utils comunes ----------
def _init_firebase():
    if not firebase_admin._apps:
        cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
        cred = credentials.Certificate(cred_dict)
        initialize_app(cred)
    return firestore.client()

def _normalizar_correo(correo: str) -> str:
    return (correo or "").strip().lower().replace("@", "_").replace(".", "_")

def _lunes_de_hoy_str() -> str:
    hoy = datetime.now()
    lunes = hoy - timedelta(days=hoy.weekday())
    return lunes.strftime("%Y-%m-%d")

def _dias_numericos(rutina_dict: dict) -> list[str]:
    """Devuelve claves '1','2','3',... presentes en rutina_dict, ordenadas."""
    if not isinstance(rutina_dict, dict):
        return []
    dias = [k for k in rutina_dict.keys() if str(k).isdigit()]
    return sorted(dias, key=lambda x: int(x))

def _obtener_rutinas_usuario(db, correo: str) -> list[dict]:
    """Carga rutinas de la colección rutinas_semanales para el correo dado."""
    docs = db.collection("rutinas_semanales").where("correo", "==", correo).stream()
    return [d.to_dict() for d in docs]

def _obtener_semanas(rutinas_cliente: list[dict]) -> list[str]:
    return sorted({r.get("fecha_lunes") for r in rutinas_cliente if r.get("fecha_lunes")}, reverse=True)

def _boton_dia(label: str, finalizado: bool, key: str) -> bool:
    """
    Renderiza un botón para el día. Uso:
      - finalizado=True  -> type="secondary" (gris)
      - finalizado=False -> type="primary"  (azul)
    """
    btn_type = "secondary" if finalizado else "primary"
    return st.button(label, key=key, type=btn_type, use_container_width=True)

# ---------- Vista principal ----------
def dashboard():
    st.set_page_config(page_title="Dashboard", layout="wide")

    # Estado de login de tu app principal (ya lo haces en app.py).
    # Aquí asumimos que ya pasó por soft_login_barrier en la app principal.
    correo = (st.session_state.get("correo") or "").strip().lower()
    rol = (st.session_state.get("rol") or "").strip().lower()

    if not correo:
        st.error("❌ No hay sesión activa. Inicia sesión en la app principal.")
        st.stop()

    db = _init_firebase()

    st.title("📊 Dashboard")

    # ======== DEPORTISTA ========
    if rol == "deportista":
        # Cargar todas las rutinas del deportista
        rutinas = _obtener_rutinas_usuario(db, correo)
        if not rutinas:
            st.warning("No se encontraron rutinas asociadas a tu cuenta.")
            st.stop()

        # Selector de semana
        semanas = _obtener_semanas(rutinas)
        semana_por_defecto = _lunes_de_hoy_str()
        semana_sel = st.selectbox(
            "📆 Semana",
            semanas,
            index=semanas.index(semana_por_defecto) if semana_por_defecto in semanas else 0,
            key="dashboard_semana_sel",
            help="Selecciona la semana para ver sus días."
        )

        doc_semana = next((r for r in rutinas if r.get("fecha_lunes") == semana_sel), None)
        if not doc_semana:
            st.warning("No hay rutina para la semana seleccionada.")
            st.stop()

        # Mostrar datos básicos del bloque si existen
        bloque_id = doc_semana.get("bloque_rutina")
        if bloque_id:
            fechas_bloque = sorted([r["fecha_lunes"] for r in rutinas if r.get("bloque_rutina") == bloque_id])
            try:
                pos = fechas_bloque.index(semana_sel) + 1
                st.caption(f"📦 Bloque de entrenamiento • Semana {pos} de {len(fechas_bloque)}")
            except ValueError:
                pass

        # Tarjetas por día
        st.subheader("🗓️ Tus días de entrenamiento")

        dias = _dias_numericos(doc_semana.get("rutina", {}))
        if not dias:
            st.info("Esta semana no tiene días configurados.")
            st.stop()

        # Grid responsivo (3 columnas)
        cols_per_row = 3
        rows = (len(dias) + cols_per_row - 1) // cols_per_row

        # Nota visual
        st.caption("Azul = pendiente • Gris = finalizado")

        idx = 0
        for _ in range(rows):
            cols = st.columns(cols_per_row)
            for c in cols:
                if idx >= len(dias):
                    break
                dia = dias[idx]
                finalizado = bool(doc_semana["rutina"].get(f"{dia}_finalizado") is True)
                with c:
                    _ = _boton_dia(
                        label=f"📅 Día {dia}",
                        finalizado=finalizado,
                        key=f"btn_dia_{semana_sel}_{dia}"
                    )
                    if _:
                        # Preselecciona semana y día para la vista de rutinas
                        st.session_state["semana_sel"] = semana_sel
                        st.session_state["dia_sel"] = dia
                        # Llama a la vista de rutina directamente en este día
                        st.markdown("---")
                        st.subheader(f"🏋️ Rutina — Semana {semana_sel} • Día {dia}")
                        ver_rutinas()
                        st.stop()
                idx += 1

        st.markdown("---")
        st.info("Haz clic en un día para abrir su detalle.")

    # ======== ENTRENADOR / ADMIN (placeholder breve) ========
    elif rol in ("entrenador", "admin", "administrador"):
        st.info("Este dashboard está enfocado al rol deportista. ¿Quieres que armemos una vista con:")
        st.markdown("- Resumen por cliente (días realizados / pendientes)")
        st.markdown("- Adherencia semanal y RPE promedio")
        st.markdown("- Atajos para saltar a cualquier día del cliente")
        st.markdown("- Top ejercicios con PRs recientes")
        st.markdown("\nDime qué KPIs priorizamos y lo integro aquí.")

    else:
        st.warning(f"Rol desconocido o sin dashboard asignado: '{rol}'")

# Ejecutar la vista si se corre directamente
if __name__ == "__main__":
    dashboard()
