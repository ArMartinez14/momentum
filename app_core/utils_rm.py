from typing import Optional


def calcular_rm_teorico(peso: float, reps: int, rir: Optional[int] = None) -> float:
    """
    Calcula el 1RM teórico usando el promedio de Epley y Brzycki.
    - peso: peso usado en la serie.
    - reps: repeticiones completadas.
    - rir: repeticiones en reserva (opcional). Si viene, se suman a reps.
    """
    reps_eq = reps + (rir or 0)
    if reps_eq <= 0:
        return 0.0
    if reps_eq >= 36:
        reps_eq = 35  # evita división por cero en Brzycki

    # Epley: 1RM = P * (1 + 0.0333 * R)
    rm_epley = peso * (1.0 + 0.0333 * reps_eq)

    # Brzycki: 1RM = (P * 36) / (37 - R)
    rm_brzycki = (peso * 36.0) / (37.0 - reps_eq)

    return (rm_epley + rm_brzycki) / 2.0


def calcular_peso_por_porcentaje(rm: float, porcentaje: float, redondeo: float = 2.5) -> float:
    """
    Devuelve el peso objetivo para un porcentaje dado del RM.
    - rm: 1RM teórico.
    - porcentaje: porcentaje deseado (ej: 80 -> 80%).
    - redondeo: múltiplo al que se aproxima (ej: 2.5 kg). Si es 0, no redondea.
    """
    if rm <= 0 or porcentaje <= 0:
        return 0.0

    peso_objetivo = rm * (porcentaje / 100.0)
    if redondeo and redondeo > 0:
        return round(peso_objetivo / redondeo) * redondeo
    return peso_objetivo
