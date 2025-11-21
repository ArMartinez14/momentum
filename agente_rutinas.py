import os
import json
import tomllib
from pathlib import Path
import unicodedata
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from openai import OpenAI

import firebase_admin
from firebase_admin import credentials, firestore
from app_core.utils_rm import calcular_rm_teorico, calcular_peso_por_porcentaje

# ==============================
# 🔐 Cargar variables
# ==============================
load_dotenv()

# ==============================
# 🔧 Cliente OpenAI
# ==============================
def _load_openai_api_key() -> Optional[str]:
    """
    Busca la API key en este orden:
    1) Variable de entorno OPENAI_API_KEY
    2) st.secrets (si se está ejecutando en Streamlit)
    3) .streamlit/secrets.toml (clave 'OPENAI_API_KEY' o openai.api_key)
    """
    env_key = os.getenv("OPENAI_API_KEY")
    if env_key:
        return env_key

    # Si estamos en un proceso Streamlit, revisa st.secrets
    try:
        import streamlit as st

        if "OPENAI_API_KEY" in st.secrets:
            return st.secrets["OPENAI_API_KEY"]
        if "openai" in st.secrets and isinstance(st.secrets["openai"], dict):
            maybe = st.secrets["openai"].get("api_key")
            if maybe:
                return maybe
    except Exception:
        # streamlit no disponible o st.secrets no accesible
        pass

    secrets_path = Path(__file__).resolve().parent / ".streamlit" / "secrets.toml"
    if secrets_path.exists():
        with secrets_path.open("rb") as f:
            secrets = tomllib.load(f)
        if "OPENAI_API_KEY" in secrets:
            return secrets["OPENAI_API_KEY"]
        openai_section = secrets.get("openai")
        if isinstance(openai_section, dict) and "api_key" in openai_section:
            return openai_section["api_key"]

    return None


def get_openai_client() -> OpenAI:
    """
    Crea el cliente tomando la key de entorno o de .streamlit/secrets.toml.
    Nunca guardes la llave en el código.
    """
    api_key = _load_openai_api_key()
    if not api_key:
        raise RuntimeError(
            "OPENAI_API_KEY no configurada. Exporta la variable o colócala en .streamlit/secrets.toml"
        )
    return OpenAI(api_key=api_key)

# ==============================
# 🔥 Cliente Firestore
# ==============================
_db: Optional[firestore.Client] = None

def get_db() -> firestore.Client:
    global _db
    if _db:
        return _db

    # Usa tu método real aquí
    if not firebase_admin._apps:
        firebase_admin.initialize_app()   # O con credentials.Certificate(...)

    _db = firestore.client()
    return _db


