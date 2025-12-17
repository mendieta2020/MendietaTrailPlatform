from django.contrib import admin
from django.utils.html import format_html
from .models import HistorialFitness

@admin.register(HistorialFitness)
class HistorialFitnessAdmin(admin.ModelAdmin):
    list_display = ('fecha', 'alumno', 'tss_diario', 'ver_metricas', 'ver_estado_forma')
    list_filter = ('alumno', 'fecha')
    date_hierarchy = 'fecha'
    
    def ver_metricas(self, obj):
        # FIX DE INGENIERÍA: 
        # Pre-formateamos los números a texto (f-string) ANTES de pasarlos a format_html.
        # Esto evita el conflicto de tipos 'SafeString' vs 'Float'.
        val_ctl = f"{obj.ctl:.1f}"
        val_atl = f"{obj.atl:.1f}"
        
        return format_html(
            '<span style="color:#2980b9;">Fitness: <b>{}</b></span> | '
            '<span style="color:#e74c3c;">Fatiga: <b>{}</b></span>',
            val_ctl, val_atl
        )
    ver_metricas.short_description = "Métricas (CTL | ATL)"

    def ver_estado_forma(self, obj):
        tsb = obj.tsb
        color = "green" if tsb > 0 else "red"
        estado = "Fresca" if tsb > 0 else "Cargada"
        
        # Rango óptimo de rendimiento
        if -10 <= tsb <= 10: 
            color = "#f39c12" # Naranja
            estado = "Óptima"
            
        val_tsb = f"{tsb:.1f}"
        
        return format_html(
            '<span style="color:{}; font-weight:bold;">{} ({})</span>',
            color, 
            val_tsb, 
            estado
        )
    ver_estado_forma.short_description = "Forma (TSB)"
