"""
difuso.py - Módulo de lógica difusa de SkyRoute

Evalúa el RIESGO (0-100) de que un dron realice una misión a partir de:
    bateria (0-100 %), viento (0-60 km/h) y distancia (0-20 km).

Flujo: fuzzificación -> evaluación de 14 reglas (AND=mín, OR=máx, NOT=1-μ)
       -> agregación -> defuzzificación por centroide.

Uso:  from difuso import calcular_riesgo
      valor, etiqueta = calcular_riesgo(90, 8, 6.5)   # -> (18.2, 'bajo')
"""

import numpy as np
import skfuzzy as fuzz
from skfuzzy import control as ctrl


def crear_variables():
    """Crea las 3 variables de entrada y la de salida con sus funciones de pertenencia."""
    # --- Batería (%) ---
    bateria = ctrl.Antecedent(np.arange(0, 101, 1), 'bateria')
    bateria['baja']  = fuzz.trapmf(bateria.universe, [0, 0, 15, 35])
    bateria['media'] = fuzz.trimf(bateria.universe, [25, 50, 75])
    bateria['alta']  = fuzz.trapmf(bateria.universe, [60, 80, 100, 100])
 
    # --- Viento (km/h) ---
    viento = ctrl.Antecedent(np.arange(0, 61, 1), 'viento')
    viento['calmo']    = fuzz.gaussmf(viento.universe, 0, 8)
    viento['moderado'] = fuzz.gaussmf(viento.universe, 25, 7)
    viento['fuerte']   = fuzz.trapmf(viento.universe, [30, 45, 60, 60])
 
    # Modificadores aplicados sobre "fuerte"
    viento['muy_fuerte'] = viento['fuerte'].mf ** 2          # μ²
    viento['lig_fuerte'] = np.sqrt(viento['fuerte'].mf)      # √μ
 
    # --- Distancia (km) ---
    distancia = ctrl.Antecedent(np.arange(0, 21, 1), 'distancia')
    distancia['corta'] = fuzz.trimf(distancia.universe, [0, 0, 5])
    distancia['media'] = fuzz.trimf(distancia.universe, [3, 8, 13])
    distancia['larga'] = fuzz.trapmf(distancia.universe, [10, 15, 20, 20])
 
    # --- Riesgo (salida, 0-100) ---
    riesgo = ctrl.Consequent(np.arange(0, 101, 1), 'riesgo')
    riesgo['bajo']     = fuzz.trimf(riesgo.universe, [0, 0, 40])
    riesgo['medio']    = fuzz.trimf(riesgo.universe, [30, 50, 70])
    riesgo['alto']     = fuzz.trimf(riesgo.universe, [55, 70, 85])
    riesgo['muy_alto'] = fuzz.trapmf(riesgo.universe, [75, 90, 100, 100])
    riesgo.defuzzify_method = 'centroid'
 
    return bateria, viento, distancia, riesgo


def crear_reglas(bateria, viento, distancia, riesgo):
    """Define las 14 reglas difusas. R10-R14 se agregaron tras las pruebas para cubrir huecos."""
    # -- Reglas --
    return [
        # R1: batería alta & viento calmo & distancia corta → riesgo bajo
        ctrl.Rule(bateria['alta'] & viento['calmo'] & distancia['corta'], riesgo['bajo']),

        # R2: batería baja | viento muy fuerte → riesgo alto
        ctrl.Rule(bateria['baja'] | viento['muy_fuerte'], riesgo['alto']),

        # R3: batería media & distancia media → riesgo medio
        ctrl.Rule(bateria['media'] & distancia['media'], riesgo['medio']),

        # R4: ~batería baja & viento moderado → riesgo medio
        ctrl.Rule(~bateria['baja'] & viento['moderado'], riesgo['medio']),

        # R5: distancia larga & batería media → riesgo alto
        ctrl.Rule(distancia['larga'] & bateria['media'], riesgo['alto']),

        # R6: batería alta & distancia larga & ~viento fuerte → riesgo medio
        ctrl.Rule(bateria['alta'] & distancia['larga'] & ~viento['fuerte'], riesgo['medio']),

        # R7: viento ligeramente fuerte & batería alta → riesgo alto
        ctrl.Rule(viento['lig_fuerte'] & bateria['alta'], riesgo['alto']),

        # R8: batería alta & viento moderado & distancia corta → riesgo bajo
        ctrl.Rule(bateria['alta'] & viento['moderado'] & distancia['corta'], riesgo['bajo']),

        # R9: batería media & viento calmo & distancia corta → riesgo bajo
        ctrl.Rule(bateria['media'] & viento['calmo'] & distancia['corta'], riesgo['bajo']),

        # R10: batería alta & viento calmo & distancia media → riesgo bajo
        ctrl.Rule(bateria['alta'] & viento['calmo'] & distancia['media'], riesgo['bajo']),

        # R11: batería baja & viento fuerte → riesgo muy alto
        ctrl.Rule(bateria['baja'] & viento['fuerte'], riesgo['muy_alto']),

        # R12: batería baja & distancia larga → riesgo muy alto
        ctrl.Rule(bateria['baja'] & distancia['larga'], riesgo['muy_alto']),

        # R13: viento fuerte & (distancia larga | batería media) → riesgo muy alto
        ctrl.Rule(viento['fuerte'] & (distancia['larga'] | bateria['media']), riesgo['muy_alto']),

        # R14: batería baja & ~viento calmo → riesgo muy alto
        ctrl.Rule(bateria['baja'] & ~viento['calmo'], riesgo['muy_alto'])
    ]


# -- Crear el sistema difuso --
bateria, viento, distancia, riesgo = crear_variables()
reglas = crear_reglas(bateria, viento, distancia, riesgo)
sistema = ctrl.ControlSystem(reglas)
simulador = ctrl.ControlSystemSimulation(sistema)


# -- API del sistema difuso --
def etiqueta_riesgo(valor):
    """Convierte el riesgo numérico (0-100) en la etiqueta correspondiente."""
    if valor < 35:
        return "bajo"
    elif valor < 60:
        return "medio"
    elif valor < 80:
        return "alto"
    else:
        return "muy_alto"


def calcular_riesgo(bateria_pct, viento_kmh, distancia_km):
    """
    Calcula el riesgo de una misión con el sistema difuso.

    Entradas:
        bateria_pct  -> batería del dron en % (0 a 100)
        viento_kmh   -> velocidad del viento en km/h (0 a 60)
        distancia_km -> distancia de la misión en km (0 a 20)
    Salida:
        (valor, etiqueta), por ejemplo (67.5, "alto")
    """
    # Si llega un valor fuera del universo, lo ajustamos al límite para que el sistema no falle.
    bateria_pct  = float(np.clip(bateria_pct, 0, 100))
    viento_kmh   = float(np.clip(viento_kmh, 0, 60))
    distancia_km = float(np.clip(distancia_km, 0, 20))

    # Cargar las entradas y calcular
    simulador.input['bateria'] = bateria_pct
    simulador.input['viento'] = viento_kmh
    simulador.input['distancia'] = distancia_km

    try:
        simulador.compute()
        valor = round(float(simulador.output['riesgo']), 1)
    except Exception:
        # Si ninguna regla se activara, por seguridad asumimos el peor caso.
        valor = 100.0

    return valor, etiqueta_riesgo(valor)
