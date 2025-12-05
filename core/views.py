from rest_framework import viewsets, permissions
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Alumno, Entrenamiento, Actividad
from .serializers import AlumnoSerializer, EntrenamientoSerializer
from allauth.socialaccount.models import SocialToken
from .services import sincronizar_actividades_strava

# --- API ---
class AlumnoViewSet(viewsets.ModelViewSet):
    queryset = Alumno.objects.all()
    serializer_class = AlumnoSerializer
    permission_classes = [permissions.IsAuthenticated]

class EntrenamientoViewSet(viewsets.ModelViewSet):
    queryset = Entrenamiento.objects.all()
    serializer_class = EntrenamientoSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        queryset = Entrenamiento.objects.all()
        alumno_id = self.request.query_params.get('alumno_id')
        if alumno_id: queryset = queryset.filter(alumno__id=alumno_id)
        fecha = self.request.query_params.get('fecha')
        if fecha: queryset = queryset.filter(fecha_asignada=fecha)
        return queryset.order_by('-fecha_asignada')

# --- DASHBOARD ---
@login_required
def dashboard_entrenador(request):
    
    # Lógica de Sincronización Manual
    if request.method == 'POST' and 'sync_strava' in request.POST:
        nuevas, actualizadas, estado = sincronizar_actividades_strava(request.user)
        
        if estado == "OK":
            if nuevas == 0 and actualizadas == 0:
                messages.info(request, "👍 Strava está al día.")
            else:
                messages.success(request, f"✅ Sincronización: {nuevas} nuevas, {actualizadas} actualizadas.")
        else:
            messages.error(request, f"⚠️ {estado}")
            
        return redirect('dashboard_principal') 

    # Carga de Datos
    entrenamientos = Entrenamiento.objects.all().select_related('alumno', 'plantilla_origen')
    eventos = []
    for entreno in entrenamientos:
        color = '#28a745' if entreno.completado else '#3788d8'
        if entreno.plantilla_origen and entreno.plantilla_origen.deporte == 'REST': color = '#6c757d'
        
        titulo = f"{entreno.alumno.nombre}: {entreno.titulo}" if entreno.alumno else entreno.titulo
        eventos.append({
            'title': titulo, 'start': entreno.fecha_asignada.strftime('%Y-%m-%d'),
            'color': color, 'url': f"/admin/core/entrenamiento/{entreno.id}/change/"
        })

    actividades_db = Actividad.objects.filter(usuario=request.user).order_by('-fecha_inicio')[:5]
    strava_connected = SocialToken.objects.filter(account__user=request.user, account__provider='strava').exists()

    context = {
        'eventos': eventos,             
        'activities': actividades_db,
        'strava_connected': strava_connected,
    }
    return render(request, 'core/dashboard.html', context)