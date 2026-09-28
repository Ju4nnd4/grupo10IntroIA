"""
SkyRoute - Módulo de Ontología (sección 2.3)
============================================

Responsabilidades:
  1. Cargar la ontología del dominio escrita en Turtle (ontologia.ttl).
  2. Aplicar razonamiento RDFS con OWL-RL: DeductiveClosure(RDFS_Semantics).
  3. Comparar el grafo antes y después del razonamiento y mostrar lo inferido.
  4. Evidenciar los casos pedidos: jerarquía de clases, dominio/rango y
     subPropertyOf.
  5. Exponer el grafo razonado de forma GENÉRICA (extraer_individuos) para
     que el traductor Ontología -> Sistema Experto lo convierta en hechos.
     Nada aquí depende de individuos concretos: si se agrega un dron,
     paquete o misión al .ttl, aparece automáticamente.

En Google Colab:
    !pip install rdflib owlrl
    (subir ontologia.ttl y ontologia.py)
    %run ontologia.py
"""

from rdflib import Graph, Namespace, RDF, RDFS, Literal, URIRef
import owlrl

DR = Namespace("http://unal.edu.co/ia/drones#")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")
DCTERMS = Namespace("http://purl.org/dc/terms/")

# Tipos que describen el esquema, no el dominio. Se excluyen al extraer
# individuos y al mostrar inferencias "relevantes".
TIPOS_DE_ESQUEMA = {RDFS.Resource, RDFS.Class, RDF.Property,
                    RDFS.Datatype, RDFS.Literal}


# ---------------------------------------------------------------------------
# Carga y razonamiento
# ---------------------------------------------------------------------------
def cargar_ontologia(ruta="ontologia.ttl"):
    """Lee el archivo Turtle y devuelve el grafo RDF original (sin inferencias)."""
    g = Graph()
    g.parse(ruta, format="turtle")
    g.bind("dr", DR)
    g.bind("foaf", FOAF)
    g.bind("dcterms", DCTERMS)
    return g


def razonar(grafo):
    """
    Devuelve una COPIA del grafo expandida con la semántica RDFS de OWL-RL.
    Se desactivan los axiomas genéricos de RDF/RDFS (axiomatic_triples y
    datatype_axioms) para que el resultado contenga solo inferencias sobre
    el dominio y no cientos de tripletas triviales.
    """
    razonado = Graph()
    for t in grafo:
        razonado.add(t)
    for prefijo, ns in grafo.namespaces():
        razonado.bind(prefijo, ns)

    owlrl.DeductiveClosure(
        owlrl.RDFS_Semantics,
        axiomatic_triples=False,
        datatype_axioms=False,
    ).expand(razonado)

    # OWL-RL trata los literales numéricos por su VALOR, así que al terminar
    # vuelve a escribir 2.0 (decimal) también como 2 (integer), o 3 como 3.0.
    # Son el mismo dato repetido, no conocimiento nuevo: se eliminan para que
    # el sistema experto no reciba valores duplicados.
    for s, p, o in list(razonado):
        if isinstance(o, Literal) and (s, p, o) not in grafo:
            if any(isinstance(x, Literal) for x in grafo.objects(s, p)):
                razonado.remove((s, p, o))
    return razonado


# ---------------------------------------------------------------------------
# Comparación antes / después
# ---------------------------------------------------------------------------
def elementos_de_esquema(grafo):
    """Clases y propiedades definidas en la ontología (no son individuos)."""
    return (set(grafo.subjects(RDF.type, RDFS.Class))
            | set(grafo.subjects(RDF.type, RDF.Property)))


def es_relevante(tripleta, esquema):
    """
    True si la tripleta es un hecho nuevo sobre un INDIVIDUO del dominio.
    Se descartan las tripletas triviales que RDFS genera siempre, como
    "X rdf:type rdfs:Resource" o "Clase rdfs:subClassOf Clase".
    """
    s, p, o = tripleta
    if isinstance(s, Literal) or not str(s).startswith(str(DR)):
        return False
    if s in esquema:
        return False
    if p == RDF.type and o in TIPOS_DE_ESQUEMA:
        return False
    return True


def tripletas_inferidas(antes, despues, solo_relevantes=True):
    """Tripletas que existen después del razonamiento y no antes."""
    nuevas = set(despues) - set(antes)
    if solo_relevantes:
        esquema = elementos_de_esquema(despues)
        nuevas = {t for t in nuevas if es_relevante(t, esquema)}
    return sorted(nuevas)


