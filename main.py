# app.py
# Chatbot NOVA con agendador inteligente conectado a Google Calendar y Cloudflared

from flask import Flask, request, Response
import requests
import subprocess
import threading
import time
from agenda_google import buscar_espacio_disponible, crear_evento, get_service
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime, timedelta
from twilio.twiml.messaging_response import MessagingResponse
from unidecode import unidecode
import dateparser
import pytz
import logging

app = Flask(__name__)
usuarios = {}

# --------------------------- CONFIGURACIÓN ---------------------------- #
SCOPE = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
CREDS = ServiceAccountCredentials.from_json_keyfile_name("credenciales.json", SCOPE)
client = gspread.authorize(CREDS)
sheet = client.open("CRM_WOLFAN").sheet1

# ID de tu número de Twilio
TWILIO_NUMBER = "whatsapp:+14155238886"

# --------------------------- UTILIDADES ------------------------------- #
def enviar_mensaje(numero, mensaje):
    requests.post(
        "https://api.ultramsg.com/instanceXXXX/messages/chat",
        json={"to": numero, "body": mensaje},
        headers={"Content-Type": "application/json"},
    )

def guardar_info(numero, campo, valor):
    if numero not in usuarios:
        usuarios[numero] = {"estado": "inicio"}
    usuarios[numero][campo] = valor

def actualizar_sheet(numero, campo, valor):
    try:
        registros = sheet.get_all_records()
        for i, fila in enumerate(registros, start=2):
            if fila["Teléfono"] == numero:
                col_index = sheet.row_values(1).index(campo) + 1
                sheet.update_cell(i, col_index, valor)
                break
    except Exception as e:
        print(f"Error actualizando sheet: {e}")

def es_afirmativo(mensaje):
    return unidecode(mensaje.lower()) in ["si", "sí", "claro", "ok", "vale", "yes"]

def retroceder(estado_actual):
    mapa = {
        "seleccion_tipo_bot": "esperando_nombre",
        "esperando_sector": "seleccion_tipo_bot",
        "esperando_funcionalidades": "esperando_sector",
        "mostrar_planes": "esperando_funcionalidades",
        "preguntar_medio_contacto": "mostrar_planes",
        "preguntar_fecha_hora": "preguntar_medio_contacto",
        "recordatorio_permiso": "preguntar_fecha_hora"
    }
    return mapa.get(estado_actual, "esperando_nombre")

# ------------------------ AGENDAR CON CONFIRMACIÓN ------------------- #
def proponer_horario(numero):
    inicio, fin = buscar_espacio_disponible()
    if not inicio:
        enviar_mensaje(numero, "😓 Lo siento, no encontré disponibilidad por ahora.")
        return

    fecha_str = inicio.strftime("%Y-%m-%d")
    hora_str = inicio.strftime("%H:%M")
    legible = inicio.strftime("%d/%m/%Y a las %I:%M %p")

    guardar_info(numero, "fecha_sugerida", fecha_str)
    guardar_info(numero, "hora_sugerida", hora_str)
    guardar_info(numero, "estado", "confirmar_cita")

    enviar_mensaje(numero, f"📅 Te propongo el siguiente horario:\n🗓️ {legible}\n¿Te parece bien? Responde *sí* o *no*.")

