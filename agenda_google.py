# agenda_google.py

from google.oauth2 import service_account
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import pytz
from config import SERVICE_ACCOUNT_FILE, CALENDAR_ID, TIMEZONE
from log import logger

# Zona horaria
TZ = pytz.timezone(TIMEZONE)

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_service():
    try:
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        return build('calendar', 'v3', credentials=creds)
    except Exception as e:
        logger.error(f"❌ Error al iniciar servicio de Calendar: {e}")
        return None

service = get_service()

def buscar_espacio_disponible(duracion_min=30):
    if not service:
        return None, None

    ahora = datetime.now(TZ)
    ahora += timedelta(minutes=15 - ahora.minute % 15)
    ahora = ahora.replace(second=0, microsecond=0)

    if ahora.hour >= 18:
        ahora += timedelta(days=1)
        ahora = ahora.replace(hour=10, minute=0)

    fin_rango = ahora.replace(hour=18, minute=0)

    body = {
        "timeMin": ahora.isoformat(),
        "timeMax": fin_rango.isoformat(),
        "items": [{"id": CALENDAR_ID}]
    }

    try:
        respuesta = service.freebusy().query(body=body).execute()
        ocupados = respuesta["calendars"][CALENDAR_ID]["busy"]

        inicio = ahora
        while inicio + timedelta(minutes=duracion_min) <= fin_rango:
            fin = inicio + timedelta(minutes=duracion_min)

            libre = all(
                not (
                    inicio < TZ.localize(datetime.fromisoformat(o["end"]).replace(tzinfo=None)) and
                    fin > TZ.localize(datetime.fromisoformat(o["start"]).replace(tzinfo=None))
                )
                for o in ocupados
            )

            if libre:
                return inicio, fin

            inicio += timedelta(minutes=15)

    except Exception as e:
        logger.error(f"❌ Error buscando disponibilidad: {e}")

    return None, None

def crear_evento(nombre, descripcion, fecha_str, hora_str, duracion_min=30, recordatorio=False):
    if not service:
        return None

    try:
        fecha = datetime.strptime(f"{fecha_str} {hora_str}", "%Y-%m-%d %H:%M")
        inicio = TZ.localize(fecha)
        fin = inicio + timedelta(minutes=duracion_min)

        evento = {
            'summary': f'Reunión con {nombre}',
            'description': descripcion,
            'start': {'dateTime': inicio.isoformat(), 'timeZone': TIMEZONE},
            'end': {'dateTime': fin.isoformat(), 'timeZone': TIMEZONE},
            'reminders': {
                'useDefault': False,
                'overrides': [
                    {'method': 'popup', 'minutes': 24 * 60},
                    {'method': 'popup', 'minutes': 2 * 60}
                ]
            } if recordatorio else {'useDefault': False}
        }

        evento_creado = service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
        link = evento_creado.get('htmlLink')
        logger.info(f"✅ Evento creado: {link}")
        return link

    except Exception as e:
        logger.error(f"❌ Error creando evento: {e}")
        return None
