# -*- coding: utf-8 -*-
"""
experto.py — Módulo de Sistema Experto (Experta) del sistema híbrido SkyRoute
Trabajo Práctico 1 — Introducción a la Inteligencia Artificial (3010476), UNAL
Persona 1 — Sistema Experto

Los cambios hechos en la rama `Test` están marcados con el comentario [Test].

===========================================================================
QUÉ RECIBE ESTE MÓDULO
===========================================================================
[Test] Este módulo YA NO recibe diccionarios escritos a mano ni lee
datos.json. Todos los hechos iniciales los genera `traductor.py` a partir
del grafo RDF razonado (ontología + inferencias de OWL-RL), tal como exige
la sección 2.4 del enunciado. `main.py` añade además las evaluaciones de
riesgo calculadas por `difuso.py`.

    decisiones = ejecutar(hechos, traza=False)

`hechos` es una lista de objetos Fact (definidos abajo) y `decisiones` es
una lista de diccionarios:
    {"accion", "dron", "mision", "motivo"}

===========================================================================
CHECKLIST DE REQUISITOS DEL ENUNCIADO (Sección 2.1 y 2.4)
===========================================================================
[x] >= 5 clases de hechos   -> 10 de dominio + 7 semánticas + 5 de control.
[x] >= 15 reglas            -> 28 reglas.
[x] >= 3 niveles de prioridad:
        ALTO  (salience 100)  seguridad de vuelo
        MEDIO (salience 50-60) operación y asignación
        BAJO  (salience 1-20) cierre, notificaciones y explicaciones
[x] Salience, Especificidad y Recencia -> estrategia propia
        `EstrategiaSkyRoute` (ver su docstring).
[x] Lock-Fact  -> hecho de control `Bloqueo` en `recargar_bateria_baja`.
[x] >= 40 hechos -> los genera el traductor desde la ontología (cientos).
[x] Hechos de la ontología usados en reglas (2.4): Pertenencia, Relacion,
        Atributo, Clase, SubClaseDe, Propiedad y SubPropiedadDe aparecen en
        las precondiciones de reglas (zona restringida, notificaciones,
        rescate de paquetes y explicación de inferencias).
"""

# ---------------------------------------------------------------------------
# [Test] Compatibilidad: Experta 1.9.4 usa `collections.Mapping`, que no
# existe desde Python 3.10 (Google Colab usa 3.12). Estas líneas restauran
# esos nombres antes de importar Experta. En Python <= 3.9 no hacen nada.
# ---------------------------------------------------------------------------
import collections
import collections.abc

for _nombre in ("Mapping", "MutableMapping", "Sequence", "Iterable",
                "Hashable", "Callable"):
    if not hasattr(collections, _nombre):
        setattr(collections, _nombre, getattr(collections.abc, _nombre))

from functools import lru_cache

from experta import KnowledgeEngine, Fact, Field, Rule, NOT, AS, MATCH, TEST, P
from experta.strategies import DepthStrategy


# ===========================================================================
# 1. CLASES DE HECHOS
# ===========================================================================

# --- 1.1 Hechos de dominio (los arma traductor.py) -------------------------

class Dron(Fact):
    """Un dron de la flota (individuo de dr:Dron)."""
    id = Field(str, mandatory=True)
    tipo = Field(str, mandatory=True)          # ligero | pesado | refrigerado | generico
    estado = Field(str, mandatory=True)        # disponible | en_vuelo | recargando | mantenimiento
                                               # [Test] + asignado | aterrizando (los pone el motor)
    bateria = Field(float, mandatory=True)     # 0-100
    capacidad_kg = Field(float, mandatory=True)
    zona = Field(str, mandatory=True)
    estacion_base = Field(str, mandatory=False)  # [Test] dr:seRecargaEn


class Paquete(Fact):
    """Un paquete a entregar (individuo de dr:Paquete)."""
    id = Field(str, mandatory=True)
    tipo = Field(str, mandatory=True)          # general | fragil | medico | express
    peso_kg = Field(float, mandatory=True)
    urgente = Field(bool, mandatory=True)      # inferido por OWL-RL (PaqueteUrgente)
    # [Test] Se quitó `destino`: en la ontología el destino pertenece a la
    # misión (dr:tieneDestino), no al paquete.


class Mision(Fact):
    """Una misión de entrega: lleva un paquete de una estación a una zona."""
    id = Field(str, mandatory=True)
    paquete = Field(str, mandatory=True)
    origen = Field(str, mandatory=True)
    destino = Field(str, mandatory=True)
    distancia_km = Field(float, mandatory=True)


class Zona(Fact):
    """Una zona de la ciudad."""
    id = Field(str, mandatory=True)
    nombre = Field(str, mandatory=True)
    tipo = Field(str, mandatory=True)          # residencial | comercial | restringida
    restringida = Field(bool, mandatory=True)  # inferido de dr:ZonaRestringida


