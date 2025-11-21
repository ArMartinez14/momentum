from __future__ import annotations
from typing import Any, Dict, List, Optional
from .firebase_client import get_db

# NOTA: No se cambian nombres de colecciones ni campos.


def usuarios_por_correo(correo: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    docs = list(db.collection("usuarios").where("correo", "==", (correo or "").lower()).limit(1).stream())
    if not docs:
        return None
    return docs[0].to_dict() or {}


def ejercicios_list(publico: Optional[bool] = None, entrenador: Optional[str] = None) -> List[Dict[str, Any]]:
    db = get_db()
    q = db.collection("ejercicios")
    if publico is True:
        q = q.where("publico", "==", True)
    if entrenador:
        q = q.where("entrenador", "==", entrenador)
    return [d.to_dict() or {} for d in q.stream()]


def rutina_semanal_por_id(doc_id: str) -> Optional[Dict[str, Any]]:
    db = get_db()
    doc = db.collection("rutinas_semanales").document(doc_id).get()
    if not doc.exists:
        return None
    return doc.to_dict() or {}


def rutinas_de_correo(correo_norm: str) -> List[Dict[str, Any]]:
    db = get_db()
    docs = list(db.collection("rutinas_semanales").where("correo", "==", correo_norm).stream())
    return [d.to_dict() or {} for d in docs]


def catalogo_ejercicios() -> Dict[str, Any]:
    db = get_db()
    doc = db.collection("configuracion_app").document("catalogos_ejercicios").get()
    return doc.to_dict() or {}
