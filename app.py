from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
from pathlib import Path
import re
import secrets
import shutil
import socket
import subprocess
import sys
import threading
from typing import Any, Generator, NoReturn, TypedDict, TypeGuard, cast
import urllib.request

ROOT = Path(__file__).resolve().parent


def _bootstrap_and_reexec() -> NoReturn:
    """Prepara `.venv` automáticamente al ejecutar `py app.py` o `python app.py` en otro equipo."""
    venv_dir = ROOT / ".venv"
    venv_python = (
        venv_dir / "Scripts" / "python.exe"
        if os.name == "nt"
        else venv_dir / "bin" / "python"
    )
    venv_ready = False
    if venv_python.is_file():
        probe = subprocess.run(
            [str(venv_python), "-c", "import bcrypt, dotenv, flask, mysql.connector"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        venv_ready = probe.returncode == 0

    if not venv_ready:
        if venv_dir.exists():
            print("[Barrica] Actualizando entorno virtual (.venv) para este computador...")
            shutil.rmtree(venv_dir, ignore_errors=True)
        else:
            print("[Barrica] Creando entorno virtual (.venv) para este computador...")
        subprocess.check_call([sys.executable, "-m", "venv", str(venv_dir)])
        print("[Barrica] Instalando dependencias desde requirements.txt...")
        subprocess.check_call(
            [
                str(venv_python),
                "-m",
                "pip",
                "install",
                "--disable-pip-version-check",
                "-r",
                str(ROOT / "requirements.txt"),
            ]
        )

    env_file = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copyfile(env_example, env_file)

    child_env = {**os.environ, "BARRICA_BOOTSTRAPPED": "1"}
    try:
        raise SystemExit(
            subprocess.call(
                [str(venv_python), str(Path(__file__).resolve()), *sys.argv[1:]],
                env=child_env,
            )
        )
    except KeyboardInterrupt:
        raise SystemExit(0)


try:
    import bcrypt
    from dotenv import load_dotenv
    from flask import Flask, Response, current_app, jsonify, make_response, request, send_file
    import mysql.connector
    from mysql.connector import IntegrityError, pooling
except ModuleNotFoundError:
    if __name__ != "__main__" or os.getenv("BARRICA_BOOTSTRAPPED") == "1":
        raise
    _bootstrap_and_reexec()

load_dotenv(ROOT / ".env")
SESSION_COOKIE = "barrica_session"
SESSION_DURATION = timedelta(days=7)
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_WINDOW_MINUTES = 15
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
VALID_ROLES = ("administrador", "vendedor")


class PlanInfo(TypedDict):
    name: str
    usd: int


# --- Pagos de prueba -------------------------------------------------------
# Tasa de referencia fija para mostrar precios en pesos colombianos.
# Si la cambias, actualiza también data-cop en los planes de Untitled-1.html
# (la prueba test_html_prices_match_server_plans te avisa si no coinciden).
COP_PER_USD = 4000
PLANS: dict[str, PlanInfo] = {
    "basico": {"name": "Básico", "usd": 29},
    "pro": {"name": "Pro", "usd": 59},
    "multilocal": {"name": "Multi-local", "usd": 129},
}
CURRENCIES = ("USD", "COP")
DOCUMENT_TYPES = ("CC", "CE", "NIT")
CARD_BRANDS = ("Visa", "Mastercard", "American Express", "Tarjeta")
COLOMBIA_TIME = timezone(timedelta(hours=-5), "COT")  # Colombia no usa horario de verano

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False
LOCAL_ORIGIN_PATTERN = re.compile(
    r"^(?:http://(?:127\.0\.0\.1|localhost|192\.168\.\d{1,3}\.\d{1,3}|10\.\d{1,3}\.\d{1,3}\.\d{1,3}|172\.(?:1[6-9]|2\d|3[01])\.\d{1,3}\.\d{1,3})(?::\d+)?|null)$"
)

_DB_POOL: pooling.MySQLConnectionPool | None = None
_DB_POOL_KEY: tuple[Any, ...] | None = None
_DB_POOL_LOCK = threading.Lock()


@app.before_request
def _handle_local_preflight() -> Response | None:
    if (
        request.method == "OPTIONS"
        and os.getenv("VERCEL") != "1"
        and os.getenv("APP_ENV", "").lower() != "production"
        and LOCAL_ORIGIN_PATTERN.fullmatch(request.headers.get("Origin", ""))
    ):
        return make_response("", 204)
    return None


@app.after_request
def _add_local_cors_headers(response: Response) -> Response:
    origin = request.headers.get("Origin", "")
    if (
        os.getenv("VERCEL") != "1"
        and os.getenv("APP_ENV", "").lower() != "production"
        and LOCAL_ORIGIN_PATTERN.fullmatch(origin)
    ):
        response.headers["Access-Control-Allow-Origin"] = origin
        response.headers["Access-Control-Allow-Credentials"] = "true"
        response.headers["Access-Control-Allow-Headers"] = "Content-Type, Accept, Authorization"
        response.headers["Access-Control-Allow-Methods"] = "GET, POST, DELETE, OPTIONS"
        response.headers["Vary"] = "Origin"
    return response


class DatabaseConfigurationError(RuntimeError):
    """Raised when required database settings are missing or invalid."""


def _database_settings() -> dict[str, Any]:
    required = ("DB_HOST", "DB_USER", "DB_PASSWORD", "DB_NAME")
    missing = [key for key in required if not os.getenv(key)]
    if missing:
        raise DatabaseConfigurationError(
            f"Missing required database settings: {', '.join(missing)}"
        )

    try:
        port = int(os.getenv("DB_PORT", "3306"))
    except ValueError as error:
        raise DatabaseConfigurationError("DB_PORT must be a number.") from error
    if not 1 <= port <= 65535:
        raise DatabaseConfigurationError("DB_PORT is outside the valid range.")

    use_ssl = os.getenv("DB_SSL", "true").strip().lower() in {"1", "true", "yes"}
    settings: dict[str, Any] = {
        "host": os.environ["DB_HOST"],
        "port": port,
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "database": os.environ["DB_NAME"],
        "connection_timeout": 5,
    }
    if use_ssl:
        settings["ssl_ca"] = os.getenv("DB_SSL_CA", str(ROOT / "ca.pem"))
    else:
        settings["ssl_disabled"] = True
    return settings


def get_db_connection() -> Any:
    global _DB_POOL, _DB_POOL_KEY
    settings = _database_settings()
    key = tuple(sorted(settings.items()))
    with _DB_POOL_LOCK:
        if _DB_POOL is None or _DB_POOL_KEY != key:
            _DB_POOL = pooling.MySQLConnectionPool(
                pool_name="barrica_pool",
                pool_size=5,
                pool_reset_session=True,
                **settings,
            )
            _DB_POOL_KEY = key
        pool = _DB_POOL

    conn: Any = pool.get_connection()
    try:
        if not conn.is_connected():
            conn.ping(reconnect=True, attempts=2, delay=0)
    except mysql.connector.Error:
        try:
            conn.close()
        except mysql.connector.Error:
            pass
        return mysql.connector.connect(**settings)
    return conn


@contextmanager
def _database_connection() -> Generator[Any, None, None]:
    connection = get_db_connection()
    try:
        yield connection
    finally:
        connection.close()


def _json_error(message: str, status: int, field: str | None = None) -> Response:
    response = jsonify(error=message) if field is None else jsonify(error=message, field=field)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _json_success(payload: dict[str, Any], status: int = 200) -> Response:
    response = jsonify(payload)
    response.status_code = status
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Content-Type-Options"] = "nosniff"
    return response


def _request_data() -> tuple[dict[str, Any] | None, Response | None]:
    if not request.is_json:
        return None, _json_error("El contenido debe enviarse como JSON.", 415)
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return None, _json_error("El JSON enviado no es válido.", 400)
    return payload, None


def _normalize_email(value: object) -> str:
    return value.strip().lower() if isinstance(value, str) else ""


def _normalize_role(value: object, default: str = "vendedor") -> str | None:
    if value is None or value == "":
        return default
    if isinstance(value, str):
        cleaned = value.strip().lower()
        if cleaned in VALID_ROLES:
            return cleaned
    return None


def _is_valid_email(email: str) -> bool:
    return len(email) <= 254 and EMAIL_PATTERN.fullmatch(email) is not None


def _name_has_digits(name: str) -> bool:
    return any(char.isnumeric() for char in name)


def _is_valid_password(password: object) -> TypeGuard[str]:
    return (
        isinstance(password, str)
        and len(password) >= 12
        and len(password.encode("utf-8")) <= 72
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _extract_request_token() -> str:
    auth_header = request.headers.get("Authorization", "").strip()
    if auth_header.lower().startswith("bearer "):
        bearer_token = auth_header[7:].strip()
        if bearer_token:
            return bearer_token
    return request.cookies.get(SESSION_COOKIE, "")


def _create_session(connection: Any, user_id: int, role: str = "vendedor") -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + SESSION_DURATION
    safe_role = role if role in VALID_ROLES else "vendedor"
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO sessions (token_hash, user_id, role, expires_at) VALUES (%s, %s, %s, %s)",
            (_token_hash(token), user_id, safe_role, expires_at),
        )
        connection.commit()
    finally:
        cursor.close()
    return token


def _set_session_cookie(response: Response, token: str) -> Response:
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=int(SESSION_DURATION.total_seconds()),
        httponly=True,
        secure=os.getenv("VERCEL") == "1"
        or os.getenv("APP_ENV", "").lower() == "production",
        samesite="Strict",
        path="/",
    )
    return response


def _get_session_user(token: str) -> dict[str, Any] | None:
    if not token:
        return None

    with _database_connection() as connection:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(
                """
                SELECT users.id,
                       users.full_name AS name,
                       users.email,
                       COALESCE(sessions.role, users.role, 'vendedor') AS role,
                       COALESCE(users.role, 'vendedor') AS account_role
                FROM sessions
                INNER JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = %s
                  AND sessions.expires_at > UTC_TIMESTAMP()
                LIMIT 1
                """,
                (_token_hash(token),),
            )
            row = cast(dict[str, Any] | None, cursor.fetchone())
            if not row:
                return None
            role = str(row.get("role") or "vendedor").lower()
            account_role = str(row.get("account_role") or "vendedor").lower()
            if account_role != "administrador":
                role = "vendedor"
            elif role not in VALID_ROLES:
                role = account_role
            return {
                "id": int(row["id"]),
                "name": str(row["name"]),
                "email": str(row["email"]),
                "role": role,
            }
        finally:
            cursor.close()


def _require_bar_user(admin_only: bool = False) -> tuple[dict[str, Any] | None, Response | None]:
    token = _extract_request_token()
    if not token:
        return None, _json_error(
            "Inicia sesión como Administrador o Vendedor para continuar.", 401
        )
    try:
        user = _get_session_user(token)
    except DatabaseConfigurationError as error:
        current_app.logger.error("Auth check config error: %s", error)
        return None, _json_error("La conexión a la base de datos no está configurada.", 503)
    except mysql.connector.Error:
        current_app.logger.exception("Auth check database error")
        return None, _json_error("No se pudo verificar tu sesión en MySQL.", 503)

    if not user:
        return None, _json_error(
            "Tu sesión expiró o no es válida. Vuelve a iniciar sesión.", 401
        )
    if admin_only and user.get("role") != "administrador":
        return None, _json_error(
            "Esta función está reservada para el perfil de Administrador.", 403
        )
    return user, None


def _login_attempt_key(email: str) -> str:
    address = (
        request.headers.get("x-vercel-forwarded-for")
        or request.remote_addr
        or "unknown"
    ).split(",")[0].strip()
    return _token_hash(f"{email}:{address}")


def _is_login_blocked(connection: Any, key_hash: str) -> bool:
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            SELECT attempts,
                   window_started_at > DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s MINUTE)
            FROM auth_attempts
            WHERE key_hash = %s
            """,
            (LOGIN_WINDOW_MINUTES, key_hash),
        )
        row = cast(tuple[Any, ...] | None, cursor.fetchone())
        return bool(row and row[1] and int(row[0]) >= LOGIN_ATTEMPT_LIMIT)
    finally:
        cursor.close()


def _record_login_failure(connection: Any, key_hash: str) -> None:
    cursor = connection.cursor()
    try:
        cursor.execute(
            """
            INSERT INTO auth_attempts
                (key_hash, attempts, window_started_at, last_attempt_at)
            VALUES (%s, 1, UTC_TIMESTAMP(), UTC_TIMESTAMP())
            ON DUPLICATE KEY UPDATE
                attempts = IF(
                    window_started_at <= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s MINUTE),
                    1,
                    attempts + 1
                ),
                window_started_at = IF(
                    window_started_at <= DATE_SUB(UTC_TIMESTAMP(), INTERVAL %s MINUTE),
                    UTC_TIMESTAMP(),
                    window_started_at
                ),
                last_attempt_at = UTC_TIMESTAMP()
            """,
            (key_hash, LOGIN_WINDOW_MINUTES, LOGIN_WINDOW_MINUTES),
        )
        connection.commit()
    finally:
        cursor.close()


def _only_ascii_digits(value: object, minimum: int, maximum: int) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and value.isascii()
        and value.isdigit()
        and minimum <= len(value) <= maximum
    )


def _person_name_error(value: object) -> str | None:
    """Devuelve el motivo por el que un nombre no es válido, o None si lo es."""
    if not isinstance(value, str) or not 2 <= len(value.strip()) <= 120:
        return "Escribe un nombre válido."
    if _name_has_digits(value):
        return "El nombre no puede contener números."
    return None


@app.get("/")
def home():
    return send_file(ROOT / "Untitled-1.html")


@app.get("/app")
@app.get("/app/")
@app.get("/bar_app")
@app.get("/bar_app/")
@app.get("/bar_app.html")
def standalone_bar_app():
    return send_file(ROOT / "bar_app.html")


@app.get("/downloads/BarricaDesktop.exe")
def download_desktop_exe():
    exe_path = ROOT / "downloads" / "BarricaDesktop.exe"
    if not exe_path.is_file():
        return _json_error("El ejecutable de escritorio no está disponible.", 404)
    return send_file(
        exe_path,
        as_attachment=True,
        download_name="BarricaDesktop.exe",
        mimetype="application/vnd.microsoft.portable-executable",
    )


@app.get("/downloads/Barrica-Movil.html")
def download_mobile_app():
    return send_file(
        ROOT / "bar_app.html",
        as_attachment=True,
        download_name="Barrica-Movil.html",
        mimetype="text/html",
    )


@app.get("/icon.svg")
def app_icon() -> Response:
    svg = (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 512 512">'
        '<rect width="512" height="512" rx="96" fill="#0E1B17"/>'
        '<circle cx="256" cy="256" r="148" fill="none" stroke="#D9A441" stroke-width="36"/>'
        '<circle cx="256" cy="256" r="92" fill="none" stroke="#EFE6D2" stroke-width="14"/>'
        "</svg>"
    )
    return Response(svg, mimetype="image/svg+xml")


@app.get("/manifest.webmanifest")
@app.get("/app/manifest.webmanifest")
def web_manifest() -> Response:
    manifest = {
        "name": "Barrica · Sistema Operativo de Bar",
        "short_name": "Barrica",
        "description": "Aplicación operativa independiente: mesas, pedidos, inventario y administración.",
        "start_url": "/app",
        "scope": "/app",
        "display": "standalone",
        "background_color": "#0E1B17",
        "theme_color": "#0E1B17",
        "lang": "es",
        "icons": [
            {
                "src": "/icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable",
            }
        ],
    }
    response = jsonify(manifest)
    response.mimetype = "application/manifest+json"
    return response


@app.get("/sw.js")
@app.get("/app/sw.js")
def service_worker() -> Response:
    script = (
        "self.addEventListener('install', () => self.skipWaiting());\n"
        "self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));\n"
        "self.addEventListener('fetch', () => {});\n"
    )
    response = Response(script, mimetype="application/javascript")
    response.headers["Cache-Control"] = "no-cache"
    return response


@app.post("/api/payments/simulate")
def simulate_payment():
    payload, error_response = _request_data()
    if error_response is not None or payload is None:
        return error_response or _json_error("El JSON enviado no es válido.", 400)

    plan_id = payload.get("plan")
    plan = PLANS.get(plan_id) if isinstance(plan_id, str) else None
    if plan is None:
        return _json_error("Elige un plan válido.", 400, "plan")

    currency = payload.get("currency")
    if currency not in CURRENCIES:
        return _json_error("Elige dólares (USD) o pesos colombianos (COP).", 400, "currency")

    payer_name = payload.get("payer_name")
    message = _person_name_error(payer_name)
    if message or not isinstance(payer_name, str):
        return _json_error(message or "Escribe un nombre válido.", 400, "payer_name")

    email = _normalize_email(payload.get("email"))
    if not _is_valid_email(email):
        return _json_error("Escribe un correo válido.", 400, "email")

    document_type = payload.get("document_type")
    if document_type not in DOCUMENT_TYPES:
        return _json_error("Elige un tipo de documento válido.", 400, "document_type")

    document_number = payload.get("document_number")
    if not _only_ascii_digits(document_number, 6, 12):
        return _json_error(
            "El documento debe tener entre 6 y 12 números, sin letras ni símbolos.",
            400,
            "document_number",
        )

    phone = payload.get("phone")
    if not _only_ascii_digits(phone, 7, 15):
        return _json_error(
            "El teléfono debe tener entre 7 y 15 números, sin letras ni símbolos.",
            400,
            "phone",
        )

    card_holder = payload.get("card_holder")
    message = _person_name_error(card_holder)
    if message or not isinstance(card_holder, str):
        return _json_error(message or "Escribe un nombre válido.", 400, "card_holder")

    card_last4 = payload.get("card_last4")
    if not _only_ascii_digits(card_last4, 4, 4):
        return _json_error("Los últimos cuatro números de la tarjeta no son válidos.", 400, "card_last4")

    card_brand = payload.get("card_brand")
    if card_brand not in CARD_BRANDS:
        card_brand = "Tarjeta"

    now = datetime.now(COLOMBIA_TIME)
    amounts = {"USD": plan["usd"], "COP": plan["usd"] * COP_PER_USD}
    receipt = {
        "number": f"SIM-{now:%Y%m%d}-{secrets.token_hex(3).upper()}",
        "issued_at": now.isoformat(timespec="seconds"),
        "simulated": True,
        "plan": {"id": plan_id, "name": plan["name"]},
        "period": "1 mes",
        "currency": currency,
        "amount": amounts[currency],
        "amounts": amounts,
        "payer": {
            "name": payer_name.strip(),
            "email": email,
            "document_type": document_type,
            "document_number": document_number,
            "phone": phone,
        },
        "card": {
            "holder": card_holder.strip(),
            "brand": card_brand,
            "last4": card_last4,
        },
    }
    return _json_success({"receipt": receipt}, 201)


@app.get("/api/auth/session")
def session():
    try:
        user = _get_session_user(_extract_request_token())
    except DatabaseConfigurationError as error:
        current_app.logger.error("Session configuration error: %s", error)
        return _json_error("La conexión a la base de datos no está configurada.", 503)
    except mysql.connector.Error:
        current_app.logger.exception("Session database request failed")
        return _json_error("No se pudo comprobar la sesión. Inténtalo más tarde.", 503)

    if user is not None:
        user = {"name": user["name"], "email": user["email"], "role": user["role"]}
    return _json_success({"user": user})


@app.post("/api/auth/register")
def register():
    payload, error_response = _request_data()
    if error_response is not None or payload is None:
        return error_response or _json_error("El JSON enviado no es válido.", 400)

    name = payload.get("name", "").strip() if isinstance(payload.get("name"), str) else ""
    email = _normalize_email(payload.get("email"))
    password = payload.get("password")
    role = _normalize_role(payload.get("role"), default="vendedor")
    if role is None:
        return _json_error("Elige un perfil válido: Administrador o Vendedor.", 400)
    if _name_has_digits(name):
        return _json_error("El nombre no puede contener números.", 400)
    if not name or len(name) > 120 or not _is_valid_email(email) or not _is_valid_password(password):
        return _json_error(
            "Revisa tu nombre, correo y contraseña. La contraseña debe tener "
            "al menos 12 caracteres y máximo 72 bytes UTF-8.",
            400,
        )

    try:
        password_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12))
        with _database_connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "INSERT INTO users (full_name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                    (name, email, password_hash.decode("ascii"), role),
                )
                user_id = cursor.lastrowid
                connection.commit()
            except IntegrityError as error:
                connection.rollback()
                if error.errno == 1062:
                    return _json_error("Ya existe una cuenta con ese correo.", 409)
                raise
            finally:
                cursor.close()
            if user_id is None:
                raise RuntimeError("No se obtuvo el ID del usuario creado.")
            token = _create_session(connection, int(user_id), role)
    except DatabaseConfigurationError as error:
        current_app.logger.error("Registration configuration error: %s", error)
        return _json_error("La conexión a la base de datos no está configurada.", 503)
    except mysql.connector.Error:
        current_app.logger.exception("Registration database request failed")
        return _json_error("No se pudo crear la cuenta. Inténtalo más tarde.", 503)

    response = _json_success(
        {"user": {"name": name, "email": email, "role": role}, "token": token},
        201,
    )
    return _set_session_cookie(response, token)


@app.post("/api/auth/login")
def login():
    payload, error_response = _request_data()
    if error_response is not None or payload is None:
        return error_response or _json_error("El JSON enviado no es válido.", 400)

    email = _normalize_email(payload.get("email"))
    password = payload.get("password")
    raw_role = payload.get("role")
    requested_role = _normalize_role(raw_role, default="") if raw_role not in (None, "") else ""
    if requested_role is None:
        return _json_error("Elige un perfil válido: Administrador o Vendedor.", 400)
    if not _is_valid_email(email) or not _is_valid_password(password):
        return _json_error(
            "Escribe un correo válido y una contraseña de al menos 12 caracteres.",
            400,
        )

    try:
        with _database_connection() as connection:
            attempt_key = _login_attempt_key(email)
            if _is_login_blocked(connection, attempt_key):
                return _json_error(
                    "Demasiados intentos. Espera 15 minutos antes de volver a intentarlo.",
                    429,
                )

            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(
                    """
                    SELECT id, full_name AS name, email, password_hash, role
                    FROM users WHERE email = %s LIMIT 1
                    """,
                    (email,),
                )
                user = cast(dict[str, Any] | None, cursor.fetchone())
            finally:
                cursor.close()

            if not user or not bcrypt.checkpw(
                password.encode("utf-8"),
                str(user["password_hash"]).encode("ascii"),
            ):
                _record_login_failure(connection, attempt_key)
                return _json_error("Correo o contraseña incorrectos.", 401)

            account_role = str(user.get("role") or "vendedor").lower()
            if account_role not in VALID_ROLES:
                account_role = "vendedor"

            if requested_role == "administrador" and account_role != "administrador":
                return _json_error(
                    "Esta cuenta pertenece al perfil de Vendedor y no tiene permisos de Administrador. "
                    "Selecciona «Vendedor» para iniciar sesión.",
                    403,
                )

            session_role = requested_role if requested_role in VALID_ROLES else account_role

            cursor = connection.cursor()
            try:
                cursor.execute("DELETE FROM auth_attempts WHERE key_hash = %s", (attempt_key,))
                connection.commit()
            finally:
                cursor.close()
            token = _create_session(connection, int(user["id"]), session_role)
    except DatabaseConfigurationError as error:
        current_app.logger.error("Login configuration error: %s", error)
        return _json_error("La conexión a la base de datos no está configurada.", 503)
    except mysql.connector.Error:
        current_app.logger.exception("Login database request failed")
        return _json_error("No se pudo iniciar sesión. Inténtalo más tarde.", 503)

    response = _json_success(
        {
            "user": {
                "name": user["name"],
                "email": user["email"],
                "role": session_role,
            },
            "token": token,
        }
    )
    return _set_session_cookie(response, token)


@app.post("/api/auth/logout")
def logout():
    token = _extract_request_token()
    try:
        if token:
            with _database_connection() as connection:
                cursor = connection.cursor()
                try:
                    cursor.execute(
                        "DELETE FROM sessions WHERE token_hash = %s",
                        (_token_hash(token),),
                    )
                    connection.commit()
                finally:
                    cursor.close()
    except DatabaseConfigurationError as error:
        current_app.logger.error("Logout configuration error: %s", error)
        return _json_error("La conexión a la base de datos no está configurada.", 503)
    except mysql.connector.Error:
        current_app.logger.exception("Logout database request failed")
        return _json_error("No se pudo cerrar sesión. Inténtalo más tarde.", 503)

    response = make_response(_json_success({"ok": True}))
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        httponly=True,
        secure=os.getenv("VERCEL") == "1"
        or os.getenv("APP_ENV", "").lower() == "production",
        samesite="Strict",
    )
    return response


# --- API Operativa del Bar (App Móvil y App de Escritorio .exe) ------------

DEFAULT_BAR_TABLES = [
    (1, "Mesa 1 · Salón", 4),
    (2, "Mesa 2 · Salón", 4),
    (3, "Mesa 3 · Ventana", 2),
    (4, "Mesa 4 · Terraza", 6),
    (5, "Mesa 5 · Terraza", 4),
    (6, "Mesa 6 · VIP", 8),
    (7, "Barra 1 · Principal", 2),
    (8, "Barra 2 · Principal", 2),
]

DEFAULT_PRODUCTS = [
    ("Negroni", "Cócteles", 28000, 24, 5),
    ("Old Fashioned", "Cócteles", 30000, 20, 5),
    ("Margarita Artesanal", "Cócteles", 26000, 18, 5),
    ("Cerveza Club Colombia", "Cervezas", 9000, 48, 12),
    ("Cerveza Artesanal IPA", "Cervezas", 15000, 30, 8),
    ("Botella Ginebra Tanqueray", "Licores", 165000, 3, 4),
    ("Botella Aguardiente Antioqueño", "Licores", 85000, 10, 4),
    ("Tabla de Quesos y Madurados", "Comida", 42000, 12, 3),
]

_BAR_TABLES_INITIALIZED = False


def _ensure_bar_tables_and_seed(connection: Any) -> None:
    global _BAR_TABLES_INITIALIZED
    if _BAR_TABLES_INITIALIZED:
        return

    cursor = connection.cursor()
    try:
        schema_statements = [
            """
            CREATE TABLE IF NOT EXISTS products (
                id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                name VARCHAR(120) NOT NULL,
                category VARCHAR(60) NOT NULL DEFAULT 'Licores',
                price_cop INT UNSIGNED NOT NULL,
                stock INT NOT NULL DEFAULT 0,
                min_stock INT NOT NULL DEFAULT 5,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS bar_tables (
                id INT UNSIGNED NOT NULL AUTO_INCREMENT,
                table_number INT UNSIGNED NOT NULL,
                label VARCHAR(60) NOT NULL,
                capacity SMALLINT UNSIGNED NOT NULL DEFAULT 4,
                status VARCHAR(20) NOT NULL DEFAULT 'libre',
                PRIMARY KEY (id),
                UNIQUE KEY uq_bar_tables_number (table_number)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS table_orders (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                table_id INT UNSIGNED NOT NULL,
                product_id INT UNSIGNED NULL,
                product_name VARCHAR(120) NOT NULL,
                quantity INT UNSIGNED NOT NULL DEFAULT 1,
                unit_price_cop INT UNSIGNED NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                KEY idx_table_orders_table_id (table_id),
                CONSTRAINT fk_table_orders_table
                    FOREIGN KEY (table_id) REFERENCES bar_tables (id) ON DELETE CASCADE,
                CONSTRAINT fk_table_orders_product
                    FOREIGN KEY (product_id) REFERENCES products (id) ON DELETE SET NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
            """
            CREATE TABLE IF NOT EXISTS sales (
                id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
                table_label VARCHAR(60) NOT NULL,
                items_summary VARCHAR(500) NOT NULL,
                total_cop INT UNSIGNED NOT NULL,
                payment_method VARCHAR(40) NOT NULL DEFAULT 'Efectivo',
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (id),
                KEY idx_sales_created_at (created_at)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
            """,
        ]
        for stmt in schema_statements:
            cursor.execute(stmt)

        cursor.execute("SHOW COLUMNS FROM users LIKE 'role'")
        if cursor.fetchone() is None:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'vendedor' AFTER password_hash"
            )
            cursor.execute(
                "UPDATE users SET role = 'administrador' WHERE id = 1 OR email = 'admin@gmail.com'"
            )

        cursor.execute("SHOW COLUMNS FROM sessions LIKE 'role'")
        if cursor.fetchone() is None:
            cursor.execute(
                "ALTER TABLE sessions ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'vendedor' AFTER user_id"
            )

        cursor.execute("SELECT COUNT(*) FROM bar_tables")
        tables_count_row = cast(tuple[Any, ...] | None, cursor.fetchone())
        if tables_count_row and int(tables_count_row[0]) == 0:
            cursor.executemany(
                "INSERT INTO bar_tables (table_number, label, capacity, status) VALUES (%s, %s, %s, 'libre')",
                DEFAULT_BAR_TABLES,
            )

        cursor.execute("SELECT COUNT(*) FROM products")
        products_count_row = cast(tuple[Any, ...] | None, cursor.fetchone())
        if products_count_row and int(products_count_row[0]) == 0:
            cursor.executemany(
                "INSERT INTO products (name, category, price_cop, stock, min_stock) VALUES (%s, %s, %s, %s, %s)",
                DEFAULT_PRODUCTS,
            )

        connection.commit()
        _BAR_TABLES_INITIALIZED = True
    finally:
        cursor.close()


def _fmt_dt(value: Any) -> str:
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return str(value) if value is not None else ""


@app.get("/api/bar/dashboard")
def bar_dashboard() -> Response:
    current_user, auth_err = _require_bar_user(admin_only=False)
    if auth_err is not None or current_user is None:
        return auth_err or _json_error("No autorizado.", 401)

    is_admin = current_user.get("role") == "administrador"

    try:
        with _database_connection() as connection:
            _ensure_bar_tables_and_seed(connection)
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(
                    "SELECT id, table_number, label, capacity, status FROM bar_tables ORDER BY table_number ASC"
                )
                tables = cast(list[dict[str, Any]], cursor.fetchall())

                cursor.execute(
                    """
                    SELECT id, table_id, product_id, product_name, quantity, unit_price_cop
                    FROM table_orders
                    ORDER BY id ASC
                    """
                )
                orders = cast(list[dict[str, Any]], cursor.fetchall())

                orders_by_table: dict[int, list[dict[str, Any]]] = {}
                for order in orders:
                    tid = int(order["table_id"])
                    subtotal = int(order["quantity"]) * int(order["unit_price_cop"])
                    orders_by_table.setdefault(tid, []).append(
                        {
                            "id": int(order["id"]),
                            "product_id": order["product_id"],
                            "product_name": order["product_name"],
                            "quantity": int(order["quantity"]),
                            "unit_price_cop": int(order["unit_price_cop"]),
                            "subtotal_cop": subtotal,
                        }
                    )

                for table in tables:
                    tid = int(table["id"])
                    t_orders = orders_by_table.get(tid, [])
                    table["id"] = tid
                    table["table_number"] = int(table["table_number"])
                    table["capacity"] = int(table["capacity"])
                    table["orders"] = t_orders
                    table["total_cop"] = sum(item["subtotal_cop"] for item in t_orders)

                cursor.execute(
                    """
                    SELECT id, name, category, price_cop, stock, min_stock
                    FROM products
                    ORDER BY category ASC, name ASC
                    """
                )
                products_raw = cast(list[dict[str, Any]], cursor.fetchall())
                products = [
                    {
                        "id": int(p["id"]),
                        "name": p["name"],
                        "category": p["category"],
                        "price_cop": int(p["price_cop"]),
                        "stock": int(p["stock"]),
                        "min_stock": int(p["min_stock"]),
                        "low_stock": int(p["stock"]) <= int(p["min_stock"]),
                    }
                    for p in products_raw
                ]

                cursor.execute(
                    """
                    SELECT COALESCE(SUM(total_cop), 0) AS total_today,
                           COUNT(*) AS count_today
                    FROM sales
                    WHERE DATE(created_at) = UTC_DATE()
                    """
                )
                sales_kpi = cast(dict[str, Any] | None, cursor.fetchone()) or {}

                users: list[dict[str, Any]] = []
                sessions_list: list[dict[str, Any]] = []
                recent_sales: list[dict[str, Any]] = []

                if is_admin:
                    cursor.execute(
                        """
                        SELECT id, table_label, items_summary, total_cop, payment_method, created_at
                        FROM sales
                        ORDER BY id DESC
                        LIMIT 30
                        """
                    )
                    recent_sales_raw = cast(list[dict[str, Any]], cursor.fetchall())
                    recent_sales = [
                        {
                            "id": int(s["id"]),
                            "table_label": s["table_label"],
                            "items_summary": s["items_summary"],
                            "total_cop": int(s["total_cop"]),
                            "payment_method": s["payment_method"],
                            "created_at": _fmt_dt(s["created_at"]),
                        }
                        for s in recent_sales_raw
                    ]

                    cursor.execute(
                        "SELECT id, full_name, email, role, created_at FROM users ORDER BY id DESC LIMIT 50"
                    )
                    users_raw = cast(list[dict[str, Any]], cursor.fetchall())
                    users = [
                        {
                            "id": int(u["id"]),
                            "full_name": u["full_name"],
                            "email": u["email"],
                            "role": str(u.get("role") or "vendedor"),
                            "created_at": _fmt_dt(u["created_at"]),
                        }
                        for u in users_raw
                    ]

                    cursor.execute(
                        """
                        SELECT u.full_name, u.email,
                               COALESCE(s.role, u.role, 'vendedor') AS role,
                               s.created_at,
                               (s.expires_at > UTC_TIMESTAMP()) AS active
                        FROM sessions s
                        INNER JOIN users u ON u.id = s.user_id
                        ORDER BY s.created_at DESC
                        LIMIT 50
                        """
                    )
                    sessions_raw = cast(list[dict[str, Any]], cursor.fetchall())
                    sessions_list = [
                        {
                            "full_name": s["full_name"],
                            "email": s["email"],
                            "role": str(s.get("role") or "vendedor"),
                            "created_at": _fmt_dt(s["created_at"]),
                            "active": bool(s["active"]),
                        }
                        for s in sessions_raw
                    ]
            finally:
                cursor.close()
    except DatabaseConfigurationError as error:
        current_app.logger.error("Bar dashboard config error: %s", error)
        return _json_error("La conexión a la base de datos no está configurada.", 503)
    except mysql.connector.Error:
        current_app.logger.exception("Bar dashboard query failed")
        return _json_error("No se pudo conectar con MySQL. Verifica que Aiven esté encendido.", 503)

    return _json_success(
        {
            "current_user": {
                "name": current_user["name"],
                "email": current_user["email"],
                "role": current_user["role"],
            },
            "tables": tables,
            "products": products,
            "admin": {
                "sales_today_cop": int(sales_kpi.get("total_today", 0)),
                "sales_count_today": int(sales_kpi.get("count_today", 0)),
                "recent_sales": recent_sales,
                "users": users,
                "sessions": sessions_list,
            },
        }
    )


@app.post("/api/bar/users/<int:target_user_id>/role")
def update_bar_user_role(target_user_id: int) -> Response:
    current_user, auth_err = _require_bar_user(admin_only=True)
    if auth_err is not None or current_user is None:
        return auth_err or _json_error("No autorizado.", 403)

    payload, error_response = _request_data()
    if error_response is not None or payload is None:
        return error_response or _json_error("JSON inválido.", 400)

    new_role = _normalize_role(payload.get("role"), default="")
    if not new_role:
        return _json_error("Rol no válido. Usa 'administrador' o 'vendedor'.", 400)

    try:
        with _database_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute("SELECT id, role FROM users WHERE id = %s LIMIT 1", (target_user_id,))
                target = cast(dict[str, Any] | None, cursor.fetchone())
                if not target:
                    return _json_error("Usuario no encontrado.", 404)

                if target.get("role") == "administrador" and new_role != "administrador":
                    cursor.execute("SELECT COUNT(*) AS cnt FROM users WHERE role = 'administrador'")
                    cnt_row = cast(dict[str, Any] | None, cursor.fetchone())
                    if cnt_row and int(cnt_row["cnt"]) <= 1:
                        return _json_error(
                            "Debe existir al menos un Administrador en el sistema.", 400
                        )

                cursor.execute(
                    "UPDATE users SET role = %s WHERE id = %s",
                    (new_role, target_user_id),
                )
                if new_role == "vendedor":
                    cursor.execute(
                        "UPDATE sessions SET role = 'vendedor' WHERE user_id = %s",
                        (target_user_id,),
                    )
                connection.commit()
            finally:
                cursor.close()
    except (DatabaseConfigurationError, mysql.connector.Error):
        current_app.logger.exception("Update user role failed")
        return _json_error("No se pudo actualizar el rol en MySQL.", 503)

    return _json_success({"ok": True, "role": new_role})


@app.post("/api/bar/products")
def create_bar_product() -> Response:
    _, auth_err = _require_bar_user(admin_only=True)
    if auth_err is not None:
        return auth_err

    payload, error_response = _request_data()
    if error_response is not None or payload is None:
        return error_response or _json_error("JSON inválido.", 400)

    name = str(payload.get("name", "")).strip()
    category = str(payload.get("category", "Licores")).strip() or "Licores"
    try:
        price_cop = int(payload.get("price_cop", 0))
        stock = int(payload.get("stock", 0))
        min_stock = int(payload.get("min_stock", 5))
    except (TypeError, ValueError):
        return _json_error("Precio y stock deben ser números enteros.", 400)

    if not 2 <= len(name) <= 120 or price_cop <= 0 or stock < 0 or min_stock < 0:
        return _json_error("Revisa el nombre, precio mayor a 0 y stock válido.", 400)

    try:
        with _database_connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "INSERT INTO products (name, category, price_cop, stock, min_stock) VALUES (%s, %s, %s, %s, %s)",
                    (name, category[:60], price_cop, stock, min_stock),
                )
                product_id = int(cursor.lastrowid or 0)
                connection.commit()
            finally:
                cursor.close()
    except (DatabaseConfigurationError, mysql.connector.Error):
        current_app.logger.exception("Create product failed")
        return _json_error("No se pudo guardar el producto en MySQL.", 503)

    return _json_success({"id": product_id, "ok": True}, 201)