class EstacionCarga(Fact):
    """Una estación de recarga."""
    id = Field(str, mandatory=True)
    zona = Field(str, mandatory=True)
    cupos = Field(int, mandatory=True)


class Clima(Fact):
    """Un registro de clima (individuo de dr:CondicionClimatica)."""
    id = Field(str, mandatory=True)
    t = Field(int, mandatory=True)             # dr:momento (mayor = más reciente)
    viento_kmh = Field(float, mandatory=True)
    condicion = Field(str, mandatory=True)     # despejado | lluvia | tormenta


class Operador(Fact):
    """[Test] Persona que supervisa drones (dr:Operador ⊑ foaf:Person)."""
    id = Field(str, mandatory=True)
    nombre = Field(str, mandatory=True)


class Cliente(Fact):
    """[Test] Persona que solicita envíos (dr:Cliente ⊑ foaf:Person)."""
    id = Field(str, mandatory=True)
    nombre = Field(str, mandatory=True)


class EvaluacionRiesgo(Fact):
    """Riesgo difuso (difuso.py) de una combinación dron-misión."""
    dron = Field(str, mandatory=True)
    mision = Field(str, mandatory=True)
    valor = Field(float, mandatory=True)       # 0-100
    etiqueta = Field(str, mandatory=True)      # bajo | medio | alto | muy_alto


# --- 1.2 [Test] Hechos semánticos: TODO el grafo razonado -------------------
# La sección 2.4 exige traducir "cada triple relevante (clases, propiedades,
# individuos e inferencias)". Estos hechos reflejan el grafo completo; el
# campo `inferido` indica si el hecho lo dedujo OWL-RL.

class Clase(Fact):
    """Una rdfs:Class con su significado (rdfs:label)."""
    id = Field(str, mandatory=True)
    etiqueta = Field(str, mandatory=True)


class SubClaseDe(Fact):
    """sub rdfs:subClassOf sup."""
    sub = Field(str, mandatory=True)
    sup = Field(str, mandatory=True)
    inferido = Field(bool, mandatory=True)


class Propiedad(Fact):
    """Una rdf:Property con su dominio, rango y significado."""
    id = Field(str, mandatory=True)
    dominio = Field(str, mandatory=True)
    rango = Field(str, mandatory=True)
    etiqueta = Field(str, mandatory=True)


class SubPropiedadDe(Fact):
    """sub rdfs:subPropertyOf sup."""
    sub = Field(str, mandatory=True)
    sup = Field(str, mandatory=True)
    inferido = Field(bool, mandatory=True)


class Pertenencia(Fact):
    """individuo rdf:type clase."""
    individuo = Field(str, mandatory=True)
    clase = Field(str, mandatory=True)
    inferido = Field(bool, mandatory=True)


class Relacion(Fact):
    """sujeto propiedad objeto, cuando el objeto es otro individuo."""
    sujeto = Field(str, mandatory=True)
    propiedad = Field(str, mandatory=True)
    objeto = Field(str, mandatory=True)
    inferido = Field(bool, mandatory=True)


class Atributo(Fact):
    """sujeto propiedad valor, cuando el valor es un literal."""
    sujeto = Field(str, mandatory=True)
    propiedad = Field(str, mandatory=True)
    valor = Field(object, mandatory=True)


# --- 1.3 Hechos de control (los crea el propio motor) ----------------------

class ClimaVigente(Fact):
    """Clima más reciente conocido (ver `actualizar_clima_vigente`)."""
    id = Field(str, mandatory=True)
    t = Field(int, mandatory=True)
    condicion = Field(str, mandatory=True)


class DecisionTomada(Fact):
    """Ya se decidió algo para una misión. [Test] Ahora guarda la acción,
    para que las reglas de notificación sepan qué se decidió."""
    mision = Field(str, mandatory=True)
    accion = Field(str, mandatory=True)


class Descartado(Fact):
    """[Test] Una combinación dron-misión descartada por riesgo. Descarta
    esa pareja, NO la misión completa: otro dron puede tomarla."""
    dron = Field(str, mandatory=True)
    mision = Field(str, mandatory=True)


class Bloqueo(Fact):
    """LOCK-FACT: candado por dron (ver `recargar_bateria_baja`)."""
    dron = Field(str, mandatory=True)


class CapacidadFlota(Fact):
    """[Test] Capacidad máxima de carga entre todos los drones."""
    maxima = Field(float, mandatory=True)


class Resumen(Fact):
    """Centinela para que el resumen final se genere una sola vez."""
    pass


# ===========================================================================
# 2. [Test] ESTRATEGIA DE RESOLUCIÓN DE CONFLICTOS
# ===========================================================================

