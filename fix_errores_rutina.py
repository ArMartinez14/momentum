# admin_fix_videos.py
# Ejecuta: streamlit run admin_fix_videos.py
import json
import unicodedata
from typing import Dict, Any, List, Optional, Tuple

import streamlit as st
import firebase_admin
from firebase_admin import credentials, firestore
import pandas as pd

st.set_page_config(page_title="Corregir videos de rutinas", page_icon="🎥", layout="wide")

# ========= Helpers =========
def normalizar_texto(texto: str) -> str:
    s = (texto or "").strip().lower()
    s = unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("utf-8")
    return s

@st.cache_resource(show_spinner=False)
def get_db():
    # === MISMA INICIALIZACIÓN QUE EN tus páginas Streamlit ===
    if not firebase_admin._apps:
        cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
        cred = credentials.Certificate(cred_dict)
        firebase_admin.initialize_app(cred)
    return firestore.client()

def cargar_indice_ejercicios(db: firestore.Client, prefer_trainer: Optional[str] = None) -> Dict[str, Dict[str, Any]]:
    """
    Retorna: nombre_normalizado -> {'video': str, '_id': doc_id, 'entrenador': str, 'publico': bool, 'nombre': str}
    Si hay duplicados por nombre:
      1) prioriza entrenador == prefer_trainer (si se da)
      2) luego público == True
      3) si no, el primero encontrado
    """
    candidatos: Dict[str, List[Tuple[str, Dict[str, Any]]]] = {}
    for doc in db.collection("ejercicios").stream():
        if not doc.exists:
            continue
        data = doc.to_dict() or {}
        nombre = (data.get("nombre") or "").strip()
        if not nombre:
            continue
        candidatos.setdefault(normalizar_texto(nombre), []).append((doc.id, data))

    prefer = (prefer_trainer or "").strip().lower()
    resolved: Dict[str, Dict[str, Any]] = {}
    for key, docs in candidatos.items():
        picked: Optional[Tuple[str, Dict[str, Any]]] = None
        if prefer:
            for did, d in docs:
                if (d.get("entrenador") or "").strip().lower() == prefer:
                    picked = (did, d); break
        if picked is None:
            for did, d in docs:
                if bool(d.get("publico", False)):
                    picked = (did, d); break
        if picked is None:
            picked = docs[0]
        did, d = picked
        resolved[key] = {
            "_id": did,
            "video": (d.get("video") or "").strip(),
            "entrenador": (d.get("entrenador") or "").strip().lower(),
            "publico": bool(d.get("publico", False)),
            "nombre": d.get("nombre") or "",
        }
    return resolved

def buscar_mismatches(db: firestore.Client, correo: str, indice: Dict[str, Dict[str, Any]], nombres_filtrados: Optional[List[str]] = None):
    """
    Devuelve lista de dicts con diferencias:
    {'doc_ref': <DocumentReference>, 'doc_id': str, 'fecha_lunes': str, 'dia': '1'..'7',
     'idx': int, 'nombre': str, 'actual': str, 'canon': str}
    """
    correo = (correo or "").strip().lower()
    nombres_norm = {normalizar_texto(n) for n in (nombres_filtrados or [])}
    docs = list(db.collection("rutinas_semanales").where("correo", "==", correo).stream())
    mismatches = []
    for snap in docs:
        data = snap.to_dict() or {}
        rutina = data.get("rutina") or {}
        fecha_lunes = (data.get("fecha_lunes") or "").strip()
        if not isinstance(rutina, dict):
            continue
        for dia_key, ejercicios_list in rutina.items():
            if not isinstance(ejercicios_list, list):
                continue
            for idx, item in enumerate(ejercicios_list):
                if not isinstance(item, dict):
                    continue
                nombre = (item.get("ejercicio") or item.get("Ejercicio") or "").strip()
                if not nombre:
                    continue
                key = normalizar_texto(nombre)
                if nombres_norm and key not in nombres_norm:
                    continue
                entry = indice.get(key)
                if not entry:
                    continue
                actual = (item.get("video") or item.get("Video") or "").strip()
                canon = (entry.get("video") or "").strip()
                if canon and canon != actual:
                    mismatches.append({
                        "doc_ref": snap.reference,
                        "doc_id": snap.id,
                        "fecha_lunes": fecha_lunes,
                        "dia": dia_key,
                        "idx": idx,
                        "nombre": nombre,
                        "actual": actual,
                        "canon": canon,
                    })
    return mismatches

def aplicar_cambios(db: firestore.Client, mismatches: List[dict], indices_seleccionados: List[int]) -> int:
    """
    Aplica cambios agrupando por documento. 'indices_seleccionados' es una lista de índices (0-based)
    que apuntan a la lista 'mismatches'.
    """
    # agrupar por doc
    por_doc: Dict[str, List[dict]] = {}
    for i in indices_seleccionados:
        m = mismatches[i]
        por_doc.setdefault(m["doc_id"], []).append(m)

    total_items = 0
    for doc_id, cambios in por_doc.items():
        doc_ref = cambios[0]["doc_ref"]
        snap = doc_ref.get()
        data = snap.to_dict() or {}
        rutina = data.get("rutina") or {}

        for m in cambios:
            dia = m["dia"]
            idx = m["idx"]
            if dia not in rutina or not isinstance(rutina[dia], list) or not (0 <= idx < len(rutina[dia])):
                continue
            item = dict(rutina[dia][idx])
            # actualiza 'video' y también 'Video' si existiera
            item["video"] = m["canon"]
            if "Video" in item:
                item["Video"] = m["canon"]
            rutina[dia][idx] = item
            total_items += 1

        doc_ref.update({"rutina": rutina})

    return total_items

