"""Comprobación rápida de rutas de Fase 6. Ejecutar dentro del venv del proyecto."""
try:
    from app import app
except Exception as exc:
    print("No se pudo importar la aplicación. Activa el venv e instala requirements.txt.")
    print(f"Detalle: {exc}")
    raise SystemExit(1)

rutas = {regla.rule for regla in app.url_map.iter_rules()}
requeridas = {
    "/solicitar-cuenta", "/operadores/<int:id_operador>/estado",
    "/restricciones/historial", "/restricciones/<int:id_restriccion>/archivar",
    "/prestamos", "/prestamos/<int:id_prestamo>/accion",
}
fallas = sorted(requeridas - rutas)
if fallas:
    print("FALTAN rutas:")
    for ruta in fallas: print(" -", ruta)
    raise SystemExit(1)
print("Correcto: las rutas principales de Fase 6 están registradas.")
print("Esto no sustituye las pruebas manuales descritas en GUIA_FASE6.txt.")
