import os
import time
import requests
from faker import Faker
from flask import Flask, request, jsonify

fake = Faker()
app = Flask(__name__)

# ============================================================
# CONFIGURACIÓN
# ============================================================

PROXY_HOST = os.environ.get("PROXY_HOST", "p.webshare.io:80")
PROXY_USER = os.environ.get("PROXY_USER")
PROXY_PASS = os.environ.get("PROXY_PASS")
PASSWORD = os.environ.get("TEST_PASSWORD")

if PROXY_USER and PROXY_PASS:
    PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}"

    proxies = {
        "http": PROXY_URL,
        "https": PROXY_URL
    }
else:
    PROXY_URL = None
    proxies = {}

session = requests.Session()
session.proxies.update(proxies)

REGISTER_URL = (
    "https://parkingpay-api-prod.azurewebsites.net/"
    "api/app/usuarios/registro"
)

LOGIN_URL = (
    "https://parkingpay-api-prod.azurewebsites.net/"
    "api/auth"
)

# ============================================================
# FUNCIONES AUXILIARES
# ============================================================

def response_info(response, elapsed=None):
    info = {
        "status_code": response.status_code,
        "url": response.url,
        "headers": dict(response.headers),
        "body": response.text[:2000]
    }

    if elapsed is not None:
        info["elapsed_seconds"] = round(elapsed, 3)

    return info


def mask_phone(phone):
    if not phone:
        return None

    if len(phone) <= 4:
        return "*" * len(phone)

    return phone[:3] + "*" * (len(phone) - 4) + phone[-1]


# ============================================================
# DIAGNÓSTICO PROXY
# ============================================================

@app.route("/diagnostico")
def diagnostico():

    result = {
        "proxy_config": {
            "configured": bool(PROXY_USER and PROXY_PASS),
            "host": PROXY_HOST,
            "url_masked": (
                f"http://{PROXY_USER}:****@{PROXY_HOST}"
                if PROXY_USER
                else None
            )
        },
        "tests": {}
    }

    # --------------------------------------------------------
    # SIN PROXY
    # --------------------------------------------------------

    try:
        start = time.perf_counter()

        r = requests.get(
            "https://httpbin.org/ip",
            timeout=10
        )

        elapsed = time.perf_counter() - start

        result["tests"]["sin_proxy"] = {
            "status": "ok",
            "status_code": r.status_code,
            "ip": r.json().get("origin"),
            "elapsed_seconds": round(elapsed, 3)
        }

    except Exception as e:

        result["tests"]["sin_proxy"] = {
            "status": "error",
            "error": str(e)
        }

    # --------------------------------------------------------
    # CON PROXY
    # --------------------------------------------------------

    try:
        start = time.perf_counter()

        r = session.get(
            "https://httpbin.org/ip",
            timeout=10
        )

        elapsed = time.perf_counter() - start

        result["tests"]["con_proxy"] = {
            "status": "ok",
            "status_code": r.status_code,
            "ip": r.json().get("origin"),
            "elapsed_seconds": round(elapsed, 3)
        }

    except Exception as e:

        result["tests"]["con_proxy"] = {
            "status": "error",
            "error": str(e)
        }

    # --------------------------------------------------------
    # COMPARACIÓN
    # --------------------------------------------------------

    ip_directa = (
        result["tests"]
        .get("sin_proxy", {})
        .get("ip")
    )

    ip_proxy = (
        result["tests"]
        .get("con_proxy", {})
        .get("ip")
    )

    result["proxy_funcionando"] = bool(
        ip_directa and
        ip_proxy and
        ip_directa != ip_proxy
    )

    return jsonify(result)


# ============================================================
# DIAGNÓSTICO PROFUNDO PROXY
# ============================================================

@app.route("/diagnostico/proxy-detalle")
def diagnostico_proxy_detalle():

    tests = {}

    # --------------------------------------------------------
    # HTTPBIN
    # --------------------------------------------------------

    try:

        start = time.perf_counter()

        r = session.get(
            "https://httpbin.org/get",
            timeout=15
        )

        elapsed = time.perf_counter() - start

        data = r.json()

        tests["httpbin"] = {
            "status_code": r.status_code,
            "origin": data.get("origin"),
            "headers_sent": data.get("headers", {}),
            "elapsed_seconds": round(elapsed, 3)
        }

    except Exception as e:

        tests["httpbin"] = {
            "status": "error",
            "error": str(e)
        }

    # --------------------------------------------------------
    # IPINFO
    # --------------------------------------------------------

    try:

        start = time.perf_counter()

        r = session.get(
            "https://ipinfo.io/json",
            timeout=15
        )

        elapsed = time.perf_counter() - start

        tests["ipinfo"] = {
            "status_code": r.status_code,
            "data": (
                r.json()
                if r.status_code == 200
                else r.text[:500]
            ),
            "elapsed_seconds": round(elapsed, 3)
        }

    except Exception as e:

        tests["ipinfo"] = {
            "status": "error",
            "error": str(e)
        }

    # --------------------------------------------------------
    # PARKINGPAY
    # --------------------------------------------------------

    try:

        start = time.perf_counter()

        r = session.head(
            "https://parkingpay-api-prod.azurewebsites.net",
            timeout=15
        )

        elapsed = time.perf_counter() - start

        tests["parkingpay"] = {
            "status_code": r.status_code,
            "headers": dict(r.headers),
            "elapsed_seconds": round(elapsed, 3)
        }

    except Exception as e:

        tests["parkingpay"] = {
            "status": "error",
            "error": str(e)
        }

    return jsonify({
        "proxy_configured": bool(PROXY_URL),
        "proxy_url": (
            f"http://{PROXY_USER}:****@{PROXY_HOST}"
            if PROXY_USER
            else None
        ),
        "tests": tests
    })


