# funciones_asesoria.py
import streamlit as st
import importlib

from rol_router import (
    exponer, requires_capability,
    ROL_ADMIN, ROL_ENTRENADOR, ROL_DEPORTISTA
)

def _call_view(module_name: str, *names):
    """Importa dinámicamente un módulo y ejecuta la 1ª función disponible del listado `names`."""
    mod = importlib.import_module(module_name)
    for n in names:
        fn = getattr(mod, n, None)
        if callable(fn):
            return fn()
    # Si no encontramos ninguna, mostramos lo que sí existe para depurar
    disponibles = [a for a in dir(mod) if not a.startswith("_")]
    raise AttributeError(
        f"En {module_name} no se encontró ninguna de {names}. "
        f"Exportados disponibles: {disponibles[:40]}{' ...' if len(disponibles)>40 else ''}"
    )

# === VER RUTINAS (todos) ===
@exponer("ver_rutinas", roles=[ROL_ADMIN, ROL_ENTRENADOR, ROL_DEPORTISTA])
def feature_ver_rutinas():
    try:
        # Busca 'ver_rutinas' y, si no está, intenta 'vista_rutinas' (alias).
        _call_view("vista_rutinas", "ver_rutinas", "vista_rutinas")
    except Exception as e:
        st.error("No se pudo cargar la vista de rutinas (vista_rutinas).")
        st.exception(e)

# === CREAR RUTINAS (admin/entrenador) ===
@exponer("crear_rutinas", roles=[ROL_ADMIN, ROL_ENTRENADOR])
def feature_crear_rutinas():
    try:
        _call_view("crear_planificaciones", "crear_rutinas")
    except Exception as e:
        st.error("No se pudo cargar Crear Rutinas.")
        st.exception(e)

# === EDITAR RUTINAS (admin/entrenador) ===
@exponer("editar_rutinas", roles=[ROL_ADMIN, ROL_ENTRENADOR])
def feature_editar_rutinas():
    try:
        _call_view("editar_rutinas", "editar_rutinas")
    except Exception as e:
        st.error("No se pudo cargar Editar Rutinas.")
        st.exception(e)

# === REPORTES (admin/entrenador) ===
@exponer("ver_reportes", roles=[ROL_ADMIN, ROL_ENTRENADOR])
def feature_ver_reportes():
    try:
        _call_view("reportes", "ver_reportes")
    except Exception as e:
        st.error("No se pudo cargar Reportes.")
        st.exception(e)

# === DESCARGA (todos) ===
@exponer("descargar_rutinas", roles=[ROL_ADMIN, ROL_ENTRENADOR, ROL_DEPORTISTA])
def feature_descarga_rutina():
    try:
        _call_view("crear_descarga", "descarga_rutina")
    except Exception as e:
        st.error("No se pudo cargar Descarga de Rutinas.")
        st.exception(e)

# === GESTIONAR CLIENTES (admin/entrenador) ===
@requires_capability("gestionar_clientes")
@exponer("gestionar_clientes", roles=[ROL_ADMIN, ROL_ENTRENADOR])
def feature_gestionar_clientes():
    try:
        _call_view("ingresar_cliente_view", "ingresar_cliente_o_video_o_ejercicio")
    except Exception as e:
        st.error("No se pudo cargar la vista de Gestión de Clientes.")
        st.exception(e)

# === EJERCICIOS (admin/entrenador) ===
@exponer("ejercicios", roles=[ROL_ADMIN, ROL_ENTRENADOR])
def feature_ejercicios():
    try:
        _call_view("seccion_ejercicios", "base_ejercicios")
    except Exception as e:
        st.error("No se pudo cargar la sección de Ejercicios.")
        st.exception(e)

# === RESUMEN ADMIN (solo admin) ===
@exponer("resumen_admin", roles=[ROL_ADMIN])
def feature_resumen_admin():
    try:
        _call_view("admin_resumen", "ver_resumen_entrenadores")
    except Exception as e:
        st.error("No se pudo cargar el Resumen de Entrenadores (admin).")
        st.exception(e)
