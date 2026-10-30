"""Las horas de carga que calcula la plantilla (hoja Actividades_Carga, columna W), para mostrarlas en el resumen."""

HORAS_POR_DIA = 8.0
DIAS_POR_MES = 23.83


def factor_mensual(frecuencia, dias_mes):
    """Veces al mes que representa una unidad de la frecuencia; None si la plantilla no la reconoce."""
    return {"Diaria": dias_mes, "Semanal": dias_mes / 5, "Quincenal": 2, "Mensual": 1, "Trimestral": 1 / 3,
            "Semestral": 1 / 6, "Anual": 1 / 12, "Eventual": 1 / 12}.get(frecuencia)


def horas_mes(tiempo_min, espera_min, eventos, frecuencia, retrabajo, dedicacion, dias_mes=DIAS_POR_MES):
    """Misma formula que la plantilla: (tiempo + espera) × eventos × veces al mes × (1 + retrabajo) × dedicacion / 60.

    Devuelve 0 cuando falta un dato obligatorio o la frecuencia no existe (igual que la plantilla, que lo oculta con IFERROR)."""
    factor = factor_mensual(frecuencia, dias_mes)
    if factor is None or tiempo_min is None or eventos is None or dedicacion is None:
        return 0.0
    return (tiempo_min + (espera_min or 0)) * eventos * factor * (1 + (retrabajo or 0)) * dedicacion / 60
