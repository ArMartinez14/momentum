# offline_sync.py
import time
from typing import Dict, Any, List, Tuple
import streamlit as st
import firebase_admin
from firebase_admin import firestore

from offline_storage import (
    peek_mutations, replace_mutations, set_last_sync_ok, is_offline
)

# === Conector Firestore (Admin SDK) ===
def get_db():
    # Ya lo inicializas en tu app principal; solo usa firestore.client()
    return firestore.client()

def _apply_mutation(db, m: Dict[str, Any]):
    """Aplica UNA mutación contra Firestore. Puedes extender con más tipos."""
    op = m.get("op")
    if op == "update_doc":
        doc_path = m["doc_path"]            # p.ej. "rutinas_semanales/abc123"
        data     = m.get("data", {})
        merge    = bool(m.get("merge", True))
        doc_ref  = _doc_ref_from_path(db, doc_path)
        # Last-write-wins (tu app define las reglas; aquí un update/merge simple)
        doc_ref.set(data, merge=merge)
        return True
    else:
        # futuros tipos: "delete_doc", "create_doc", "array_union", etc.
        return False

def _doc_ref_from_path(db, path: str):
    # path "col/doc/col/doc" -> navegar dinámico
    parts = path.split("/")
    ref = None
    if len(parts) % 2 != 0:
        raise ValueError(f"doc_path inválido: {path}")
    for i in range(0, len(parts), 2):
        col = parts[i]; doc = parts[i+1]
        if ref is None:
            ref = db.collection(col).document(doc)
        else:
            ref = ref.collection(col).document(doc)
    return ref

def try_sync_now() -> Tuple[int, int]:
    """Intenta sincronizar toda la cola. Devuelve (ok, fail)."""
    if is_offline():
        return (0, 0)

    db = get_db()
    queue = peek_mutations()
    if not queue:
        return (0, 0)

    ok = 0
    fail = 0
    new_queue: List[Dict[str, Any]] = []
    for m in queue:
        try:
            _apply_mutation(db, m)
            ok += 1
        except Exception as e:
            # Si falla por red o conflicto, lo reintentamos más tarde
            new_queue.append(m)
            fail += 1

    replace_mutations(new_queue)
    if fail == 0:  # todo OK
        set_last_sync_ok()
    return (ok, fail)