def corto(nodo, grafo):
    """Representación corta (dr:D01, foaf:Person, "texto")."""
    if isinstance(nodo, Literal):
        return f'"{nodo}"'
    return nodo.n3(grafo.namespace_manager)


def imprimir_tripletas(tripletas, grafo, limite=None):
    for i, (s, p, o) in enumerate(tripletas):
        if limite and i >= limite:
            print(f"   ... ({len(tripletas) - limite} más)")
            break
        print(f"   {corto(s, grafo)}  {corto(p, grafo)}  {corto(o, grafo)}")


def comparar_grafos(antes, despues):
    """Imprime el tamaño de ambos grafos y las inferencias agrupadas por tipo."""
    nuevas_total = tripletas_inferidas(antes, despues, solo_relevantes=False)
    nuevas = tripletas_inferidas(antes, despues)

    print("=" * 70)
    print("COMPARACIÓN DEL GRAFO ANTES Y DESPUÉS DEL RAZONAMIENTO")
    print("=" * 70)
    print(f"Tripletas antes del razonamiento   : {len(antes)}")
    print(f"Tripletas después del razonamiento : {len(despues)}")
    print(f"Tripletas nuevas (todas)           : {len(nuevas_total)}")
    print(f"Hechos nuevos sobre individuos     : {len(nuevas)}")

    tipos = [t for t in nuevas if t[1] == RDF.type]
    otras = [t for t in nuevas if t[1] != RDF.type]
    print(f"\n-> Nuevas pertenencias a clases (rdf:type): {len(tipos)}")
    imprimir_tripletas(tipos, despues, limite=15)
    print(f"\n-> Nuevas relaciones entre individuos: {len(otras)}")
    imprimir_tripletas(otras, despues, limite=15)
    return nuevas


# ---------------------------------------------------------------------------
# Evidencia de los casos pedidos en el enunciado
# ---------------------------------------------------------------------------
def _verificar(antes, despues, tripleta, explicacion):
    estaba = tripleta in antes
    esta = tripleta in despues
    s, p, o = tripleta
    print(f"   {corto(s, despues)} {corto(p, despues)} {corto(o, despues)}")
    print(f"      ¿Antes? {'Sí' if estaba else 'No'}   ¿Después? {'Sí' if esta else 'No'}"
          f"   -> {'INFERIDA' if (esta and not estaba) else 'no inferida'}")
    print(f"      Por qué: {explicacion}")


def demostrar_casos(antes, despues):
    print("\n" + "=" * 70)
    print("CASOS DE GENERACIÓN DE NUEVO CONOCIMIENTO")
    print("=" * 70)

    print("\nCASO 1a - Jerarquía de clases (rdfs:subClassOf, transitividad)")
    _verificar(antes, despues, (DR.P02, RDF.type, DR.PaqueteUrgente),
               "P02 es PaqueteMedico y PaqueteMedico ⊑ PaqueteUrgente.")
    _verificar(antes, despues, (DR.P02, RDF.type, DR.Paquete),
               "PaqueteUrgente ⊑ Paquete (cadena de dos niveles).")

    print("\nCASO 1b - Jerarquía de clases con vocabulario externo (FOAF)")
    _verificar(antes, despues, (DR.D01, RDF.type, DR.Vehiculo),
               "DronLigero ⊑ Dron ⊑ Vehiculo.")
    _verificar(antes, despues, (DR.OP01, RDF.type, FOAF.Person),
               "Operador ⊑ foaf:Person.")

    print("\nCASO 2 - Pertenencia a clase desde dominio / rango")
    _verificar(antes, despues, (DR.CL03, RDF.type, DR.Cliente),
               "CL03 aparece como objeto de solicitadoPor, cuyo rango es Cliente.")
    _verificar(antes, despues, (DR.CL03, RDF.type, FOAF.Person),
               "Luego, por Cliente ⊑ foaf:Person, también es persona.")

    print("\nCASO 3 - Nuevos hechos desde rdfs:subPropertyOf")
    _verificar(antes, despues, (DR.M01, DR.involucraUbicacion, DR.Z05),
               "M01 tieneDestino Z05 y tieneDestino ⊑ involucraUbicacion.")
    _verificar(antes, despues, (DR.M01, DR.involucraUbicacion, DR.E01),
               "M01 tieneOrigen E01 y tieneOrigen ⊑ involucraUbicacion.")