# ============================================================
# REGISTRO
# ============================================================

def registro_usuario():

    if not PASSWORD:
        raise RuntimeError(
            "TEST_PASSWORD no está configurada en Railway"
        )

    email = fake.email()

    telefono = "".join(
        str(fake.random_digit_not_null())
        for _ in range(10)
    )

    payload = {
        "correoElectronico": email,
        "nombre": fake.first_name(),
        "apellidos": fake.last_name(),
        "telefono": telefono,
        "contrasena": PASSWORD
    }

    headers = {
        "User-Agent": "Dart/3.8 (dart:io)",
        "Content-Type": "application/json; charset=utf-8"
    }

    start = time.perf_counter()

    response = session.post(
        REGISTER_URL,
        json=payload,
        headers=headers,
        timeout=20
    )

    elapsed = time.perf_counter() - start

    return {
        "response": response,
        "email": email,
        "telefono": telefono,
        "elapsed": elapsed
    }


# ============================================================
# LOGIN
# ============================================================

def login_usuario(email):

    if not PASSWORD:
        raise RuntimeError(
            "TEST_PASSWORD no está configurada en Railway"
        )

    payload = {
        "correoElectronico": email,
        "contrasena": PASSWORD
    }

    headers = {
        "User-Agent": "Dart/3.8 (dart:io)",
        "Content-Type": "application/json; charset=utf-8"
    }

    start = time.perf_counter()

    response = session.post(
        LOGIN_URL,
        json=payload,
        headers=headers,
        timeout=20
    )

    elapsed = time.perf_counter() - start

    token = None
    data = None

    try:

        data = response.json()

        token = (
            data.get("token")
            or data.get("accessToken")
            or (data.get("data") or {}).get("token")
        )

    except Exception:
        pass

    return {
        "response": response,
        "token": token,
        "data": data,
        "elapsed": elapsed
    }


# ============================================================
# DIAGNÓSTICO COMPLETO
# ============================================================

@app.route("/diagnostico/flujo", methods=["POST"])
def diagnostico_flujo():

    trace = []

    # --------------------------------------------------------
    # START
    # --------------------------------------------------------

    trace.append({
        "stage": "start",
        "status": "success"
    })

    # --------------------------------------------------------
    # REGISTER
    # --------------------------------------------------------

    try:

        trace.append({
            "stage": "register",
            "status": "started"
        })

        registro = registro_usuario()

        response = registro["response"]
        email = registro["email"]
        telefono = registro["telefono"]
        elapsed = registro["elapsed"]

        success = response.status_code in (200, 201)

        trace.append({
            "stage": "register",
            "status": "success" if success else "failed",
            "status_code": response.status_code,
            "elapsed_seconds": round(elapsed, 3),

            "generated_data": {
                "email": email,
                "telefono": mask_phone(telefono)
            },

            "response_body": response.text[:1000]
        })

        if not success:

            return jsonify({
                "status": "error",
                "failed_stage": "register",
                "trace": trace
            })

    except Exception as e:

        trace.append({
            "stage": "register",
            "status": "exception",
            "error": str(e)
        })

        return jsonify({
            "status": "error",
            "failed_stage": "register",
            "trace": trace
        })

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    try:

        trace.append({
            "stage": "login",
            "status": "started"
        })

        login = login_usuario(email)

        response = login["response"]
        token = login["token"]
        data = login["data"]
        elapsed = login["elapsed"]

        success = (
            response.status_code in (200, 201)
            and bool(token)
        )

        trace.append({
            "stage": "login",
            "status": "success" if success else "failed",
            "status_code": response.status_code,
            "elapsed_seconds": round(elapsed, 3),
            "token_present": bool(token),

            "response_keys": (
                list(data.keys())
                if isinstance(data, dict)
                else []
            ),

            "response_body": response.text[:1000]
        })

        if not success:

            return jsonify({
                "status": "error",
                "failed_stage": "login",
                "trace": trace
            })

    except Exception as e:

        trace.append({
            "stage": "login",
            "status": "exception",
            "error": str(e)
        })

        return jsonify({
            "status": "error",
            "failed_stage": "login",
            "trace": trace
        })

    # --------------------------------------------------------
    # COMPLETADO
    # --------------------------------------------------------

    trace.append({
        "stage": "completed",
        "status": "success",
        "message": (
            "Registro y autenticación completados correctamente."
        )
    })

    return jsonify({
        "status": "ok",
        "email": email,
        "trace": trace
    })


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({
        "status": "ok",
        "message": "API de diagnóstico activa",

        "endpoints": {
            "GET /diagnostico":
                "Comprobar proxy e IP",

            "GET /diagnostico/proxy-detalle":
                "Diagnóstico profundo del proxy",

            "POST /diagnostico/flujo":
                "Diagnóstico de registro y login"
        }
    })


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get("PORT", 5000)
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
