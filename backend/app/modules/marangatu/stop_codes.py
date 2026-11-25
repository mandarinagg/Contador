"""Motivos de detención del bot (spec §8), cada uno con su texto para la persona.

El texto dice qué pasó y qué hacer. La base guarda el código (CHECK de `marangatu.runs`, que
copia esta lista en la migración 0007); la interfaz muestra el texto.
"""

from enum import StrEnum


class StopCode(StrEnum):
    RULE_PENDING = "RULE_PENDING"
    PROFILE_MISMATCH = "PROFILE_MISMATCH"
    LEDGER_MISMATCH = "LEDGER_MISMATCH"
    DATA_INCOMPLETE = "DATA_INCOMPLETE"
    ALREADY_FILED = "ALREADY_FILED"
    READBACK_MISMATCH = "READBACK_MISMATCH"
    UNKNOWN_SCREEN = "UNKNOWN_SCREEN"
    LOGIN_FAILED = "LOGIN_FAILED"
    CAPTCHA = "CAPTCHA"
    NO_RECEIPT = "NO_RECEIPT"
    RECEIPT_MISMATCH = "RECEIPT_MISMATCH"
    TOO_LATE = "TOO_LATE"
    BOT_OFF = "BOT_OFF"
    NOT_ENABLED = "NOT_ENABLED"
    NO_CREDENTIALS = "NO_CREDENTIALS"
    BROWSER_ERROR = "BROWSER_ERROR"


STOP_TEXTS: dict[StopCode, str] = {
    StopCode.RULE_PENDING: (
        "Una regla tributaria que usa esta presentación todavía no está verificada. Verificala "
        "en Impuestos → Reglas y feriados y volvé a intentar."
    ),
    StopCode.PROFILE_MISMATCH: (
        "Los datos de Marangatu (RUC, DV, razón social u obligaciones) no coinciden con el perfil "
        "fiscal verificado. Revisá el perfil fiscal contra la constancia de RUC."
    ),
    StopCode.LEDGER_MISMATCH: (
        "Lo calculado no cuadra con la contabilidad. Revisá el control contra el mayor del mes "
        "antes de presentar."
    ),
    StopCode.DATA_INCOMPLETE: (
        "Faltan datos para preparar la presentación. Completalos en la herramienta y volvé a "
        "intentar."
    ),
    StopCode.ALREADY_FILED: (
        "Marangatu dice que este período ya está presentado. No se presentó nada; revisá la "
        "constancia y marcá la obligación como presentada."
    ),
    StopCode.READBACK_MISMATCH: (
        "Al leer de vuelta el formulario, una casilla o un total no coincide con lo calculado. "
        "No se presentó nada; revisá la diferencia con la guía paso a paso."
    ),
    StopCode.UNKNOWN_SCREEN: (
        "Marangatu mostró una pantalla, un texto o un mensaje que el bot no conoce (el portal "
        "puede haber cambiado). No se hizo nada más; mirá la captura y hacé un reconocimiento "
        "nuevo."
    ),
    StopCode.LOGIN_FAILED: (
        "Marangatu rechazó el ingreso. El bot no reintenta: revisá la clave guardada (o cambiala "
        "en Marangatu) y volvé a guardarla antes del próximo intento."
    ),
    StopCode.CAPTCHA: (
        "Marangatu pide un código captcha, que el bot no resuelve. Ingresá una vez a mano en "
        "Marangatu para que deje de pedirlo y después volvé a intentar."
    ),
    StopCode.NO_RECEIPT: (
        "Marangatu no mostró el acuse de la presentación: cuenta como no hecha. La próxima "
        "corrida revisa primero si quedó presentada; no la presentes a mano hasta saberlo."
    ),
    StopCode.RECEIPT_MISMATCH: (
        "La constancia no coincide con lo calculado. Hace falta una rectificativa: revisá la "
        "alerta en Impuestos."
    ),
    StopCode.TOO_LATE: (
        "Falta muy poco para el vencimiento y el bot ya no presenta solo. Presentala a mano con "
        "la guía paso a paso."
    ),
    StopCode.BOT_OFF: (
        "El bot está apagado. Encendelo en Impuestos → Marangatu si querés que trabaje."
    ),
    StopCode.NOT_ENABLED: (
        "Esta tarea no está habilitada para presentar sola. El bot no hizo el clic que presenta; "
        "si hace falta, presentala a mano con la guía paso a paso."
    ),
    StopCode.NO_CREDENTIALS: (
        "No hay clave de Marangatu guardada para el RUC de la empresa. Guardala en Impuestos → "
        "Marangatu."
    ),
    StopCode.BROWSER_ERROR: (
        "El navegador falló, tardó demasiado o se cerró antes de terminar. No se presentó nada; "
        "volvé a intentar y, si se repite, mirá el registro de la corrida."
    ),
}


def stop_text(code: str | None) -> str | None:
    if code is None:
        return None
    return STOP_TEXTS[StopCode(code)]
