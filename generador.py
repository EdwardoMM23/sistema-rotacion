from algoritmo import validar_secuencia, normalizar_estacion
import re

PERIODOS_PRODUCCION = {
    "Matutino": [("06:00", "09:00"), ("09:00", "12:00"), ("12:00", "15:12")],
    "Vespertino": [("15:30", "18:30"), ("18:30", "21:30"), ("21:30", "00:30")],
}
# Alias de compatibilidad con verificaciones y módulos de fases anteriores.
PERIODOS = PERIODOS_PRODUCCION

PERIODOS_MFI = {
    "Matutino": [("06:00", "10:00"), ("10:30", "15:12")],
    # Los horarios vespertinos de MFI no se configuran hasta confirmarlos con la planta.
    "Vespertino": [],
}
# Las reglas de MFI se mantienen independientes de Producción.
POSTURA_MFI = {
    "BREAKOUT": "De pie", "BREAKOUT 1": "De pie", "BREAKOUT 2": "De pie",
    "PULIDO": "De pie",
    "PEGAMENTO": "Sentado", "INSERCION": "Sentado", "INSERCION 1": "Sentado",
    "INSERCION 2": "Sentado", "CRIMPEO": "Sentado", "HORNO": "Sentado",
    "VISUAL": "Sentado", "INT/VISUAL": "Sentado", "INTERFEROMETRO": "Sentado",
    "IL": "Sentado", "TEST A": "Sentado", "EMPAQUE 1": "Sentado", "EMPAQUE 2": "Sentado",
}

def _es_mfi(nombre_linea):
    texto = str(nombre_linea or "").upper()
    return any(token in texto for token in ("MFI", "HFC", "META"))

