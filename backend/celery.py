import os
from celery import Celery
from celery.schedules import crontab

# 1. Establecemos el módulo de configuración de Django por defecto
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# 2. Creamos la instancia de la aplicación Celery
# IMPORTANTE: Aquí definimos la variable 'app'. Por eso el comando debe terminar en ':app'
app = Celery('backend')

# 3. Le decimos que lea la configuración desde el archivo settings.py de Django
#    (Busca variables que empiecen con 'CELERY_')
app.config_from_object('django.conf:settings', namespace='CELERY')

# 3.1. Schedule diario (Celery Beat)
# Nota: requiere ejecutar celery beat en el entorno. Idempotente por diseño (UPSERT).
app.conf.beat_schedule = {
    "injury-risk-daily-recompute": {
        "task": "analytics.tasks.recompute_injury_risk_daily",
        "schedule": crontab(hour=2, minute=10),  # 02:10 UTC
        "args": (None,),
    },
}

# 4. Auto-descubrir tareas en todas las apps instaladas (core, etc.)
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')