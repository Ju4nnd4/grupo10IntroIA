"""
traductor.py — Traductor Ontología -> Sistema Experto (sección 2.4)

Lee el grafo RDF RAZONADO (ontología + inferencias de OWL-RL) y genera los
hechos iniciales del sistema experto. Cumple lo que exige el enunciado:

  * Consulta el grafo de forma dinámica: no contiene nombres ni valores de
    individuos concretos (ni D01, ni P02, ni 95.0...). Si se agrega un
    individuo o una relación al .ttl, aparece como hecho sin tocar código.
  * Traduce TODO el grafo relevante, no una parte:
      - Capa semántica: cada clase, subclase, propiedad, subpropiedad,
        pertenencia de un individuo a una clase, relación y atributo.
        Cada hecho indica si fue escrito en el .ttl o inferido por OWL-RL.
      - Capa de dominio: hechos cómodos para las reglas (Dron, Paquete,
        Mision...), armados a partir del VOCABULARIO de la ontología
        (nombres de clases y propiedades), que no depende del caso.

Uso:
    from traductor import traducir
    t = traducir(grafo_original, grafo_razonado)
    t["hechos"]        -> lista de Fact listos para declarar
    t["advertencias"]  -> individuos que no se pudieron completar
    t["conteo"]        -> cantidad de hechos por tipo
"""

from collections import Counter

from rdflib import RDF, RDFS, XSD, Literal, URIRef

from ontologia import DR, nombre_local, valor_python
from experto import (Dron, Paquete, Mision, Zona, EstacionCarga, Clima,
                     Operador, Cliente, Clase, SubClaseDe, Propiedad,
                     SubPropiedadDe, Pertenencia, Relacion, Atributo)

# Espacios de nombres que pertenecen al lenguaje RDF/RDFS/XSD y no al dominio.
NS_DEL_LENGUAJE = (str(RDF), str(RDFS), str(XSD))


def es_del_lenguaje(nodo):
    return str(nodo).startswith(NS_DEL_LENGUAJE)


def es_del_dominio(nodo):
    return isinstance(nodo, URIRef) and str(nodo).startswith(str(DR))


# ===========================================================================
# 1. CAPA SEMÁNTICA: todo el grafo razonado
# ===========================================================================

def _etiqueta(grafo, nodo):
    return str(grafo.value(nodo, RDFS.label) or "")


def _uno(grafo, sujeto, predicado):
    """Nombre local de un valor (dominio o rango); '' si no tiene."""
    valores = sorted(nombre_local(v) for v in grafo.objects(sujeto, predicado))
    return valores[0] if valores else ""


def traducir_semantica(original, razonado):
    hechos = []

    # Una clase es lo declarado como rdfs:Class y también todo lo que aparece
    # en una jerarquía o como tipo de un individuo del dominio. Así se
    # incluyen clases de vocabularios externos, como foaf:Person.
    candidatas = set(razonado.subjects(RDF.type, RDFS.Class))
    for sub, sup in razonado.subject_objects(RDFS.subClassOf):
        candidatas.update((sub, sup))
    for s, o in razonado.subject_objects(RDF.type):
        if es_del_dominio(s):
            candidatas.add(o)
    propiedades = {p for p in razonado.subjects(RDF.type, RDF.Property)
                   if isinstance(p, URIRef) and not es_del_lenguaje(p)}
    clases = {c for c in candidatas
              if isinstance(c, URIRef) and not es_del_lenguaje(c)
              and c not in propiedades}

    for c in sorted(clases):
        hechos.append(Clase(id=nombre_local(c), etiqueta=_etiqueta(razonado, c)))

    for sub, sup in sorted(razonado.subject_objects(RDFS.subClassOf)):
        if sub != sup and sub in clases and sup in clases:
            hechos.append(SubClaseDe(
                sub=nombre_local(sub), sup=nombre_local(sup),
                inferido=(sub, RDFS.subClassOf, sup) not in original))

    for p in sorted(propiedades):
        hechos.append(Propiedad(
            id=nombre_local(p),
            dominio=_uno(razonado, p, RDFS.domain),
            rango=_uno(razonado, p, RDFS.range),
            etiqueta=_etiqueta(razonado, p)))

    for sub, sup in sorted(razonado.subject_objects(RDFS.subPropertyOf)):
        if sub != sup and sub in propiedades and sup in propiedades:
            hechos.append(SubPropiedadDe(
                sub=nombre_local(sub), sup=nombre_local(sup),
                inferido=(sub, RDFS.subPropertyOf, sup) not in original))

    # Individuos: recursos del dominio que no son clases ni propiedades.
    esquema = clases | propiedades
    individuos = sorted({s for s in razonado.subjects()
                         if es_del_dominio(s) and s not in esquema})

    for ind in individuos:
        nombre = nombre_local(ind)
        for p, o in sorted(razonado.predicate_objects(ind)):
            if p == RDF.type:
                if o in clases:
                    hechos.append(Pertenencia(
                        individuo=nombre, clase=nombre_local(o),
                        inferido=(ind, p, o) not in original))
            elif isinstance(o, Literal):
                hechos.append(Atributo(sujeto=nombre, propiedad=nombre_local(p),
                                       valor=valor_python(o)))
            elif isinstance(o, URIRef):
                hechos.append(Relacion(
                    sujeto=nombre, propiedad=nombre_local(p),
                    objeto=nombre_local(o),
                    inferido=(ind, p, o) not in original))

    return hechos


