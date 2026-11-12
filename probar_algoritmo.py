from algoritmo import puede_asignarse

casos = [
    ("Horno", "Pulido", "De pie", "De pie", False),
    ("IL / RL", "Visual / Interferómetro", "Ambas", "Sentado", False),
    ("Pegamento", "Accesorios", "Sentado", "Sentado", True),
    ("Pulido", "Brady", "De pie", "De pie", False),
]

for anterior, actual, postura_a, postura_b, esperado in casos:
    valido, motivo = puede_asignarse(
        autorizado=True,
        presente=True,
        estacion_permitida=True,
        estacion_anterior=anterior,
        estacion_actual=actual,
        postura_anterior=postura_a,
        postura_actual=postura_b,
    )
    resultado = "CORRECTO" if valido == esperado else "REVISAR"
    print(f"{resultado}: {anterior} -> {actual} | Válido: {valido} | {motivo}")

# Pruebas adicionales
print("Inserción y Crimpeo son el mismo tipo:", ("Inserción", "Crimpeo"))
print("TEST A y TEST B son el mismo tipo:", ("TEST A", "TEST B"))
