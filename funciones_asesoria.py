# funciones_asesoria.py
# Registro robusto de features con import perezoso
from __future__ import annotations
import importlib
import streamlit as st

# Soporte para dos APIs de router:
# - exponer(nombre) como decorador
# - o register_feature(nombre, fn) como fallback
try:
    from rol_router import exponer  # decorador
except Exception:
    from rol_router import register_feature as _register_feature
    def exponer(nombre: str):
        def _decorador(fn):
            _register_feature(nombre, fn)
            return fn
        return _decorador


def _resolver_impl(modulos_posibles: list[str], funciones_posibles: list[str]):
    """
    Intenta importar uno de los módulos en modulos_posibles y obtener
    una función de funciones_posibles. Retorna el callable encontrado o
    lanza la última excepción si no encuentra nada.
    """
    ultimo_error = None
    for mod_name in modulos_posibles:
        try:
            m = importlib.import_module(mod_name)
        except Exception as e:
            ultimo_error = e
            continue
        for fn_name in funciones_posibles:
            fn = getattr(m, fn_name, None)
            if callable(fn):
                return fn
    if ultimo_error:
        raise ultimo_error
    raise ImportError(f"No se encontró ninguna función {funciones_posibles} en módulos {modulos_posibles}")


# ==============================
#  Features expuestas al router
# ==============================

@exponer("ver_rutinas")
def feature_ver_rutinas():
    # Primero intenta tu nombre real de archivo: ver_rutinas.py
    # como fallback soporta vista_rutinas.py
    try:
        impl = _resolver_impl(["ver_rutinas", "vista_rutinas"], ["ver_rutinas", "main", "run", "app"])
        return impl()
    except Exception as e:
        st.error("❌ No se pudo abrir 'Ver Rutinas'. Revisa el módulo 'ver_rutinas.py'.")
        st.exception(e)

@exponer("crear_rutinas")
def feature_crear_rutinas():
    try:
        impl = _resolver_impl(["crear_rutinas"], ["crear_rutinas", "main", "run", "app"])
        return impl()
    except Exception as e:
        st.error("❌ No se pudo abrir 'Crear Rutinas'.")
        st.exception(e)

@exponer("editar_rutinas")
def feature_editar_rutinas():
    try:
        impl = _resolver_impl(["editar_rutinas"], ["editar_rutinas", "main", "run", "app"])
        return impl()
    except Exception as e:
        st.error("❌ No se pudo abrir 'Editar Rutinas'.")
        st.exception(e)

@exponer("gestionar_clientes")
def feature_gestionar_clientes():
    try:
        impl = _resolver_impl(["gestionar_clientes", "ingresar_cliente"], ["gestionar_clientes", "ingresar_cliente", "main", "run", "app"])
        return impl()
    except Exception as e:
        st.error("❌ No se pudo abrir 'Ingresar Deportista o Ejercicio'.")
        st.exception(e)

@exponer("ejercicios")
def feature_ejercicios():
    try:
        impl = _resolver_impl(["ejercicios"], ["ejercicios", "main", "run", "app"])
        return impl()
    except Exception as e:
        st.error("❌ No se pudo abrir 'Ejercicios'.")
        st.exception(e)

@exponer("descargar_rutinas")
def feature_descargar_rutinas():
    try:
        impl = _resolver_impl(["descargar_rutinas", "crear_descarga", "descarga"], ["descargar_rutinas", "crear_descarga", "main", "run", "app"])
        return impl()
    except Exception as e:
        st.error("❌ No se pudo abrir 'Crear Descarga'.")
        st.exception(e)

@exponer("ver_reportes")
def feature_ver_reportes():
    try:
        impl = _resolver_impl(["ver_reportes", "reportes"], ["ver_reportes", "main", "run", "app"])
        return impl()
    except Exception as e:
        st.error("❌ No se pudo abrir 'Reportes'.")
        st.exception(e)

@exponer("resumen_admin")
def feature_resumen_admin():
    try:
        impl = _resolver_impl(["resumen_admin", "resumen"], ["resumen_admin", "resumen", "main", "run", "app"])
        return impl()
    except Exception as e:
        st.error("❌ No se pudo abrir 'Resumen (Admin)'.")
        st.exception(e)