# ===========================================================================
# 2. CAPA DE DOMINIO: hechos cómodos para las reglas
# ===========================================================================
# Cada entrada relaciona una CLASE de la ontología con una clase de hecho.
#   "tipo":   primera clase que coincida (en orden) -> valor del campo tipo
#   "campos": campo del hecho -> (propiedad de la ontología, conversión)
# Todo son nombres del vocabulario de la ontología, nunca de individuos.

MAPEO = [
    {"clase": "Dron", "hecho": Dron,
     "tipo": [("DronLigero", "ligero"), ("DronPesado", "pesado"),
              ("DronRefrigerado", "refrigerado")],
     "tipo_por_defecto": "generico",
     "campos": {"estado": ("estadoOperativo", str),
                "bateria": ("nivelBateria", float),
                "capacidad_kg": ("capacidadKg", float),
                "zona": ("zonaActual", str)},
     "opcionales": {"estacion_base": ("seRecargaEn", str)}},

    {"clase": "Paquete", "hecho": Paquete,
     "tipo": [("PaqueteMedico", "medico"), ("PaqueteFragil", "fragil"),
              ("PaqueteUrgente", "express")],
     "tipo_por_defecto": "general",
     "banderas": {"urgente": "PaqueteUrgente"},
     "campos": {"peso_kg": ("pesoKg", float)}},

    {"clase": "Mision", "hecho": Mision,
     "campos": {"paquete": ("incluyePaquete", str),
                "origen": ("tieneOrigen", str),
                "destino": ("tieneDestino", str),
                "distancia_km": ("distanciaKm", float)}},

    {"clase": "Zona", "hecho": Zona,
     "tipo": [("ZonaRestringida", "restringida"),
              ("ZonaResidencial", "residencial"),
              ("ZonaComercial", "comercial")],
     "tipo_por_defecto": "sin_tipo",
     "banderas": {"restringida": "ZonaRestringida"},
     "campos": {"nombre": ("label", str)}},

    {"clase": "EstacionCarga", "hecho": EstacionCarga,
     "campos": {"zona": ("ubicadaEn", str),
                "cupos": ("cuposDisponibles", int)}},

    {"clase": "CondicionClimatica", "hecho": Clima,
     "campos": {"t": ("momento", int),
                "viento_kmh": ("velocidadVientoKmh", float),
                "condicion": ("tipoCondicion", str)}},

    {"clase": "Operador", "hecho": Operador,
     "campos": {"nombre": ("name", str)}},

    {"clase": "Cliente", "hecho": Cliente,
     "campos": {"nombre": ("name", str)}},
]


def _indexar(hechos_semanticos):
    """Agrupa los hechos semánticos por individuo: tipos y propiedades."""
    tipos, props = {}, {}
    for h in hechos_semanticos:
        if isinstance(h, Pertenencia):
            tipos.setdefault(h["individuo"], set()).add(h["clase"])
        elif isinstance(h, Relacion):
            props.setdefault(h["sujeto"], {}).setdefault(h["propiedad"], []).append(h["objeto"])
        elif isinstance(h, Atributo):
            props.setdefault(h["sujeto"], {}).setdefault(h["propiedad"], []).append(h["valor"])
    return tipos, props


def traducir_dominio(hechos_semanticos):
    hechos, advertencias = [], []
    tipos, props = _indexar(hechos_semanticos)

    for individuo in sorted(tipos):
        clases = tipos[individuo]
        valores = props.get(individuo, {})

        for m in MAPEO:
            if m["clase"] not in clases:
                continue
            datos = {"id": individuo}

            if "tipo" in m:
                datos["tipo"] = next((v for c, v in m["tipo"] if c in clases),
                                     m["tipo_por_defecto"])
            for campo, clase in m.get("banderas", {}).items():
                datos[campo] = clase in clases

            faltantes = []
            for campo, (prop, convertir) in m["campos"].items():
                if prop in valores:
                    datos[campo] = convertir(sorted(valores[prop], key=str)[0])
                else:
                    faltantes.append(prop)
            for campo, (prop, convertir) in m.get("opcionales", {}).items():
                if prop in valores:
                    datos[campo] = convertir(sorted(valores[prop], key=str)[0])

            if faltantes:
                advertencias.append(
                    f"{individuo} es {m['clase']} pero le falta: "
                    f"{', '.join(faltantes)}. No se creó el hecho {m['hecho'].__name__} "
                    f"(sus hechos semánticos sí se declararon).")
                continue
            hechos.append(m["hecho"](**datos))

    return hechos, advertencias


# ===========================================================================
# 3. FUNCIÓN PRINCIPAL
# ===========================================================================

def traducir(original, razonado):
    """Traduce el grafo razonado completo a hechos del sistema experto."""
    semanticos = traducir_semantica(original, razonado)
    dominio, advertencias = traducir_dominio(semanticos)
    hechos = semanticos + dominio
    conteo = Counter(type(h).__name__ for h in hechos)
    return {"hechos": hechos, "semanticos": semanticos, "dominio": dominio,
            "advertencias": advertencias, "conteo": conteo}


if __name__ == "__main__":
    from ontologia import cargar_ontologia, razonar

    original = cargar_ontologia("ontologia.ttl")
    razonado = razonar(original)
    t = traducir(original, razonado)

    print(f"Hechos generados: {len(t['hechos'])}")
    for tipo, n in sorted(t["conteo"].items()):
        print(f"  {tipo:<16} {n}")
    inferidos = sum(1 for h in t["semanticos"] if h.get("inferido") is True)
    print(f"Hechos semánticos que provienen de inferencias: {inferidos}")
    for a in t["advertencias"]:
        print("ADVERTENCIA:", a)
