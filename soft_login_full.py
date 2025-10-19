# soft_login_full.py
from __future__ import annotations
import json
import time
from datetime import datetime, timezone, timedelta

import streamlit as st

# Dependencias opcionales (manejamos degradado si no están)
try:
    from itsdangerous import TimestampSigner, BadSignature, SignatureExpired
except Exception:
    TimestampSigner = None
    BadSignature = Exception
    SignatureExpired = Exception

try:
    import extra_streamlit_components as stx
except Exception:
    stx = None

__all__ = ["soft_login_barrier", "soft_logout", "soft_login_test_ui"]

# =========================
# Config
# =========================
COOKIE_NAME = "momentum_auth"
COOKIE_TTL_SECONDS = 24 * 60 * 60    # 24 horas por defecto cuando no hay "Recordarme"
REMEMBER_TTL_SECONDS = 7 * 24 * 3600
COL_USUARIOS = "usuarios"

# Keys internas (session_state)
_CM_USER_KEY      = "softlogin_cookie_mgr"      # key visible del componente
_CM_STATE_KEY     = "_softlogin_cm_instance"    # instancia del componente
_CACHE_TOKEN_KEY  = "_softlogin_cached_token"   # token cacheado en memoria
_BOOTSTRAP_FLAG   = "_softlogin_bootstrapped"   # 1 solo rerun inicial
_KILL_TS_KEY      = "_softlogin_kill_ts"        # marca de logout
_COOKIE_TS_FIELD  = "ts"                        # campo "ts" en la cookie
_PAYLOAD_KEY      = "_softlogin_payload"        # último payload persistido
_REMEMBER_KEY     = "_softlogin_remember"       # preferencia de recordarme
_UI_STATE_KEY     = "ui_state"                  # snapshot liviano de estado de UI
_UI_RESTORED_FLAG = "_softlogin_ui_restored"    # evita rehidratar varias veces en la misma sesión

# Qué versiones usamos para evolucionar el formato sin romper sesiones previas
_UI_STATE_VERSION = 1


def _role_bucket(role: str | None) -> str | None:
    """Agrupa roles equivalentes para persistir/restaurar estado contextual."""
    if not role:
        return None
    role_key = str(role).strip().lower()
    if role_key in ("entrenador", "admin", "administrador"):
        return "entrenador"
    if role_key == "deportista":
        return "deportista"
    return None


def _collect_persisted_ui_state(role: str | None) -> dict:
    """Obtiene un snapshot acotado del estado que queremos recordar entre sesiones."""
    snapshot: dict[str, object] = {"version": _UI_STATE_VERSION}

    menu_actual = st.session_state.get("menu_radio")
    if isinstance(menu_actual, str) and menu_actual:
        snapshot["menu_radio"] = menu_actual

    bucket = _role_bucket(role)
    role_payload: dict[str, object] = {}
    if bucket == "entrenador":
        cliente_sel = st.session_state.get("_cliente_sel")
        if isinstance(cliente_sel, str) and cliente_sel:
            role_payload["_cliente_sel"] = cliente_sel

        semana_sel = st.session_state.get("semana_sel")
        if isinstance(semana_sel, str) and semana_sel:
            role_payload["semana_sel"] = semana_sel

        dia_sel = st.session_state.get("dia_sel")
        if isinstance(dia_sel, (str, int)) and dia_sel != "":
            role_payload["dia_sel"] = str(dia_sel)

        mostrar_lista = st.session_state.get("_mostrar_lista_clientes")
        if isinstance(mostrar_lista, bool):
            role_payload["_mostrar_lista_clientes"] = mostrar_lista

    elif bucket == "deportista":
        semana_sel = st.session_state.get("semana_sel")
        if isinstance(semana_sel, str) and semana_sel:
            role_payload["semana_sel"] = semana_sel

        dia_sel = st.session_state.get("dia_sel")
        if isinstance(dia_sel, (str, int)) and dia_sel != "":
            role_payload["dia_sel"] = str(dia_sel)

    if role_payload and bucket:
        snapshot["role_state"] = {bucket: role_payload}

    # Si sólo tenemos la versión (sin datos útiles) retornamos dict vacío
    if len(snapshot) == 1 and "version" in snapshot:
        return {}
    return snapshot


