import time
import os
import requests
from faker import Faker
from flask import Flask, jsonify

fake = Faker("es_MX")
app = Flask(__name__)

# ============================================================
# CONFIGURACIÓN
# ============================================================

PROXY_HOST = os.getenv("PROXY_HOST", "p.webshare.io:80")
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")

PASSWORD = os.getenv("TEST_PASSWORD", "TestPassword123!")

EMAIL_DOMAIN = "mailgrid.shop"

REGISTER_URL = (
    "https://parkingpay-api-prod.azurewebsites.net"
    "/api/app/usuarios/registro"
)

LOGIN_URL = (
    "https://parkingpay-api-prod.azurewebsites.net"
    "/api/auth"
)

# ============================================================
# PROXY
# ============================================================

if PROXY_USER and PROXY_PASS:
    PROXY_URL = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}"

    proxies = {
        "http": PROXY_URL,
        "https": PROXY_URL
    }
else:
    PROXY_URL = ""
    proxies = {}


# ============================================================
# SESIÓN
# ============================================================

c = requests.Session()

if proxies:
    c.proxies.update(proxies)


# ============================================================
# HEADERS
# ============================================================

API_HEADERS = {
    "User-Agent": "Dart/3.8 (dart:io)",
    "Content-Type": "application/json; charset=utf-8"
}


# ============================================================
# GENERAR CORREO
# ============================================================

def generar_email():
    """
    Genera un correo utilizando exclusivamente
    el dominio mailgrid.shop.
    """

    nombre = fake.first_name().lower()
    apellido = fake.last_name().lower()
    numero = fake.random_int(
        min=1000,
        max=999999
    )

    return f"{nombre}.{apellido}{numero}@{EMAIL_DOMAIN}"


# ============================================================
# GENERAR DATOS DE REGISTRO
# ============================================================

def generar_datos_usuario():

    nombre = fake.first_name()

    apellidos = fake.last_name()

    telefono = "".join(
        str(fake.random_digit_not_null())
        for _ in range(10)
    )

    email = generar_email()

    return {
        "correoElectronico": email,
        "nombre": nombre,
        "apellidos": apellidos,
        "telefono": telefono,
        "contrasena": PASSWORD
    }


# ============================================================
# REGISTRO
# ============================================================

def registro_usuario():

    payload = generar_datos_usuario()

    inicio = time.time()

    try:

        r = c.post(
            REGISTER_URL,
            json=payload,
            headers=API_HEADERS,
            timeout=20
        )

        elapsed = round(
            time.time() - inicio,
            3
        )

        return {
            "ok": r.status_code in (200, 201),
            "status_code": r.status_code,
            "elapsed_seconds": elapsed,
            "email": payload["correoElectronico"],
            "telefono": (
                payload["telefono"][:3]
                + "******"
                + payload["telefono"][-1:]
            ),
            "response_body": r.text[:2000]
        }

    except requests.RequestException as e:

        return {
            "ok": False,
            "status_code": None,
            "elapsed_seconds": round(
                time.time() - inicio,
                3
            ),
            "email": payload["correoElectronico"],
            "error": str(e)
        }


# ============================================================
# LOGIN
# ============================================================

def login_usuario(email):

    payload = {
        "correoElectronico": email,
        "contrasena": PASSWORD
    }

    inicio = time.time()

    try:

        r = c.post(
            LOGIN_URL,
            json=payload,
            headers=API_HEADERS,
            timeout=20
        )

        elapsed = round(
            time.time() - inicio,
            3
        )

        resultado = {
            "ok": r.status_code in (200, 201),
            "status_code": r.status_code,
            "elapsed_seconds": elapsed,
            "response_body": r.text[:2000],
            "token_detectado": False
        }

        # No mostramos el token.
        if r.status_code in (200, 201):

            try:

                data = r.json()

                token = (
                    data.get("token")
                    or data.get("accessToken")
                    or (data.get("data") or {}).get("token")
                )

                resultado["token_detectado"] = bool(token)

            except Exception:
                pass

        return resultado

    except requests.RequestException as e:

        return {
            "ok": False,
            "status_code": None,
            "elapsed_seconds": round(
                time.time() - inicio,
                3
            ),
            "error": str(e)
        }


