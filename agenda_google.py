# agenda_google.py (versión corregida)

from dotenv import load_dotenv
load_dotenv()
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from datetime import datetime, timedelta
import json
import pytz
import os
from config import SERVICE_ACCOUNT_FILE, CALENDAR_ID, TIMEZONE
from log import logger

# Zona horaria
TZ = pytz.timezone(TIMEZONE)

SCOPES = ['https://www.googleapis.com/auth/calendar']

def get_service():
    """
    Crea y devuelve el cliente de la API de Calendar.
    """
    credenciales_dict = json.loads(os.environ["GOOGLE_CREDS_JSON"])
    creds = Credentials.from_service_account_file("credenciales.json", scopes=SCOPES)
    return build('calendar', 'v3', credentials=creds)

def verificar_ocupado(service, inicio, fin):
    try:
        eventos = service.events().list(
            calendarId=CALENDAR_ID,
            timeMin=inicio.isoformat(),
            timeMax=fin.isoformat(),
            singleEvents=True,
            orderBy='startTime'
        ).execute()
        return len(eventos.get('items', [])) > 0
    except Exception as e:
        logger.error(f"❌ Error verificando ocupación: {e}")
        return True  # Por seguridad asumimos ocupado si falla

def buscar_espacio_disponible(service=None, inicio=None, duracion_min=30):
    """
    Ahora acepta un servicio y un inicio.
    Si no recibimos service o inicio, crea uno nuevo y usa la hora actual.
    """
    if service is None:
        service = get_service()
    if inicio is None:
        ahora = datetime.now(TZ)
        # redondear próximos 15 minutos
        minutos = (15 - ahora.minute % 15) % 15
        inicio = ahora + timedelta(minutes=minutos)
        inicio = inicio.replace(second=0, microsecond=0)
    else:
        inicio = inicio.astimezone(TZ)

    fin_rango = inicio.replace(hour=18, minute=0)
    if inicio.hour >= 18:
        # pasamos al día siguiente a las 10:00
        inicio = (inicio + timedelta(days=1)).replace(hour=10, minute=0)
        fin_rango = inicio.replace(hour=18, minute=0)

    body = {
        "timeMin": inicio.isoformat(),
        "timeMax": fin_rango.isoformat(),
        "items": [{"id": CALENDAR_ID}]
    }

    try:
        respuesta = service.freebusy().query(body=body).execute()
        ocupados = respuesta["calendars"][CALENDAR_ID]["busy"]

        slot = inicio
        while slot + timedelta(minutes=duracion_min) <= fin_rango:
            end_slot = slot + timedelta(minutes=duracion_min)
            libre = all(
                not (
                    slot < datetime.fromisoformat(o["end"]).astimezone(TZ) and
                    end_slot > datetime.fromisoformat(o["start"]).astimezone(TZ)
                )
                for o in ocupados
            )
            if libre:
                return slot, end_slot
            slot += timedelta(minutes=15)

    except Exception as e:
        logger.error(f"❌ Error buscando disponibilidad: {e}")

    return None, None

def crear_evento(nombre, descripcion, fecha_str, hora_str, duracion_min=30, recordatorio=False):
    """
    Crea el evento: obtiene internamente el servicio y no depende
    de una variable global inexistente.
    """
    service = get_service()

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

        creado = service.events().insert(calendarId=CALENDAR_ID, body=evento).execute()
        link = creado.get('htmlLink')
        logger.info(f"✅ Evento creado: {link}")
        return link

    except Exception as e:
        logger.error(f"❌ Error creando evento: {e}")
        return None