def _restore_persisted_ui_state(role: str | None, state: object) -> bool:
    """Rehidrata el estado persistido. Devuelve True si se sembró algo."""
    if not isinstance(state, dict):
        return False

    restored = False

    menu_guardado = state.get("menu_radio")
    if isinstance(menu_guardado, str) and menu_guardado and "menu_radio" not in st.session_state:
        st.session_state["menu_radio"] = menu_guardado
        restored = True

    bucket = _role_bucket(role)
    if not bucket:
        return restored

    role_state = None
    role_state_map = state.get("role_state")
    if isinstance(role_state_map, dict):
        role_state = role_state_map.get(bucket)

    # Compatibilidad: si antes guardábamos plano, tomar de raíz
    if role_state is None:
        role_state = state

    if not isinstance(role_state, dict):
        return restored

    def _seed_if_absent(key: str, value: object):
        nonlocal restored
        if value is None or key in st.session_state:
            return
        st.session_state[key] = value
        restored = True

    if bucket == "entrenador":
        cliente_sel = role_state.get("_cliente_sel")
        if isinstance(cliente_sel, str) and cliente_sel:
            _seed_if_absent("_cliente_sel", cliente_sel)

        semana_sel = role_state.get("semana_sel")
        if isinstance(semana_sel, str) and semana_sel:
            _seed_if_absent("semana_sel", semana_sel)

        dia_sel = role_state.get("dia_sel")
        if isinstance(dia_sel, (str, int)) and str(dia_sel):
            _seed_if_absent("dia_sel", str(dia_sel))

        mostrar_lista = role_state.get("_mostrar_lista_clientes")
        if isinstance(mostrar_lista, bool):
            _seed_if_absent("_mostrar_lista_clientes", mostrar_lista)

    elif bucket == "deportista":
        semana_sel = role_state.get("semana_sel")
        if isinstance(semana_sel, str) and semana_sel:
            _seed_if_absent("semana_sel", semana_sel)

        dia_sel = role_state.get("dia_sel")
        if isinstance(dia_sel, (str, int)) and str(dia_sel):
            _seed_if_absent("dia_sel", str(dia_sel))

    return restored

# =========================
# Helpers de URL (respaldo móvil)
# =========================
def _set_url_token(token: str):
    """Guarda el token firmado en la URL (?mt=...) para rehidratar sesión en móviles si la cookie no vuelve."""
    try:
        qs = dict(st.query_params)
        if qs.get("mt") != token:
            qs["mt"] = token
            st.query_params.update(qs)
    except Exception:
        # Compatibilidad con versiones antiguas
        pass

def _read_token_from_url() -> str | None:
    try:
        return st.query_params.get("mt")
    except Exception:
        return None

def _clear_url_token():
    try:
        qs = dict(st.query_params)
        if "mt" in qs:
            qs.pop("mt", None)
            st.query_params.update(qs)
    except Exception:
        pass

# =========================
# Policies coherentes para la cookie
# =========================
def _cookie_flags():
    """
    Cloud (HTTPS): SameSite=None + Secure=True (requerido por Safari/Chrome móviles).
    Local (HTTP):  SameSite=Lax  + Secure=False (en http no se puede secure=True).
    Controlado por secrets, con defaults seguros.
    Puedes forzar con:
      ENV = "cloud" | "local"
      SOFTLOGIN_SAMESITE = "None" | "Lax"
      SOFTLOGIN_SECURE = true | false
    """
    env = (str(st.secrets.get("ENV", "cloud")) or "cloud").lower()
    if env not in ("cloud", "local"):
        env = "cloud"

    if env == "cloud":
        same_site = "None"
        secure_flag = True
    else:
        same_site = "Lax"
        secure_flag = False

    # Override opcional por secrets
    same_site = str(st.secrets.get("SOFTLOGIN_SAMESITE", same_site))
    secure_flag = bool(st.secrets.get("SOFTLOGIN_SECURE", secure_flag))

    return {
        "path": "/",
        "same_site": same_site,  # ¡ojo: 'same_site' (no 'samesite')!
        "secure": secure_flag,
    }

# =========================
# Firmado
# =========================
def _signer():
    secret = st.secrets.get("SOFTLOGIN_SECRET", "dev-secret-change-me")
    if TimestampSigner is None:
        # Modo degradado (dev) si faltan deps: no firma (solo para pruebas locales)
        class _Dummy:
            def sign(self, b): return b.decode() if isinstance(b, (bytes, bytearray)) else str(b)
            def unsign(self, s, max_age=None): return s
        return _Dummy()
    return TimestampSigner(secret)

# =========================
# Firebase helpers
# =========================
def _db():
    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
        if not firebase_admin._apps:
            cred_dict = json.loads(st.secrets["FIREBASE_CREDENTIALS"])
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred)
        return firestore.client()
    except Exception:
        return None

