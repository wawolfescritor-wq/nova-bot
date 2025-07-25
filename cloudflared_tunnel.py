import subprocess

def iniciar_cloudflared():
    try:
        print("\n⏳ Iniciando Cloudflared...\n")
        proc = subprocess.Popen(["cloudflared", "tunnel", "--url", "http://localhost:5000"])
        print("🚀 NOVA está lista para recibir mensajes por WhatsApp...")
    except Exception as e:
        print(f"❌ Error al iniciar Cloudflared: {e}")
