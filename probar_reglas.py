from algoritmo import normalizar_estacion, validar_secuencia

pruebas = [
    ("Horno", "Pulido", "De pie", "De pie", False),
    ("TEST A", "Visual", "Ambas", "Sentado", False),
    ("Visual", "TEST B", "Sentado", "Ambas", False),
    ("Pegamento", "Accesorios", "Sentado", "Sentado", True),
    ("Pulido", "Brady", "De pie", "De pie", False),
]

for anterior, actual, postura_a, postura_b, esperado in pruebas:
    valida, motivo = validar_secuencia(
        anterior, actual, postura_a, postura_b
    )

    estado = "CORRECTO" if valida == esperado else "REVISAR"

    print(
        f"{estado}: {anterior} -> {actual} | "
        f"Válida={valida} | {motivo}"
    )

print("Alias Inserción:", normalizar_estacion("Inserción"))
print("Alias Montaje:", normalizar_estacion("Montaje"))
print("Alias TEST A:", normalizar_estacion("TEST A"))