class EstrategiaSkyRoute(DepthStrategy):
    """
    Decide qué activación de la agenda se ejecuta primero. Compara, en orden:

    1) SALIENCE: prioridad declarada en la regla. Separa los tres niveles
       (seguridad > operación > cierre). Una regla de salience 100 siempre
       se ejecuta antes que una de 50, sin importar lo demás.

    2) ESPECIFICIDAD: si dos activaciones tienen el mismo salience, gana la
       regla con MÁS elementos condicionales (patrones, TEST y NOT). Una
       regla con más condiciones describe una situación más particular y
       por eso debe preferirse sobre una más general.
       Experta NO trae este criterio: su única estrategia, DepthStrategy,
       solo usa salience y recencia. Por eso se implementa aquí.

    3) RECENCIA: si también empatan en especificidad, gana la activación
       cuyos hechos se declararon más recientemente (mayor id de hecho).
       Este es el comportamiento nativo de DepthStrategy y se conserva.

    La clave de ordenamiento es la tupla (salience, especificidad, recencia);
    la agenda ejecuta siempre la activación con la clave mayor.
    """

    @lru_cache()
    def get_key(self, activation):
        salience = activation.rule.salience
        especificidad = len(activation.rule)  # nº de elementos condicionales
        recencia = sorted((f['__factid__'] for f in activation.facts),
                          reverse=True)
        return (salience, especificidad, recencia)


# ===========================================================================
# 3. MOTOR DE REGLAS
# ===========================================================================

ACEPTABLE = P(lambda e: e in ("bajo", "medio"))
NO_MEDICO = P(lambda t: t != "medico")
NO_REFRIGERADO = P(lambda t: t != "refrigerado")
EN_TIERRA = P(lambda e: e in ("disponible", "recargando"))


