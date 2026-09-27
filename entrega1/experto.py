# -*- coding: utf-8 -*-
"""
experto.py — Módulo de Sistema Experto (Experta) del sistema híbrido SkyRoute
Trabajo Práctico 1 — Introducción a la Inteligencia Artificial (3010476), UNAL
Persona 1 — Sistema Experto

===========================================================================
QUÉ RECIBE ESTE MÓDULO (contrato acordado con el grupo)
===========================================================================
La función pública `ejecutar(hechos)` es el único punto de entrada que usa
`main.py` (Persona 4). `hechos` es un diccionario con siete listas, una por
cada clase de hecho, ya con los campos `urgente` (Paquete) y `restringida`
(Zona) completados por `ontologia.py` (Persona 3), y las evaluaciones de
riesgo ya calculadas por `difuso.py` (Persona 2):

    {
        "drones":     [{"id","tipo","estado","bateria","capacidad_kg","zona"}, ...],
        "paquetes":   [{"id","tipo","peso_kg","destino","urgente"}, ...],
        "misiones":   [{"id","paquete","origen","destino","distancia_km"}, ...],
        "zonas":      [{"id","nombre","tipo","restringida"}, ...],
        "estaciones": [{"id","zona","cupos"}, ...],
        "climas":     [{"id","t","viento_kmh","condicion"}, ...],
        "riesgos":    [{"dron","mision","valor","etiqueta"}, ...],
    }

`ejecutar(hechos)` devuelve una lista de decisiones:
    [{"accion", "dron", "mision", "motivo"}, ...]

===========================================================================
CHECKLIST DE REQUISITOS DEL ENUNCIADO (Sección 2.1)
===========================================================================
[x] >= 5 clases de hechos           -> 7 clases de dominio (Dron, Paquete,
                                        Mision, Zona, EstacionCarga, Clima,
                                        EvaluacionRiesgo) + 3 clases de
                                        control internas (ClimaVigente,
                                        DecisionTomada, Bloqueo).
[x] >= 15 reglas                    -> 18 reglas (ver abajo).
[x] >= 3 niveles de prioridad       -> salience 100 / 52-55 / 50 / 10 / 1
                                        agrupados conceptualmente en tres
                                        niveles: ALTO (seguridad, 100),
                                        MEDIO (operación, 50-55) y BAJO
                                        (optimización/reportes, 1-10).
[x] Recencia    -> regla `actualizar_clima_vigente` (ver explicación ahí).
[x] Especificidad -> par de reglas `asignar_pese_riesgo_alto_medico`
                      (específica) / `posponer_riesgo_alto` (general).
[x] Salience    -> nivel ALTO (seguridad, 100) siempre gana sobre nivel
                    MEDIO/BAJO; ver ejemplo en la regla de zona restringida.
[x] No-Loop / Lock-Fact -> hecho de control `Bloqueo` + transición de
                            estado en `recargar_bateria_baja`.
[x] >= 40 hechos -> ver bloque de demostración en `if __name__ == "__main__"`
                    con el dataset de 40 hechos acordado por el grupo.
"""

from experta import (
    KnowledgeEngine,
    Fact,
    Field,
    Rule,
    NOT,
    AS,
    MATCH,
    TEST,
    P,
)


# ===========================================================================
# 1. CLASES DE HECHOS (>= 5 requeridas; aquí hay 7 de dominio + 3 de control)
# ===========================================================================

class Dron(Fact):
    """Un dron de la flota."""
    id = Field(str, mandatory=True)
    tipo = Field(str, mandatory=True)          # ligero | pesado | refrigerado
    estado = Field(str, mandatory=True)        # disponible | en_vuelo | recargando | mantenimiento | aterrizando
    bateria = Field(float, mandatory=True)     # 0-100
    capacidad_kg = Field(float, mandatory=True)
    zona = Field(str, mandatory=True)


class Paquete(Fact):
    """Un paquete a entregar."""
    id = Field(str, mandatory=True)
    tipo = Field(str, mandatory=True)          # general | fragil | medico | express
    peso_kg = Field(float, mandatory=True)
    destino = Field(str, mandatory=True)
    urgente = Field(bool, mandatory=True)      # viene de la ontología (OWL-RL)


