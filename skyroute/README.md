# SkyRoute — Sistema híbrido para una flota de drones de entrega urbana

Trabajo Práctico 1 — Introducción a la Inteligencia Artificial (UNAL Medellín).
Integra un sistema experto (Experta), lógica difusa (Scikit-Fuzzy) y una
ontología RDF/RDFS con razonamiento (RDFLib + OWL-RL).

## Archivos

| Archivo | Qué hace |
|---|---|
| `ontologia.ttl` | Ontología del dominio en Turtle: clases, propiedades e individuos. **Es la única fuente de datos.** |
| `ontologia.py` | Carga la ontología, razona con `DeductiveClosure(RDFS_Semantics)` y muestra lo inferido. |
| `traductor.py` | Convierte todo el grafo razonado en hechos de Experta, sin valores fijos. |
| `difuso.py` | Calcula el riesgo (0-100) de una pareja dron-misión. |
| `experto.py` | Hechos, estrategia de resolución de conflictos y 28 reglas. |
| `main.py` | Conecta los cuatro módulos y muestra el resultado. |
| `difuso.ipynb` | Explicación del módulo difuso y gráficas de las funciones de pertenencia. |

## Flujo

```
ontologia.ttl -> ontologia.py (razonamiento) -> traductor.py -> hechos
                                                  difuso.py -> riesgos
                                  hechos + riesgos -> experto.py -> decisiones
```

## Cómo ejecutar

```
pip install -r requirements.txt
python main.py              # ejecución normal
python main.py --traza      # muestra cada regla disparada (salience, especificidad, hechos)
python main.py --detalle    # muestra todas las explicaciones
python ontologia.py         # evidencia del razonamiento (casos 1, 2 y 3)
python traductor.py         # cantidad de hechos generados por tipo
```

Funciona en Python 3.12 (Google Colab): `experto.py` incluye un parche de
compatibilidad para Experta 1.9.4.

## Resolución de conflictos

`experto.py` define `EstrategiaSkyRoute`, que ordena la agenda por
**salience → especificidad → recencia**. Experta solo trae salience y
recencia; la especificidad (número de condiciones de la regla) se agregó en
esta estrategia. Con `python main.py --traza` se ve el orden real de disparo.

## Caso de prueba obligatorio

Editar `ontologia.ttl` (sin tocar el código) y volver a ejecutar `main.py`.

**Opción 1 — tormenta.** Agregar al final:

```
dr:C05 a dr:CondicionClimatica ; dr:momento 5 ;
    dr:velocidadVientoKmh 50.0 ; dr:tipoCondicion "tormenta" .
```

Resultado esperado: C05 pasa a ser el clima vigente y todas las misiones
pendientes se posponen (`suspender_por_tormenta`).

**Opción 2 — dron y misión nuevos.** Agregar al final:

```
dr:D13 a dr:DronLigero ; dr:capacidadKg 2.0 ; dr:nivelBateria 90.0 ;
    dr:estadoOperativo "disponible" ; dr:zonaActual dr:Z06 ;
    dr:seRecargaEn dr:E02 ; dr:supervisadoPor dr:OP02 .
dr:P15 a dr:Paquete ; dr:pesoKg 1.5 ; dr:solicitadoPor dr:CL01 .
dr:M09 a dr:Mision ; dr:incluyePaquete dr:P15 ; dr:tieneOrigen dr:E04 ;
    dr:tieneDestino dr:Z06 ; dr:distanciaKm 2.5 ;
    dcterms:description "Misión de prueba agregada en vivo." .
```

Resultado esperado: aparecen los hechos de D13, P15 y M09, y las reglas de
asignación los procesan.

## Escenarios para ver otras reglas

- Registro de clima con viento de 36-40 km/h (`dr:tipoCondicion "lluvia"`):
  se dispara `asignar_pese_riesgo_alto_medico` (especificidad).
- Individuo sin tipo, por ejemplo
  `dr:D14 dr:capacidadKg 2.0 ; dr:nivelBateria 80.0 ; dr:estadoOperativo "disponible" ; dr:zonaActual dr:Z01 .`:
  el razonador lo clasifica como Dron por el dominio de `zonaActual`
  (`explicar_por_dominio`).