@app.post("/api/bar/products/<int:product_id>/stock")
def adjust_bar_product_stock(product_id: int) -> Response:
    _, auth_err = _require_bar_user(admin_only=True)
    if auth_err is not None:
        return auth_err

    payload, error_response = _request_data()
    if error_response is not None or payload is None:
        return error_response or _json_error("JSON inválido.", 400)

    try:
        delta = int(payload.get("delta", 0))
    except (TypeError, ValueError):
        return _json_error("El ajuste de stock debe ser numérico.", 400)

    try:
        with _database_connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "UPDATE products SET stock = GREATEST(0, stock + %s) WHERE id = %s",
                    (delta, product_id),
                )
                connection.commit()
            finally:
                cursor.close()
    except (DatabaseConfigurationError, mysql.connector.Error):
        current_app.logger.exception("Stock update failed")
        return _json_error("No se pudo actualizar el stock en MySQL.", 503)

    return _json_success({"ok": True})


@app.delete("/api/bar/products/<int:product_id>")
def delete_bar_product(product_id: int) -> Response:
    _, auth_err = _require_bar_user(admin_only=True)
    if auth_err is not None:
        return auth_err

    try:
        with _database_connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute("DELETE FROM products WHERE id = %s", (product_id,))
                connection.commit()
            finally:
                cursor.close()
    except (DatabaseConfigurationError, mysql.connector.Error):
        current_app.logger.exception("Delete product failed")
        return _json_error("No se pudo eliminar el producto.", 503)

    return _json_success({"ok": True})