class Mision(Fact):
    """Una misión de entrega: transporta un paquete de una estación a una zona."""
    id = Field(str, mandatory=True)
    paquete = Field(str, mandatory=True)
    origen = Field(str, mandatory=True)
    destino = Field(str, mandatory=True)
    distancia_km = Field(float, mandatory=True)


class Zona(Fact):
    """Una zona geográfica de la ciudad."""
    id = Field(str, mandatory=True)
    nombre = Field(str, mandatory=True)
    tipo = Field(str, mandatory=True)          # residencial | comercial | restringida
    restringida = Field(bool, mandatory=True)  # viene de la ontología (OWL-RL)


class EstacionCarga(Fact):
    """Una estación de recarga."""
    id = Field(str, mandatory=True)
    zona = Field(str, mandatory=True)
    cupos = Field(int, mandatory=True)


class Clima(Fact):
    """Un registro de clima en un instante t (puede haber varios: histórico)."""
    id = Field(str, mandatory=True)
    t = Field(int, mandatory=True)             # marca temporal creciente
    viento_kmh = Field(float, mandatory=True)
    condicion = Field(str, mandatory=True)     # despejado | lluvia | tormenta


class EvaluacionRiesgo(Fact):
    """Riesgo difuso (Scikit-Fuzzy) de una combinación dron-mision."""
    dron = Field(str, mandatory=True)
    mision = Field(str, mandatory=True)
    valor = Field(float, mandatory=True)       # 0-100
    etiqueta = Field(str, mandatory=True)      # bajo | medio | alto | muy_alto


# --- Hechos de control (no vienen de datos.json; los usa el motor) --------

class ClimaVigente(Fact):
    """Snapshot del clima más reciente. Ver `actualizar_clima_vigente`."""
    id = Field(str, mandatory=True)
    t = Field(int, mandatory=True)
    condicion = Field(str, mandatory=True)


class DecisionTomada(Fact):
    """Marca que ya se decidió algo para una misión (evita duplicados y
    es la pieza clave del mecanismo de ESPECIFICIDAD, ver más abajo)."""
    mision = Field(str, mandatory=True)


class Bloqueo(Fact):
    """Mecanismo de LOCK-FACT: candado por dron para evitar que una regla
    que modifica el propio hecho que la activó vuelva a dispararse en
    bucle infinito (requisito de la sección 2.1)."""
    dron = Field(str, mandatory=True)


class Resumen(Fact):
    """Hecho centinela para que el resumen final se genere una sola vez."""
    pass


# ===========================================================================
# 2. MOTOR DE REGLAS
# ===========================================================================