def _find_user(correo: str):
    """Busca usuario por correo (normalizado a minúsculas) en la colección 'usuarios'."""
    db = _db()
    if db is None:
        return None
    try:
        correo = (correo or "").strip().lower()
        q = db.collection(COL_USUARIOS).where("correo", "==", correo).limit(1).stream()
        doc = next(q, None)
        if not doc:
            return None
        d = doc.to_dict() or {}
        return {
            "correo": d.get("correo", correo).strip().lower(),
            "nombre": d.get("nombre", ""),
            "rol": (d.get("rol", "") or "deportista").strip().lower(),
            "activo": False if d.get("activo") is False else True,
        }
    except Exception:
        return None

# =========================
# CookieManager (singleton)
# =========================
def _cm():
    if stx is None:
        return None
    inst = st.session_state.get(_CM_STATE_KEY)
    if inst is None:
        inst = stx.CookieManager(key=_CM_USER_KEY)
        st.session_state[_CM_STATE_KEY] = inst
        # Montar el componente y precargar cookies
        try:
            inst.get_all()
        except Exception:
            pass
    return inst

# =========================
# Set/Get/Del cookie (robustos)
# =========================
def _set_cookie(cm, payload: dict, ttl: int):
    ttl = int(ttl)
    payload_to_store = dict(payload)
    payload_to_store.setdefault(_COOKIE_TS_FIELD, int(time.time()))
    payload_to_store["ttl"] = int(payload_to_store.get("ttl", ttl))

    token = _signer().sign(json.dumps(payload_to_store).encode())
    if isinstance(token, (bytes, bytearray)):
        token = token.decode()

    # Cache en memoria para el siguiente render
    st.session_state[_CACHE_TOKEN_KEY] = token
    st.session_state[_PAYLOAD_KEY] = payload_to_store
    st.session_state[_REMEMBER_KEY] = bool(payload_to_store.get("remember"))

    # Respaldo en URL (para móviles donde la cookie puede no volver en el 1er refresh)
    _set_url_token(token)

    if not cm:
        return

    expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl)
    flags = _cookie_flags()

    # Intento 1: firma moderna (same_site / expires_at)
    try:
        cm.set(
            COOKIE_NAME, token,
            expires_at=expires_at,
            key="set_"+COOKIE_NAME,
            path=flags["path"],
            same_site=flags["same_site"],
            secure=flags["secure"],
        )
        return
    except TypeError:
        pass

    # Intento 2 (fallback): firma antigua (samesite / expires)
    try:
        cm.set(
            COOKIE_NAME, token,
            expires=expires_at,                 # 👈 nota el nombre
            key="set_"+COOKIE_NAME,
            path=flags["path"],
            samesite=flags["same_site"],        # 👈 nota el nombre
            secure=flags["secure"],
        )
    except Exception:
        # Último recurso: no romper la app, pero avisar en UI
        st.warning("No se pudo persistir la cookie de sesión. Revisa la versión de extra-streamlit-components.")

def _read_token_from_component(cm):
    """Lee primero get_all() (suele estar antes), luego get()."""
    if not cm:
        return None
    try:
        all_c = cm.get_all() or {}
        tok = all_c.get(COOKIE_NAME)
        if tok:
            return tok
    except Exception:
        pass
    try:
        return cm.get(COOKIE_NAME)
    except Exception:
        return None

def _get_cookie(cm):
    # 1) componente (get_all -> get)
    token = _read_token_from_component(cm)

    # 2) respaldo: token en URL
    if not token:
        token = _read_token_from_url()

    # 3) fallback a cache en memoria
    if not token:
        token = st.session_state.get(_CACHE_TOKEN_KEY)

    if not token:
        return None
    try:
        raw = _signer().unsign(token, max_age=31 * 24 * 3600)  # tope 31 días
        if isinstance(raw, (bytes, bytearray)):
            raw = raw.decode()
        return json.loads(raw)
    except (BadSignature, SignatureExpired, Exception):
        return None

