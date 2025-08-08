# app.py (versión corregida con simulación de respuesta en el mismo hilo)
from flask import Flask, request, Response
from twilio.twiml.messaging_response import MessagingResponse
from unidecode import unidecode
from agenda_google import crear_evento, buscar_espacio_disponible, get_service
from datetime import datetime, timedelta
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import threading
import logging
import dateparser
import pytz
import subprocess
import re
import time
import os

app = Flask(__name__)
logging.basicConfig(filename='nova.log', level=logging.INFO)

# Google Sheets
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", SCOPE)
client = gspread.authorize(CREDS)
sheet = None
try:
    sheet = client.open("CRM_WOLFAN").sheet1
except Exception as e:
    logging.error(f"❌ Error abriendo hoja de cálculo: {e}")

ESTADOS = [
    "inicio", "esperando_nombre", "seleccion_tipo_bot", "esperando_sector",
    "esperando_funcionalidades", "mostrar_planes", "preguntar_medio_contacto",
    "preguntar_fecha_hora", "confirmar_agenda", "recordatorio_permiso", "despedida"
]

usuarios = {}

def retroceder(estado_actual):
    indice = ESTADOS.index(estado_actual)
    return ESTADOS[max(0, indice - 1)]

def es_afirmativo(texto):
    t = unidecode(texto.lower().strip())
    afirmativos = ["si", "sí", "claro", "ok", "dale", "vale", "por supuesto", "si por favor", "sí por favor", "sip"]
    return any(p in t for p in afirmativos)

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        numero = request.values.get("From", "")
        mensaje = request.values.get("Body", "").strip()
        normalizado = unidecode(mensaje.lower())
        twiml = MessagingResponse()
        logging.info(f"[📩] Mensaje de {numero}: {mensaje}")
        print(f"[DEBUG] Mensaje recibido de {numero}: {mensaje}")

        # Inicializar usuario si no existe
        if numero not in usuarios:
            usuarios[numero] = {
                "estado": "esperando_nombre", "estado_anterior": None,
                "nombre": "", "tipo_bot": "", "sector": "", "funcionalidades": "",
                "medio_contacto": "", "agendado": "No", "guardado": False,
                "contador_no": 0, "enlace_evento": "", "fecha_cita": ""
            }
            twiml.message("Hola 🌟 Soy NOVA, tu asistente digital. ¿Cómo te llamas?")
            return Response(str(twiml), mimetype="application/xml")

        user = usuarios[numero]
        estado = user["estado"]
        respuesta = ""
        libre = True  # Variable definida por defecto

        # Comandos especiales
        if normalizado == "inicio":
            user.update({k: "" for k in ["nombre", "tipo_bot", "sector", "funcionalidades", "medio_contacto", "enlace_evento", "fecha_cita"]})
            user.update({"estado": "esperando_nombre", "estado_anterior": None, "agendado": "No", "guardado": False, "contador_no": 0})
            twiml.message("Reiniciando entrevista ✨ ¿Cómo te llamas?")
            return Response(str(twiml), mimetype="application/xml")
        elif normalizado == "atras":
            anterior = user.get("estado_anterior")
            if anterior:
                user["estado"], user["estado_anterior"] = anterior, estado
                estado = anterior
                respuesta = "🔙 Retrocediendo... continúa por favor."
                twiml.message(respuesta)
                return Response(str(twiml), mimetype="application/xml")

        # Procesamiento por estado
        if estado == "esperando_nombre":
            if mensaje:
                user["estado_anterior"] = estado
                user["nombre"] = mensaje.split()[0].capitalize()
                user["estado"] = "seleccion_tipo_bot"
                respuesta = (
                    f"Encantada, {user['nombre']} 😌\n"
                    "¿Qué tipo de bot te interesa?\n"
                    "1⃣ Asistente virtual\n"
                    "2⃣ Agendador de citas\n"
                    "3⃣ Tomador de pedidos\n"
                    "4⃣ Consulta de documentos\n"
                    "5⃣ Otro tipo\n"
                    "(Responde con un número o 'atrás')"
                )
            else:
                respuesta = "¿Me dices tu nombre, por favor?"

        elif estado == "seleccion_tipo_bot":
            opciones = {
                "1": "Asistente virtual", "2": "Agendador de citas",
                "3": "Tomador de pedidos", "4": "Consulta de documentos", "5": "Otro tipo"
            }
            if mensaje in opciones:
                user["estado_anterior"] = estado
                user["tipo_bot"] = opciones[mensaje]
                user["estado"] = "esperando_sector"
                respuesta = (
                    f"Perfecto {user['nombre']} 🤖. ¿En qué área o tipo de negocio lo usarás?\n"
                    "Ejemplos: consultorio médico, restaurante con delivery, tienda online, oficina contable, barbería..."
                )
            else:
                respuesta = "Elige un número del 1 al 5, o escribe 'atrás'."

        elif estado == "esperando_sector":
            if mensaje:
                user["estado_anterior"] = estado
                user["sector"] = mensaje
                user["estado"] = "esperando_funcionalidades"
                respuesta = (
                    "✨ ¿Qué funcionalidades deseas incluir?\n"
                    "(Ej: agendar citas, enviar PDFs, respuestas automáticas...)"
                )
            else:
                respuesta = "¿Podrías indicarme el área o rubro del bot?"

        elif estado == "esperando_funcionalidades":
            if mensaje:
                user["estado_anterior"] = estado
                user["funcionalidades"] = mensaje
                user["estado"] = "mostrar_planes"
                respuesta = (
                    "🎯 Gracias por compartir tu visión, ¡me encanta la dirección que estás tomando! 🧠✨\n"
                    "Con base en lo que me has contado, diseñamos diferentes opciones para adaptarnos a tus necesidades y presupuesto:\n\n"
                    "💡 *Plan Básico* – $60\n"
                    "Ideal si estás comenzando: respuestas automáticas personalizadas que atienden por ti, incluso cuando no estás conectado.\n\n"
                    "🚀 *Plan Intermedio* – $120\n"
                    "Perfecto para crecer: incluye agendamiento de citas, recordatorios automáticos y un CRM para gestionar a tus clientes.\n\n"
                    "🌐 *Plan Avanzado* – $180+\n"
                    "Tu copiloto digital completo: integraciones con Google Calendar, sistemas de pedidos, WooCommerce, automatizaciones inteligentes y mucho más, todo ajustado a tu negocio.\n\n"
                    "🤝 ¿Te gustaría agendar una llamada de 10 minutos para ayudarte a elegir el que más te conviene y mostrarte ejemplos reales?\n"
                    "Responde *sí* o *no*, sin compromiso. 😊"
                )
            else:
                respuesta = "¿Qué funcionalidades específicas quieres incluir?"

        elif estado == "mostrar_planes":
            if es_afirmativo(mensaje):
                user["estado_anterior"] = estado
                user["estado"] = "preguntar_medio_contacto"
                user["contador_no"] = 0
                respuesta = "¿Cómo prefieres que te contactemos? (visita, llamada o mensaje)"
            else:
                user["contador_no"] = user.get("contador_no", 0) + 1
                if user["contador_no"] == 1:
                    respuesta = (
                        "😌 Entiendo. Pero si gustas, puedo mostrarte ejemplos de bots en tu rubro.\n"
                        "¿Te gustaría? (sí/no)"
                    )
                elif user["contador_no"] == 2:
                    respuesta = (
                        "💬 Sin problema. Aun así, una llamada de 5 minutos podría aclararte muchas dudas sin compromiso.\n"
                        "¿Te animas? (sí/no)"
                    )
                elif user["contador_no"] >= 3:
                    user["estado_anterior"] = estado
                    user["estado"] = "despedida"
                    respuesta = (
                        "👌 Perfecto. Si en el futuro te animas, estaré por aquí para ayudarte.\n"
                        "¡Gracias por tu interés y éxitos con tu proyecto! 🌟"
                    )

        elif estado == "preguntar_medio_contacto":
            medios = ["visita", "llamada", "mensaje"]
            encontrado = next((m for m in medios if m in normalizado), None)
            if encontrado:
                user["estado_anterior"] = estado
                user["medio_contacto"] = encontrado
                user["estado"] = "preguntar_fecha_hora"
                respuesta = (
                    "Perfecto, ¿qué día y hora te va bien?\n"
                    "Ej: 'mañana a las 9am', 'jueves en la tarde', '16/07/2025 3pm'"
                )
            else:
                respuesta = "¿Prefieres visita, llamada o mensaje?"

        elif estado == "preguntar_fecha_hora":
            dt = dateparser.parse(
                mensaje,
                settings={"TIMEZONE": "America/Caracas", "RETURN_AS_TIMEZONE_AWARE": True}
            )
            ahora = datetime.now(pytz.timezone("America/Caracas"))
            if not dt or dt < ahora:
                respuesta = "La fecha no es válida o ya pasó 😬. Intenta con otra, por favor."
            else:
                inicio, fin = dt, dt + timedelta(minutes=30)
                try:
                    service = get_service()
                    ocupado = service.freebusy().query(body={
                        "timeMin": inicio.isoformat(),
                        "timeMax": fin.isoformat(),
                        "items": [{"id": "primary"}]
                    }).execute()
                    eventos = ocupado["calendars"]["primary"].get("busy", [])
                    if eventos:
                        libre = False
                    else:
                        libre = True
                except Exception as e:
                    print("⚠️ Error al consultar disponibilidad en Google Calendar:", e)
                    libre = True  # En caso de error asumimos disponible

                if libre:
                    # Agendar la cita
                    nombre = user.get("nombre", "Cliente")
                    tipo = user.get("tipo_bot", "bot")
                    funciones = user.get("funcionalidades", "funciones")
                    medio = user.get("medio_contacto", "llamada")
                    enlace = crear_evento(
                        nombre=nombre,
                        descripcion=f"{nombre} pidió contacto vía {medio} sobre: {tipo} — {funciones}",
                        fecha_str=dt.strftime("%Y-%m-%d"),
                        hora_str=dt.strftime("%H:%M"),
                        duracion_min=30,
                        recordatorio=True
                    )
                    user.update({
                        "estado_anterior": estado,
                        "estado": "recordatorio_permiso",
                        "agendado": "Sí",
                        "enlace_evento": enlace,
                        "fecha_cita": dt.strftime("%Y-%m-%d %H:%M"),
                        "guardado": False
                    })
                    respuesta = (
                        f"✅ ¡Listo! Tu {medio} está programado para el "
                        f"{dt.strftime('%A %d de %B a las %I:%M %p')}.\n"
                        "¿Quieres que te recuerde la cita un día antes y dos horas antes? (sí/no)"
                    )
                else:
                    # Buscar próxima hora libre que esté al menos a 1 hora de distancia de otras citas
                    sugerido = None
                    for i in range(1, 48):  # Buscar en las próximas 48 medias horas (~1 día)
                        nuevo_inicio = inicio + timedelta(minutes=30 * i)
                        nuevo_fin = nuevo_inicio + timedelta(minutes=30)

                        try:
                            ocupado_nuevo = service.freebusy().query(body={
                                "timeMin": (nuevo_inicio - timedelta(minutes=60)).isoformat(),
                                "timeMax": (nuevo_fin + timedelta(minutes=60)).isoformat(),
                                "items": [{"id": "primary"}]
                            }).execute()

                            eventos_nuevo = ocupado_nuevo["calendars"]["primary"].get("busy", [])
                            hay_conflicto = False
                            for evento in eventos_nuevo:
                                start = dateparser.parse(evento["start"])
                                end = dateparser.parse(evento["end"])
                                if (nuevo_inicio < end + timedelta(minutes=60)) and (nuevo_fin > start - timedelta(minutes=60)):
                                    hay_conflicto = True
                                    break

                            if not hay_conflicto:
                                sugerido = nuevo_inicio
                                break

                        except Exception as e:
                            logging.warning(f"⚠️ Error buscando sugerencia: {e}")
                            break

                    if sugerido:
                        respuesta = (
                            "😬 Ya tengo una cita cercana a esa hora.\n"
                            f"¿Te parece bien esta alternativa?: {sugerido.strftime('%A %d de %B a las %I:%M %p')} (responde con *sí* o intenta otra fecha)"
                        )
                    else:
                        respuesta = (
                            "🚫 No conseguí una hora libre cercana sin interferencias.\n"
                            "Por favor intenta con otra fecha y hora."
                        )

        elif estado == "recordatorio_permiso":
            if es_afirmativo(mensaje):
                respuesta = (
                    "✅ ¡Perfecto! La cita ha sido agendada y te enviaré recordatorios automáticos.\n"
                    "📌 Prepárate para nuestra reunión y ten tus ideas claras. Estoy aquí para ayudarte a llevar tu proyecto al siguiente nivel. 🚀"
                )
            else:
                respuesta = (
                    "✅ ¡Tu cita ha sido confirmada sin recordatorios automáticos!\n"
                    "Confío en que será una conversación valiosa para que des el siguiente paso en tu emprendimiento. 🌟"
                )
            user["estado_anterior"] = estado
            user["estado"] = "despedida"

        # Guardar en Google Sheets
        if sheet and not user["guardado"] and user["estado"] in ["mostrar_planes", "preguntar_medio_contacto", "recordatorio_permiso", "despedida"]:
            fila = [
                numero, user["nombre"], user["tipo_bot"],
                user["sector"], user["funcionalidades"], user["agendado"],
                user.get("fecha_cita", "")
            ]
            try:
                filas = sheet.get_all_values()
                if [numero, user["nombre"], user["tipo_bot"], user["sector"], user["funcionalidades"]] not in filas:
                    sheet.append_row(fila)
                    user["guardado"] = True
                    print(f"✅ Fila guardada en Google Sheets para {numero}")
            except Exception as e:
                logging.error(f"❌ Error al guardar en Sheets: {e}")

        # Mensaje por defecto si no hay respuesta
        if not respuesta:
            respuesta = "Lo siento, no entendí. Puedes escribir *inicio* para comenzar o *atrás* para retroceder."

        twiml.message(respuesta)
        return Response(str(twiml), mimetype="application/xml")

    except Exception as e:
        logging.exception("❌ Error en webhook:")
        return Response("Error interno", status=500)

def iniciar_tunel_localtunnel():
    print("⏳ Iniciando LocalTunnel...")
    npx_path = r"C:\Program Files\nodejs\npx.cmd"  # Asegúrate de que esta ruta sea correcta para tu sistema
    proceso = subprocess.Popen(
        [npx_path, "lt", "--port", "5000"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    for linea in proceso.stdout:
        print(linea.strip())
        match = re.search(r"https://[a-zA-Z0-9\-]+\.loca\.lt", linea)
        if match:
            print(f"\n✅ URL pública definitiva para Twilio: {match.group(0)}/webhook\n")
            break

if __name__ == "__main__":
    threading.Thread(target=iniciar_tunel_localtunnel, daemon=True).start()
    time.sleep(3)
    print("🚀 NOVA está lista para recibir mensajes...")
    app.run(port=5000, debug=False)