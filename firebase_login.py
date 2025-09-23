# firebase_login.py
import streamlit as st
import streamlit.components.v1 as components
import json

def firebase_login_ui(cookie_name: str = "fb_idtoken", height: int = 560):
    """
    Muestra FirebaseUI (Google + Email/Password) y mantiene el ID token
    actualizado en una cookie accesible desde Streamlit.
    Requiere: st.secrets["FIREBASE_CONFIG"]
    """
    firebase_config = json.loads(st.secrets["FIREBASE_CONFIG"])
    firebase_config_js = json.dumps(firebase_config)

    html = f"""
    <html>
      <head>
        <meta charset="UTF-8" />
        <!-- Firebase SDK (compat) -->
        <script src="https://www.gstatic.com/firebasejs/10.12.4/firebase-app-compat.js"></script>
        <script src="https://www.gstatic.com/firebasejs/10.12.4/firebase-auth-compat.js"></script>
        <!-- FirebaseUI -->
        <link rel="stylesheet" type="text/css" href="https://www.gstatic.com/firebasejs/ui/6.0.2/firebase-ui-auth.css" />
        <script src="https://www.gstatic.com/firebasejs/ui/6.0.2/firebase-ui-auth.js"></script>
        <style>
          body {{ margin:0; font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu; }}
          #loader {{ padding: 16px; }}
        </style>
      </head>
      <body>
        <div id="firebaseui-auth-container"></div>
        <div id="loader">Cargando login…</div>

        <script>
          const firebaseConfig = {firebase_config_js};
          if (!firebase.apps.length) {{
            firebase.initializeApp(firebaseConfig);
          }}
          const auth = firebase.auth();

          // Helpers
          function setCookie(name, value, days) {{
            const d = new Date();
            d.setTime(d.getTime() + (days*24*60*60*1000));
            const expires = "expires="+ d.toUTCString();
            document.cookie = name + "=" + (value || "") + ";" + expires + ";path=/";
          }}
          function postTokenToParent(idToken) {{
            setCookie("{cookie_name}", idToken, 1); // 1 día; el SDK lo reescribe al renovar
            if (window.parent) {{
              window.parent.postMessage({{ type: "fb_idtoken", token: idToken }}, "*");
            }}
          }}

          // Renueva/propaga token automáticamente
          auth.onIdTokenChanged(async (user) => {{
            if (user) {{
              const token = await user.getIdToken(/* forceRefresh */ true);
              localStorage.setItem("fb_idtoken", token);
              postTokenToParent(token);
            }}
          }});

          // Config FirebaseUI
          const uiConfig = {{
            callbacks: {{
              signInSuccessWithAuthResult: function(authResult, redirectUrl) {{
                document.getElementById('loader').textContent = "";
                return false; // sin redirección
              }},
              uiShown: function() {{
                document.getElementById('loader').style.display = 'none';
              }}
            }},
            signInFlow: 'popup',
            signInOptions: [
              firebase.auth.GoogleAuthProvider.PROVIDER_ID,
              firebase.auth.EmailAuthProvider.PROVIDER_ID
            ],
          }};

          const ui = firebaseui.auth.AuthUI.getInstance() || new firebaseui.auth.AuthUI(auth);
          ui.start('#firebaseui-auth-container', uiConfig);

          // Si ya hay sesión, emite token al cargar
          auth.onAuthStateChanged(async (user) => {{
            if (user) {{
              const token = await user.getIdToken();
              localStorage.setItem("fb_idtoken", token);
              postTokenToParent(token);
            }}
          }});
        </script>
      </body>
    </html>
    """
    components.html(html, height=height, scrolling=True)