def _del_cookie(cm):
    if not cm:
        return
    flags = _cookie_flags()
    # 1) delete directo
    try:
        cm.delete(COOKIE_NAME, key="del_"+COOKIE_NAME, path=flags["path"])
    except Exception:
        pass
    # 2) expirar en pasado (compat estricta, moderna)
    try:
        past = datetime(1970, 1, 1, tzinfo=timezone.utc)
        cm.set(
            COOKIE_NAME, "",
            expires_at=past,
            key="expire_"+COOKIE_NAME,
            path=flags["path"],
            same_site=flags["same_site"],
            secure=flags["secure"],
        )
    except TypeError:
        # 3) expirar en pasado (fallback: samesite/expires)
        try:
            past = datetime(1970, 1, 1, tzinfo=timezone.utc)
            cm.set(
                COOKIE_NAME, "",
                expires=past,
                key="expire2_"+COOKIE_NAME,
                path=flags["path"],
                samesite=flags["same_site"],
                secure=flags["secure"],
            )
        except Exception:
            pass

# =========================
# Hidratación de sesión desde cookie/URL
# =========================
def _hydrate_from_cookie():
    # Forzar instanciación del componente (ayuda a iOS/Android en 1er render)
    cm = _cm()

    data = _get_cookie(cm)
    if data:
        # Kill-switch: si hiciste logout, ignora cookies anteriores a ese momento
        kill_ts = st.session_state.get(_KILL_TS_KEY, 0)
        cookie_ts = int(data.get(_COOKIE_TS_FIELD, 0) or 0)
        if cookie_ts <= kill_ts:
            st.session_state[_BOOTSTRAP_FLAG] = True
            st.session_state.pop(_PAYLOAD_KEY, None)
            st.session_state.pop(_REMEMBER_KEY, None)
            return cm

        remember_flag = bool(data.get("remember"))
        if int(data.get("ttl") or 0) <= 0:
            data["ttl"] = REMEMBER_TTL_SECONDS if remember_flag else COOKIE_TTL_SECONDS

        if not st.session_state.get("correo"):
            st.session_state.correo = data.get("correo", "")
            st.session_state.rol = data.get("rol", "")
            st.session_state.nombre = data.get("nombre", "")
            st.session_state.primer_nombre = data.get("primer_nombre", "")

        st.session_state[_PAYLOAD_KEY] = data
        st.session_state[_REMEMBER_KEY] = remember_flag

        if not st.session_state.get(_UI_RESTORED_FLAG):
            if _restore_persisted_ui_state(st.session_state.get("rol"), data.get(_UI_STATE_KEY)):
                st.session_state[_UI_RESTORED_FLAG] = True
        st.session_state[_BOOTSTRAP_FLAG] = True
        return cm

    # 1 solo rerun de bootstrap para que el componente devuelva cookies en el siguiente frame
    if not st.session_state.get(_BOOTSTRAP_FLAG):
        st.session_state[_BOOTSTRAP_FLAG] = True
        st.rerun()

    return cm

