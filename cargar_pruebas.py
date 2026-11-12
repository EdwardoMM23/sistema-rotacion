import sqlite3
from database import conectar

conexion = conectar()
# Configurar row_factory para acceder por nombre de columna
conexion.row_factory = sqlite3.Row

try:
    # Asegurarnos de que la línea exista
    conexion.execute("""
        INSERT OR IGNORE INTO lineas (nombre_linea)
        VALUES (?)
    """, ("LINEA_PRUEBA",))
    conexion.commit()

    # Recuperar el id_linea
    linea = conexion.execute(""" 
        SELECT id_linea
        FROM lineas
        WHERE nombre_linea = ?
        """, ("LINEA_PRUEBA",)).fetchone()

    if linea is None:
        raise ValueError("No se pudo crear ni encontrar la línea 'LINEA_PRUEBA'")

    operadores = [
        ("TEST001", "EDUARDO"),
        ("TEST002", "ZURY"),
        ("TEST003", "EDGARDO"),
        ("TEST004", "JAZMIN"),
        ("TEST005", "LUPITA"),
        ("TEST006", "YISSEL"),
        ("TEST007", "MAYREL"),
        ("TEST008", "IVONNE"),
    ]

    for numero, nombre in operadores:
        conexion.execute("""
            INSERT OR REPLACE INTO operadores
            (numero_empleado, nombre, id_linea)
            VALUES (?, ?, ?)
            """, (numero, nombre, linea["id_linea"]))
        conexion.commit()

    print("Operadores ficticios registrados correctamente.")

except Exception as e:
    conexion.rollback()
    raise e
finally:
    conexion.close()
