"""Inicializa o actualiza el esquema vigente de la aplicación. No borra datos."""
from database import crear_base_datos

if __name__ == "__main__":
    crear_base_datos()
    print("Base de datos inicializada correctamente mediante database.py.")
