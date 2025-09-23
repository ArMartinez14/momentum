# REFactor PLAN

Este documento inventaría duplicados, código muerto y propone la nueva estructura modular para una refactorización segura (sin cambios de comportamiento).

## Duplicados y patrones detectados

- Inicialización de Firebase/Firestore (variantes):
  - `crear_planificaciones.get_db` (cacheado con `@st.cache_resource`).
  - `diagnotico_rutina.get_db_safe` (con fallback ADC y mensajes).
  - `soft_login_full._db` (silencioso, puede devolver `None`).
  - `auth_guard` (init en módulo y `_db` global).
  - `_init_db` en `inicio.py`, `_ensure_fb` en `seguimiento_entrenamiento.py`, `dashboard._init_firebase`, `reportes.init_firebase`, `fix_errores_rutina.get_db`, `servicio_catalogos._init_db`, `editar_rutinas.get_db`, `offline_sync.get_db`.

- Normalización de correo/ID:
  - `normalizar_correo`, `correo_a_id`, `_norm_mail`, `normalizar_id`, `_normalizar_correo` en múltiples archivos (`inicio.py`, `crear_descarga.py`, `ingresar_cliente_view.py`, `seguimiento_entrenamiento.py`, etc.). Patrón: minúsculas + `@`/`.` → `_`.

- Inyección de CSS/tema Streamlit:
  - Bloques `<style>` repetidos en `crear_planificaciones.py`, `vista_rutinas.py`, `editar_rutinas.py`, `ingresar_cliente_view.py`, `inicio.py` con mismas variables (PRIMARY, SUCCESS, BG, SURFACE, TEXT_MAIN, TEXT_MUTED, STROKE) y selectores.

- Utilidades de parseo y helpers:
  - Float/int seguros (`_f`, `safe_float`, `to_float_or_zero`).
  - Parseo de repeticiones y RIR (min/max) en `guardar_rutina_view.py` y consumo en `seguimiento_entrenamiento.py`.
  - Fechas/semana: obtención de lunes actual, `fecha_lunes`, normalizaciones `YYYY_MM_DD`.

- Acceso a datos Firestore (consultas recurrentes):
  - Colecciones: `rutinas_semanales`, `usuarios`, `ejercicios`, `resumen_coach`, `configuracion_app/catalogos_ejercicios`.
  - Patrones de lectura por `correo` normalizado y `fecha_lunes`.

- Caching:
  - Uso de `@st.cache_resource` para DB y `@st.cache_data` para catálogos/ejercicios.

## Código muerto/obsoleto (candidatos)

- Comentarios largos de estilos duplicados que serán centralizados.
- Inicializaciones Firebase in-module una vez que se use `app_core/firebase_client.get_db()`.
- Duplicados de normalización de correo tras mover a `app_core/auth.py`.

Nota: Se eliminarán solo bloques no referenciados tras sustitución, sin cambiar comportamiento.

## Propuesta de estructura modular

- `app_core/`
  - `firebase_client.py`: `get_db()` único, cacheado, con prioridad `st.secrets["FIREBASE_CREDENTIALS"]` y fallback ADC; retorna `firestore.Client`.
  - `auth.py`: `normalizar_correo`, obtención de usuario por correo, checks de rol (`es_admin`, `rol_es`), integración suave con `soft_login_full` sin cambiar su API.
  - `theme.py`: paletas LIGHT/DARK, `inject_base_theme()` para insertar CSS variables y estilos comunes; permite overrides locales.
  - `utils.py`: `safe_int`, `safe_float`, normalización de texto, parseo reps/RIR a min/max, utilidades de fecha (`lunes_actual`, `iso_to_date`, `fecha_to_norm`).
  - `data_access.py`: funciones finas para leer/escribir `usuarios`, `ejercicios`, `rutinas_semanales`, `resumen_coach`, etc. Mantiene nombres/campos de Firestore (sin cambios de esquema).
  - `cache.py`: atajos a `@st.cache_data`/`@st.cache_resource` para estandarizar configuración.
  - `types.py` (opcional): `TypedDict`/`dataclasses` para hints (no rompe comportamiento).

## Plan de reemplazo seguro

1. Crear `app_core/*` con docstrings y type hints. No introducir dependencias nuevas.
2. Reemplazar llamadas de inicialización Firebase por `from app_core.firebase_client import get_db`.
3. Centralizar `normalizar_correo` y checks de rol en `app_core.auth` y reemplazar usos locales.
4. Reemplazar bloques de CSS repetidos por `from app_core.theme import inject_base_theme` y llamar al inicio de cada página.
5. Extraer parseos (`_f`, parse reps/RIR, semanas) a `app_core.utils` y actualizar importaciones.
6. Donde hay consultas recurrentes, introducir `app_core.data_access` sin cambiar la forma de los datos devueltos.
7. Limpiar imports no usados y comentarios obsoletos.

## Riesgos y mitigación

- Diferencias en inicialización Firebase: mantener misma prioridad de credenciales y cacheo; incluir fallback ADC como opción no disruptiva.
- CSS: mantener variables y selectores existentes para que la UI se vea igual; permitir overrides por página si existían.
- Normalización de correo: unificar a regla más común `(lower + @/. → _)` y revisar call sites afectadas.
- Caché: preservar decoradores y parámetros (e.g., `show_spinner=False`).

## Validación (smoke tests)

- Login suave (persistencia cookie, roles).
- Ver/Crear/Editar/Guardar Rutina.
- Reportes y “Finalizar día”.
- Gestión de ejercicios y catálogos.

Al finalizar, se publicará `REFACTOR_SUMMARY.md` con el mapa de cambios y ubicaciones nuevas, y se actualizará `README.md` con la estructura y ejecución.
