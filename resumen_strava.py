# resumen_strava.py
# ---------------------------------------------------------
# Genera una imagen tipo "tarjeta Strava" con el resumen de
# la sesión (ejercicios del día) y permite descargarla en PNG.
# ---------------------------------------------------------

import streamlit as st
from datetime import datetime, date, timedelta
from io import BytesIO
import matplotlib.pyplot as plt
import textwrap
import json
import unicodedata

# Firebase
import firebase_admin
from firebase_admin import credentials, firestore

# ==========================
#  Utilidades generales
# ==========================
def normalizar_correo(correo: str) -> str:
    if not correo:
        return ""
    c = correo.strip().lower()
    # normalizar caracteres raros
    c = unicodedata.normalize('NFKD', c).encode('ASCII', 'ignore').decode('utf-8')
    return c

def lunes_de(una_fecha: date) -> date:
    # lunes como inicio de semana (0 = lunes)
    return una_fecha - timedelta(days=una_fecha.weekday())

def str_fecha_dmy(fecha: date) -> str:
    return fecha.strftime("%d/%m/%Y")

def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

def _safe_float(x, default=0.0):
    try:
        return float(x)
    except Exception:
        return default

# ==========================
#  Datos de ejemplo (fallback)
# ==========================
EJEMPLO_EJERCICIOS = [
    {"nombre": "Sentadilla", "series": 4, "reps": 8, "peso": 60, "detalle": ""},
    {"nombre": "Press Banca", "series": 3, "reps": 10, "peso": 40, "detalle": ""},
    {"nombre": "Remo Mancuerna", "series": 3, "reps": 12, "peso": 22.5, "detalle": ""},
    {"nombre": "Plancha", "series": 3, "reps": 45, "peso": 0, "detalle": "seg"},
]

MENSAJES_MOTIVACIONALES = [
    "💪 ¡Éxito en tu entrenamiento de hoy, {nombre}! 🔥",
    "🚀 {nombre}, cada repetición te acerca más a tu objetivo.",
    "🏋️‍♂️ {nombre}, hoy es un gran día para superar tus límites.",
    "🔥 Vamos {nombre}, conviértete en la mejor versión de ti mismo.",
    "⚡ {nombre}, la constancia es la clave. ¡Dalo todo hoy!",
    "🔥 {nombre}, suma una repetición más: ahí pasa la magia.",
]

# ==========================
#  Inicialización Firebase
# ==========================
def init_firebase():
    if not firebase_admin._apps:
        # Usa tus secrets en Streamlit Cloud/local
        cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

# ==========================
#  Carga de ejercicios sesión
# ==========================
def cargar_ejercicios_sesion(
    db,
    correo: str,
    fecha_base: date,
    dia_semana: str,
) -> dict:
    """
    Devuelve un dict con:
      {
        "nombre": <string o vacío>,
        "ejercicios": [ { nombre, series, reps, peso, detalle }, ... ]
      }

    Adaptadores:
    - Intenta colección 'rutinas' (documentos por ejercicio) con campos:
        correo, semana_lunes (yyyy-mm-dd), dia, nombre_ejercicio, series, reps, peso, detalle
    - Si no encuentra, intenta 'rutinas_semanales' (array de ejercicios por día)
      con una estructura típica: { correo, semana_lunes, dias: { lunes: [...], ... } }

    Ajusta aquí si tu esquema es distinto.
    """
    correo = normalizar_correo(correo)
    semana = lunes_de(fecha_base)
    semana_str = semana.isoformat()

    resultado = {"nombre": "", "ejercicios": []}

    # ---- Intento 1: colección 'rutinas' (un doc por ejercicio) ----
    try:
        q = (
            db.collection("rutinas")
              .where("correo", "==", correo)
              .where("semana_lunes", "==", semana_str)
              .where("dia", "==", dia_semana.lower())
        )
        docs = list(q.stream())

        if docs:
            # Si tus docs incluyen el nombre del atleta:
            try:
                resultado["nombre"] = docs[0].to_dict().get("nombre", "")
            except Exception:
                pass

            for d in docs:
                row = d.to_dict()
                ej = {
                    "nombre": row.get("nombre_ejercicio") or row.get("ejercicio") or "Ejercicio",
                    "series": _safe_int(row.get("series", 0)),
                    "reps": _safe_int(row.get("reps", 0)),
                    # Considera 'peso_alcanzado' si existe, sino 'peso'
                    "peso": _safe_float(row.get("peso_alcanzado", row.get("peso", 0))),
                    "detalle": row.get("detalle", ""),
                }
                resultado["ejercicios"].append(ej)

            return resultado
    except Exception as e:
        st.warning(f"⚠️ No se pudo consultar 'rutinas': {e}")

    # ---- Intento 2: colección 'rutinas_semanales' (array por día) ----
    try:
        doc_id = f"{correo}_{semana_str}"
        doc = db.collection("rutinas_semanales").document(doc_id).get()
        if doc.exists:
            data = doc.to_dict()

            # Nombre del deportista si existe
            resultado["nombre"] = data.get("nombre", "")

            dias = data.get("dias", {})
            lista = dias.get(dia_semana.lower(), [])
            for row in lista:
                ej = {
                    "nombre": row.get("nombre") or row.get("ejercicio") or "Ejercicio",
                    "series": _safe_int(row.get("series", 0)),
                    "reps": _safe_int(row.get("reps", 0)),
                    "peso": _safe_float(row.get("peso_alcanzado", row.get("peso", 0))),
                    "detalle": row.get("detalle", ""),
                }
                resultado["ejercicios"].append(ej)

            return resultado
    except Exception as e:
        st.warning(f"⚠️ No se pudo consultar 'rutinas_semanales': {e}")

    # ---- Fallback si no hay nada ----
    resultado["ejercicios"] = EJEMPLO_EJERCICIOS
    return resultado

