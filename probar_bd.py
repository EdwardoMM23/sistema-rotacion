from database import conectar

conexion = conectar()

try:
    tablas = conexion.execute("""
        SELECT name
        FROM sqlite_master
        WHERE type = 'table'
        ORDER BY name
    """).fetchall()

    print("TABLAS DE LA BASE DE DATOS:")

    for tabla in tablas:
        print("-", tabla["name"])

    estaciones = conexion.execute("""
        SELECT nombre_estacion, postura
        FROM estaciones
        ORDER BY id_estacion
    """).fetchall()

    print("\nESTACIONES REGISTRADAS:")

    for estacion in estaciones:
        print(
            f"- {estacion['nombre_estacion']}: "
            f"{estacion['postura']}"
        )

    print(f"\nTotal de estaciones: {len(estaciones)}")

finally:
    conexion.close()
