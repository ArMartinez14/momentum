# motivacional.py
from __future__ import annotations
import random
from datetime import date

MENSAJES_MOTIVACIONALES = [
    "💪 ¡Éxito en tu entrenamiento de hoy, {nombre}! 🔥",
    "🚀 {nombre}, cada repetición te acerca más a tu objetivo.",
    "🏋️‍♂️ {nombre}, hoy es un gran día para superar tus límites.",
    "🔥 Vamos {nombre}, conviértete en la mejor versión de ti mismo.",
    "⚡ {nombre}, la constancia es la clave. ¡Dalo todo hoy!",
    "🥇 {nombre}, cada sesión es un paso más hacia la victoria.",
    "🌟 Nunca te detengas, {nombre}. ¡Hoy vas a brillar en tu entrenamiento!",
    "🏆 {nombre}, recuerda: disciplina > motivación. ¡Tú puedes!",
    "🙌 A disfrutar el proceso, {nombre}. ¡Confía en ti!",
    "💥 {nombre}, el esfuerzo de hoy es el resultado de mañana.",
    "🔥 {nombre}, hoy es el día perfecto para superar tu récord.",
]

def _random_mensaje(nombre: str) -> str:
    try:
        base = random.choice(MENSAJES_MOTIVACIONALES)
    except Exception:
        base = "💪 ¡Buen trabajo, {nombre}!"
    return base.format(nombre=(nombre or "Atleta").split(" ")[0])

def mensaje_motivador_del_dia(nombre: str, correo_id: str) -> str:
    """
    Mensaje 1x día por usuario, estable durante el día.
    """
    import streamlit as st
    hoy = date.today().isoformat()
    key = f"mot_msg_{correo_id}_{hoy}"
    if key not in st.session_state:
        st.session_state[key] = _random_mensaje(nombre)
    return st.session_state[key]
