"""Crea una cuenta de usuario desde la terminal."""
from getpass import getpass
from werkzeug.security import generate_password_hash
from database import crear_base_datos, conectar

ROLES = ("Lider", "Supervisor", "Enfermeria", "Administrador")


def main():
    crear_base_datos()
    print("\n=== Crear cuenta del Sistema de Rotación ===")
    nombre_usuario = input("Nombre de usuario: ").strip()
    nombre_completo = input("Nombre completo: ").strip()
    print("Tipo de usuario disponible: Lider, Supervisor, Enfermeria o Administrador")
    rol = input("Rol: ").strip()

    if not nombre_usuario or not nombre_completo or rol not in ROLES:
        print("Datos inválidos. No se creó la cuenta.")
        return

    clave = getpass("Contraseña (mínimo 10 caracteres): ")
    confirmacion = getpass("Repite la contraseña: ")
    if len(clave) < 10 or clave != confirmacion:
        print("La contraseña debe tener al menos 10 caracteres y ambas entradas deben coincidir.")
        return

    conexion = conectar()
    try:
        conexion.execute(
            "INSERT INTO usuarios(nombre_usuario,nombre_completo,contrasena_hash,rol,activo) VALUES(?,?,?,?,1)",
            (nombre_usuario, nombre_completo, generate_password_hash(clave), rol),
        )
        conexion.commit()
        print("Cuenta creada correctamente. En el inicio de sesión, selecciona el mismo tipo de usuario.")
    except Exception as error:
        conexion.rollback()
        print("No se creó la cuenta. Comprueba que el nombre de usuario no exista ya.")
        print(f"Detalle: {error}")
    finally:
        conexion.close()


if __name__ == "__main__":
    main()
