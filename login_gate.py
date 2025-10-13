# login_gate.py
import streamlit as st
import extra_streamlit_components as stx
from firebase_login import firebase_login_ui
from auth_guard import ensure_user_session, is_token_expired

def get_cookie_manager():
    return stx.CookieManager()

def login_barrier(cookie_name: str = "fb_idtoken") -> bool:
    st.subheader("Autenticación")
    cookie_manager = get_cookie_manager()

    # Lee token de cookie
    id_token = cookie_manager.get(cookie_name)

    # Si no hay sesión válida, muestra UI de login
    if not id_token or ("user" not in st.session_state) or is_token_expired():
        st.info("Inicia sesión para continuar.")
        firebase_login_ui(cookie_name=cookie_name, height=560)  # embebe FirebaseUI

        # Reintenta leer cookie por si el usuario acaba de loguearse
        id_token = cookie_manager.get(cookie_name)
        if id_token and ensure_user_session(id_token):
            st.success("Sesión iniciada ✅")
            st.experimental_rerun()
        else:
            st.stop()  # corta la ejecución hasta que haya sesión

    # Verifica/actualiza datos de sesión si el token cambió
    if id_token and ensure_user_session(id_token):
        st.success(f"Conectado: {st.session_state['correo']}")
        return True

    st.stop()