@app.post("/api/bar/tables")
def create_bar_table() -> Response:
    _, auth_err = _require_bar_user(admin_only=True)
    if auth_err is not None:
        return auth_err

    payload, error_response = _request_data()
    if error_response is not None or payload is None:
        return error_response or _json_error("JSON inválido.", 400)

    label = str(payload.get("label", "")).strip()
    try:
        table_number = int(payload.get("table_number", 0))
        capacity = int(payload.get("capacity", 4))
    except (TypeError, ValueError):
        return _json_error("Número de mesa y capacidad deben ser enteros.", 400)

    if table_number <= 0 or not 2 <= len(label) <= 60 or not 1 <= capacity <= 50:
        return _json_error("Datos de la mesa inválidos.", 400)

    try:
        with _database_connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "INSERT INTO bar_tables (table_number, label, capacity, status) VALUES (%s, %s, %s, 'libre')",
                    (table_number, label, capacity),
                )
                connection.commit()
            except IntegrityError:
                connection.rollback()
                return _json_error("Ya existe una mesa con ese número.", 409)
            finally:
                cursor.close()
    except (DatabaseConfigurationError, mysql.connector.Error):
        current_app.logger.exception("Create bar table failed")
        return _json_error("No se pudo crear la mesa en MySQL.", 503)

    return _json_success({"ok": True}, 201)