def generar_propuesta(conexion, id_linea, fecha, turno="Matutino", usar_habilidades=True, lineas_grupo=None):
    """Genera una propuesta; las restricciones médicas y autorizaciones son obligatorias."""
    if turno not in ("Matutino", "Vespertino"):
        return None, ["Turno no válido."]
    linea = conexion.execute(
        "SELECT id_linea,nombre_linea,area FROM lineas WHERE id_linea=? AND activa=1",
        (id_linea,)
    ).fetchone()
    if not linea:
        return None, ["La línea no existe o está inactiva."]

    es_mfi = (linea["area"] == "MFI") if "area" in linea.keys() else _es_mfi(linea["nombre_linea"])
    periodos = (PERIODOS_MFI if es_mfi else PERIODOS_PRODUCCION)[turno]
    if not periodos:
        return None, ["No están confirmados los horarios vespertinos de MFI. Confirma los periodos con el líder antes de generar."]
    puestos = conexion.execute("""
        SELECT e.id_estacion,e.nombre_estacion,ea.postura,p.cantidad_requerida
        FROM puestos_linea p JOIN estaciones e ON e.id_estacion=p.id_estacion
        JOIN estaciones_areas ea ON ea.id_estacion=e.id_estacion AND ea.area=?
        WHERE p.id_linea=? AND p.activa=1 AND e.activa=1
        ORDER BY e.id_estacion
    """, ("MFI" if es_mfi else "Producción", id_linea)).fetchall()
    if not puestos:
        return None, ["Configura primero los puestos requeridos por línea."]

    # Un préstamo solo se incorpora si está aprobado y vigente para esa fecha.
    prestamos = conexion.execute("""
        SELECT po.id_operador,po.id_linea_origen,po.id_linea_destino,po.hora_inicio,po.hora_fin,po.hora_devolucion
        FROM prestamos_operadores po
        WHERE po.estado='Aprobado' AND (po.id_linea_destino=? OR po.id_linea_origen=?)
          AND po.fecha_inicio<=? AND (po.fecha_fin IS NULL OR po.fecha_fin>=?)
    """, (id_linea, id_linea, fecha, fecha)).fetchall()
    prestamo_detalle = {r["id_operador"]: dict(r) for r in prestamos}
    prestamos_destino = {r["id_operador"]: r for r in prestamos if r["id_linea_destino"] == id_linea}
    prestamos_origen = {r["id_operador"]: r for r in prestamos if r["id_linea_origen"] == id_linea}
    prestados = {r["id_operador"]: r["id_linea_origen"] for r in prestamos_destino.values()}
    # Personal compartido por parejas de Producción y por el conjunto MFI.
    if es_mfi:
        filas_pool = [dict(x) for x in conexion.execute("SELECT id_linea,nombre_linea FROM lineas WHERE activa=1 AND area='MFI'").fetchall()]
        filas_pool.sort(key=lambda x: (int(re.search(r"\d+", x["nombre_linea"]).group()) if re.search(r"\d+", x["nombre_linea"]) else 999, x["nombre_linea"]))
        lineas_pool = [x["id_linea"] for x in filas_pool]
        if lineas_grupo is not None:
            permitidas = {int(x) for x in lineas_grupo}
            lineas_pool = [x for x in lineas_pool if x in permitidas]
    else:
        filas_prod = [dict(x) for x in conexion.execute("SELECT id_linea,nombre_linea FROM lineas WHERE activa=1 AND area='Producción'").fetchall()]
        filas_prod.sort(key=lambda x: (int(re.search(r"\d+", x["nombre_linea"]).group()) if re.search(r"\d+", x["nombre_linea"]) else 999, x["nombre_linea"]))
        lineas_prod = [x["id_linea"] for x in filas_prod]
        try:
            posicion = lineas_prod.index(id_linea)
            lineas_pool = lineas_prod[(posicion // 2) * 2:(posicion // 2) * 2 + 2]
        except ValueError:
            lineas_pool = [id_linea]
    if id_linea not in lineas_pool:
        lineas_pool.append(id_linea)
    pool_sql = ",".join("?" for _ in lineas_pool)
    placeholders = ",".join("?" for _ in prestados) if prestados else "NULL"
    ops = conexion.execute(f"""
        SELECT DISTINCT o.id_operador,o.numero_empleado,o.nombre,o.id_linea
        FROM operadores o JOIN asistencia a ON a.id_operador=o.id_operador
        WHERE o.activo=1 AND o.turno=? AND a.fecha=? AND a.estado='Presente'
          AND ((o.id_linea IN ({pool_sql}) AND o.id_operador NOT IN (
                SELECT po.id_operador FROM prestamos_operadores po
                WHERE po.id_linea_origen=o.id_linea AND po.id_linea_destino NOT IN ({pool_sql})
                  AND po.estado='Aprobado' AND po.fecha_inicio<=?
                  AND (po.fecha_fin IS NULL OR po.fecha_fin>=?)
                  AND (po.hora_inicio IS NULL OR po.hora_fin IS NULL)))
               OR o.id_operador IN ({placeholders}))
        ORDER BY o.id_operador
    """, (turno, fecha, *lineas_pool, *lineas_pool, fecha, fecha, *prestados.keys())).fetchall()
    if not ops:
        return None, ["No hay operadores presentes y disponibles para esta línea/turno."]

    auth = {(r["id_operador"], r["id_estacion"]) for r in conexion.execute(
        "SELECT id_operador,id_estacion FROM autorizaciones WHERE autorizado=1"
    ).fetchall()}
    restricciones = {}
    for r in conexion.execute("""
        SELECT r.id_operador,d.id_estacion
        FROM restricciones_medicas r JOIN detalle_restriccion d
          ON d.id_restriccion=r.id_restriccion
        WHERE r.estado='Activa' AND r.fecha_inicio<=?
          AND (r.fecha_fin IS NULL OR r.fecha_fin>=?) AND d.permitida=0
    """, (fecha, fecha)).fetchall():
        restricciones.setdefault(r["id_operador"], set()).add(r["id_estacion"])

    habilidades = {(r["id_operador"], r["id_estacion"]): r["nivel"] for r in conexion.execute(
        "SELECT id_operador,id_estacion,nivel FROM habilidades_estacion"
    ).fetchall()}

    # Historial del día anterior para favorecer variedad real de estaciones y horarios.
    from datetime import date, timedelta
    try:
        fecha_anterior = (date.fromisoformat(fecha) - timedelta(days=1)).isoformat()
    except ValueError:
        return None, ["La fecha no tiene un formato válido."]
    anterior = {}
    for r in conexion.execute("""
        SELECT a.id_operador,a.id_estacion,a.hora_inicio,e.nombre_estacion
        FROM asignaciones a JOIN rotaciones ro ON ro.id_rotacion=a.id_rotacion
        JOIN estaciones e ON e.id_estacion=a.id_estacion
        WHERE ro.id_linea=? AND ro.fecha=? AND ro.turno=? AND ro.estado<>'Cancelada'
    """, (id_linea, fecha_anterior, turno)).fetchall():
        anterior.setdefault(r["id_operador"], []).append(dict(r))

    opmap = {o["id_operador"]: o for o in ops}
    # La demanda se calcula por periodo. El personal sobrante queda disponible
    # para apoyo y no se asigna dos veces ni se elimina de la plantilla.
    historial = {oid: [] for oid in opmap}
    propuesta = []
    cohorte_produccion = None
    cantidad_por_periodo = []
    for numero_periodo in range(1, len(periodos) + 1):
        configurada = conexion.execute("SELECT COUNT(*) AS n FROM puestos_periodo WHERE id_linea=? AND turno=? AND periodo=?", (id_linea, turno, numero_periodo)).fetchone()["n"] > 0
        total = 0
        for puesto in puestos:
            fila = conexion.execute("SELECT cantidad_requerida FROM puestos_periodo WHERE id_linea=? AND id_estacion=? AND turno=? AND periodo=?", (id_linea, puesto["id_estacion"], turno, numero_periodo)).fetchone() if configurada else None
            total += int(fila["cantidad_requerida"] if fila else (puesto["cantidad_requerida"] if not configurada else 0))
        cantidad_por_periodo.append(total)
    if not es_mfi and len(set(cantidad_por_periodo)) > 1:
        return None, [
            "La demanda de Producción no es igual en los tres periodos.",
            "Para evitar que un operador aparezca en una rotación y desaparezca en la siguiente, configura la misma cantidad de puestos para los tres periodos. Los operadores excedentes quedarán como personal de apoyo durante el turno."
        ]
    if es_mfi and not any(cantidad_por_periodo):
        return None, [
            "No se generó la rotación MFI porque la demanda guardada es 0 en todos los puestos y periodos de esta línea.",
            "Entra a ‘Puestos por línea’, selecciona el área MFI y la línea correspondiente (MFI1, MFI2, MFI3 o MFI4). Captura cuántas personas requiere cada estación en cada periodo y guarda antes de volver a generar.",
            "Importante: las estaciones con demanda 0 se dejan sin asignación; las estaciones con demanda mayor que 0 sí se consideran aunque su cantidad base en el catálogo sea 0."
        ]
    for n, (inicio, fin) in enumerate(periodos, 1):
        numero_guardado = n if turno == "Matutino" else n + (2 if es_mfi else 3)
        slots = []
        demanda_configurada = conexion.execute("SELECT COUNT(*) AS n FROM puestos_periodo WHERE id_linea=? AND turno=? AND periodo=?",
                                               (id_linea,turno,n)).fetchone()["n"] > 0
        for p in puestos:
            nombre = p["nombre_estacion"]
            cantidad = p["cantidad_requerida"]
            if demanda_configurada:
                fila_demanda = conexion.execute("SELECT cantidad_requerida FROM puestos_periodo WHERE id_linea=? AND id_estacion=? AND turno=? AND periodo=?",
                                                (id_linea,p["id_estacion"],turno,n)).fetchone()
                cantidad = fila_demanda["cantidad_requerida"] if fila_demanda else 0
            postura = POSTURA_MFI.get(normalizar_estacion(nombre), POSTURA_MFI.get(nombre.upper(), p["postura"])) if es_mfi else p["postura"]
            for indice in range(int(cantidad)):
                slots.append({**dict(p), "cantidad_requerida":cantidad, "postura": postura, "copia_puesto": indice + 1})

        # Si ningún operador puede cubrir un puesto, devolver una guía útil.
        for p in slots:
            elegibles = [oid for oid in opmap
                if (oid, p["id_estacion"]) in auth
                and p["id_estacion"] not in restricciones.get(oid, set())]
            if not elegibles:
                return None, [
                    f"No hay operador autorizado y médicamente compatible para {p['nombre_estacion']} ({inicio}–{fin}).",
                    "Opciones: revisa las autorizaciones; consulta con Enfermería las restricciones vigentes; o solicita un préstamo aprobado de otra línea/área con personal capacitado."
                ]

        asignados, seleccion, nodes = set(), [], [0]
        def penalizacion(oid, p, repeticion):
            # La habilidad solo mejora la prioridad; nunca supera autorizaciones,
            # restricciones médicas ni reglas ergonómicas, que se validan antes.
            penalty = ({"Alta": -12, "Media": 0, "Baja": 18}.get(
                habilidades.get((oid, p["id_estacion"]), "Media"), 0) if usar_habilidades else 0)
            # Preferir estación distinta a la del mismo horario del día anterior.
            for old in anterior.get(oid, []):
                if old["hora_inicio"] == inicio and old["id_estacion"] == p["id_estacion"]:
                    penalty += 100
                elif old["id_estacion"] == p["id_estacion"]:
                    penalty += 15
            # Evitar repetir estación durante el mismo turno cuando exista alternativa.
            if any(x["id_estacion"] == p["id_estacion"] for x in historial[oid]):
                penalty += 20
            if repeticion:
                penalty += 5
            return penalty

        def solve(restantes, permitir_repeticion):
            nodes[0] += 1
            if nodes[0] > 50000:
                return False
            if not restantes:
                return True
            opciones_por_puesto = []
            for i, p in enumerate(restantes):
                opciones = []
                for oid in opmap:
                    if cohorte_produccion is not None and oid not in cohorte_produccion:
                        continue
                    if oid in asignados or (oid, p["id_estacion"]) not in auth:
                        continue
                    if p["id_estacion"] in restricciones.get(oid, set()):
                        continue
                    if oid in prestamos_destino:
                        pr = prestamos_destino[oid]
                        inicio_prestamo = pr["hora_inicio"]
                        fin_prestamo = pr["hora_fin"]
                        if inicio_prestamo and inicio < inicio_prestamo:
                            continue
                        if fin_prestamo and fin > fin_prestamo:
                            continue
                        if pr["hora_devolucion"] and inicio >= pr["hora_devolucion"]:
                            continue
                    if oid in prestamos_origen:
                        pr_origen = prestamos_origen[oid]
                        hi, hf = pr_origen["hora_inicio"], pr_origen["hora_fin"]
                        # Si el préstamo cubre todo el día o coincide con este periodo,
                        # el operador no puede seguir asignado a la línea de origen.
                        if not hi or not hf or (inicio < hf and fin > hi):
                            continue
                    conflicto_linea = conexion.execute("""SELECT 1 FROM asignaciones ax JOIN rotaciones rx ON rx.id_rotacion=ax.id_rotacion
                        WHERE ax.id_operador=? AND rx.fecha=? AND rx.turno=? AND rx.id_linea<>?
                          AND rx.estado!='Cancelada' AND ax.hora_inicio < ? AND ax.hora_fin > ? LIMIT 1""",
                        (oid,fecha,turno,id_linea,fin,inicio)).fetchone()
                    if conflicto_linea:
                        continue
                    if historial[oid]:
                        prev = historial[oid][-1]
                        ok, _ = validar_secuencia(prev["nombre_estacion"], p["nombre_estacion"],
                                                  prev["postura"], p["postura"])
                        if not ok:
                            continue
                    repetida = any(x["id_estacion"] == p["id_estacion"] for x in historial[oid])
                    if repetida and not permitir_repeticion:
                        continue
                    opciones.append((penalizacion(oid, p, repetida), oid))
                opciones.sort(key=lambda x: (x[0], x[1]))
                opciones_por_puesto.append((len(opciones), i, p, opciones))
            opciones_por_puesto.sort(key=lambda x: x[0])
            count, i, p, opciones = opciones_por_puesto[0]
            if not opciones:
                return False
            rest = restantes[:i] + restantes[i+1:]
            for _, oid in opciones:
                asignados.add(oid)
                item = {
                    "id_operador": oid,
                    "numero_empleado": opmap[oid]["numero_empleado"],
                    "nombre_operador": opmap[oid]["nombre"],
                    "id_estacion": p["id_estacion"],
                    "nombre_estacion": p["nombre_estacion"],
                    "postura": p["postura"],
                    "hora_inicio": inicio, "hora_fin": fin,
                    "numero_rotacion": numero_guardado,
                    "es_prestado": 1 if oid in prestados else 0,
                    "id_linea_origen": prestados.get(oid)
                }
                seleccion.append(item)
                if solve(rest, permitir_repeticion):
                    return True
                seleccion.pop()
                asignados.remove(oid)
            return False

        if not solve(slots, False):
            return None, [
                f"No se encontró una combinación válida para el periodo {n} ({inicio}–{fin}) sin repetir estaciones para una misma persona durante el turno.",
                "No se relajaron las restricciones médicas ni la regla de variedad. Revisa los puestos requeridos, las autorizaciones y las restricciones activas.",
                "Opciones: recalcular; desactivar puestos que realmente no se necesiten; pedir a Administración revisar autorizaciones; consultar con Enfermería las restricciones vigentes; o solicitar personal de apoyo mediante un préstamo aprobado.",
                "Si el problema es la cobertura de una estación, no cambies manualmente una asignación si eso deja otro puesto por debajo de su dotación requerida."
            ]
        if not es_mfi and cohorte_produccion is None:
            cohorte_produccion = {item["id_operador"] for item in seleccion}
            if len(cohorte_produccion) != len(slots):
                return None, ["No fue posible formar un grupo fijo de operadores para toda la jornada.", "Revisa las autorizaciones, las restricciones médicas y la demanda de puestos. Los operadores que no formen parte del grupo quedarán disponibles como apoyo."]
        for item in seleccion:
            historial[item["id_operador"]].append(item)
        propuesta.append(seleccion)
    return propuesta, []
