# diagnostico_rutinas.py  — SOLO LECTURA
import re, json, sys, traceback
import streamlit as st

# ===== UI básica para verificar que la app cargó =====
st.set_page_config(page_title="Diagnóstico Rutinas", layout="centered")
st.title("🔎 Diagnóstico de Rutinas (solo lectura)")
st.caption("Si ves esta línea, la app cargó. Si abajo no aparece nada, revisa la consola por errores.")

# ====== Firebase ======
import firebase_admin
from firebase_admin import credentials, firestore

def normalizar_correo(c: str) -> str:
    return (c or "").strip().lower()

def correo_a_id(correo_norm: str) -> str:
    # ej: hconchamunoz@gmail.com -> hconchamunoz_gmail_com
    return re.sub(r"[@.]", "_", correo_norm)

@st.cache_resource(show_spinner=False)
def get_db_safe():
    """
    Intenta 3 caminos de credenciales, sin escribir nada.
    Muestra errores en pantalla si algo falla.
    """
    try:
        if not firebase_admin._apps:
            # 1) Secrets estilo tu app
            try:
                cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
                cred = credentials.Certificate(cred_dict)
                firebase_admin.initialize_app(cred)
            except Exception as e1:
                # 2) Application Default Credentials (ADC)
                try:
                    firebase_admin.initialize_app()
                except Exception as e2:
                    # 3) Mensaje claro si no hay credenciales
                    raise RuntimeError(
                        "No se pudo inicializar Firebase.\n"
                        "Prueba alguna de estas opciones:\n"
                        " - Agregar FIREBASE_CREDENTIALS en .streamlit/secrets.toml\n"
                        " - Exportar GOOGLE_APPLICATION_CREDENTIALS con ruta a service-account.json\n"
                        f"Errores:\nA) {repr(e1)}\nB) {repr(e2)}"
                    )
        return firestore.client()
    except Exception as e:
        st.error("❌ Error inicializando Firebase.")
        st.exception(e)
        raise

def diagnosticar(db, correo_input: str):
    correo_norm = normalizar_correo(correo_input)
    correo_id  = correo_a_id(correo_norm)

    st.subheader("1) Normalización")
    st.write({"correo_ingresado": correo_input, "correo_normalizado": correo_norm, "posible_doc_id": correo_id})

    # ====== Usuario
    st.subheader("2) Usuario")
    posibles_colecciones = ["usuarios", "usuario", "users"]
    usuario_por_campo, usuario_por_id = [], None
    for colname in posibles_colecciones:
        try:
            q = db.collection(colname).where("correo", "==", correo_norm)
            usuario_por_campo += [(colname, d.id, d.to_dict() or {}) for d in q.stream()]
            # por ID subrayado
            snap = db.collection(colname).document(correo_id).get()
            if snap.exists:
                usuario_por_id = (colname, snap.id, snap.to_dict() or {})
        except Exception:
            pass

    if usuario_por_campo:
        st.success(f"Usuarios por CAMPO: {len(usuario_por_campo)}")
        for colname, uid, data in usuario_por_campo:
            st.write({"coleccion": colname, "id": uid, "correo": data.get("correo"), "rol": data.get("rol"), "nombre": data.get("nombre")})
    else:
        st.warning("No hay usuarios por CAMPO (correo == normalizado).")

    if usuario_por_id:
        st.info("Usuario por ID subrayado:")
        st.write({"coleccion": usuario_por_id[0], "id": usuario_por_id[1], **(usuario_por_id[2] or {})})

    # ====== Rutinas
    st.subheader("3) Rutinas en 'rutinas_semanales'")
    col = db.collection("rutinas_semanales")
    match_exactos = list(col.where("correo", "==", correo_norm).stream())
    st.write(f"Match exacto por campo (correo == '{correo_norm}'): {len(match_exactos)}")
    for d in match_exactos[:50]:
        data = d.to_dict() or {}
        st.write({"id": d.id, "fecha_lunes": data.get("fecha_lunes"), "cliente": data.get("cliente"), "correo": data.get("correo")})

    variantes = [f" {correo_norm}", f"{correo_norm} ", correo_norm.upper()]
    variantes_halladas = []
    for v in variantes:
        cand = list(col.where("correo", "==", v).stream())
        if cand:
            variantes_halladas.append((v, cand))

    if variantes_halladas:
        st.warning("⚠️ Rutinas con variantes problemáticas en `correo`:")
        for v, cand in variantes_halladas:
            st.write(f"- Variante '{v}': {len(cand)} doc(s)")
            for d in cand[:50]:
                data = d.to_dict() or {}
                st.write({"id": d.id, "fecha_lunes": data.get("fecha_lunes"), "cliente": data.get("cliente"), "correo": data.get("correo")})
    else:
        st.write("Sin variantes (espacios/mayúsculas).")

    st.subheader("✅ Resumen")
    st.json({
        "correo_norm": correo_norm,
        "usuarios_por_campo": len(usuario_por_campo),
        "usuario_por_id_subrayado": bool(usuario_por_id),
        "rutinas_match_exactas": len(match_exactos),
        "tiene_variantes": {v: len(c) for v, c in variantes_halladas} if variantes_halladas else {},
    })

# ===== UI =====
correo_default = "hconchamunoz@gmail.com"
correo = st.text_input("Correo a diagnosticar", value=correo_default)
if st.button("Ejecutar diagnóstico"):
    try:
        db = get_db_safe()
        diagnosticar(db, correo)
    except Exception as e:
        st.error("Se produjo un error durante el diagnóstico.")
        st.exception(e)
        st.code("".join(traceback.format_exception(*sys.exc_info())))
