#!/usr/bin/env python3
"""Marca todos los ejercicios como públicos en Firestore."""

import argparse
import sys
from typing import Optional

import firebase_admin
from firebase_admin import credentials, firestore


def _init_firebase(cred_path: Optional[str]) -> None:
    if firebase_admin._apps:
        return

    if cred_path:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)
        return

    try:
        firebase_admin.initialize_app()
    except ValueError as exc:
        raise SystemExit(
            "No se pudo inicializar Firebase. Usa --cred con el path al JSON del servicio."
        ) from exc


def _marcar_publicos(batch_size: int) -> tuple[int, int]:
    db = firestore.client()
    coleccion = db.collection("ejercicios")

    batch = db.batch()
    writes = 0
    total = 0
    pendientes = 0

    for doc in coleccion.stream():
        total += 1
        data = doc.to_dict() or {}
        if data.get("publico") is True:
            continue

        batch.update(doc.reference, {"publico": True})
        pendientes += 1
        writes += 1

        if writes >= batch_size:
            batch.commit()
            batch = db.batch()
            writes = 0

    if writes:
        batch.commit()

    return total, pendientes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--cred",
        help="Ruta al archivo JSON de credenciales de servicio.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=400,
        help="Límite de escrituras por batch (default: 400).",
    )
    args = parser.parse_args()

    _init_firebase(args.cred)

    total, actualizados = _marcar_publicos(args.batch_size)
    print(f"Documentos leídos: {total}")
    print(f"Documentos actualizados a público: {actualizados}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