# ========= Estado =========
if "__FIX_INPUTS__" not in st.session_state:
    st.session_state["__FIX_INPUTS__"] = {"correo": "", "prefer": "", "nombres": ""}

if "__MISMATCHES__" not in st.session_state:
    st.session_state["__MISMATCHES__"] = []

# ========= UI: Búsqueda =========
st.title("🎥 Corregir links de video en rutinas")

db = get_db()
inputs = st.session_state["__FIX_INPUTS__"]

with st.form("buscar_form", clear_on_submit=False):
    correo = st.text_input("Correo de la clienta", value=inputs["correo"], placeholder="cliente@dominio.com")
    prefer_trainer = st.text_input("Preferir ejercicios del entrenador (opcional, correo exacto)", value=inputs["prefer"], placeholder="coach@dominio.com")
    nombres_raw = st.text_input("Limitar a nombres de ejercicios (opcional, separados por coma)", value=inputs["nombres"])
    submitted = st.form_submit_button("🔎 Buscar diferencias")

if submitted:
    with st.spinner("Construyendo índice y comparando..."):
        indice = cargar_indice_ejercicios(db, prefer_trainer=prefer_trainer or None)
        nombres_filtrados = [n.strip() for n in nombres_raw.split(",") if n.strip()] if nombres_raw else None
        mismatches = buscar_mismatches(db, correo, indice, nombres_filtrados=nombres_filtrados)

    st.session_state["__FIX_INPUTS__"] = {"correo": correo.strip(), "prefer": prefer_trainer.strip(), "nombres": nombres_raw.strip()}
    st.session_state["__MISMATCHES__"] = mismatches or []

# ========= UI: Resultados persistentes (fuera del if submitted) =========
mismatches = st.session_state["__MISMATCHES__"]
inputs = st.session_state["__FIX_INPUTS__"]

if mismatches:
    st.warning(f"⚠️ Se encontraron {len(mismatches)} ejercicio(s) con link distinto para {inputs['correo'] or '(correo no definido)'}.")

    df = pd.DataFrame([{
        "doc_id": m["doc_id"],
        "fecha_lunes": m["fecha_lunes"],
        "día": m["dia"],
        "índice": m["idx"],
        "ejercicio": m["nombre"],
        "video_actual": m["actual"],
        "video_canónico": m["canon"],
    } for m in mismatches])
    st.dataframe(df, use_container_width=True, hide_index=True)

    st.markdown("### Selección de items a corregir")
    checks = []
    for i, m in enumerate(mismatches):
        with st.expander(f"[{i}] {m['fecha_lunes']} · Día {m['dia']} · idx {m['idx']} — {m['nombre']}"):
            st.write("**Actual:**", m["actual"] or "(vacío)")
            st.write("**Canónico:**", m["canon"])
            chk = st.checkbox("Corregir este item", key=f"fix_chk_{i}")
            checks.append(chk)

    colA, colB, colC = st.columns(3)
    aplicar_todos = colA.button("✅ Corregir TODOS")
    aplicar_sel   = colB.button("✳️ Corregir SELECCIONADOS")
    refrescar     = colC.button("🔄 Recalcular diferencias")

    if aplicar_todos or aplicar_sel:
        if aplicar_todos:
            indices = list(range(len(mismatches)))
        else:
            indices = [i for i, v in enumerate(checks) if v]
            if not indices:
                st.info("No seleccionaste ningún item."); 
                st.stop()

        with st.spinner("Aplicando cambios en Firestore..."):
            total = aplicar_cambios(db, mismatches, indices)

        # Recalcular mismatches para reflejar estado actual
        with st.spinner("Actualizando vista..."):
            indice = cargar_indice_ejercicios(db, prefer_trainer=inputs["prefer"] or None)
            nombres_filtrados = [n.strip() for n in inputs["nombres"].split(",") if n.strip()] if inputs["nombres"] else None
            st.session_state["__MISMATCHES__"] = buscar_mismatches(db, inputs["correo"], indice, nombres_filtrados=nombres_filtrados)

        st.success(f"✅ Listo. Items actualizados: {total}")
        try:
            st.rerun()
        except Exception:
            st.experimental_rerun()

    if refrescar:
        with st.spinner("Recalculando diferencias..."):
            indice = cargar_indice_ejercicios(db, prefer_trainer=inputs["prefer"] or None)
            nombres_filtrados = [n.strip() for n in inputs["nombres"].split(",") if n.strip()] if inputs["nombres"] else None
            st.session_state["__MISMATCHES__"] = buscar_mismatches(db, inputs["correo"], indice, nombres_filtrados=nombres_filtrados)
        try:
            st.rerun()
        except Exception:
            st.experimental_rerun()
else:
    st.info("Ingresa el correo y presiona **Buscar diferencias** para comenzar.")
