# REFACTOR SUMMARY

Este resumen documenta cambios aplicados, funciones extraídas, archivos afectados y riesgos controlados.

## Módulos creados
- `app_core/firebase_client.py` (nuevo): fuente única de `get_db()`; prioriza `st.secrets["FIREBASE_CREDENTIALS"]` con fallback ADC; cache con `@st.cache_resource`.
- `app_core/theme.py` (nuevo): `inject_theme()`/`inject_base_theme()` para CSS/tema unificado.
- `app_core/auth.py` (nuevo): `normalizar_correo`, `correo_actual`, `es_admin`, `rol_es`, `buscar_usuario_por_correo`.
- `app_core/utils.py` (nuevo): `safe_int`, `safe_float`, `normalizar_texto`, `parse_reps`, `parse_rir`, `parse_semanas`, `lunes_actual`, `iso_to_date`, `fecha_to_norm`.
- `app_core/data_access.py` (nuevo): utilidades de Firestore sin cambio de esquema (`usuarios_por_correo`, `ejercicios_list`, `rutina_semanal_por_id`, `rutinas_de_correo`, `catalogo_ejercicios`).

## Archivos de vistas actualizados (reemplazos no funcionales)
- `inicio.py`:
  - Firebase: `_init_db()` → `get_db()`.
  - CSS: bloque `<style>` → `inject_theme()`.
- `crear_planificaciones.py`:
  - Firebase: `get_db()` local eliminado → `get_db()` centralizado.
  - CSS: bloque `<style>` → `inject_theme()`.
  - Limpieza de imports duplicados.
- `vista_rutinas.py`:
  - Firebase: init manual → `get_db()`.
  - CSS: bloques `<style>` → `inject_theme()`.
- `editar_rutinas.py`:
  - Firebase: `get_db()` local eliminado → `get_db()` centralizado.
  - CSS: bloque `<style>` → `inject_theme()`.
- `dashboard.py`:
  - Firebase: `_init_firebase()` → `get_db()`.
  - CSS: se inyecta `inject_theme()`.
- `seguimiento_entrenamiento.py`:
  - Firebase: `_ensure_fb()` → `get_db()`.
  - CSS: bloque `<style>` → `inject_theme()`.
- `guardar_rutina_view.py`:
  - Firebase: `firestore.client()` directo → `get_db()`.

## Funciones extraídas / centralizadas
- Inicialización de Firebase: múltiples variantes (en `inicio.py`, `crear_planificaciones.py`, `vista_rutinas.py`, `editar_rutinas.py`, `dashboard.py`, `seguimiento_entrenamiento.py`) ahora usan `app_core/firebase_client.get_db()`.
- Tema/CSS: bloques repetidos en varias vistas ahora usan `app_core/theme.inject_theme()`.
- Normalización de correos y helpers de rol disponibles en `app_core/auth.py` (se usará progresivamente en futuras limpiezas).

## Código eliminado / limpiado
- Eliminadas inicializaciones locales de Firebase y funciones duplicadas (`_init_db`, `_init_firebase`, `_ensure_fb`, `get_db` local).
- Removidos bloques `<style>` grandes, sustituidos por `inject_theme()`.
- Limpieza de imports redundantes (p.ej., eliminación de `firebase_admin`, `credentials`, `initialize_app` donde ya no son necesarios; imports duplicados de `streamlit` en `crear_planificaciones.py`).

## Riesgos y mitigación
- Inicialización Firebase: se preserva prioridad de `st.secrets` y se añade fallback ADC idéntico al detectado en el repo; cacheado via `@st.cache_resource`.
- CSS/tema: selectores y variables conservan nombres y semántica, minimizando riesgos visuales. `inject_theme()` respeta estilos previos.
- Firestore: no se cambian nombres de colecciones ni campos; solo se centraliza el cliente. La lógica de consultas se mantiene.

## Verificación
- Ejecutar pruebas manuales según `smoke_tests.md`.
- Confirmar que flujos clave (login suave, ver/crear/editar/guardar rutina, reportes) se comportan igual.
