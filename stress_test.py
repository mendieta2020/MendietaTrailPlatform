import requests
import time
import threading

NGROK_URL = "https://overfaithfully-piquant-bryn.ngrok-free.dev" # TU URL ACTUAL
ENDPOINT = f"{NGROK_URL}/webhooks/strava/"

def atacar_servidor(i):
    payload = {
        "aspect_type": "create",
        "event_time": int(time.time()),
        "object_id": 1000000000 + i, # IDs diferentes
        "object_type": "activity",
        "owner_id": 68831859,
        "subscription_id": 319552
    }
    try:
        r = requests.post(ENDPOINT, json=payload)
        print(f"🚀 Disparo {i}: {r.status_code}")
    except Exception as e:
        print(f"❌ Fallo {i}: {e}")

# Lanzar 10 hilos simultáneos
threads = []
print("🔥 INICIANDO PRUEBA DE ESTRÉS...")
for i in range(10):
    t = threading.Thread(target=atacar_servidor, args=(i,))
    threads.append(t)
    t.start()

for t in threads:
    t.join()
print("✅ Ataque finalizado.")