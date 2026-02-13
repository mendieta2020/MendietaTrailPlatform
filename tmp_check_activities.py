from django.apps import apps
from core.models import Alumno
a = Alumno.objects.get(id=17)

models = list(apps.get_app_config("core").get_models())
cand = [m for m in models if "activ" in m.__name__.lower()]

print("CANDIDATE_MODELS:", [m.__name__ for m in cand])

# Intenta encontrar un modelo con FK a alumno/user típico
for M in cand:
    fields = [f.name for f in M._meta.fields]
    # Heurística: campos comunes
    for fk in ["alumno", "athlete", "owner", "user"]:
        if fk in fields:
            try:
                qs = M.objects.filter(**{fk: a})
                print("MODEL", M.__name__, "FIELD", fk, "COUNT", qs.count())
                break
            except Exception as e:
                pass
