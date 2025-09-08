# rol_router.py
from typing import Callable, Dict, Any, Optional, Iterable
import functools

# ===== Roles =====
ROL_ADMIN = "admin"
ROL_ENTRENADOR = "entrenador"
ROL_DEPORTISTA = "deportista"
ROLES_VALIDOS = {ROL_ADMIN, ROL_ENTRENADOR, ROL_DEPORTISTA}

# ===== Permisos (capabilities) por rol =====
PERMISOS_POR_ROL = {
    ROL_ADMIN: {
        "ver_rutinas", "crear_rutinas", "editar_rutinas", "ver_reportes",
        "gestionar_clientes", "descargar_rutinas", "ejercicios", "resumen_admin",
    },
    ROL_ENTRENADOR: {
        "ver_rutinas", "crear_rutinas", "editar_rutinas", "ver_reportes",
        "gestionar_clientes", "descargar_rutinas", "ejercicios",
    },
    ROL_DEPORTISTA: {
        "ver_rutinas", "descargar_rutinas",
    },
}

# ===== Registro de implementaciones por feature =====
# { "feature": { "admin": func, "entrenador": func, "deportista": func, "default": func } }
_REGISTRO: Dict[str, Dict[str, Callable[..., Any]]] = {}

_get_current_role_adapter: Optional[Callable[[], str]] = None

def set_role_adapter(adapter: Callable[[], str]) -> None:
    global _get_current_role_adapter
    _get_current_role_adapter = adapter

def get_current_role(default: str = ROL_DEPORTISTA) -> str:
    if _get_current_role_adapter is None:
        return default
    rol = _get_current_role_adapter() or default
    return rol if rol in ROLES_VALIDOS else default

def can(rol: str, capability: str) -> bool:
    return capability in PERMISOS_POR_ROL.get(rol, set())

def requires_capability(capability: str):
    def deco(fn: Callable[..., Any]):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            rol = get_current_role()
            if not can(rol, capability):
                raise PermissionError(f"No autorizado: rol '{rol}' no tiene '{capability}'.")
            return fn(*args, **kwargs)
        return wrapper
    return deco

def exponer(feature_name: str, roles: Optional[Iterable[str]] = None, default: bool = False):
    roles = set(roles or [])
    def deco(fn: Callable[..., Any]):
        if feature_name not in _REGISTRO:
            _REGISTRO[feature_name] = {}
        if default:
            _REGISTRO[feature_name]["default"] = fn
        for r in roles:
            if r not in ROLES_VALIDOS:
                raise ValueError(f"Rol inválido '{r}' al registrar '{feature_name}'")
            _REGISTRO[feature_name][r] = fn
        return fn
    return deco

def get_feature_impl(feature_name: str, rol: Optional[str] = None) -> Callable[..., Any]:
    if feature_name not in _REGISTRO:
        raise KeyError(f"No existe feature registrado: '{feature_name}'")
    rol = rol or get_current_role()
    opciones = _REGISTRO[feature_name]
    if rol in opciones:
        return opciones[rol]
    if "default" in opciones:
        return opciones["default"]
    raise KeyError(f"No hay implementación para feature '{feature_name}' con rol '{rol}' y sin default.")

def run_feature(feature_name: str, *args, rol: Optional[str] = None, **kwargs) -> Any:
    impl = get_feature_impl(feature_name, rol=rol)
    return impl(*args, **kwargs)