class SistemaExpertoDrones(KnowledgeEngine):
    """
    Motor de reglas de SkyRoute.

    Niveles de prioridad (salience):
      - ALTO  (100):    seguridad de vuelo. Siempre gana.
      - MEDIO (50-60):  operación. 60 = paquetes urgentes; 50 = el resto.
      - BAJO  (1-20):   cierre (20), notificaciones y reportes (10),
                        explicación de inferencias (5) y resumen (1).

    Dónde se ve cada mecanismo de resolución de conflictos:
      - SALIENCE: `prohibir_zona_restringida` (100) resuelve M03 antes de
        que cualquier regla de asignación (50-60) pueda tomarla.
      - ESPECIFICIDAD (mismo salience 50, gana la de más condiciones):
          * `redirigir_estacion_llena` (8) sobre `recargar_bateria_baja` (3)
          * `asignar_dron_cercano` (8) sobre `asignar_dron_ligero`/`pesado` (7)
          * `asignar_pese_riesgo_alto_medico` (8) sobre `descartar_riesgo_alto` (3)
          * `priorizar_urgente_en_dron_ligero` (8) sobre
            `priorizar_paquetes_urgentes` (7)
        (El número es len(regla): patrones, TEST y NOT de la regla.)
      - RECENCIA: `actualizar_clima_vigente` se activa una vez por cada
        registro de clima; se ejecuta primero la del registro declarado
        más recientemente.
      - LOCK-FACT: ver `recargar_bateria_baja`.
    """

    __strategy__ = EstrategiaSkyRoute  # [Test]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.decisiones = []
        self.clima_vigente = None
        self.capacidad_max = None  # [Test]
        self.traza = False       # [Test] imprimir cada regla disparada
        self.disparos = []       # [Test] (regla, salience, especificidad)

    # ------------------------------------------------------------------
    def run(self, steps=float("inf")):
        """[Test] Igual que KnowledgeEngine.run, pero registra cada regla
        disparada con su salience y especificidad (evidencia de los
        mecanismos de resolución de conflictos)."""
        obtener = self.agenda.get_next

        def siguiente():
            act = obtener()
            if act is not None:
                registro = (act.rule.__name__, act.rule.salience, len(act.rule))
                self.disparos.append(registro)
                if self.traza:
                    # Hechos que activaron la regla, del más reciente al más
                    # antiguo (f-N = N-ésimo hecho declarado): muestra la recencia.
                    hechos = sorted(act.facts, key=lambda f: f["__factid__"],
                                    reverse=True)
                    ids = ", ".join(f"f-{f['__factid__']}" +
                                    (f"({f['id']})" if "id" in f else "")
                                    for f in hechos[:3])
                    print(f"  FIRE {len(self.disparos):>3}  salience={registro[1]:>3}"
                          f"  especificidad={registro[2]:>2}  {registro[0]:<34} {ids}")
            return act

        self.agenda.get_next = siguiente
        try:
            super().run(steps)
        finally:
            self.agenda.get_next = obtener

    def _decidir(self, accion, dron=None, mision=None, motivo=""):
        """Registra una decisión; si es sobre una misión, declara
        DecisionTomada para que ninguna otra regla la vuelva a decidir."""
        self.decisiones.append(
            {"accion": accion, "dron": dron, "mision": mision, "motivo": motivo})
        if mision is not None:
            self.declare(DecisionTomada(mision=mision, accion=accion))

    def _reportar(self, accion, motivo, dron=None, mision=None):
        """Registra algo que no es una decisión operativa (reportes,
        notificaciones y explicaciones)."""
        self.decisiones.append(
            {"accion": accion, "dron": dron, "mision": mision, "motivo": motivo})

    def _asignar(self, hecho_dron, d, m, motivo):
        """[Test] Asigna y marca el dron como ocupado, para que no pueda
        tomar otra misión (antes un mismo dron quedaba en dos misiones)."""
        self.modify(hecho_dron, estado="asignado")
        self._decidir("asignar", dron=d, mision=m, motivo=motivo)

    # ==================================================================
    # NIVEL ALTO — SEGURIDAD (salience = 100)
    # ==================================================================

    @Rule(Clima(id=MATCH.id, t=MATCH.t, condicion=MATCH.condicion),
          salience=100)
    def actualizar_clima_vigente(self, id, t, condicion):
        """
        RECENCIA. Hay varios registros Clima en la base de hechos (vienen
        de la ontología) y esta regla se activa una vez por cada uno.
        Todas tienen igual salience y especificidad, así que la estrategia
        ejecuta primero la del hecho declarado más recientemente.

        Además, solo se acepta un registro si su `t` es mayor al vigente.
        Así el resultado es siempre el clima más reciente, sin importar el
        orden de ejecución. Con la ontología base, el vigente es C04
        (despejado) aunque exista un registro anterior de tormenta (C03).

        El clima vigente se guarda como hecho (`ClimaVigente`) y no solo
        como atributo de Python, para que otras reglas lo usen en sus
        condiciones (ver `suspender_por_tormenta`).
        """
        if self.clima_vigente is None or t > self.clima_vigente["t"]:
            self.clima_vigente = {"id": id, "t": t, "condicion": condicion}
            for f in list(self.facts.values()):
                if isinstance(f, ClimaVigente):
                    self.retract(f)
            self.declare(ClimaVigente(id=id, t=t, condicion=condicion))

    @Rule(Dron(capacidad_kg=MATCH.c), salience=100)
    def calcular_capacidad_flota(self, c):
        """[Test] Mantiene un único hecho CapacidadFlota con la mayor
        capacidad de la flota (mismo patrón que el clima vigente)."""
        if self.capacidad_max is None or c > self.capacidad_max:
            self.capacidad_max = c
            for f in list(self.facts.values()):
                if isinstance(f, CapacidadFlota):
                    self.retract(f)
            self.declare(CapacidadFlota(maxima=c))

    @Rule(AS.f << Dron(id=MATCH.d, estado="en_vuelo", bateria=MATCH.b),
          TEST(lambda b: b < 15),
          salience=100)
    def aterrizaje_emergencia_bateria_critica(self, f, d, b):
        """Un dron en vuelo con batería crítica aterriza de inmediato."""
        self.modify(f, estado="aterrizando")
        self._decidir("aterrizaje_emergencia", dron=d,
                      motivo=f"batería crítica ({b}%) en vuelo: aterrizaje inmediato")

    @Rule(Mision(id=MATCH.m),
          Relacion(sujeto=MATCH.m, propiedad="involucraUbicacion", objeto=MATCH.z),
          Pertenencia(individuo=MATCH.z, clase="ZonaRestringida"),
          Zona(id=MATCH.z, nombre=MATCH.nombre),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=100)
    def prohibir_zona_restringida(self, m, z, nombre):
        """SALIENCE. [Test] Usa dos inferencias de la ontología:
        `involucraUbicacion` (inferida por subPropertyOf a partir de
        tieneOrigen/tieneDestino) y la pertenencia a ZonaRestringida.
        Como tiene salience 100, se ejecuta antes que cualquier regla de
        asignación (50-60) y ningún dron llega a ser enviado ahí."""
        self._decidir("rechazar", mision=m,
                      motivo=f"la misión involucra una zona restringida "
                             f"({z}, {nombre}): vuelo prohibido")

    @Rule(Mision(id=MATCH.m),
          NOT(DecisionTomada(mision=MATCH.m)),
          ClimaVigente(condicion="tormenta"),
          salience=100)
    def suspender_por_tormenta(self, m):
        """Si el clima vigente es tormenta, se suspenden las misiones
        pendientes. Se activa en cuanto aparece un ClimaVigente de tormenta."""
        self._decidir("posponer", mision=m,
                      motivo="tormenta en el clima vigente: vuelos suspendidos")

    @Rule(EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta="muy_alto"),
          NOT(Descartado(dron=MATCH.d, mision=MATCH.m)),
          salience=100)
    def descartar_riesgo_muy_alto(self, d, m):
        """[Test] Antes abortaba la misión completa si UN dron tenía riesgo
        muy alto. Ahora solo descarta esa pareja dron-misión."""
        self.declare(Descartado(dron=d, mision=m))
        self._reportar("descartar", dron=d, mision=m,
                       motivo="riesgo difuso muy_alto para esta pareja dron-misión")

    # ==================================================================
    # NIVEL MEDIO — OPERACIÓN (salience = 50 y 60)
    # ==================================================================

    # ---- 60: paquetes urgentes (se atienden antes que el resto) --------

    @Rule(Paquete(id=MATCH.p, tipo="medico", peso_kg=MATCH.peso),
          Mision(id=MATCH.m, paquete=MATCH.p),
          AS.fd << Dron(id=MATCH.d, tipo="refrigerado", estado="disponible",
                        capacidad_kg=MATCH.cap, bateria=MATCH.b),
          TEST(lambda peso, cap: peso <= cap),
          TEST(lambda b: b > 30),
          EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta=ACEPTABLE),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=60)
    def asignar_dron_refrigerado_medico(self, fd, d, m, p, peso, cap, b):
        """Los paquetes médicos (urgentes por inferencia) van en dron
        refrigerado para mantener la cadena de frío."""
        self._asignar(fd, d, m, f"paquete médico {p} en dron refrigerado {d} "
                                f"(cadena de frío, batería {b}%)")

    @Rule(Paquete(id=MATCH.p, urgente=True, tipo=NO_MEDICO, peso_kg=MATCH.peso),
          Mision(id=MATCH.m, paquete=MATCH.p),
          AS.fd << Dron(id=MATCH.d, tipo=NO_REFRIGERADO, estado="disponible",
                        capacidad_kg=MATCH.cap, bateria=MATCH.b),
          TEST(lambda peso, cap: peso <= cap),
          TEST(lambda b: b > 30),
          EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta=ACEPTABLE),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=60)
    def priorizar_paquetes_urgentes(self, fd, d, m, p, peso, cap, b):
        """[Test] Ahora revisa capacidad y batería, y tiene salience 60
        para que de verdad se atienda antes que los paquetes normales.
        Los médicos se excluyen porque exigen dron refrigerado, y los drones
        refrigerados se reservan para ellos (cadena de frío)."""
        self._asignar(fd, d, m, f"paquete urgente {p} ({peso} kg) priorizado; "
                                f"dron {d} con capacidad y batería suficientes")

    @Rule(Paquete(id=MATCH.p, urgente=True, tipo=NO_MEDICO, peso_kg=MATCH.peso),
          Mision(id=MATCH.m, paquete=MATCH.p),
          AS.fd << Dron(id=MATCH.d, estado="disponible",
                        capacidad_kg=MATCH.cap, bateria=MATCH.b),
          Pertenencia(individuo=MATCH.d, clase="DronLigero"),
          TEST(lambda peso, cap: peso <= cap),
          TEST(lambda b: b > 30),
          EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta=ACEPTABLE),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=60)
    def priorizar_urgente_en_dron_ligero(self, fd, d, m, p, peso):
        """[Test] ESPECIFICIDAD (8 condiciones contra 7 de
        `priorizar_paquetes_urgentes`, mismo salience 60). Si el paquete
        urgente cabe en un dron ligero, se prefiere ese y se dejan libres
        los pesados para la carga que realmente los necesita. Usa la
        pertenencia a dr:DronLigero que viene de la ontología."""
        self._asignar(fd, d, m, f"paquete urgente {p} ({peso} kg) priorizado en el "
                                f"dron ligero {d}; los pesados quedan para carga grande")

    # ---- 50: pareja de ESPECIFICIDAD con riesgo alto -------------------

    @Rule(EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta="alto"),
          Mision(id=MATCH.m, paquete=MATCH.p),
          Paquete(id=MATCH.p, tipo="medico", peso_kg=MATCH.peso),
          AS.fd << Dron(id=MATCH.d, tipo="refrigerado", estado="disponible",
                        capacidad_kg=MATCH.cap, bateria=MATCH.b),
          TEST(lambda b: b >= 50),
          TEST(lambda peso, cap: peso <= cap),
          NOT(DecisionTomada(mision=MATCH.m)),
          NOT(Descartado(dron=MATCH.d, mision=MATCH.m)),
          salience=50)
    def asignar_pese_riesgo_alto_medico(self, fd, d, m, p, b):
        """ESPECIFICIDAD, regla específica (8 condiciones). [Test] Tiene el
        MISMO salience que `descartar_riesgo_alto`: gana por tener más
        condiciones, no por prioridad. Un paquete médico se envía aunque el
        riesgo sea alto si hay un dron refrigerado con batería >= 50%."""
        self._asignar(fd, d, m, f"paquete médico {p}: se asigna pese al riesgo "
                                f"alto porque {d} tiene batería suficiente ({b}%)")

    @Rule(EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta="alto"),
          NOT(DecisionTomada(mision=MATCH.m)),
          NOT(Descartado(dron=MATCH.d, mision=MATCH.m)),
          salience=50)
    def descartar_riesgo_alto(self, d, m):
        """ESPECIFICIDAD, regla general (3 condiciones). Solo se ejecuta si
        la específica no resolvió antes la misión. [Test] Ya no pospone la
        misión completa: descarta la pareja y deja que otro dron la tome."""
        self.declare(Descartado(dron=d, mision=m))
        self._reportar("descartar", dron=d, mision=m,
                       motivo="riesgo difuso alto para esta pareja dron-misión")

    # ---- 50: asignación general ----------------------------------------

    @Rule(Mision(id=MATCH.m, paquete=MATCH.p, origen=MATCH.o),
          Paquete(id=MATCH.p, tipo=NO_MEDICO, peso_kg=MATCH.peso),
          EstacionCarga(id=MATCH.o, zona=MATCH.zd),
          AS.fd << Dron(id=MATCH.d, estado="disponible", zona=MATCH.zd,
                        capacidad_kg=MATCH.cap, bateria=MATCH.b),
          TEST(lambda peso, cap: peso <= cap),
          TEST(lambda b: b > 30),
          EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta=ACEPTABLE),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=50)
    def asignar_dron_cercano(self, fd, d, m, o, zd):
        """ESPECIFICIDAD (8 condiciones). [Test] Antes estaba en el nivel
        bajo y casi nunca se ejecutaba. Ahora comparte salience con las
        asignaciones generales y les gana por especificidad: si hay un dron
        apto en la misma zona de la estación de origen, se prefiere."""
        self._asignar(fd, d, m, f"dron {d} ya está en la zona de la estación "
                                f"de origen {o} ({zd}): se prefiere por cercanía")

    @Rule(Paquete(id=MATCH.p, tipo=NO_MEDICO, peso_kg=MATCH.peso),
          Mision(id=MATCH.m, paquete=MATCH.p),
          AS.fd << Dron(id=MATCH.d, tipo="ligero", estado="disponible",
                        capacidad_kg=MATCH.cap, bateria=MATCH.b),
          TEST(lambda peso, cap: peso <= cap),
          TEST(lambda b: b > 30),
          EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta=ACEPTABLE),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=50)
    def asignar_dron_ligero(self, fd, d, m, peso):
        self._asignar(fd, d, m, f"dron ligero {d} con capacidad para {peso} kg, "
                                f"batería y riesgo aceptables")

    @Rule(Paquete(id=MATCH.p, tipo=NO_MEDICO, peso_kg=MATCH.peso),
          Mision(id=MATCH.m, paquete=MATCH.p),
          AS.fd << Dron(id=MATCH.d, tipo="pesado", estado="disponible",
                        capacidad_kg=MATCH.cap, bateria=MATCH.b),
          TEST(lambda peso, cap: peso <= cap),
          TEST(lambda b: b > 30),
          EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta=ACEPTABLE),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=50)
    def asignar_dron_pesado(self, fd, d, m, peso):
        self._asignar(fd, d, m, f"dron pesado {d} con capacidad para {peso} kg, "
                                f"batería y riesgo aceptables")

    @Rule(Paquete(id=MATCH.p, peso_kg=MATCH.peso),
          Mision(id=MATCH.m, paquete=MATCH.p),
          CapacidadFlota(maxima=MATCH.cmax),
          TEST(lambda peso, cmax: peso > cmax),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=50)
    def rechazar_paquete_sobrepeso(self, m, p, peso, cmax):
        """[Test] Antes comparaba contra 10 kg escrito en el código. Ahora
        compara contra la capacidad máxima real de la flota, calculada a
        partir de los drones de la ontología (`calcular_capacidad_flota`)."""
        self._decidir("rechazar", mision=m,
                      motivo=f"el paquete {p} pesa {peso} kg y ningún dron de la "
                             f"flota carga más de {cmax} kg")

    # ---- 50: batería baja: pareja de ESPECIFICIDAD + LOCK-FACT ---------

    @Rule(AS.f << Dron(id=MATCH.d, estado=EN_TIERRA, bateria=MATCH.b),
          TEST(lambda b: b <= 30),
          NOT(Bloqueo(dron=MATCH.d)),
          salience=50)
    def recargar_bateria_baja(self, f, d, b):
        """
        LOCK-FACT. Esta regla modifica el mismo hecho `Dron` que la activó.
        En Experta, `modify` retracta el hecho y declara uno nuevo; el nuevo
        dron sigue cumpliendo el patrón (sigue en tierra y con batería
        <= 30), así que sin control la regla se volvería a activar para
        siempre (bucle infinito).

        El candado es el hecho `Bloqueo(dron=d)`: la regla exige que NO
        exista, y lo declara al ejecutarse. Así se ejecuta una sola vez por
        dron. Pueden comprobarlo comentando `self.declare(Bloqueo(dron=d))`
        (aquí y en `redirigir_estacion_llena`) y ejecutando con un límite de
        pasos, por ejemplo motor.run(steps=400): la regla se repite sin parar.
        """
        self.modify(f, estado="recargando")
        self.declare(Bloqueo(dron=d))
        self._decidir("recargar", dron=d,
                      motivo=f"batería baja ({b}%): se envía a recargar")

    @Rule(AS.f << Dron(id=MATCH.d, estado=EN_TIERRA, bateria=MATCH.b,
                       estacion_base=MATCH.e1),
          TEST(lambda b: b <= 30),
          EstacionCarga(id=MATCH.e1, cupos=MATCH.c1),
          TEST(lambda c1: c1 <= 0),
          EstacionCarga(id=MATCH.e2, cupos=MATCH.c2),
          TEST(lambda c2: c2 > 0),
          TEST(lambda e1, e2: e1 != e2),
          NOT(Bloqueo(dron=MATCH.d)),
          salience=50)
    def redirigir_estacion_llena(self, f, d, b, e1, e2):
        """ESPECIFICIDAD (8 condiciones contra 3 de `recargar_bateria_baja`,
        mismo salience). [Test] Usa la estación base del dron
        (dr:seRecargaEn) y ahora también cambia su estado a "recargando";
        antes el dron quedaba "disponible" con 20% de batería.
        Comparte el candado `Bloqueo` con la recarga normal: la que se
        ejecute primero impide que la otra actúe sobre el mismo dron."""
        self.modify(f, estado="recargando")
        self.declare(Bloqueo(dron=d))
        self._decidir("redirigir", dron=d,
                      motivo=f"batería baja ({b}%) y su estación base {e1} sin "
                             f"cupos: redirigido a {e2}")

    # ==================================================================
    # NIVEL BAJO — CIERRE (20), REPORTES (10), EXPLICACIONES (5), RESUMEN (1)
    # ==================================================================

    @Rule(Mision(id=MATCH.m),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=20)
    def posponer_sin_dron_viable(self, m):
        """[Test] Reemplaza a `posponer_riesgo_alto`. Como tiene salience 20,
        solo se ejecuta cuando ya terminaron todas las reglas de asignación:
        si a esa altura la misión sigue sin decisión, es porque ningún dron
        disponible tenía capacidad, batería y riesgo aceptables."""
        self._decidir("posponer", mision=m,
                      motivo="ningún dron disponible cumple capacidad, batería "
                             "y riesgo aceptable")

    @Rule(Dron(id=MATCH.d, estado="aterrizando"),
          Relacion(sujeto=MATCH.d, propiedad="supervisadoPor", objeto=MATCH.op),
          Operador(id=MATCH.op, nombre=MATCH.nombre),
          salience=10)
    def notificar_operador_emergencia(self, d, op, nombre):
        """[Test] Usa la relación dr:supervisadoPor y el hecho Operador."""
        self._reportar("notificar_operador", dron=d,
                       motivo=f"se avisa a {nombre} ({op}), operador de {d}, "
                              f"por el aterrizaje de emergencia")

    @Rule(Dron(id=MATCH.d, estado="aterrizando"),
          Relacion(sujeto=MATCH.d, propiedad="transporta", objeto=MATCH.p),
          Paquete(id=MATCH.p),
          salience=10)
    def rescatar_paquete_transportado(self, d, p):
        """[Test] Usa la relación dr:transporta: el paquete que llevaba un
        dron en emergencia queda en tierra y hay que recogerlo."""
        self._reportar("rescatar_paquete", dron=d,
                       motivo=f"el paquete {p} quedó en tierra con {d}: "
                              f"programar recogida")

    @Rule(DecisionTomada(mision=MATCH.m,
                         accion=P(lambda a: a in ("posponer", "rechazar"))),
          Mision(id=MATCH.m, paquete=MATCH.p),
          Relacion(sujeto=MATCH.p, propiedad="solicitadoPor", objeto=MATCH.c),
          Cliente(id=MATCH.c, nombre=MATCH.nombre),
          salience=10)
    def notificar_cliente(self, m, p, c, nombre):
        """[Test] Usa dr:solicitadoPor y el hecho Cliente. Para CL03 y CL04,
        que no se declararon como clientes en el .ttl, el hecho Cliente
        existe gracias a la inferencia por rango."""
        self._reportar("notificar_cliente", mision=m,
                       motivo=f"se avisa a {nombre} ({c}) que su paquete {p} "
                              f"no saldrá por ahora")

    @Rule(Mision(id=MATCH.m),
          DecisionTomada(mision=MATCH.m, accion=MATCH.a),
          Atributo(sujeto=MATCH.m, propiedad="description", valor=MATCH.desc),
          salience=10)
    def registrar_mision_procesada(self, m, a, desc):
        """[Test] Incluye la descripción de la misión (dcterms:description)."""
        self._reportar("reporte", mision=m,
                       motivo=f"misión {m} ({desc}) -> {a}")

    @Rule(Dron(id=MATCH.d, estado="disponible", bateria=MATCH.b),
          TEST(lambda b: b > 60),
          salience=10)
    def sugerir_balanceo_flota(self, d, b):
        """Drones libres y con buena batería al terminar la asignación.
        [Test] Ya no revisa la lista de decisiones en Python: los drones
        asignados cambian a estado "asignado" y dejan de cumplir el patrón."""
        self._reportar("reporte", dron=d,
                       motivo=f"dron {d} quedó libre con {b}% de batería: "
                              f"candidato para balancear la flota")

    # ---- 5: explicación de las inferencias de la ontología -------------

    @Rule(Pertenencia(individuo=MATCH.i, clase=MATCH.sup, inferido=True),
          Pertenencia(individuo=MATCH.i, clase=MATCH.sub, inferido=False),
          SubClaseDe(sub=MATCH.sub, sup=MATCH.sup),
          Clase(id=MATCH.sup, etiqueta=MATCH.etq),
          salience=5)
    def explicar_herencia_de_clase(self, i, sub, sup, etq):
        """[Test] Usa Pertenencia, SubClaseDe y Clase (caso 1 de la 2.3)."""
        self._reportar("explicacion",
                       motivo=f"{i} es {sup} porque es {sub} y {sub} ⊑ {sup}"
                              + (f"  [{etq}]" if etq else ""))

    @Rule(Pertenencia(individuo=MATCH.i, clase=MATCH.c, inferido=True),
          NOT(Pertenencia(individuo=MATCH.i, inferido=False)),
          Relacion(sujeto=MATCH.s, propiedad=MATCH.prop, objeto=MATCH.i),
          Propiedad(id=MATCH.prop, rango=MATCH.c),
          salience=5)
    def explicar_por_rango(self, i, c, s, prop):
        """[Test] Usa Propiedad.rango (caso 2 de la 2.3). Solo explica
        individuos sin ningún tipo declarado en el .ttl."""
        self._reportar("explicacion",
                       motivo=f"{i} es {c} porque aparece como objeto de "
                              f"{s} {prop} {i} y el rango de {prop} es {c}")

    @Rule(Pertenencia(individuo=MATCH.i, clase=MATCH.c, inferido=True),
          NOT(Pertenencia(individuo=MATCH.i, inferido=False)),
          Relacion(sujeto=MATCH.i, propiedad=MATCH.prop),
          Propiedad(id=MATCH.prop, dominio=MATCH.c),
          salience=5)
    def explicar_por_dominio(self, i, c, prop):
        """[Test] Usa Propiedad.dominio (caso 2 de la 2.3)."""
        self._reportar("explicacion",
                       motivo=f"{i} es {c} porque usa la propiedad {prop}, "
                              f"cuyo dominio es {c}")

    @Rule(Relacion(sujeto=MATCH.s, propiedad=MATCH.sup, objeto=MATCH.o, inferido=True),
          Relacion(sujeto=MATCH.s, propiedad=MATCH.sub, objeto=MATCH.o, inferido=False),
          SubPropiedadDe(sub=MATCH.sub, sup=MATCH.sup),
          salience=5)
    def explicar_subpropiedad(self, s, o, sub, sup):
        """[Test] Usa SubPropiedadDe (caso 3 de la 2.3)."""
        self._reportar("explicacion",
                       motivo=f"{s} {sup} {o} porque {s} {sub} {o} "
                              f"y {sub} ⊑ {sup}")

    @Rule(NOT(Resumen()), salience=1)
    def generar_resumen_final(self):
        """Salience más baja: se ejecuta cuando ya no queda nada pendiente."""
        self.declare(Resumen())
        total = sum(1 for d in self.decisiones
                    if d["accion"] in ACCIONES_OPERATIVAS)
        self._reportar("resumen",
                       motivo=f"{total} decisiones operativas generadas")


ACCIONES_OPERATIVAS = {"asignar", "posponer", "rechazar", "recargar",
                       "redirigir", "aterrizaje_emergencia"}


# ===========================================================================
# 4. FUNCIÓN DE CONTRATO (usada por main.py)
# ===========================================================================

def ejecutar(hechos, traza=False):
    """
    Recibe la lista de hechos (generados por traductor.py a partir de la
    ontología, más las evaluaciones de riesgo de difuso.py), ejecuta el
    motor y devuelve (decisiones, motor).

    [Test] Se eliminó la demostración con 40 hechos escritos a mano: el
    enunciado prohíbe declarar en el código del sistema experto los datos
    que están en la ontología. Para probar el sistema, ejecutar main.py.
    """
    motor = SistemaExpertoDrones()
    motor.traza = traza
    motor.reset()
    for hecho in hechos:
        motor.declare(hecho)
    motor.run()
    return motor.decisiones, motor


if __name__ == "__main__":
    print("Este módulo no se ejecuta solo: sus hechos vienen de la ontología.")
    print("Ejecute:  python main.py")
