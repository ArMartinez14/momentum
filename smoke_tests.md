# Smoke tests (validación manual rápida)

Realiza estas pruebas en un entorno limpio con Python 3.11+.

## Preparación
- Activar venv y dependencias (ver README).
- Asegurar `FIREBASE_CREDENTIALS` en `.streamlit/secrets.toml` o configurar `GOOGLE_APPLICATION_CREDENTIALS`.

## 1. Login suave (soft login)
- `streamlit run inicio.py`
- Ver la pantalla de login (si aplica) o hidratación de cookie.
- Iniciar sesión con un usuario válido en colección `usuarios`.
- Confirmar que `st.session_state` contiene `correo`, `rol`, `nombre`.
- Cerrar sesión y volver a entrar.

## 2. Ver Rutinas
- Abrir `vista_rutinas.py`.
- Seleccionar cliente y semana.
- Validar render de días, finalización de día y cálculo de racha.

## 3. Crear Rutinas
- Abrir `crear_planificaciones.py`.
- Elegir cliente, correo y fecha (lunes).
- Agregar filas en Warm Up y Work Out, incluyendo RIR y repeticiones.
- Previsualizar rutina.
- Guardar rutina y verificar en Firestore `rutinas_semanales`.

## 4. Editar Rutinas
- Abrir `editar_rutinas.py`.
- Cargar una semana existente.
- Modificar ejercicios y guardar.
- Validar que cambios aparezcan en Firestore.

## 5. Guardar Reportes del Día
- Abrir `vista_rutinas.py`.
- Completar reporte de un día: series, reps, peso, RPE.
- Marcar día finalizado y validar flags `*_finalizado` y `*_rpe` en Firestore.

## 6. Gestión de ejercicios y catálogos
- Abrir `ingresar_cliente_view.py`.
- Crear/editar un ejercicio con video y atributos.
- Confirmar persistencia en `ejercicios`, visibilidad por rol (público/privado) y catálogos.

## 7. Reportes/Resumen
- Abrir `reportes.py` o `resumen_strava.py` si aplica.
- Validar agregaciones por semana, filtro warm up y real/teórico.

## 8. Temas/Estilos
- Cambiar preferencia de tema del sistema (oscuro/claro) y validar colores.
- Verificar botones primarios/secundarios, tarjetas y badges.

## 9. Caché
- Forzar recarga de catálogos/ejercicios y comprobar tiempos (cache vs. no cache).

## 10. Regresión de Firestore
- Revisar que nombres de colecciones y campos no hayan cambiado (lecturas/escrituras OK).