# ==========================
#  Render de tarjeta (imagen)
# ==========================
def generar_tarjeta_resumen(
    nombre: str,
    fecha_sesion: date,
    dia_semana: str,
    ejercicios: list[dict],
    gym_name: str = "Motion Performance",
) -> plt.Figure:
    """
    Crea un gráfico tipo "tarjeta Strava" con:
      - Encabezado con marca
      - Nombre deportista + fecha + día
      - Lista de ejercicios (truncada si hay muchos)
      - Totales de la sesión
      - Mensaje motivacional
    """
    # Totales
    total_series = 0
    total_reps = 0
    total_peso = 0.0
    for ej in ejercicios:
        s = _safe_int(ej.get("series", 0))
        r = _safe_int(ej.get("reps", 0))
        p = _safe_float(ej.get("peso", 0.0))
        total_series += s
        total_reps += s * r
        total_peso += s * r * p

    fig, ax = plt.subplots(figsize=(6, 8), dpi=200)
    ax.axis("off")

    # Encabezado marca
    ax.text(
        0.5, 0.96, gym_name,
        ha="center", va="center",
        fontsize=18, fontweight="bold"
    )
    ax.text(
        0.5, 0.92, "Resumen de Entrenamiento",
        ha="center", va="center",
        fontsize=13
    )

    # Nombre + fecha
    fecha_str = str_fecha_dmy(fecha_sesion)
    subtitulo = f"{nombre or 'Atleta'} • {dia_semana.capitalize()} {fecha_str}"
    ax.text(0.5, 0.87, subtitulo, ha="center", va="center", fontsize=11)

    # Caja ejercicios
    y = 0.80
    ax.text(0.05, y, "Ejercicios de hoy", fontsize=12, fontweight="bold")
    y -= 0.03

    # Limita a 8 líneas y luego “+N más…”
    max_lineas = 8
    mostrados = 0
    for ej in ejercicios:
        if mostrados >= max_lineas:
            break
        linea = f"• {ej.get('nombre','Ejercicio')}: {ej.get('series',0)}x{ej.get('reps',0)}"
        peso = ej.get("peso", 0)
        if peso:
            linea += f" ({peso:g} kg)"
        detalle = ej.get("detalle", "")
        if detalle:
            linea += f" [{detalle}]"

        # wrap suave por si el nombre es largo
        for chunk in textwrap.wrap(linea, width=40):
            ax.text(0.07, y, chunk, fontsize=10, ha="left")
            y -= 0.028
        mostrados += 1
        y -= 0.01

    restantes = len(ejercicios) - mostrados
    if restantes > 0:
        ax.text(0.07, y, f"+ {restantes} ejercicio(s) más…", fontsize=10, ha="left", style="italic")
        y -= 0.04

    # Totales sesión
    y -= 0.01
    ax.text(0.05, y, "Totales", fontsize=12, fontweight="bold")
    y -= 0.035
    ax.text(0.07, y, f"• Series: {total_series}", fontsize=11, ha="left"); y -= 0.028
    ax.text(0.07, y, f"• Repeticiones: {total_reps}", fontsize=11, ha="left"); y -= 0.028
    ax.text(0.07, y, f"• Volumen estimado: {total_peso:g} kg", fontsize=11, ha="left"); y -= 0.02

    # Mensaje motivacional
    frase = random_mensaje(nombre or "Atleta")
    ax.text(0.5, 0.08, frase, fontsize=10.5, ha="center", style="italic")

    # Pie
    ax.text(0.5, 0.04, "Comparte tu progreso 📸", fontsize=9, ha="center")

    fig.tight_layout()
    return fig