# ============================================================
# 🧩 Obtener historial real según tu estructura
# ============================================================
def get_historial_ejercicio_firestore(
    correo_cliente: str,
    nombre_ejercicio: str,
    fecha_semana_actual: str,
    semanas_atras: int = 4,
    incluir_semana_actual: bool = False,
    debug: bool = False,
) -> List[Dict[str, Any]]:

    """
    Lee Firestore de acuerdo a la estructura REAL que tienes:
    - Documentos tipo: correo_formateado_YYYY_MM_DD
    - Campo: rutina = [ [ej1, ej2...], [ej1, ej2...], ... ]
    Busca hacia atrás hasta `semanas_atras` semanas. Por defecto NO incluye la semana actual.
    """

    db = get_db()
    historial: List[Dict[str, Any]] = []

    def _norm(txt: str) -> str:
        txt = (txt or "").strip().lower()
        txt = unicodedata.normalize("NFD", txt).encode("ascii", "ignore").decode("utf-8")
        return txt

    nombre_norm = _norm(nombre_ejercicio)

    # Formatear correo para IDs
    correo_formateado = correo_cliente.replace("@", "_").replace(".", "_")

    # Convertir fecha actual (YYYY_MM_DD)
    fecha_base = datetime.strptime(fecha_semana_actual, "%Y_%m_%d").date()

    start = 0 if incluir_semana_actual else 1
    if debug:
        print(f"[debug] buscando ejercicio='{nombre_ejercicio}' correo='{correo_cliente}' fecha_base='{fecha_semana_actual}' semanas_atras={semanas_atras} incluir_actual={incluir_semana_actual}")
    docs_revisados = []
    for i in range(start, start + semanas_atras):
        fecha_semana = fecha_base - timedelta(weeks=i)
        fecha_str = fecha_semana.strftime("%Y_%m_%d")

        doc_id = f"{correo_formateado}_{fecha_str}"
        doc = db.collection("rutinas_semanales").document(doc_id).get()
        docs_revisados.append(doc_id)

        if not doc.exists:
            continue

        data = doc.to_dict() or {}

        # Extrae ejercicios desde varias formas posibles:
        # 1) data["rutina"] = lista de días -> lista de ejercicios (dicts)
        # 2) data["ejercicios"] = lista de ejercicios (dicts)
        # 3) cualquier campo lista que contenga dicts con clave "ejercicio"
        # 4) sub-mapas o el propio documento con clave "ejercicio"
        contenedores: list = []
        rutina = data.get("rutina")
        if isinstance(rutina, list):
            contenedores.append(rutina)
        elif isinstance(rutina, dict):
            # rutina como mapa de días -> lista de ejercicios
            contenedores.append(list(rutina.values()))

        ejercicios_flat = data.get("ejercicios")
        if isinstance(ejercicios_flat, list):
            contenedores.append([ejercicios_flat])

        for v in data.values():
            if isinstance(v, list) and any(isinstance(x, dict) and "ejercicio" in x for x in v):
                contenedores.append([v])
            if isinstance(v, dict):
                if "ejercicio" in v:
                    contenedores.append([[v]])
                # dict de días u otras claves que contengan listas de ejercicios
                for sub in v.values():
                    if isinstance(sub, list) and any(isinstance(x, dict) and "ejercicio" in x for x in sub):
                        contenedores.append([sub])

        if "ejercicio" in data:
            contenedores.append([[data]])

        if not contenedores:
            continue

        for cont in contenedores:
            for dia_index, ejercicios_dia in enumerate(cont):
                if not isinstance(ejercicios_dia, list):
                    continue
                for ej in ejercicios_dia:
                    if not isinstance(ej, dict):
                        continue
                    if _norm(str(ej.get("ejercicio", ""))) == nombre_norm:

                        historial.append({
                            "fecha": fecha_str,
                            "dia": dia_index + 1,
                            "bloque": ej.get("bloque"),
                            "circuito": ej.get("circuito"),
                            "peso": ej.get("peso"),
                            "reps_min": ej.get("reps_min"),
                            "reps_max": ej.get("reps_max"),
                            "rir": ej.get("rir"),
                        })

    historial.sort(key=lambda x: x["fecha"])
    if debug:
        print(f"[debug] documentos revisados: {docs_revisados}")
        print(f"[debug] coincidencias encontradas: {len(historial)}")
        if historial:
            print(f"[debug] ejemplo: {historial[-1]}")
    return historial


