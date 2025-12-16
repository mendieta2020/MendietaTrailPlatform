from django.apps import AppConfig

class AnalyticsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'analytics'
    verbose_name = "📊 Centro de Rendimiento"

    def ready(self):
        import analytics.signals # <--- IMPORTANTE: Activa la escucha