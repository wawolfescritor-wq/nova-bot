# templates/respuestas.py

usuarios = {}

def generar_respuesta(mensaje, numero):
    if numero not in usuarios:
        usuarios[numero] = {"estado": "inicio"}

    estado = usuarios[numero]["estado"]

    # Flujo inicial
    if estado == "inicio":
        usuarios[numero]["estado"] = "menu_principal"
        return (
            "👋 ¡Hola! Soy el Asistente Virtual de Wolfan.\n"
            "Estoy aquí para ayudarte a automatizar tu negocio con bots por WhatsApp.\n\n"
            "¿Con qué te gustaría empezar?\n"
            "1️⃣ Ver soluciones disponibles\n"
            "2️⃣ Agendar una asesoría\n"
            "3️⃣ Tengo preguntas"
        )

    # Menú principal
    if estado == "menu_principal":
        if mensaje in ["1", "1️⃣", "ver soluciones"]:
            usuarios[numero]["estado"] = "ver_solutions"
            return (
                "Aquí tienes las soluciones disponibles:\n"
                "📁 1. Bot para contadores\n"
                "🏥 2. Bot para consultorios/peluquerías\n"
                "🍔 3. Bot para delivery/restaurantes\n"
                "🎯 4. Otro tipo de negocio\n\n"
                "Escribe el número del que te interesa."
            )
        elif mensaje in ["2", "2️⃣", "agendar"]:
            usuarios[numero]["estado"] = "agendar_nombre"
            return "Perfecto. ¿Cuál es tu nombre?"
        elif mensaje in ["3", "3️⃣", "preguntas"]:
            usuarios[numero]["estado"] = "preguntas_faq"
            return (
                "Preguntas frecuentes:\n"
                "💸 1. ¿Cuánto cuesta?\n"
                "⚙️ 2. ¿Qué necesito?\n"
                "📱 3. ¿Funciona solo con WhatsApp?\n"
                "📊 4. ¿Se conecta con Sheets?\n"
                "❔ 5. Otra pregunta"
            )
        else:
            return "Por favor elige una opción válida: 1, 2 o 3."

    # Ver soluciones
    if estado == "ver_solutions":
        soluciones = {
            "1": "Bot para contadores: permite recibir documentos, responder consultas frecuentes y más.",
            "2": "Bot para consultorios: agenda citas, envía recordatorios y encuestas de satisfacción.",
            "3": "Bot para restaurantes: muestra menú, toma pedidos y notifica al repartidor.",
            "4": "Cuéntame sobre tu negocio y veremos qué solución se adapta mejor."
        }
        if mensaje in soluciones:
            if mensaje == "4":
                usuarios[numero]["estado"] = "describir_negocio"
                return "Genial. Cuéntame brevemente sobre tu negocio y lo que deseas automatizar."
            else:
                return f"{soluciones[mensaje]}\n\n¿Quieres cotizar uno igual? Escribe: cotizar"
        else:
            return "Escribe 1, 2, 3 o 4 según la solución que te interesa."

    # Cotización directa
    if mensaje == "cotizar":
        usuarios[numero]["estado"] = "agendar_nombre"
        return "Perfecto, empecemos con tu nombre para avanzar."

    # Descripción libre de negocio
    if estado == "describir_negocio":
        usuarios[numero]["estado"] = "agendar_nombre"
        return "Gracias por la info. ¿Cuál es tu nombre para agendar una asesoría personalizada?"

    # Flujo de agendamiento
    if estado == "agendar_nombre":
        usuarios[numero]["nombre"] = mensaje
        usuarios[numero]["estado"] = "agendar_rubro"
        return "¿A qué te dedicas o qué tipo de negocio manejas?"

    if estado == "agendar_rubro":
        usuarios[numero]["rubro"] = mensaje
        usuarios[numero]["estado"] = "agendar_objetivo"
        return "¿Qué te gustaría automatizar con el bot?"

    if estado == "agendar_objetivo":
        usuarios[numero]["objetivo"] = mensaje
        usuarios[numero]["estado"] = "agendar_fecha"
        return "¿Día y hora preferida para la reunión?"

    if estado == "agendar_fecha":
        usuarios[numero]["fecha"] = mensaje
        usuarios[numero]["estado"] = "finalizado"
        return (
            f"¡Listo! Guardé tus datos:\n"
            f"👤 Nombre: {usuarios[numero]['nombre']}\n"
            f"📌 Rubro: {usuarios[numero]['rubro']}\n"
            f"🎯 Objetivo: {usuarios[numero]['objetivo']}\n"
            f"📅 Fecha: {usuarios[numero]['fecha']}\n\n"
            "Wolfan te escribirá pronto para la asesoría. ¿Quieres ver ejemplos de bots mientras tanto?"
        )

    # Preguntas frecuentes
    if estado == "preguntas_faq":
        faqs = {
            "1": "💸 Un bot base puede iniciar desde $50 USD. Con funciones avanzadas puede estar entre $100-$150.",
            "2": "⚙️ Solo necesitas una cuenta de WhatsApp y una idea de lo que deseas automatizar.",
            "3": "📱 Funciona principalmente con WhatsApp, pero puede adaptarse a otros canales como Telegram.",
            "4": "📊 Sí, se conecta con Google Sheets para guardar datos y generar reportes.",
            "5": "Escríbela aquí y la responderemos pronto."
        }
        if mensaje in faqs:
            return faqs[mensaje]
        else:
            return "Escribe el número de la pregunta que quieres consultar: 1 a 5."

    # Final
    if estado == "finalizado":
        return "¿Quieres hacer algo más? Escribe 'menú' para volver al inicio."

    if mensaje == "menú":
        usuarios[numero]["estado"] = "menu_principal"
        return "Volviendo al menú principal... ¿Qué deseas hacer?\n1️⃣ Ver soluciones\n2️⃣ Agendar\n3️⃣ Preguntas"

    return "No entendí eso. Puedes escribir 'menú' para volver al inicio."