@app.delete("/api/bar/tables/<int:table_id>")
def delete_bar_table(table_id: int) -> Response:
    _, auth_err = _require_bar_user(admin_only=True)
    if auth_err is not None:
        return auth_err

    try:
        with _database_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM table_orders WHERE table_id = %s",
                    (table_id,),
                )
                orders_row = cast(dict[str, Any] | None, cursor.fetchone())
                if orders_row and int(orders_row["cnt"]) > 0:
                    return _json_error(
                        "No se puede eliminar una mesa que tiene consumos activos.", 400
                    )
                cursor.execute("DELETE FROM bar_tables WHERE id = %s", (table_id,))
                connection.commit()
            finally:
                cursor.close()
    except (DatabaseConfigurationError, mysql.connector.Error):
        current_app.logger.exception("Delete bar table failed")
        return _json_error("No se pudo eliminar la mesa.", 503)

    return _json_success({"ok": True})


@app.post("/api/bar/tables/<int:table_id>/orders")
def add_table_order(table_id: int) -> Response:
    _, auth_err = _require_bar_user(admin_only=False)
    if auth_err is not None:
        return auth_err

    payload, error_response = _request_data()
    if error_response is not None or payload is None:
        return error_response or _json_error("JSON inválido.", 400)

    try:
        product_id = int(payload.get("product_id", 0))
        quantity = int(payload.get("quantity", 1))
    except (TypeError, ValueError):
        return _json_error("Producto y cantidad inválidos.", 400)

    if product_id <= 0 or not 1 <= quantity <= 99:
        return _json_error("Selecciona un producto y cantidad entre 1 y 99.", 400)

    try:
        with _database_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(
                    "SELECT id, name, price_cop, stock FROM products WHERE id = %s LIMIT 1",
                    (product_id,),
                )
                product = cast(dict[str, Any] | None, cursor.fetchone())
                if not product:
                    return _json_error("Producto no encontrado.", 404)
                if int(product["stock"]) < quantity:
                    return _json_error(
                        f"Stock insuficiente de {product['name']} (quedan {product['stock']}).",
                        400,
                    )

                cursor.execute(
                    """
                    SELECT id FROM table_orders
                    WHERE table_id = %s AND product_id = %s
                    LIMIT 1
                    """,
                    (table_id, product_id),
                )
                existing = cast(dict[str, Any] | None, cursor.fetchone())
                if existing:
                    cursor.execute(
                        "UPDATE table_orders SET quantity = quantity + %s WHERE id = %s",
                        (quantity, int(existing["id"])),
                    )
                else:
                    cursor.execute(
                        """
                        INSERT INTO table_orders (table_id, product_id, product_name, quantity, unit_price_cop)
                        VALUES (%s, %s, %s, %s, %s)
                        """,
                        (table_id, product_id, product["name"], quantity, int(product["price_cop"])),
                    )

                cursor.execute(
                    "UPDATE products SET stock = stock - %s WHERE id = %s",
                    (quantity, product_id),
                )
                cursor.execute(
                    "UPDATE bar_tables SET status = 'ocupada' WHERE id = %s",
                    (table_id,),
                )
                connection.commit()
            finally:
                cursor.close()
    except (DatabaseConfigurationError, mysql.connector.Error):
        current_app.logger.exception("Add order failed")
        return _json_error("No se pudo agregar el pedido en MySQL.", 503)

    return _json_success({"ok": True}, 201)


