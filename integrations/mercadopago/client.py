import os
import requests
import logging

logger = logging.getLogger(__name__)
MP_API_BASE = "https://api.mercadopago.com"


def _headers():
    token = os.environ.get("MERCADOPAGO_ACCESS_TOKEN", "")
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def mp_get(path):
    response = requests.get(f"{MP_API_BASE}{path}", headers=_headers(), timeout=10)
    response.raise_for_status()
    return response.json()


def mp_post(path, json=None):
    response = requests.post(f"{MP_API_BASE}{path}", json=json, headers=_headers(), timeout=10)
    response.raise_for_status()
    return response.json()


def mp_put(path, json=None):
    response = requests.put(f"{MP_API_BASE}{path}", json=json, headers=_headers(), timeout=10)
    response.raise_for_status()
    return response.json()
