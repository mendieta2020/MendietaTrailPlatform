import os
import django

# Configuración de entorno
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()

from core.models import Alumno
from django.contrib.auth import get_user_model

print("🚀 Iniciando asignación de alumnos huérfanos...")

User = get_user_model()
# Buscamos al admin (Tú)
coach = User.objects.filter(is_superuser=True).first()

if coach:
    print(f"👨‍🏫 Entrenador Maestro encontrado: {coach.username}")
    
    # Buscamos alumnos sin dueño
    huerfanos = Alumno.objects.filter(entrenador__isnull=True)
    total = huerfanos.count()
    
    if total > 0:
        # Los adoptamos masivamente
        huerfanos.update(entrenador=coach)
        print(f"✅ ÉXITO: Se han asignado {total} alumnos a tu cuenta.")
    else:
        print("👍 Todo en orden: No hay alumnos huérfanos.")
else:
    print("❌ ERROR CRÍTICO: No existe un usuario Admin. Crea uno con 'createsuperuser'.")