# ---------------------------- WEBHOOK --------------------------------- #
@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        numero = request.values.get("From", "")
        mensaje = request.values.get("Body", "").strip()
        normalizado = unidecode(mensaje.lower())
        twiml = MessagingResponse()

        logging.info(f"[📩] Mensaje de {numero}: {mensaje}")
        print(f"[DEBUG] Mensaje recibido de {numero}: {mensaje}")

        if numero not in usuarios:
            usuarios[numero] = {
                "estado": "esperando_nombre", "nombre": "", "tipo_bot": "", "sector": "",
                "funcionalidades": "", "medio_contacto": "", "agendado": "No", "guardado": False,
                "contador_no": 0, "enlace_evento": ""
            }
            twiml.message("Hola 🌟 Soy NOVA, tu asistente digital. ¿Cómo te llamas?")
            return Response(str(twiml), mimetype="application/xml")

        user = usuarios[numero]
        estado = user["estado"]

        if normalizado == "inicio":
            user.update({k: "" for k in ["nombre", "tipo_bot", "sector", "funcionalidades", "medio_contacto", "enlace_evento"]})
            user.update({"estado": "esperando_nombre", "agendado": "No", "guardado": False, "contador_no": 0})
            twiml.message("Reiniciando entrevista ✨ ¿Cómo te llamas?")
            return Response(str(twiml), mimetype="application/xml")

        if normalizado == "atras":
            user["estado"] = retroceder(estado)
            estado = user["estado"]
            mensaje = ""

        respuesta = ""

        if estado == "esperando_nombre":
            if mensaje:
                user["nombre"] = mensaje.split()[0].capitalize()
                user["estado"] = "seleccion_tipo_bot"
                respuesta = (
                    f"Encantada, {user['nombre']} 😌\n\n"
                    "¿Qué tipo de bot te interesa?\n"
                    "1⃣ Asistente virtual\n2⃣ Agendador de citas\n3⃣ Tomador de pedidos\n"
                    "4⃣ Consulta de documentos\n5⃣ Otro tipo\n\n(Responde con un número o 'atrás')"
                )
            else:
                respuesta = "¿Me dices tu nombre, por favor?"

        elif estado == "seleccion_tipo_bot":
            opciones = {
                "1": "Asistente virtual", "2": "Agendador de citas",
                "3": "Tomador de pedidos", "4": "Consulta de documentos", "5": "Otro tipo"
            }
            if mensaje in opciones:
                user["tipo_bot"] = opciones[mensaje]
                user["estado"] = "esperando_sector"
                respuesta = (
                    f"Perfecto {user['nombre']} 🤖. ¿En qué área o tipo de negocio lo usarás?\n\n"
                    "Ejemplos: consultorio médico, restaurante con delivery, tienda online, oficina contable, barbería..."
                )
            else:
                respuesta = "Elige un número del 1 al 5, o escribe 'atrás'."

        elif estado == "esperando_sector":
            if mensaje:
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
                user["funcionalidades"] = mensaje
                user["estado"] = "mostrar_planes"
                respuesta = (
                    "Gracias por compartir eso 🧠\n\n"
                    "Con base en tu idea, estos son los planes que tenemos para ti:\n\n"
                    "💡 *Básico* – $60: respuestas automáticas personalizadas para tu negocio.\n"
                    "🚀 *Intermedio* – $120: agenda + recordatorios + CRM de clientes.\n"
                    "🌐 *Avanzado* – $180+: integraciones (Google Calendar, WooCommerce) y automatizaciones a medida.\n\n"
                    "¿Te gustaría agendar una llamada para ayudarte a elegir el mejor? 📞😊 (responde *sí* o *no*)"
                )
            else:
                respuesta = "¿Qué funcionalidades específicas quieres incluir?"

        elif estado == "mostrar_planes":
            if es_afirmativo(mensaje):
                user["estado"] = "preguntar_medio_contacto"
                user["contador_no"] = 0
                respuesta = "¿Cómo prefieres que te contactemos? (visita, llamada o mensaje)"
            else:
                user["contador_no"] += 1
                if user["contador_no"] == 1:
                    respuesta = (
                        "😌 Entiendo. Pero si gustas, puedo mostrarte ejemplos de bots en tu rubro.\n¿Te gustaría? (sí/no)"
                    )
                elif user["contador_no"] == 2:
                    respuesta = (
                        "💬 Sin problema. Aun así, una llamada de 5 minutos podría aclararte muchas dudas sin compromiso. ¿Te animas? (sí/no)"
                    )
                elif user["contador_no"] >= 3:
                    user["estado"] = "despedida"
                    respuesta = (
                        "👌 Perfecto. Si en el futuro te animas, estaré por aquí para ayudarte.\n¡Gracias por tu interés y éxitos con tu proyecto! 🌟"
                    )

        elif estado == "preguntar_medio_contacto":
            medios = ["visita", "llamada", "mensaje"]
            encontrado = next((m for m in medios if m in normalizado), None)
            if encontrado:
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
            if not dt:
                respuesta = "No entendí la fecha 😅. Prueba con 'mañana a las 10am'."
            else:
                ahora = datetime.now(pytz.timezone("America/Caracas"))
                if dt < ahora:
                    respuesta = "La fecha ya pasó 😬. Indica otra por favor."
                else:
                    inicio, fin = dt, dt + timedelta(minutes=30)
                    try:
                        service = get_service()
                        ocupado = service.freebusy().query(body={
                            "timeMin": inicio.isoformat(),
                            "timeMax": fin.isoformat(),
                            "items": [{"id": "primary"}]
                        }).execute()
                        libre = not ocupado["calendars"]["primary"]["busy"]
                    except:
                        libre = True

                    if libre:
                        enlace = crear_evento(
                            nombre=user["nombre"],
                            descripcion=f"{user['nombre']} pidió contacto vía {user['medio_contacto']} sobre: {user['tipo_bot']} — {user['funcionalidades']}",
                            fecha_str=dt.strftime("%Y-%m-%d"),
                            hora_str=dt.strftime("%H:%M"),
                            duracion_min=30,
                            recordatorio=True
                        )
                        user["estado"] = "recordatorio_permiso"
                        user["agendado"] = "Sí"
                        user["enlace_evento"] = enlace
                        respuesta = (
                            f"✅ ¡Listo! Tu {user['medio_contacto']} está programado para el "
                            f"{dt.strftime('%A %d de %B a las %I:%M %p')}.\n\n"
                            f"¿Quieres que te recuerde la cita un día antes y dos horas antes? (sí/no)"
                        )
                    else:
                        respuesta = "😕 Ya hay una cita en ese horario. ¿Otra hora?"

        elif estado == "recordatorio_permiso":
            if es_afirmativo(mensaje):
                respuesta = (
                    "🚀 Genial. Activaré los recordatorios automáticos.\n"
                    f"¡Nos vemos pronto! Enlace de la cita: {user['enlace_evento']}"
                )
            else:
                respuesta = (
                    f"✅ Cita confirmada sin recordatorios.\n"
                    f"Gracias por confiar en nosotros, {user['nombre']}.\n🌟 Estás dando un paso brillante hacia la automatización de tu negocio.\n"
                    f"¡Nos vemos pronto! Enlace: {user['enlace_evento']}"
                )

            user["estado"] = "despedida"

            # Guardar fecha de la cita en Sheets (columna 7)
            if sheet and user.get("enlace_evento") and user.get("fecha_sugerida") and user.get("hora_sugerida"):
                try:
                    registros = sheet.get_all_records()
                    for i, fila in enumerate(registros, start=2):
                        telefono_fila = str(fila.get("Teléfono", "")).replace("whatsapp:", "").strip()
                        telefono_usuario = numero.replace("whatsapp:", "").strip()
                        if telefono_fila == telefono_usuario:
                            fecha_hora = f"{user['fecha_sugerida']} {user['hora_sugerida']}"
                            col_index = sheet.row_values(1).index("Fecha de la cita") + 1  # columna G
                            sheet.update_cell(i, col_index, fecha_hora)
                            print(f"✅ Fecha de cita guardada en fila {i}, columna {col_index}")
                            break
                    else:
                        print(f"⚠️ No se encontró fila para el número {numero}")
                except Exception as e:
                    print(f"❌ Error al guardar fecha de la cita: {e}")

        twiml.message(respuesta)
        return Response(str(twiml), mimetype="application/xml")

    except Exception as e:
        logging.exception("❌ Error en webhook:")
        return Response("Error interno", status=500)

# ------------------------ CLOUDflared ---------------------------------- #
def iniciar_tunel():
    print("\n⏳ Iniciando Cloudflared...")
    comando = ["cloudflared", "tunnel", "--url", "http://localhost:5000"]
    proceso = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    for linea in proceso.stdout:
        if "trycloudflare.com" in linea:
            for parte in linea.strip().split():
                if "https://" in parte:
                    url = parte + "/webhook"
                    print(f"\n🚀 NOVA está lista para recibir mensajes por WhatsApp...")
                    print(f"✅ URL pública activa: {url}")
                    print(f"📬 Pega esta URL en Twilio para recibir mensajes.")
                    break

if __name__ == '__main__':
    threading.Thread(target=iniciar_tunel).start()
    time.sleep(5)
    app.run(host="0.0.0.0", port=5000, debug=True)