# ============================================================
# DIAGNÓSTICO DEL FLUJO
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

    trace.append({
        "stage": "register",
        "status": "started"
    })

    registro = registro_usuario()

    if not registro["ok"]:

        trace.append({
            "stage": "register",
            "status": "failed",
            **registro
        })

        return jsonify({
            "status": "error",
            "failed_stage": "register",
            "trace": trace
        }), 400

    trace.append({
        "stage": "register",
        "status": "success",
        **registro
    })

    email = registro["email"]

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    trace.append({
        "stage": "login",
        "status": "started"
    })

    login = login_usuario(email)

    if not login["ok"]:

        trace.append({
            "stage": "login",
            "status": "failed",
            **login
        })

        return jsonify({
            "status": "error",
            "failed_stage": "login",
            "trace": trace
        }), 400

    trace.append({
        "stage": "login",
        "status": "success",
        "status_code": login["status_code"],
        "elapsed_seconds": login["elapsed_seconds"],
        "token_detectado": login["token_detectado"]
    })

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    return jsonify({
        "status": "success",
        "message": "Registro y login funcionan correctamente",
        "email_domain": EMAIL_DOMAIN,
        "trace": trace
    })


# ============================================================
# DIAGNÓSTICO DEL PROXY
# ============================================================

@app.route("/diagnostico")
def diagnostico():

    result = {
        "proxy_config": {
            "host": PROXY_HOST,
            "user": PROXY_USER,
            "configured": bool(PROXY_USER and PROXY_PASS)
        },
        "tests": {}
    }

    # --------------------------------------------------------
    # SIN PROXY
    # --------------------------------------------------------

    try:

        inicio = time.time()

        r = requests.get(
            "https://httpbin.org/ip",
            timeout=10
        )

        result["tests"]["sin_proxy"] = {
            "status": "ok",
            "status_code": r.status_code,
            "elapsed_seconds": round(
                time.time() - inicio,
                3
            ),
            "ip": r.json().get(
                "origin",
                "unknown"
            )
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

        inicio = time.time()

        r = c.get(
            "https://httpbin.org/ip",
            timeout=10
        )

        result["tests"]["con_proxy"] = {
            "status": "ok",
            "status_code": r.status_code,
            "elapsed_seconds": round(
                time.time() - inicio,
                3
            ),
            "ip": r.json().get(
                "origin",
                "unknown"
            )
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

    result["proxy_funcionando"] = (
        bool(ip_directa)
        and bool(ip_proxy)
        and ip_directa != ip_proxy
    )

    result["conclusion"] = (
        "Proxy funcionando"
        if result["proxy_funcionando"]
        else "No se pudo confirmar el proxy"
    )

    return jsonify(result)


# ============================================================
# DIAGNÓSTICO DETALLADO DEL PROXY
# ============================================================

@app.route("/diagnostico/proxy-detalle")
def diagnostico_proxy_detalle():

    tests = {}

    # --------------------------------------------------------
    # HTTPBIN
    # --------------------------------------------------------

    try:

        r = c.get(
            "https://httpbin.org/get",
            timeout=15
        )

        data = r.json()

        tests["httpbin"] = {
            "status_code": r.status_code,
            "origin": data.get("origin"),
            "headers": data.get("headers", {})
        }

    except Exception as e:

        tests["httpbin"] = {
            "error": str(e)
        }

    # --------------------------------------------------------
    # IPINFO
    # --------------------------------------------------------

    try:

        r = c.get(
            "https://ipinfo.io/json",
            timeout=15
        )

        tests["ipinfo"] = {
            "status_code": r.status_code,
            "data": (
                r.json()
                if r.status_code == 200
                else r.text[:500]
            )
        }

    except Exception as e:

        tests["ipinfo"] = {
            "error": str(e)
        }

    # --------------------------------------------------------
    # PARKINGPAY
    # --------------------------------------------------------

    try:

        inicio = time.time()

        r = c.head(
            "https://parkingpay-api-prod.azurewebsites.net",
            timeout=10
        )

        tests["parkingpay"] = {
            "status_code": r.status_code,
            "elapsed_seconds": round(
                time.time() - inicio,
                3
            ),
            "server": r.headers.get("Server"),
            "powered_by": r.headers.get("X-Powered-By")
        }

    except Exception as e:

        tests["parkingpay"] = {
            "error": str(e)
        }

    return jsonify({
        "proxy": {
            "host": PROXY_HOST,
            "user": PROXY_USER,
            "configured": bool(
                PROXY_USER and PROXY_PASS
            )
        },
        "tests": tests
    })


# ============================================================
# HOME
# ============================================================

@app.route("/")
def home():

    return jsonify({
        "status": "ok",
        "message": "API de diagnóstico activa",
        "email_domain": EMAIL_DOMAIN,
        "endpoints": {
            "GET /diagnostico":
                "Verificar proxy",
            "GET /diagnostico/proxy-detalle":
                "Diagnóstico detallado",
            "POST /diagnostico/flujo":
                "Probar registro y login"
        }
    })


# ============================================================
# START
# ============================================================

if __name__ == "__main__":

    port = int(
        os.environ.get(
            "PORT",
            5000
        )
    )

    app.run(
        host="0.0.0.0",
        port=port
    )
