from django.apps import AppConfig

class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'
    verbose_name = "Núcleo de la Plataforma"

    def ready(self):
        # ESTA LÍNEA ES LA LLAVE DE ENCENDIDO 🔑
        import core.signals