# ============================================================
# 🤖 AGENTE DE RUTINAS — Versión ajustada
# ============================================================
def agente_sugerencia_rutina(
    correo_cliente: str,
    nombre_ejercicio: str,
    fecha_semana_actual: str,
    porcentaje_objetivo: Optional[float] = None,
) -> Dict[str, Any]:

    PORCENTAJE_OBJETIVO = 80.0  # valor por defecto si no viene de la UI
    SEMANAS_ATRAS = 2  # revisar solo las 2 semanas previas

    historial = get_historial_ejercicio_firestore(
        correo_cliente,
        nombre_ejercicio,
        fecha_semana_actual,
        semanas_atras=SEMANAS_ATRAS,
        incluir_semana_actual=False,
        debug=False,
    )

    def _to_float(value) -> Optional[float]:
        try:
            return float(str(value).replace(",", "."))
        except Exception:
            return None

    def _to_int(value) -> Optional[int]:
        try:
            return int(str(value).strip())
        except Exception:
            return None

    def _to_pct(value) -> Optional[float]:
        try:
            val = float(str(value).replace(",", "."))
            return val if val > 0 else None
        except Exception:
            return None

    # usa el mayor peso de las últimas 2 semanas (si empata, el más reciente)
    ultimo_peso = None
    ultimo_fecha = None
    ultimo_reps = None
    ultimo_rir = None

    for item in sorted(historial, key=lambda x: ( _to_float(x.get("peso")) or 0, x["fecha"]), reverse=True):
        p = _to_float(item.get("peso"))
        reps_candidatos = [_to_int(item.get("reps_max")), _to_int(item.get("reps_min"))]
        reps_val = next((r for r in reps_candidatos if r is not None and r > 0), None)
        rir_val = _to_int(item.get("rir"))
        if p is not None and reps_val is not None:
            ultimo_peso = p
            ultimo_fecha = item.get("fecha")
            ultimo_reps = reps_val
            ultimo_rir = rir_val
            break

    historial_json = json.dumps(historial, ensure_ascii=False)

    porcentaje_final = _to_pct(porcentaje_objetivo) or PORCENTAJE_OBJETIVO
    rm_teorico = None
    peso_objetivo = None
    if ultimo_peso is not None and ultimo_reps is not None:
        rm_teorico = calcular_rm_teorico(ultimo_peso, ultimo_reps, ultimo_rir)
        peso_objetivo = calcular_peso_por_porcentaje(rm_teorico, porcentaje_final)

    system_msg = """
Eres un experto coach de fuerza.
Analiza el historial del ejercicio y genera:
- peso sugerido (si hay último peso, úsalo como referencia base)
- reps sugeridas (usar reps_min / reps_max si existen)
- RIR sugerido
- Comentario explicativo

Responde SOLO JSON válido con esta estructura:

{
 "peso_sugerido": número o null,
 "reps_sugeridas": "texto",
 "rir_sugerido": número o null,
 "comentario": "texto"
}
"""

    user_msg = f"""
Cliente: {correo_cliente}
Ejercicio: {nombre_ejercicio}
Fecha semana actual: {fecha_semana_actual}

Historial encontrado:
{historial_json}

Ultimo peso registrado (si existe): {ultimo_peso} (fecha: {ultimo_fecha})
Últimas reps usadas para RM (si existen): {ultimo_reps} (RIR: {ultimo_rir})
RM teórico estimado (si existe): {rm_teorico}
Porcentaje solicitado: {porcentaje_objetivo} | Usando: {porcentaje_final}%
Peso objetivo para {porcentaje_final}% del RM (si existe): {peso_objetivo}
Mayor peso encontrado (últimas {SEMANAS_ATRAS} semanas previas): {ultimo_peso} (fecha: {ultimo_fecha}, reps: {ultimo_reps}, RIR: {ultimo_rir})

Genera la recomendación.
"""

    client = get_openai_client()

    response = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": system_msg},
            {"role": "user", "content": user_msg},
        ]
    )

    raw = response.output_text or ""

    def _parse_json(texto: str) -> Optional[dict]:
        """
        Intenta parsear JSON aun si viene envuelto en ```json ...```, con texto extra
        o agregado "undefined" al final. Busca el primer bloque {...}.
        """
        txt = (texto or "").strip()
        # Quita fences ```json ... ```
        if txt.startswith("```"):
            parts = txt.split("```")
            if len(parts) >= 3:
                # part[1] suele ser 'json\n{...}' o directamente '{...}'
                candidate = parts[1].strip()
                if candidate.lower().startswith("json"):
                    candidate = candidate[4:].strip()
                txt = candidate or parts[2].strip()
        # Si queda basura afuera, toma el primer bloque { ... }
        if "{" in txt and "}" in txt:
            try:
                start = txt.index("{")
                end = txt.rindex("}")
                txt = txt[start:end+1]
            except Exception:
                pass
        try:
            return json.loads(txt)
        except Exception:
            return None

    sugerencia = _parse_json(raw)
    if not isinstance(sugerencia, dict):
        sugerencia = {
            "peso_sugerido": None,
            "reps_sugeridas": None,
            "rir_sugerido": None,
            "comentario": f"Respuesta no válida: {raw}"
        }

    if rm_teorico is not None:
        sugerencia["rm_teorico"] = rm_teorico
    if peso_objetivo is not None:
        sugerencia["peso_objetivo_porcentaje"] = peso_objetivo
    sugerencia["porcentaje_usado"] = porcentaje_final

    sugerencia["historial_usado"] = historial
    return sugerencia


# ============================================================
# 🧪 Test rápido
# ============================================================
def main():
    # Ejemplo de uso con debug activado
    correo = "rbn.rodriguez94@gmail.com"
    ejercicio = "Barbell Hip Thrust"
    fecha_semana = "2025_11_17"

    try:
        _ = get_historial_ejercicio_firestore(
            correo_cliente=correo,
            nombre_ejercicio=ejercicio,
            fecha_semana_actual=fecha_semana,
            semanas_atras=4,
            incluir_semana_actual=True,
            debug=True,
        )
        sug = agente_sugerencia_rutina(
            correo_cliente=correo,
            nombre_ejercicio=ejercicio,
            fecha_semana_actual=fecha_semana,
        )
        print(json.dumps(sug, indent=2, ensure_ascii=False))
    except Exception as exc:
        print(f"[debug] error ejecutando agente: {exc}")


if __name__ == "__main__":
    main()