@app.delete("/api/bar/orders/<int:order_id>")
def remove_table_order(order_id: int) -> Response:
    _, auth_err = _require_bar_user(admin_only=False)
    if auth_err is not None:
        return auth_err

    try:
        with _database_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(
                    "SELECT id, table_id, product_id, quantity FROM table_orders WHERE id = %s LIMIT 1",
                    (order_id,),
                )
                order = cast(dict[str, Any] | None, cursor.fetchone())
                if not order:
                    return _json_error("Pedido no encontrado.", 404)

                cursor.execute("DELETE FROM table_orders WHERE id = %s", (order_id,))
                if order["product_id"] is not None:
                    cursor.execute(
                        "UPDATE products SET stock = stock + %s WHERE id = %s",
                        (int(order["quantity"]), int(order["product_id"])),
                    )
                cursor.execute(
                    "SELECT COUNT(*) AS cnt FROM table_orders WHERE table_id = %s",
                    (int(order["table_id"]),),
                )
                rem = cast(dict[str, Any] | None, cursor.fetchone())
                if rem and int(rem["cnt"]) == 0:
                    cursor.execute(
                        "UPDATE bar_tables SET status = 'libre' WHERE id = %s",
                        (int(order["table_id"]),),
                    )
                connection.commit()
            finally:
                cursor.close()
    except (DatabaseConfigurationError, mysql.connector.Error):
        current_app.logger.exception("Remove order failed")
        return _json_error("No se pudo quitar el producto de la cuenta.", 503)

    return _json_success({"ok": True})