def random_mensaje(nombre: str) -> str:
    import random
    frase = random.choice(MENSAJES_MOTIVACIONALES)
    return frase.format(nombre=nombre.split(" ")[0])

# ==========================
#  APP Streamlit
# ==========================
def ui_resumen_strava():
    st.set_page_config(page_title="Resumen tipo Strava", layout="centered")
    st.title("📸 Resumen tipo Strava")

    # Init DB
    try:
        db = init_firebase()
    except KeyError:
        st.error("Falta configurar `st.secrets['FIREBASE_CREDENTIALS']`.")
        st.stop()

    # Opciones principales (antes en la barra lateral)
    opciones_box = st.container()
    with opciones_box:
        st.markdown("### Opciones")
        opt_cols = st.columns([2, 1])
        with opt_cols[0]:
            gym_name = st.text_input("Nombre Gimnasio / Marca", value="Motion Performance")
        with opt_cols[1]:
            usar_ejemplo = st.checkbox("Usar datos de ejemplo (ignora Firestore)", value=False)

    # Form de filtros
    st.subheader("Selecciona la sesión")
    col1, col2 = st.columns([1, 1])
    with col1:
        correo = st.text_input("Correo del deportista", key="correo_sesion").strip()
    with col2:
        fecha_sesion = st.date_input("Fecha de la sesión", value=date.today())

    dias = ["lunes", "martes", "miercoles", "jueves", "viernes", "sabado"]
    dia_semana = st.selectbox("Día de entrenamiento", dias, index=min(date.today().weekday(), 5))

    st.markdown("---")

    # Cargar ejercicios
    if usar_ejemplo:
        nombre = "Ariel Martínez"
        ejercicios = EJEMPLO_EJERCICIOS
    else:
        if not correo:
            st.info("Ingresa un correo para buscar la sesión en la base de datos.")
            ejercicios = []
            nombre = ""
        else:
            datos = cargar_ejercicios_sesion(db, correo, fecha_sesion, dia_semana)
            nombre = datos.get("nombre") or correo
            ejercicios = datos.get("ejercicios", [])

    # Vista previa simple (tabla)
    if ejercicios:
        st.write(f"**Deportista:** {nombre}")
        st.write(f"**Fecha:** {str_fecha_dmy(fecha_sesion)} — **Día:** {dia_semana.capitalize()}")
        st.write("**Ejercicios encontrados:**")
        st.dataframe(
            [
                {
                    "Ejercicio": e.get("nombre", ""),
                    "Series": e.get("series", 0),
                    "Reps": e.get("reps", 0),
                    "Peso": e.get("peso", 0),
                    "Detalle": e.get("detalle", ""),
                }
                for e in ejercicios
            ],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.warning("No se encontraron ejercicios para esa sesión. Puedes probar con datos de ejemplo en la barra lateral.")

    # Botón generar imagen
    generar = st.button("📸 Generar imagen de resumen", use_container_width=True)

    if generar and ejercicios:
        fig = generar_tarjeta_resumen(
            nombre=nombre,
            fecha_sesion=fecha_sesion,
            dia_semana=dia_semana,
            ejercicios=ejercicios,
            gym_name=gym_name
        )
        st.pyplot(fig, clear_figure=False)

        # Descargar como PNG
        buf = BytesIO()
        fig.savefig(buf, format="png", bbox_inches="tight")
        buf.seek(0)
        st.download_button(
            "⬇️ Descargar PNG",
            data=buf,
            file_name=f"resumen_{normalizar_correo(nombre or 'atleta')}_{fecha_sesion.isoformat()}.png",
            mime="image/png",
            use_container_width=True
        )

# Permite ejecutar como página independiente
if __name__ == "__main__":
    ui_resumen_strava()
