import random
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.models import Alumno, Entrenamiento

class Command(BaseCommand):
    help = 'Genera datos de prueba para TODOS los alumnos existentes'

    def handle(self, *args, **kwargs):
        # 1. Obtener TODOS los alumnos de la base de datos
        alumnos = Alumno.objects.all()
        count = alumnos.count()
        
        self.stdout.write(f"👥 Se encontraron {count} alumnos en el sistema.")

        if count == 0:
            self.stdout.write(self.style.WARNING("⚠️ No hay alumnos. Crea algunos en el Panel Admin primero."))
            return

        # 2. Bucle: Repetir la lógica para cada persona encontrada
        for alumno in alumnos:
            self.stdout.write(f"👉 Generando datos para: {alumno.nombre} {alumno.apellido}...")

            # A. Limpieza: Borrar entrenamientos viejos de este alumno específico para evitar duplicados
            Entrenamiento.objects.filter(alumno=alumno).delete()

            # B. Generar Historia (Últimos 30 días)
            fecha_base = timezone.now().date()
            tipos = ['RUN', 'TRAIL', 'FUERZA', 'BICICLETA', 'DESCANSO']
            
            for i in range(30, 0, -1):
                fecha = fecha_base - timedelta(days=i)
                tipo_hoy = random.choice(tipos)
                
                # Si es descanso
                if tipo_hoy == 'DESCANSO':
                    Entrenamiento.objects.create(
                        alumno=alumno,
                        fecha_asignada=fecha,
                        tipo='DESCANSO',
                        titulo="Descanso / Recuperación",
                        completado=True,
                        rpe=1
                    )
                    continue

                # Entrenamiento activo
                dist_plan = random.randint(5, 20) # Random para que cada alumno tenga distancias distintas
                
                # Variación realista: Fernando quizás cumple al 100%, Messi quizás al 90% (Random)
                variacion = random.uniform(0.7, 1.2) 
                dist_real = round(dist_plan * variacion, 2)
                
                Entrenamiento.objects.create(
                    alumno=alumno,
                    fecha_asignada=fecha,
                    tipo=tipo_hoy,
                    titulo=f"Entrenamiento {tipo_hoy}",
                    
                    # Planificado
                    distancia_planificada_km=dist_plan,
                    desnivel_planificado_m=random.randint(50, 800),
                    tiempo_planificado_min=dist_plan * 6,
                    
                    # Real (Simulamos ejecución)
                    completado=True,
                    fecha_ejecucion=timezone.now() - timedelta(days=i),
                    distancia_real_km=dist_real,
                    desnivel_real_m=random.randint(50, 800),
                    tiempo_real_min=int(dist_real * random.uniform(5, 8)),
                    
                    # Feedback
                    rpe=random.randint(3, 10),
                    feedback_alumno="Entrenamiento cargado automáticamente."
                )

            # C. Generar Futuro (Próxima semana)
            for i in range(1, 8):
                fecha = fecha_base + timedelta(days=i)
                Entrenamiento.objects.create(
                    alumno=alumno,
                    fecha_asignada=fecha,
                    tipo='RUN',
                    titulo="Planificación Semanal",
                    distancia_planificada_km=12,
                    desnivel_planificado_m=150,
                    tiempo_planificado_min=70,
                    completado=False
                )
                
            self.stdout.write(self.style.SUCCESS(f"   ✅ {alumno.nombre} completado."))

        self.stdout.write(self.style.SUCCESS(f"🚀 ¡Proceso finalizado! Base de datos poblada para {count} alumnos."))