class SistemaExpertoDrones(KnowledgeEngine):
    """
    Motor de reglas de SkyRoute.

    Niveles de prioridad (salience) usados en este archivo:
      - ALTO   (salience=100): seguridad de vuelo. Siempre gana.
      - MEDIO  (salience=50, con 52 y 55 para casos que deben ganarle a
                otras reglas del mismo nivel): asignación y operación.
      - BAJO   (salience=1 y 10): optimización, reportes y cierre.

    MECANISMOS DE RESOLUCIÓN DE CONFLICTOS IMPLEMENTADOS
    ------------------------------------------------------------------
    1) SALIENCE: las reglas de seguridad (aterrizaje de emergencia, zona
       restringida, tormenta, riesgo muy alto) tienen salience=100, el
       valor más alto del sistema. Así, aunque una regla de nivel medio
       (p. ej. "asignar dron ligero") también podría dispararse para la
       misma misión, Experta coloca primero en la agenda las activaciones
       de salience=100 y estas se ejecutan antes, dejando la misión ya
       resuelta (vía DecisionTomada) antes de que la regla de nivel medio
       llegue a evaluarse.

    2) ESPECIFICIDAD: comparar la regla general `posponer_riesgo_alto`
       (una sola condición: riesgo=alto) contra la específica
       `asignar_pese_riesgo_alto_medico` (cuatro condiciones: riesgo=alto
       + paquete médico + dron pesado disponible + batería >= 50%). La
       regla específica tiene salience=55 (más alto que los 50 de la
       general) para que, cuando AMBAS calcen, se dispare primero. Al
       hacerlo, declara `DecisionTomada(mision=m)`, lo que invalida
       automáticamente la activación de la regla general para esa misión
       (su condición `NOT(DecisionTomada(mision=m))` deja de cumplirse).
       Esto es exactamente cómo CLIPS/Experta resuelven especificidad en
       la práctica: con más condiciones + un hecho de control que hace
       mutuamente excluyentes a las dos reglas.

    3) RECENCIA: ver el docstring de `actualizar_clima_vigente`. Cuando
       existen varios hechos `Clima`, se usa siempre el de mayor `t`
       (el más reciente), y el `Bloqueo`/`redirigir_estacion_llena` vs.
       `recargar_bateria_baja` (mismo salience=50/52) resuelven su empate
       según qué hecho fue declarado más recientemente en la agenda.

    4) LOCK-FACT (control de bucles): `recargar_bateria_baja` modifica el
       propio hecho `Dron` que la activó (le sube la batería y cambia su
       estado a "recargando"). Sin control, cada modificación volvería a
       intentar calzar el patrón. Se usa doble protección: (a) el cambio
       de `estado` saca al dron del patrón `estado='disponible'`, y
       (b) se declara explícitamente `Bloqueo(dron=d)`, que la regla exige
       ausente (`NOT(Bloqueo(dron=d))`) antes de dispararse. Así se
       garantiza una única ejecución por dron y corrida.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.decisiones = []
        self.clima_vigente = None  # dict con el clima más reciente conocido

    # ------------------------------------------------------------------
    def _decidir(self, accion, dron=None, mision=None, motivo=""):
        """Registra una decisión y, si aplica a una misión, marca
        DecisionTomada para activar el mecanismo de especificidad /
        evitar decisiones duplicadas sobre la misma misión."""
        self.decisiones.append(
            {"accion": accion, "dron": dron, "mision": mision, "motivo": motivo}
        )
        if mision is not None:
            self.declare(DecisionTomada(mision=mision))

    def cargar_hechos(self, hechos):
        """Declara en el motor todos los hechos recibidos desde main.py."""
        for d in hechos.get("drones", []):
            self.declare(Dron(id=d["id"], tipo=d["tipo"], estado=d["estado"],
                               bateria=float(d["bateria"]),
                               capacidad_kg=float(d["capacidad_kg"]),
                               zona=d["zona"]))
        for p in hechos.get("paquetes", []):
            self.declare(Paquete(id=p["id"], tipo=p["tipo"],
                                  peso_kg=float(p["peso_kg"]),
                                  destino=p["destino"],
                                  urgente=bool(p.get("urgente", False))))
        for m in hechos.get("misiones", []):
            self.declare(Mision(id=m["id"], paquete=m["paquete"],
                                 origen=m["origen"], destino=m["destino"],
                                 distancia_km=float(m["distancia_km"])))
        for z in hechos.get("zonas", []):
            self.declare(Zona(id=z["id"], nombre=z["nombre"], tipo=z["tipo"],
                               restringida=bool(z.get("restringida", False))))
        for e in hechos.get("estaciones", []):
            self.declare(EstacionCarga(id=e["id"], zona=e["zona"],
                                        cupos=int(e["cupos"])))
        for c in hechos.get("climas", []):
            self.declare(Clima(id=c["id"], t=int(c["t"]),
                                viento_kmh=float(c["viento_kmh"]),
                                condicion=c["condicion"]))
        for r in hechos.get("riesgos", []):
            self.declare(EvaluacionRiesgo(dron=r["dron"], mision=r["mision"],
                                           valor=float(r["valor"]),
                                           etiqueta=r["etiqueta"]))

    # ==================================================================
    # NIVEL ALTO — SEGURIDAD (salience=100)
    # ==================================================================

    @Rule(Clima(id=MATCH.id, t=MATCH.t, condicion=MATCH.condicion),
          salience=100)
    def actualizar_clima_vigente(self, id, t, condicion):
        """
        MECANISMO DE RECENCIA.

        Esta regla calza con TODOS los hechos Clima presentes (puede haber
        varios simultáneamente, o llegar uno nuevo a mitad de la ejecución
        cuando main.py hace `engine.declare(Clima(...))` seguido de otro
        `engine.run()`). Cada vez que se dispara, solo actualiza
        `self.clima_vigente` si el `t` del hecho que la activó es mayor
        al que ya tenía guardado. De este modo, sin importar el orden en
        que Experta decida procesar las activaciones en la agenda, el
        resultado siempre converge al clima con el `t` más alto: el más
        reciente. Esto es justo el criterio de "recencia" pedido en el
        enunciado, y se ve claramente en el escenario de la sustentación
        donde se declara C03 (tormenta) y luego C04 (despejado) a mitad
        de la corrida: el sistema reacciona primero a la tormenta y luego
        vuelve a operar normalmente al recibir el clima más nuevo.

        El hecho de control `ClimaVigente` se retracta y se vuelve a
        declarar cada vez que cambia (patrón "hecho singleton"). Esto es
        clave: otras reglas (como `suspender_por_tormenta`) lo incluyen
        como condición directa en su patrón, así que al declarar un
        `ClimaVigente` nuevo, Experta genera automáticamente activaciones
        frescas contra TODAS las misiones aún pendientes -- incluyendo
        las que ya estaban en el sistema antes del cambio de clima. Si en
        vez de esto solo se guardara `self.clima_vigente` como atributo de
        Python y se leyera con un `if` dentro del cuerpo de otra regla,
        esa regla no se re-evaluaría al cambiar el clima (su activación ya
        se habría consumido antes, con el clima anterior).
        """
        if self.clima_vigente is None or t > self.clima_vigente["t"]:
            self.clima_vigente = {"id": id, "t": t, "condicion": condicion}
            for f in list(self.facts.values()):
                if isinstance(f, ClimaVigente):
                    self.retract(f)
            self.declare(ClimaVigente(id=id, t=t, condicion=condicion))

    @Rule(Dron(id=MATCH.d, estado="en_vuelo", bateria=MATCH.b),
          TEST(lambda b: b < 15),
          salience=100)
    def aterrizaje_emergencia_bateria_critica(self, d, b):
        """SALIENCE: seguridad primero. Si un dron en vuelo tiene batería
        crítica, se ordena aterrizaje de emergencia sin esperar a que se
        evalúen reglas de asignación u optimización de nivel medio/bajo."""
        for f in self.facts.values():
            if isinstance(f, Dron) and f["id"] == d:
                self.modify(f, estado="aterrizando")
                break
        self._decidir("aterrizaje_emergencia", dron=d,
                       motivo=f"batería crítica ({b}%) en vuelo: aterrizaje inmediato")

    @Rule(Mision(id=MATCH.m, destino=MATCH.z),
          Zona(id=MATCH.z, restringida=True),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=100)
    def prohibir_zona_restringida(self, m, z):
        """SALIENCE: ejemplo pedido en el enunciado. Un dron podría en
        principio calzar con las condiciones de una regla de asignación
        (nivel medio, salience=50) para esta misión, pero como esta regla
        de seguridad tiene salience=100, Experta la ejecuta primero,
        declara DecisionTomada y así ninguna regla de asignación llega
        a intentar mandar un dron a la zona restringida."""
        self._decidir("rechazar", mision=m,
                       motivo=f"destino en zona restringida ({z}): vuelo prohibido")

    @Rule(Mision(id=MATCH.m),
          NOT(DecisionTomada(mision=MATCH.m)),
          ClimaVigente(condicion="tormenta"),
          salience=100)
    def suspender_por_tormenta(self, m):
        """Si el clima vigente (hecho `ClimaVigente`, ver
        `actualizar_clima_vigente`) es tormenta, se suspenden todas las
        misiones aún no decididas. Al incluir `ClimaVigente` directamente
        en el patrón (y no solo como un `if` sobre un atributo de Python),
        esta regla se re-evalúa automáticamente contra las misiones
        pendientes cada vez que el clima vigente cambia a mitad de
        ejecución."""
        self._decidir("posponer", mision=m,
                       motivo="tormenta activa en el clima vigente: se suspenden vuelos por seguridad")

    @Rule(EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta="muy_alto"),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=100)
    def abortar_riesgo_muy_alto(self, d, m):
        self._decidir("abortar", dron=d, mision=m,
                       motivo="riesgo difuso evaluado como muy_alto para esta combinación dron-misión")

    # ==================================================================
    # NIVEL MEDIO — OPERACIÓN (salience=50, y 52/55 para casos que deben
    # ganarle a otra regla del mismo nivel)
    # ==================================================================

    @Rule(EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta="alto"),
          Paquete(id=MATCH.p, tipo="medico"),
          Mision(id=MATCH.m, paquete=MATCH.p),
          Dron(id=MATCH.d, tipo="pesado", estado="disponible", bateria=MATCH.b),
          TEST(lambda b: b >= 50),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=55)
    def asignar_pese_riesgo_alto_medico(self, d, m, b):
        """ESPECIFICIDAD (regla específica). Cuatro condiciones a la vez:
        riesgo alto + paquete médico + dron pesado disponible + batería
        suficiente (>=50%). Gracias a salience=55 (mayor que el 50 de la
        regla general `posponer_riesgo_alto`), esta se evalúa primero
        cuando ambas calzan, y su DecisionTomada bloquea a la general."""
        self._decidir("asignar", dron=d, mision=m,
                       motivo="paquete médico urgente: se asigna pese al riesgo alto porque el "
                              f"dron pesado {d} tiene batería suficiente ({b}%) — regla específica")

    @Rule(EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta="alto"),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=50)
    def posponer_riesgo_alto(self, d, m):
        """ESPECIFICIDAD (regla general). Solo se dispara si ninguna
        regla más específica (como `asignar_pese_riesgo_alto_medico`) ya
        resolvió la misión."""
        self._decidir("posponer", mision=m,
                       motivo=f"riesgo alto evaluado para el dron {d}: se pospone por precaución")

    @Rule(Paquete(id=MATCH.p, peso_kg=MATCH.peso),
          Mision(id=MATCH.m, paquete=MATCH.p),
          Dron(id=MATCH.d, tipo="ligero", estado="disponible",
               capacidad_kg=MATCH.cap, bateria=MATCH.b),
          TEST(lambda peso, cap: peso <= cap),
          TEST(lambda b: b >= 30),
          EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m,
                            etiqueta=P(lambda e: e in ("bajo", "medio"))),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=50)
    def asignar_dron_ligero(self, d, m, peso, cap, b):
        self._decidir("asignar", dron=d, mision=m,
                       motivo=f"dron ligero {d} disponible, capacidad y batería suficientes, riesgo aceptable")

    @Rule(Paquete(id=MATCH.p, peso_kg=MATCH.peso),
          Mision(id=MATCH.m, paquete=MATCH.p),
          Dron(id=MATCH.d, tipo="pesado", estado="disponible",
               capacidad_kg=MATCH.cap, bateria=MATCH.b),
          TEST(lambda peso, cap: peso <= cap),
          TEST(lambda b: b >= 30),
          EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m,
                            etiqueta=P(lambda e: e in ("bajo", "medio"))),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=50)
    def asignar_dron_pesado(self, d, m, peso, cap, b):
        self._decidir("asignar", dron=d, mision=m,
                       motivo=f"paquete de {peso}kg requiere dron pesado; {d} disponible con capacidad suficiente")

    @Rule(Paquete(id=MATCH.p, tipo="medico", peso_kg=MATCH.peso),
          Mision(id=MATCH.m, paquete=MATCH.p),
          Dron(id=MATCH.d, tipo="refrigerado", estado="disponible",
               capacidad_kg=MATCH.cap, bateria=MATCH.b),
          TEST(lambda peso, cap: peso <= cap),
          TEST(lambda b: b >= 30),
          EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m,
                            etiqueta=P(lambda e: e in ("bajo", "medio"))),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=50)
    def asignar_dron_refrigerado_medico(self, d, m, peso, cap, b):
        self._decidir("asignar", dron=d, mision=m,
                       motivo=f"paquete médico asignado a dron refrigerado {d} (cadena de frío)")

    @Rule(AS.f << Dron(id=MATCH.d, estado="disponible", bateria=MATCH.b),
          TEST(lambda b: b <= 30),
          NOT(Bloqueo(dron=MATCH.d)),
          salience=50)
    def recargar_bateria_baja(self, f, d, b):
        """LOCK-FACT + auto-invalidación de estado: ver docstring de la
        clase `SistemaExpertoDrones`."""
        self.modify(f, estado="recargando", bateria=100.0)
        self.declare(Bloqueo(dron=d))
        self._decidir("recargar", dron=d,
                       motivo=f"batería baja ({b}%): se envía a recargar")

    @Rule(Dron(id=MATCH.d, estado="disponible", bateria=MATCH.b, zona=MATCH.zd),
          TEST(lambda b: b <= 30),
          EstacionCarga(id=MATCH.e1, zona=MATCH.zd, cupos=MATCH.c1),
          TEST(lambda c1: c1 <= 0),
          EstacionCarga(id=MATCH.e2, cupos=MATCH.c2),
          TEST(lambda c2: c2 > 0),
          TEST(lambda e1, e2: e1 != e2),
          NOT(Bloqueo(dron=MATCH.d)),
          salience=52)
    def redirigir_estacion_llena(self, d, b, zd, e1, e2, c1, c2):
        """Comparte el candado `Bloqueo(dron=d)` con `recargar_bateria_baja`
        (RECENCIA/empate de salience: salience=52 > 50 le da preferencia
        a la redirección cuando de verdad hay una estación alternativa
        disponible; si no la hay, esta regla simplemente no calza y la
        recarga local (salience=50) sigue siendo el respaldo)."""
        self.declare(Bloqueo(dron=d))
        self._decidir("redirigir", dron=d,
                       motivo=f"estación {e1} en zona {zd} sin cupos: redirigido a {e2}")

    @Rule(Paquete(id=MATCH.p, urgente=True),
          Mision(id=MATCH.m, paquete=MATCH.p),
          Dron(id=MATCH.d, estado="disponible"),
          EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m,
                            etiqueta=P(lambda e: e in ("bajo", "medio"))),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=50)
    def priorizar_paquetes_urgentes(self, d, m, p):
        self._decidir("asignar", dron=d, mision=m,
                       motivo=f"paquete {p} urgente (declarado o inferido por la ontología): se prioriza")

    @Rule(Paquete(id=MATCH.p, peso_kg=MATCH.peso),
          TEST(lambda peso: peso > 10),
          Mision(id=MATCH.m, paquete=MATCH.p),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=50)
    def rechazar_paquete_sobrepeso(self, m, peso):
        self._decidir("rechazar", mision=m,
                       motivo=f"peso {peso}kg supera la capacidad máxima de la flota (10kg)")

    # ==================================================================
    # NIVEL BAJO — OPTIMIZACIÓN Y REPORTES (salience=1 y 10)
    # ==================================================================

    @Rule(Dron(id=MATCH.d, zona=MATCH.zd, estado="disponible"),
          Mision(id=MATCH.m, origen=MATCH.o),
          EstacionCarga(id=MATCH.o, zona=MATCH.zd),
          EvaluacionRiesgo(dron=MATCH.d, mision=MATCH.m, etiqueta="bajo"),
          NOT(DecisionTomada(mision=MATCH.m)),
          salience=10)
    def preferir_dron_mas_cercano(self, d, m, zd, o):
        self._decidir("asignar", dron=d, mision=m,
                       motivo=f"dron {d} ya está en la zona de origen de la misión: se prioriza por cercanía")

    @Rule(Dron(id=MATCH.d, estado="disponible", bateria=MATCH.b),
          TEST(lambda b: b > 60),
          salience=10)
    def sugerir_balanceo_flota(self, d, b):
        """Reporte de optimización: drones que quedaron libres y con
        buena batería, útiles para balancear la flota en la próxima
        ronda de asignación."""
        ya_asignado = any(dec["dron"] == d and dec["accion"] == "asignar"
                           for dec in self.decisiones)
        if not ya_asignado:
            self.decisiones.append({
                "accion": "reporte", "dron": d, "mision": None,
                "motivo": f"dron {d} quedó disponible sin misión (batería {b}%): "
                          "candidato para balancear la flota"
            })

    @Rule(Mision(id=MATCH.m), DecisionTomada(mision=MATCH.m), salience=10)
    def registrar_mision_procesada(self, m):
        self.decisiones.append({
            "accion": "reporte", "dron": None, "mision": m,
            "motivo": f"misión {m} procesada por el sistema experto"
        })

    @Rule(NOT(Resumen()), salience=1)
    def generar_resumen_final(self):
        """Salience más baja del sistema: se ejecuta solo cuando ya no
        quedan activaciones pendientes de mayor prioridad, es decir, al
        final de la corrida."""
        self.declare(Resumen())
        total = sum(1 for d in self.decisiones if d["accion"] != "reporte")
        self.decisiones.append({
            "accion": "reporte", "dron": None, "mision": None,
            "motivo": f"resumen: {total} decisiones operativas generadas por el sistema experto"
        })


# ===========================================================================
# 3. FUNCIÓN DE CONTRATO (usada por main.py)
# ===========================================================================

def ejecutar(hechos):
    """Punto de entrada acordado con el grupo: recibe el diccionario de
    hechos (ya enriquecido por ontologia.py y difuso.py) y devuelve la
    lista de decisiones del sistema experto."""
    engine = SistemaExpertoDrones()
    engine.reset()
    engine.cargar_hechos(hechos)
    engine.run()
    return engine.decisiones


# ===========================================================================
# 4. DEMOSTRACIÓN INDEPENDIENTE (40 hechos + escenario de recencia)
# ===========================================================================
# Estos datos de ejemplo siguen el dataset acordado en el Paso 0 para que
# el módulo se pueda probar solo, sin depender todavía de ontologia.py ni
# difuso.py. Persona 4 los reemplazará por la lectura real de datos.json
# + las salidas reales de los otros dos módulos.

def _dataset_ejemplo():
    drones = [
        {"id": "D01", "tipo": "ligero", "capacidad_kg": 2, "bateria": 95, "estado": "disponible", "zona": "Z01"},
        {"id": "D02", "tipo": "ligero", "capacidad_kg": 2, "bateria": 30, "estado": "disponible", "zona": "Z03"},
        {"id": "D03", "tipo": "ligero", "capacidad_kg": 2, "bateria": 12, "estado": "en_vuelo", "zona": "Z05"},
        {"id": "D04", "tipo": "pesado", "capacidad_kg": 10, "bateria": 80, "estado": "disponible", "zona": "Z03"},
        {"id": "D05", "tipo": "pesado", "capacidad_kg": 10, "bateria": 45, "estado": "recargando", "zona": "Z02"},
        {"id": "D06", "tipo": "refrigerado", "capacidad_kg": 5, "bateria": 90, "estado": "disponible", "zona": "Z01"},
        {"id": "D07", "tipo": "refrigerado", "capacidad_kg": 5, "bateria": 20, "estado": "disponible", "zona": "Z05"},
        {"id": "D08", "tipo": "pesado", "capacidad_kg": 10, "bateria": 60, "estado": "mantenimiento", "zona": "Z02"},
    ]
    paquetes = [
        {"id": "P01", "tipo": "general", "peso_kg": 1.2, "destino": "Z02", "urgente": False},
        {"id": "P02", "tipo": "medico", "peso_kg": 0.8, "destino": "Z05", "urgente": True},
        {"id": "P03", "tipo": "fragil", "peso_kg": 1.5, "destino": "Z01", "urgente": False},
        {"id": "P04", "tipo": "general", "peso_kg": 7.5, "destino": "Z03", "urgente": False},
        {"id": "P05", "tipo": "express", "peso_kg": 1.0, "destino": "Z06", "urgente": True},
        {"id": "P06", "tipo": "medico", "peso_kg": 3.5, "destino": "Z04", "urgente": True},
        {"id": "P07", "tipo": "general", "peso_kg": 0.5, "destino": "Z05", "urgente": False},
        {"id": "P08", "tipo": "fragil", "peso_kg": 4.0, "destino": "Z02", "urgente": False},
        {"id": "P09", "tipo": "general", "peso_kg": 12.0, "destino": "Z01", "urgente": False},
        {"id": "P10", "tipo": "medico", "peso_kg": 1.1, "destino": "Z03", "urgente": True},
        {"id": "P11", "tipo": "general", "peso_kg": 2.0, "destino": "Z06", "urgente": False},
        {"id": "P12", "tipo": "express", "peso_kg": 6.0, "destino": "Z05", "urgente": True},
    ]
    misiones = [
        {"id": "M01", "paquete": "P02", "origen": "E01", "destino": "Z05", "distancia_km": 6.5},
        {"id": "M02", "paquete": "P04", "origen": "E02", "destino": "Z03", "distancia_km": 2.0},
        {"id": "M03", "paquete": "P06", "origen": "E01", "destino": "Z04", "distancia_km": 5.0},
        {"id": "M04", "paquete": "P10", "origen": "E04", "destino": "Z03", "distancia_km": 4.2},
        {"id": "M05", "paquete": "P09", "origen": "E02", "destino": "Z01", "distancia_km": 7.0},
        {"id": "M06", "paquete": "P12", "origen": "E04", "destino": "Z05", "distancia_km": 11.5},
    ]
    zonas = [
        {"id": "Z01", "nombre": "Laureles", "tipo": "residencial", "restringida": False},
        {"id": "Z02", "nombre": "El Poblado", "tipo": "residencial", "restringida": False},
        {"id": "Z03", "nombre": "Centro", "tipo": "comercial", "restringida": False},
        {"id": "Z04", "nombre": "Aeropuerto Olaya Herrera", "tipo": "restringida", "restringida": True},
        {"id": "Z05", "nombre": "Belén", "tipo": "residencial", "restringida": False},
        {"id": "Z06", "nombre": "Guayabal", "tipo": "comercial", "restringida": False},
    ]
    estaciones = [
        {"id": "E01", "zona": "Z01", "cupos": 3},
        {"id": "E02", "zona": "Z03", "cupos": 2},
        {"id": "E03", "zona": "Z05", "cupos": 0},
        {"id": "E04", "zona": "Z02", "cupos": 2},
    ]
    return drones, paquetes, misiones, zonas, estaciones


def _imprimir_decisiones(etiqueta, decisiones):
    print(f"\n--- {etiqueta} ({len(decisiones)} nuevas) ---")
    for d in decisiones:
        print(f"  [{d['accion']}] dron={d['dron']} mision={d['mision']} :: {d['motivo']}")


if __name__ == "__main__":
    drones, paquetes, misiones, zonas, estaciones = _dataset_ejemplo()

    engine = SistemaExpertoDrones()
    engine.reset()
    engine.cargar_hechos({
        "drones": drones, "paquetes": paquetes, "misiones": misiones,
        "zonas": zonas, "estaciones": estaciones,
        "climas": [
            {"id": "C01", "t": 1, "viento_kmh": 8.0, "condicion": "despejado"},
            {"id": "C02", "t": 2, "viento_kmh": 25.0, "condicion": "lluvia"},
        ],
        # M06 llega sin evaluación de riesgo todavía: queda pendiente
        # a propósito para el escenario de recencia (clima) de abajo.
        "riesgos": [
            {"dron": "D06", "mision": "M01", "valor": 25, "etiqueta": "bajo"},
            {"dron": "D04", "mision": "M02", "valor": 30, "etiqueta": "bajo"},
            {"dron": "D06", "mision": "M03", "valor": 40, "etiqueta": "medio"},
            {"dron": "D04", "mision": "M04", "valor": 65, "etiqueta": "alto"},
        ],
    })

    print("=== ESCENARIO 1: día normal (C01 despejado, C02 lluvia ya en el histórico) ===")
    prev = 0
    engine.run()
    _imprimir_decisiones("Corrida 1", engine.decisiones[prev:])
    prev = len(engine.decisiones)

    print("\n=== ESCENARIO 2: cambio de clima a mitad de ejecución -> tormenta (RECENCIA) ===")
    engine.declare(Clima(id="C03", t=3, viento_kmh=45.0, condicion="tormenta"))
    engine.declare(EvaluacionRiesgo(dron="D04", mision="M06", valor=55.0, etiqueta="medio"))
    engine.run()
    _imprimir_decisiones("Corrida 2 (tormenta)", engine.decisiones[prev:])
    prev = len(engine.decisiones)

    print("\n=== ESCENARIO 3: el clima mejora -> despejado de nuevo (RECENCIA) ===")
    engine.declare(Clima(id="C04", t=4, viento_kmh=15.0, condicion="despejado"))
    engine.run()
    _imprimir_decisiones("Corrida 3 (despejado)", engine.decisiones[prev:])

    print(f"\nClima vigente final: {engine.clima_vigente}")
    print(f"Total de hechos base declarados: "
          f"{len(drones)+len(paquetes)+len(misiones)+len(zonas)+len(estaciones)+4} "
          f"(6 zonas + 4 estaciones + 8 drones + 12 paquetes + 6 misiones + 4 climas = 40)")
