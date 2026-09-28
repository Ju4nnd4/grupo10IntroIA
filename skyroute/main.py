"""
main.py — Orquestador del sistema híbrido SkyRoute

Flujo:
  1. ontologia.py : carga ontologia.ttl y aplica razonamiento RDFS (OWL-RL).
  2. traductor.py : convierte TODO el grafo razonado en hechos de Experta.
  3. difuso.py    : calcula el riesgo de cada pareja (dron disponible,
                    misión) con el viento del clima más reciente.
  4. experto.py   : ejecuta las reglas y devuelve las decisiones.

Uso:
    python main.py                      # usa ontologia.ttl
    python main.py --ttl otra.ttl       # usa otra ontología
    python main.py --traza              # muestra cada regla disparada
    python main.py --detalle            # muestra todas las explicaciones
"""

import argparse
from collections import Counter

from ontologia import cargar_ontologia, razonar, tripletas_inferidas
from traductor import traducir
from difuso import calcular_riesgo
from experto import (ejecutar, Dron, Mision, Clima, EvaluacionRiesgo,
                     ACCIONES_OPERATIVAS)


def titulo(texto):
    print("\n" + "=" * 72)
    print(texto)
    print("=" * 72)


def de_tipo(hechos, clase):
    return [h for h in hechos if isinstance(h, clase)]


def evaluar_riesgos(hechos_dominio):
    """
    Calcula el riesgo difuso de cada pareja (dron disponible, misión).
    El viento se toma del registro climático más reciente (mayor `t`).
    Todo sale de los hechos traducidos: no hay valores fijos.
    """
    climas = de_tipo(hechos_dominio, Clima)
    if not climas:
        return [], None
    vigente = max(climas, key=lambda c: c["t"])

    riesgos = []
    for dron in de_tipo(hechos_dominio, Dron):
        if dron["estado"] != "disponible":
            continue
        for mision in de_tipo(hechos_dominio, Mision):
            valor, etiqueta = calcular_riesgo(dron["bateria"], vigente["viento_kmh"],
                                              mision["distancia_km"])
            riesgos.append(EvaluacionRiesgo(dron=dron["id"], mision=mision["id"],
                                            valor=valor, etiqueta=etiqueta))
    return riesgos, vigente


def imprimir(decisiones, acciones, limite=None):
    seleccion = [d for d in decisiones if d["accion"] in acciones]
    for i, d in enumerate(seleccion):
        if limite is not None and i >= limite:
            print(f"   ... y {len(seleccion) - limite} más (use --detalle)")
            break
        quien = " ".join(x for x in (d["dron"], d["mision"]) if x)
        quien = f"{quien:<9}" if quien else " " * 9
        print(f"   [{d['accion']}] {quien} {d['motivo']}")
    return len(seleccion)


def main():
    parser = argparse.ArgumentParser(description="Sistema híbrido SkyRoute")
    parser.add_argument("--ttl", default="ontologia.ttl")
    parser.add_argument("--traza", action="store_true")
    parser.add_argument("--detalle", action="store_true")
    args = parser.parse_args()

    # 1. Ontología ---------------------------------------------------------
    titulo("1. ONTOLOGÍA Y RAZONAMIENTO (RDFLib + OWL-RL)")
    original = cargar_ontologia(args.ttl)
    razonado = razonar(original)
    print(f"Tripletas escritas en {args.ttl}: {len(original)}")
    print(f"Tripletas después de razonar:      {len(razonado)}")
    print(f"Hechos nuevos sobre individuos:    {len(tripletas_inferidas(original, razonado))}")

    # 2. Traductor ---------------------------------------------------------
    titulo("2. TRADUCTOR ONTOLOGÍA -> SISTEMA EXPERTO")
    t = traducir(original, razonado)
    inferidos = sum(1 for h in t["semanticos"] if h.get("inferido") is True)
    print(f"Hechos generados desde el grafo: {len(t['hechos'])} "
          f"({inferidos} provienen de inferencias)")
    for tipo, n in sorted(t["conteo"].items()):
        print(f"   {tipo:<16} {n}")
    for a in t["advertencias"]:
        print(f"   ADVERTENCIA: {a}")

    # 3. Lógica difusa -----------------------------------------------------
    titulo("3. LÓGICA DIFUSA: RIESGO DE CADA PAREJA DRON-MISIÓN")
    riesgos, vigente = evaluar_riesgos(t["dominio"])
    if vigente:
        print(f"Clima más reciente: {vigente['id']} ({vigente['condicion']}, "
              f"viento {vigente['viento_kmh']} km/h)")
    conteo = Counter(r["etiqueta"] for r in riesgos)
    print(f"Evaluaciones: {len(riesgos)}  ->  " +
          ", ".join(f"{k}: {conteo.get(k, 0)}"
                    for k in ("bajo", "medio", "alto", "muy_alto")))

    # 4. Sistema experto ---------------------------------------------------
    titulo("4. SISTEMA EXPERTO (Experta)")
    if args.traza:
        print("Traza de reglas disparadas (orden de ejecución):")
    decisiones, motor = ejecutar(t["hechos"] + riesgos, traza=args.traza)

    limite = None if args.detalle else 6
    print("\nDecisiones operativas:")
    imprimir(decisiones, ACCIONES_OPERATIVAS)
    print("\nParejas dron-misión descartadas por riesgo:")
    imprimir(decisiones, {"descartar"}, limite)
    print("\nNotificaciones y acciones derivadas de la ontología:")
    imprimir(decisiones, {"notificar_operador", "notificar_cliente", "rescatar_paquete"})
    print("\nReportes:")
    imprimir(decisiones, {"reporte"})
    print("\nExplicación de las inferencias de la ontología:")
    imprimir(decisiones, {"explicacion"}, limite)
    print()
    imprimir(decisiones, {"resumen"})

    # Evidencia de la resolución de conflictos y uso de los hechos ---------
    reglas = Counter(nombre for nombre, _, _ in motor.disparos)
    print(f"\nReglas disparadas: {len(motor.disparos)} veces, "
          f"{len(reglas)} reglas distintas de {len(motor.get_rules())}")


if __name__ == "__main__":
    main()
