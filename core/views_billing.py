import json
import logging
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.http import HttpResponse

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def mercadopago_webhook(request):
    from integrations.mercadopago.webhook import process_subscription_webhook  # lazy — Law 4
    try:
        payload = json.loads(request.body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning("mp.webhook.invalid_json")
        return HttpResponse(status=400)

    process_subscription_webhook(payload)
    return HttpResponse(status=200)
