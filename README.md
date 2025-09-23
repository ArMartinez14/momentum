# App Asesorías

Aplicación Streamlit con Firebase/Firestore y Google Sheets.

## Requisitos
- Python 3.11+
- Entorno virtual (recomendado)
- Dependencias en `requirements.txt`
- Credenciales Firebase vía uno de:
  - `FIREBASE_CREDENTIALS` en `.streamlit/secrets.toml` (JSON del service account)
  - Variable `GOOGLE_APPLICATION_CREDENTIALS` apuntando a un service-account.json

## Instalación
```bash
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

## Ejecución
Ejemplos de páginas:
```bash
streamlit run inicio.py
# o
streamlit run vista_rutinas.py
# o
streamlit run crear_planificaciones.py
```

## Nuevo mapa de módulos (app_core)
- `app_core/firebase_client.py`: inicialización única de Firebase + `get_db()` cacheado con fallback ADC.
- `app_core/theme.py`: `inject_theme()`/`inject_base_theme()` con variables LIGHT/DARK y estilos compartidos.
- `app_core/auth.py`: helpers de autenticación: `normalizar_correo`, `correo_actual`, `es_admin`, `rol_es`, `buscar_usuario_por_correo`.
- `app_core/utils.py`: utilidades puras: `safe_int`, `safe_float`, `normalizar_texto`, `parse_reps`, `parse_rir`, `parse_semanas`, `lunes_actual`, `iso_to_date`, `fecha_to_norm`.
- `app_core/data_access.py`: acceso fino a Firestore (usuarios, ejercicios, rutinas, catálogos) sin cambiar esquemas.

## Convenciones
- Todas las páginas deben:
  - Obtener Firestore con:
    ```python
    from app_core.firebase_client import get_db
    db = get_db()
    ```
  - Inyectar tema con:
    ```python
    from app_core.theme import inject_theme
    inject_theme()
    ```
- No se cambian nombres de colecciones ni campos.
- Caches con `@st.cache_data` y `@st.cache_resource` se mantienen.

## Validación rápida
Consulta `smoke_tests.md` para un checklist de validación manual.