@app.post("/api/bar/tables/<int:table_id>/status")
def set_bar_table_status(table_id: int) -> Response:
    _, auth_err = _require_bar_user(admin_only=False)
    if auth_err is not None:
        return auth_err

    payload, error_response = _request_data()
    if error_response is not None or payload is None:
        return error_response or _json_error("JSON inválido.", 400)

    status = str(payload.get("status", "")).strip()
    if status not in {"libre", "ocupada", "por_cobrar"}:
        return _json_error("Estado de mesa no válido.", 400)

    try:
        with _database_connection() as connection:
            cursor = connection.cursor()
            try:
                cursor.execute(
                    "UPDATE bar_tables SET status = %s WHERE id = %s",
                    (status, table_id),
                )
                connection.commit()
            finally:
                cursor.close()
    except (DatabaseConfigurationError, mysql.connector.Error):
        current_app.logger.exception("Set table status failed")
        return _json_error("No se pudo cambiar el estado de la mesa.", 503)

    return _json_success({"ok": True})


@app.post("/api/bar/tables/<int:table_id>/checkout")
def checkout_bar_table(table_id: int) -> Response:
    _, auth_err = _require_bar_user(admin_only=False)
    if auth_err is not None:
        return auth_err

    payload, error_response = _request_data()
    if error_response is not None or payload is None:
        return error_response or _json_error("JSON inválido.", 400)

    payment_method = str(payload.get("payment_method", "Efectivo")).strip()
    if payment_method not in {"Efectivo", "Tarjeta", "Transferencia / Nequi"}:
        payment_method = "Efectivo"

    try:
        with _database_connection() as connection:
            cursor = connection.cursor(dictionary=True)
            try:
                cursor.execute(
                    "SELECT id, label FROM bar_tables WHERE id = %s LIMIT 1",
                    (table_id,),
                )
                table = cast(dict[str, Any] | None, cursor.fetchone())
                if not table:
                    return _json_error("Mesa no encontrada.", 404)

                cursor.execute(
                    "SELECT product_name, quantity, unit_price_cop FROM table_orders WHERE table_id = %s",
                    (table_id,),
                )
                orders = cast(list[dict[str, Any]], cursor.fetchall())
                if not orders:
                    return _json_error("Esta mesa no tiene consumos por cobrar.", 400)

                total_cop = sum(int(o["quantity"]) * int(o["unit_price_cop"]) for o in orders)
                summary = ", ".join(f"{o['quantity']}x {o['product_name']}" for o in orders)[:500]

                cursor.execute(
                    """
                    INSERT INTO sales (table_label, items_summary, total_cop, payment_method)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (table["label"], summary, total_cop, payment_method),
                )
                cursor.execute("DELETE FROM table_orders WHERE table_id = %s", (table_id,))
                cursor.execute("UPDATE bar_tables SET status = 'libre' WHERE id = %s", (table_id,))
                connection.commit()
            finally:
                cursor.close()
    except (DatabaseConfigurationError, mysql.connector.Error):
        current_app.logger.exception("Checkout table failed")
        return _json_error("No se pudo registrar el cobro en MySQL.", 503)

    return _json_success({"ok": True, "total_cop": total_cop, "summary": summary})


def _detect_lan_ip() -> str:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return str(sock.getsockname()[0])
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


def _is_port_in_use(port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        probe.settimeout(0.35)
        return probe.connect_ex(("127.0.0.1", port)) == 0


def _is_barrica_running_on(port: int) -> bool:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/icon.svg", timeout=1.0) as resp:
            body = resp.read(512).decode("utf-8", errors="ignore")
            return resp.status == 200 and "#D9A441" in body
    except Exception:
        return False


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    env_file = ROOT / ".env"
    env_example = ROOT / ".env.example"
    if not env_file.exists() and env_example.exists():
        shutil.copyfile(env_example, env_file)
        load_dotenv(env_file)

    host = os.getenv("HOST", "0.0.0.0")
    requested_port = int(os.getenv("PORT", "5000"))
    port = requested_port

    if _is_port_in_use(port):
        if _is_barrica_running_on(port):
            logging.info("Barrica ya está encendido en http://127.0.0.1:%s/bar_app", port)
            raise SystemExit(0)
        if "PORT" not in os.environ:
            for candidate in range(5001, 5020):
                if not _is_port_in_use(candidate):
                    port = candidate
                    break

    lan_ip = _detect_lan_ip()
    logging.info("Web principal: http://127.0.0.1:%s", port)
    logging.info("App operativa (bar_app) en este equipo: http://127.0.0.1:%s/bar_app", port)
    if lan_ip != "127.0.0.1":
        logging.info(
            "Abrir desde otro PC o celular en la misma red Wi-Fi/LAN: http://%s:%s/bar_app",
            lan_ip,
            port,
        )
    if not os.getenv("DB_HOST"):
        logging.info(
            "Sin credenciales MySQL en .env: bar_app funcionará automáticamente en Modo Local (puedes configurar .env cuando quieras conectar MySQL)."
        )
    try:
        app.run(host=host, port=port, debug=False)
    except KeyboardInterrupt:
        pass
