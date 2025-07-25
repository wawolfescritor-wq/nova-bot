import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

creds = ServiceAccountCredentials.from_json_keyfile_name("credentiales.json", scope)
client = gspread.authorize(creds)

# Cambia esto por el nombre de tu hoja
sheet = client.open("CRM_WOLFAN").sheet1

def guardar_datos(numero, mensaje, respuesta):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    fila = [timestamp, numero, mensaje, respuesta]
    sheet.append_row(fila)
