# login_gate.py
import streamlit as st
import extra_streamlit_components as stx
import streamlit.components.v1 as components
from textwrap import dedent
from firebase_login import firebase_login_ui
from auth_guard import ensure_user_session, is_token_expired

def get_cookie_manager():
    return stx.CookieManager()

def login_barrier(cookie_name: str = "fb_idtoken") -> bool:
    st.subheader("Autenticación")
    cookie_manager = get_cookie_manager()

    script = dedent(
        """
        <script>
        (function() {{
          const cookieName = "{cookie}";
          const maxAgeDays = 7;

          async function ensureStorageAccess() {{
            if (!document.hasStorageAccess) {{
              return;
            }}
            try {{
              const hasAccess = await document.hasStorageAccess();
              if (!hasAccess) {{
                await document.requestStorageAccess();
              }}
            }} catch (err) {{
              console.warn('Storage access request was rejected', err);
            }}
          }}

          function setCookieFromToken(token) {{
            if (!token) {{
              return;
            }}
            const expires = new Date(Date.now() + maxAgeDays * 24 * 60 * 60 * 1000).toUTCString();
            const isHttps = window.location.protocol === 'https:';
            const sameSite = isHttps ? 'SameSite=None' : 'SameSite=Lax';
            const secureAttr = isHttps ? ';Secure' : '';
            document.cookie = `${{cookieName}}=${{token}};expires=${{expires}};path=/;${{sameSite}}${{secureAttr}}`;
          }}

          async function propagateFromStorage() {{
            try {{
              await ensureStorageAccess();
              const stored = window.localStorage.getItem('fb_idtoken');
              if (stored) {{
                setCookieFromToken(stored);
              }}
            }} catch (err) {{
              console.warn('No se pudo leer localStorage', err);
            }}
          }}

          window.addEventListener('message', async (event) => {{
            if (!event.data || event.data.type !== 'fb_idtoken' || !event.data.token) {{
              return;
            }}
            try {{
              await ensureStorageAccess();
              window.localStorage.setItem('fb_idtoken', event.data.token);
            }} catch (err) {{
              console.warn('No se pudo persistir token en localStorage', err);
            }}
            setCookieFromToken(event.data.token);
          }});

          (async () => {{
            await propagateFromStorage();
          }})();

          document.addEventListener('visibilitychange', () => {{
            if (!document.hidden) {{
              propagateFromStorage();
            }}
          }});

          setInterval(propagateFromStorage, 1500);
        }})();
        </script>
        """
    ).format(cookie=cookie_name)

    components.html(script, height=0)

    if st.session_state.pop("auth_clear_cookie", False):
        try:
            cookie_manager.delete(cookie_name)
        except Exception:
            pass

    auth_error = st.session_state.pop("auth_error", None)
    if auth_error:
        st.error(auth_error)

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
