import unicodedata

ALIAS_ESTACION = {
    "PEGAMENTO": "PEGAMENTO",
    "ACCESORIOS": "ACCESORIOS",
    "ANEL": "ANEL",
    "DECAPADO": "DECAPADO",
    "CRIMPEO": "CRIMPEO",
    "CRIMEPO": "CRIMPEO",
    "INSERCION": "CRIMPEO",
    "HORNO": "HORNO",
    "CLIVADO": "HORNO",
    "MONTAJE": "HORNO",
    "PULIDO": "PULIDO",
    "VISUAL": "VISUAL",
    "INT/VISUAL": "VISUAL",
    "INTER": "VISUAL",
    "INTERFEROMETRO": "VISUAL",
    "IL": "IL_RL",
    "IL/RL": "IL_RL",
    "RL": "IL_RL",
    "TEST": "IL_RL",
    "TEST A": "IL_RL",
    "TEST B": "IL_RL",
    "BRADY": "BRADY",
    "AMARRE": "AMARRE",
}


def normalizar_estacion(nombre):
    """Convierte un alias al tipo estándar de estación."""
    texto = unicodedata.normalize("NFKD", str(nombre or "").strip().upper())
    clave = "".join(caracter for caracter in texto if not unicodedata.combining(caracter))
    clave = " ".join(clave.split())
    return ALIAS_ESTACION.get(clave, clave)


def validar_secuencia(
    estacion_anterior,
    estacion_actual,
    postura_anterior,
    postura_actual,
    ):

    
    # Normalizar nombres de estación
    est_ant = normalizar_estacion(estacion_anterior)
    est_act = normalizar_estacion(estacion_actual)

    # Reglas de incompatibilidad entre estaciones consecutivas
    incompatibles = {
        ("HORNO", "PULIDO"),
        ("IL_RL", "VISUAL"),
        ("VISUAL", "IL_RL"),
    }

    if (est_ant, est_act) in incompatibles:
        return False, f"La secuencia {est_ant} -> {est_act} no está permitida."

    # Regla: dos estaciones de pie consecutivas no están permitidas
    post_ant = " ".join(str(postura_anterior or "").strip().upper().split())
    post_act = " ".join(str(postura_actual or "").strip().upper().split())
    if post_ant in ("DE PIE", "DEPIE", "STANDING") and post_act in ("DE PIE", "DEPIE", "STANDING"):
        return False, "No se permiten dos estaciones consecutivas de pie."

    # Si pasa todas las validaciones
    return True, "Secuencia válida."

    