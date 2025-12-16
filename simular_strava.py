import requests
import time

# --- CONFIGURACIÓN DE ENTORNO (DEV) ---
# Extraída de tus logs recientes. Si reinicias ngrok, actualiza esto.
NGROK_URL = "https://overfaithfully-piquant-bryn.ngrok-free.dev"
WEBHOOK_ENDPOINT = f"{NGROK_URL}/webhooks/strava/"

# --- DATOS DE LA PRUEBA REAL ---
# Usamos el ID Real que realizaste hoy para ver datos verídicos en el sistema
TEST_ACTIVITY_ID = 16709148871  
TEST_ATHLETE_ID = 68831859      

def simular_webhook_strava():
    print(f"🚀 Iniciando simulación de Webhook Strava...")
    print(f"📡 Endpoint: {WEBHOOK_ENDPOINT}")
    
    # Payload oficial que envía Strava
    payload = {
        "aspect_type": "create",       # Importante: 'create' dispara la ingesta
        "event_time": int(time.time()),
        "object_id": TEST_ACTIVITY_ID, # Tu actividad real de hoy
        "object_type": "activity",
        "owner_id": TEST_ATHLETE_ID,   # Tu usuario real
        "subscription_id": 319552      # ID genérico de suscripción
    }
    
    print(f"📦 Payload preparado: Actividad {TEST_ACTIVITY_ID} para Atleta {TEST_ATHLETE_ID}")
    
    try:
        # Enviamos la petición POST simulando ser Strava
        response = requests.post(WEBHOOK_ENDPOINT, json=payload)
        
        # Análisis de respuesta
        if response.status_code == 200:
            print("\n✅ ¡ÉXITO! El servidor recibió la notificación (200 OK).")
            print("---------------------------------------------------------")
            print("👀 PASOS SIGUIENTES PARA VERIFICAR:")
            print("1. Mira la terminal de CELERY: Debería decir '✨ [NUEVO] Actividad no planificada...'")
            print("2. Ve al Admin de Django > Entrenamientos.")
            print("3. Busca la actividad 'Evening Trail Run' (o el nombre que tenga en Strava).")
            print("4. Verifica que 'Planificación' esté vacía y el estado sea '⚪ N/A'.")
        else:
            print(f"\n❌ ERROR: El servidor respondió con código {response.status_code}")
            print(f"Respuesta: {response.text}")
            
    except Exception as e:
        print(f"\n❌ FALLO DE CONEXIÓN: No se pudo contactar con Ngrok.")
        print(f"Detalle: {e}")
        print("Tip: Verifica que tu túnel Ngrok siga activo y la URL sea la correcta.")

if __name__ == "__main__":
    simular_webhook_strava()