# =========================
# API pública
# =========================
def soft_login_barrier(required_roles=None, titulo="Bienvenido", ttl_seconds: int = COOKIE_TTL_SECONDS) -> bool:
    """Login por correo con persistencia en cookie firmada + respaldo URL para móviles."""
    cm = _hydrate_from_cookie()

    if st.session_state.get("correo"):
        user_data = _find_user(st.session_state.get("correo"))
        if not user_data or not user_data.get("activo", True):
            st.error("Tu cuenta está desactivada. Contacta al administrador.")
            if st.button("Cambiar de cuenta", key="btn_logout_inactivo"):
                soft_logout()
            return False
        if required_roles:
            rol = (st.session_state.get("rol") or "").lower()
            if rol not in [r.lower() for r in required_roles]:
                st.error("No tienes permisos para ver esta aplicación.")
                st.caption(f"Tu rol actual es: **{rol or '(desconocido)'}**")
                if st.button("Cambiar de cuenta"):
                    soft_logout()
                return False

        remember_flag = bool(st.session_state.get(_REMEMBER_KEY, False))
        payload = dict(st.session_state.get(_PAYLOAD_KEY) or {})
        payload.update({
            "correo": st.session_state.get("correo", ""),
            "rol": st.session_state.get("rol", payload.get("rol", "")),
            "nombre": st.session_state.get("nombre", payload.get("nombre", "")),
            "primer_nombre": st.session_state.get("primer_nombre", payload.get("primer_nombre", "")),
            "remember": remember_flag,
            _COOKIE_TS_FIELD: int(time.time()),
        })
        ttl_pref = REMEMBER_TTL_SECONDS if remember_flag else ttl_seconds
        payload["ttl"] = ttl_pref

        ui_state = _collect_persisted_ui_state(payload.get("rol"))
        if ui_state:
            payload[_UI_STATE_KEY] = ui_state
        else:
            payload.pop(_UI_STATE_KEY, None)

        if cm:
            _set_cookie(cm, payload, ttl_pref)
        else:
            st.session_state[_PAYLOAD_KEY] = payload
            st.session_state[_REMEMBER_KEY] = remember_flag
        return True

    # UI del login
    st.title(titulo)
    st.caption("Ingresa tu correo (no se requiere contraseña).")

    if stx is None or TimestampSigner is None:
        st.info("Nota: faltan dependencias para persistir la sesión. Instala "
                "`extra-streamlit-components` e `itsdangerous`.")

    correo = st.text_input("Correo electrónico", key="login_correo", placeholder="nombre@dominio.com")
    # “Recordarme” a 7 días
    col1, _ = st.columns([1, 3])
    remember = col1.checkbox("Recordarme (7 días)", value=True)

    if st.button("Continuar"):
        correo = (correo or "").strip().lower().replace(" ", "")
        if not correo or "@" not in correo:
            st.warning("Escribe un correo válido.")
            st.stop()

        user = _find_user(correo)
        if not user:
            st.error("Correo no encontrado en la colección 'usuarios'.")
            st.stop()

        if not user.get("activo", True):
            st.error("Tu cuenta está desactivada. Contacta al administrador.")
            st.stop()

        st.session_state.correo = user["correo"]
        st.session_state.rol = user["rol"]
        st.session_state.nombre = user.get("nombre", "")
        st.session_state.primer_nombre = (st.session_state.nombre.split()[0].title()
                                          if st.session_state.nombre else st.session_state.correo.split("@")[0].title())

        remember_flag = bool(remember)
        ttl = REMEMBER_TTL_SECONDS if remember_flag else ttl_seconds
        payload = {
            "correo": st.session_state.correo,
            "rol": st.session_state.rol,
            "nombre": st.session_state.nombre,
            "primer_nombre": st.session_state.primer_nombre,
            _COOKIE_TS_FIELD: int(time.time()),
            "remember": remember_flag,
            "ttl": ttl,
        }
        ui_state = _collect_persisted_ui_state(st.session_state.get("rol"))
        if ui_state:
            payload[_UI_STATE_KEY] = ui_state
        _set_cookie(cm, payload, ttl)

        st.rerun()

    return False

def soft_logout():
    cm = _cm()

    # Kill-switch: marca logout; ignoraremos cualquier cookie con ts <= ahora
    st.session_state[_KILL_TS_KEY] = int(time.time())

    # Borra/expira cookie
    _del_cookie(cm)

    # Limpia token en URL (respaldo móviles)
    _clear_url_token()

    # Limpia estado y caches
    for k in ["correo", "rol", "nombre", "primer_nombre",
              "menu_radio", "_menu_target", "_last_menu",
              "_mostrar_lista_clientes", "_cliente_sel",
              "semana_sel", "dia_sel",
              _CACHE_TOKEN_KEY, _BOOTSTRAP_FLAG,
              _PAYLOAD_KEY, _REMEMBER_KEY,
              _UI_RESTORED_FLAG]:
        st.session_state.pop(k, None)

    st.rerun()

# =========================
# UI mínima de prueba
# =========================
def soft_login_test_ui():
    """
    Prueba el módulo sin tocar la app principal:
        streamlit run app_login_test.py
    """
    ok = soft_login_barrier(titulo="Bienvenido (test)", required_roles=None)
    if not ok:
        return

    st.success(f"Conectado: {st.session_state.get('correo')} ({st.session_state.get('rol')})")

    # Botón de logout de prueba
    if st.button("Cerrar sesión", key="btn_logout_test"):
        soft_logout()

    # Diagnóstico de cookie/token (usar key distinta para evitar colisión)
    try:
        import extra_streamlit_components as stx_local
        cm_dbg = stx_local.CookieManager(key="debug_cookie_mgr_unique")
        tok_cookie = cm_dbg.get(COOKIE_NAME)
    except Exception:
        tok_cookie = None

    st.caption(f"Cookie presente: {bool(tok_cookie)}  |  Token URL: {bool(_read_token_from_url())}")

# soft_login_full.py (solo SI te faltan estas funciones)
import streamlit as st

def get_logged_email() -> str | None:
    # Estándar de este proyecto: guardamos el correo en session_state
    # y/o (según tu implementación) lo lees de cookie/token.
    return st.session_state.get("soft_login_email")

def soft_login_test_ui():
    st.subheader("Diagnóstico Soft Login")
    st.write("session_state email:", st.session_state.get("soft_login_email"))
    st.write("query params:", dict(st.query_params))
    st.write("recuerda 7 días:", True)
