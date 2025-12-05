import os
from celery import Celery

# 1. Establecemos el módulo de configuración de Django por defecto
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

# 2. Creamos la instancia de la aplicación Celery
# IMPORTANTE: Aquí definimos la variable 'app'. Por eso el comando debe terminar en ':app'
app = Celery('backend')

# 3. Le decimos que lea la configuración desde el archivo settings.py de Django
#    (Busca variables que empiecen con 'CELERY_')
app.config_from_object('django.conf:settings', namespace='CELERY')

# 4. Auto-descubrir tareas en todas las apps instaladas (core, etc.)
app.autodiscover_tasks()

@app.task(bind=True)
def debug_task(self):
    print(f'Request: {self.request!r}')