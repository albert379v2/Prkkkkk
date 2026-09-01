import os
import time
import requests
from faker import Faker
from flask import Flask, request, jsonify

app = Flask(__name__)
fake = Faker("es_MX")

# ============================================================
# CONFIGURACIÓN
# ============================================================

PROXY_HOST = os.getenv("PROXY_HOST", "")
PROXY_USER = os.getenv("PROXY_USER", "")
PROXY_PASS = os.getenv("PROXY_PASS", "")

TEST_PASSWORD = os.getenv("TEST_PASSWORD", "TestPassword123!")

# Tu dominio
EMAIL_DOMAIN = "mailgrid.shop"

REGISTER_URL = (
    "https://parkingpay-api-prod.azurewebsites.net"
    "/api/app/usuarios/registro"
)

LOGIN_URL = (
    "https://parkingpay-api-prod.azurewebsites.net"
    "/api/auth"
)

TIMEOUT = 30


# ============================================================
# PROXY
# ============================================================

def get_proxies():
    if not PROXY_HOST or not PROXY_USER or not PROXY_PASS:
        return None

    proxy = f"http://{PROXY_USER}:{PROXY_PASS}@{PROXY_HOST}"

    return {
        "http": proxy,
        "https": proxy
    }


PROXIES = get_proxies()


# ============================================================
# SESIÓN HTTP
# ============================================================

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/128.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json"
})


# ============================================================
# GENERACIÓN DE DATOS
# ============================================================

def generar_email():
    """
    Genera siempre un correo usando el dominio controlado
    mailgrid.shop.

    Ejemplo:
        juan.lopez48321@mailgrid.shop
    """

    nombre = fake.first_name().lower()
    apellido = fake.last_name().lower()
    numero = fake.random_int(min=1000, max=999999)

    return f"{nombre}.{apellido}{numero}@{EMAIL_DOMAIN}"


def generar_telefono():
    """
    Genera un teléfono de prueba con formato mexicano.
    """

    return "961" + str(
        fake.random_number(digits=7, fix_len=True)
    )


def generar_usuario():
    email = generar_email()

    return {
        "email": email,
        "telefono": generar_telefono()
    }


# ============================================================
# UTILIDADES
# ============================================================

def safe_response(response):
    """
    Devuelve información útil de la respuesta sin exponer
    tokens o credenciales.
    """

    try:
        body = response.text[:2000]
    except Exception:
        body = ""

    return {
        "status_code": response.status_code,
        "response_body": body
    }


# ============================================================
# REGISTRO
# ============================================================

def registro_usuario():
    datos = generar_usuario()

    payload = {
        "email": datos["email"],
        "telefono": datos["telefono"],
        "password": TEST_PASSWORD
    }

    inicio = time.time()

    try:
        response = session.post(
            REGISTER_URL,
            json=payload,
            proxies=PROXIES,
            timeout=TIMEOUT
        )

        elapsed = round(time.time() - inicio, 3)

        return {
            "ok": response.ok,
            "elapsed_seconds": elapsed,
            "generated_data": {
                "email": datos["email"],
                "telefono": (
                    datos["telefono"][:3]
                    + "******"
                    + datos["telefono"][-1:]
                )
            },
            **safe_response(response)
        }

    except requests.RequestException as e:

        return {
            "ok": False,
            "elapsed_seconds": round(time.time() - inicio, 3),
            "generated_data": {
                "email": datos["email"],
                "telefono": (
                    datos["telefono"][:3]
                    + "******"
                    + datos["telefono"][-1:]
                )
            },
            "error": str(e)
        }


# ============================================================
# LOGIN
# ============================================================

def login_usuario(email):
    payload = {
        "email": email,
        "password": TEST_PASSWORD
    }

    inicio = time.time()

    try:
        response = session.post(
            LOGIN_URL,
            json=payload,
            proxies=PROXIES,
            timeout=TIMEOUT
        )

        elapsed = round(time.time() - inicio, 3)

        resultado = {
            "ok": response.ok,
            "elapsed_seconds": elapsed,
            "status_code": response.status_code,
            "response_body": response.text[:2000]
        }

        # No devolvemos tokens al cliente.
        try:
            data = response.json()

            if isinstance(data, dict):
                resultado["token_detectado"] = bool(
                    data.get("token")
                    or data.get("access_token")
                    or data.get("accessToken")
                )

        except Exception:
            resultado["token_detectado"] = False

        return resultado

    except requests.RequestException as e:

        return {
            "ok": False,
            "elapsed_seconds": round(time.time() - inicio, 3),
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

    if not registro.get("ok"):

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

    email = registro["generated_data"]["email"]

    # --------------------------------------------------------
    # LOGIN
    # --------------------------------------------------------

    trace.append({
        "stage": "login",
        "status": "started"
    })

    login = login_usuario(email)

    if not login.get("ok"):

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
        "elapsed_seconds": login.get("elapsed_seconds"),
        "status_code": login.get("status_code"),
        "token_detectado": login.get("token_detectado")
    })

    # --------------------------------------------------------
    # RESULTADO
    # --------------------------------------------------------

    return jsonify({
        "status": "success",
        "message": "Registro y login completados correctamente",
        "trace": trace
    })


# ============================================================
# DIAGNÓSTICO DE PROXY
# ============================================================

@app.route("/diagnostico", methods=["GET"])
def diagnostico():

    resultado = {}

    try:
        inicio = time.time()

        response = session.get(
            "https://api.ipify.org?format=json",
            proxies=PROXIES,
            timeout=TIMEOUT
        )

        resultado["proxy"] = {
            "status": response.status_code,
            "elapsed_seconds": round(time.time() - inicio, 3),
            "response": response.text[:500]
        }

    except Exception as e:

        resultado["proxy"] = {
            "status": "error",
            "error": str(e)
        }

    return jsonify(resultado)


# ============================================================
# DETALLE DEL PROXY
# ============================================================

@app.route("/diagnostico/proxy-detalle", methods=["GET"])
def diagnostico_proxy_detalle():

    resultados = {}

    urls = {
        "ipify": "https://api.ipify.org?format=json",
        "httpbin": "https://httpbin.org/ip"
    }

    for nombre, url in urls.items():

        try:

            inicio = time.time()

            response = session.get(
                url,
                proxies=PROXIES,
                timeout=TIMEOUT
            )

            resultados[nombre] = {
                "status_code": response.status_code,
                "elapsed_seconds": round(
                    time.time() - inicio,
                    3
                ),
                "response": response.text[:1000]
            }

        except Exception as e:

            resultados[nombre] = {
                "status": "error",
                "error": str(e)
            }

    return jsonify(resultados)


# ============================================================
# HOME
# ============================================================

@app.route("/", methods=["GET"])
def home():

    return jsonify({
        "status": "online",
        "service": "ParkingPay diagnostic",
        "email_domain": EMAIL_DOMAIN,
        "endpoints": {
            "flujo": "POST /diagnostico/flujo",
            "proxy": "GET /diagnostico",
            "proxy_detalle": "GET /diagnostico/proxy-detalle"
        }
    })


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    port = int(os.getenv("PORT", 8080))

    app.run(
        host="0.0.0.0",
        port=port
    )