# ---------------------------------------------------------------------------
# Interfaz para el traductor Ontología -> Sistema Experto
# ---------------------------------------------------------------------------
def nombre_local(nodo):
    """dr:D01 -> 'D01'; foaf:Person -> 'Person'."""
    texto = str(nodo)
    for sep in ("#", "/"):
        if sep in texto:
            texto = texto.rsplit(sep, 1)[-1]
    return texto


def valor_python(nodo):
    """Literal -> valor Python (float, int, str); URI -> nombre local."""
    if isinstance(nodo, Literal):
        v = nodo.toPython()
        return float(v) if hasattr(v, "as_tuple") else v   # Decimal -> float
    return nombre_local(nodo)


def extraer_individuos(grafo):
    """
    Recorre el grafo RAZONADO y devuelve TODOS los individuos del dominio:

        {
          "D01": {"tipos": ["Dron", "DronLigero", "Vehiculo"],
                  "props": {"nivelBateria": [95.0], "zonaActual": ["Z01"], ...}},
          ...
        }

    Es completamente genérico: no contiene nombres de individuos ni valores
    fijos. Todo lo que exista en el .ttl (o haya sido inferido) aparece aquí.
    """
    clases = set(grafo.subjects(RDF.type, RDFS.Class))
    propiedades = set(grafo.subjects(RDF.type, RDF.Property))
    individuos = {}

    for s, o in grafo.subject_objects(RDF.type):
        if not str(s).startswith(str(DR)):
            continue
        if s in clases or s in propiedades or o in TIPOS_DE_ESQUEMA:
            continue
        ind = individuos.setdefault(nombre_local(s), {"tipos": set(), "props": {}})
        ind["tipos"].add(nombre_local(o))

    for nombre, datos in individuos.items():
        sujeto = DR[nombre]
        for p, o in grafo.predicate_objects(sujeto):
            if p == RDF.type:
                continue
            datos["props"].setdefault(nombre_local(p), []).append(valor_python(o))
        datos["tipos"] = sorted(datos["tipos"])
        for k in datos["props"]:
            datos["props"][k] = sorted(datos["props"][k], key=str)

    return individuos


def obtener_grafo_razonado(ruta="ontologia.ttl"):
    """Atajo para los otros módulos: carga + razonamiento."""
    return razonar(cargar_ontologia(ruta))


# ---------------------------------------------------------------------------
# Consultas SPARQL de ejemplo sobre el grafo razonado
# ---------------------------------------------------------------------------
CONSULTA_URGENTES = """
SELECT ?paquete ?peso WHERE {
    ?paquete a dr:PaqueteUrgente ; dr:pesoKg ?peso .
} ORDER BY ?paquete
"""

CONSULTA_MISIONES_RESTRINGIDAS = """
SELECT ?mision ?zona ?nombre WHERE {
    ?mision dr:tieneDestino ?zona .
    ?zona a dr:ZonaRestringida ; rdfs:label ?nombre .
}
"""


def ejecutar_consultas(antes, despues):
    print("\n" + "=" * 70)
    print("CONSULTAS SPARQL: MISMA PREGUNTA ANTES Y DESPUÉS DE RAZONAR")
    print("=" * 70)
    ns = {"dr": DR, "rdfs": RDFS}
    for titulo, q in [("Paquetes urgentes", CONSULTA_URGENTES),
                      ("Misiones hacia zonas restringidas", CONSULTA_MISIONES_RESTRINGIDAS)]:
        r_antes = list(antes.query(q, initNs=ns))
        r_despues = list(despues.query(q, initNs=ns))
        print(f"\n{titulo}: {len(r_antes)} resultados antes, {len(r_despues)} después")
        for fila in r_despues:
            print("   " + "  ".join(str(valor_python(x)) for x in fila))


# ---------------------------------------------------------------------------
# Ejecución directa del módulo
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    original = cargar_ontologia("ontologia.ttl")
    razonado = razonar(original)

    comparar_grafos(original, razonado)
    demostrar_casos(original, razonado)
    ejecutar_consultas(original, razonado)

    individuos = extraer_individuos(razonado)
    print("\n" + "=" * 70)
    print(f"INDIVIDUOS DISPONIBLES PARA EL SISTEMA EXPERTO: {len(individuos)}")
    print("=" * 70)
    for ejemplo in ("D01", "P02", "CL03", "M01"):
        print(f"{ejemplo}: {individuos[ejemplo]}")

    razonado.serialize("ontologia_inferida.ttl", format="turtle")
    print("\nGrafo razonado guardado en ontologia_inferida.ttl")
