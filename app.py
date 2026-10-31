from __future__ import annotations

import mysql.connector
import os
from dotenv import load_dotenv
import hashlib
import logging
import os
import re
import secrets
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Generator, TypeGuard


import bcrypt
import mysql.connector
from dotenv import load_dotenv
from flask import Flask, Response, current_app, jsonify, make_response, request, send_file
from mysql.connector import IntegrityError, MySQLConnection
import os
from dotenv import load_dotenv
import mysql.connector


load_dotenv()
def get_db_connection():
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        ssl_ca=os.getenv("DB_SSL_CA", str(ROOT / "ca.pem"))
    )

ROOT = Path(__file__).resolve().parent
SESSION_COOKIE = "barrica_session"
SESSION_DURATION = timedelta(days=7)
LOGIN_ATTEMPT_LIMIT = 5
LOGIN_WINDOW_MINUTES = 15
EMAIL_PATTERN = re.compile(r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
load_dotenv(ROOT / ".env")

app = Flask(__name__)
app.config["JSON_AS_ASCII"] = False


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
    return {
        "host": os.environ["DB_HOST"],
        "port": port,
        "user": os.environ["DB_USER"],
        "password": os.environ["DB_PASSWORD"],
        "database": os.environ["DB_NAME"],
        "connection_timeout": 5,
        "ssl_disabled": not use_ssl,
        "ssl_verify_cert": use_ssl,
        "ssl_verify_identity": use_ssl,
    }


@contextmanager
def _database_connection() -> Generator[MySQLConnection, None, None]:
    connection = get_db_connection()
    try:
        yield connection
    finally:
        connection.close()


def _json_error(message: str, status: int) -> Response:
    response = jsonify(error=message)
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


def _is_valid_email(email: str) -> bool:
    return len(email) <= 254 and EMAIL_PATTERN.fullmatch(email) is not None


def _is_valid_password(password: object) -> TypeGuard[str]:
    return (
        isinstance(password, str)
        and len(password) >= 12
        and len(password.encode("utf-8")) <= 72
    )


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _create_session(connection: MySQLConnection, user_id: int) -> str:
    token = secrets.token_urlsafe(32)
    expires_at = datetime.now(timezone.utc).replace(tzinfo=None) + SESSION_DURATION
    cursor = connection.cursor()
    try:
        cursor.execute(
            "INSERT INTO sessions (token_hash, user_id, expires_at) VALUES (%s, %s, %s)",
            (_token_hash(token), user_id, expires_at),
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
                SELECT users.full_name AS name, users.email
                FROM sessions
                INNER JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = %s
                  AND sessions.expires_at > UTC_TIMESTAMP()
                LIMIT 1
                """,
                (_token_hash(token),),
            )
            return cursor.fetchone()
        finally:
            cursor.close()


def _login_attempt_key(email: str) -> str:
    address = (
        request.headers.get("x-vercel-forwarded-for")
        or request.remote_addr
        or "unknown"
    ).split(",")[0].strip()
    return _token_hash(f"{email}:{address}")


def _is_login_blocked(connection: MySQLConnection, key_hash: str) -> bool:
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
        row = cursor.fetchone()
        return bool(row and row[1] and row[0] >= LOGIN_ATTEMPT_LIMIT)
    finally:
        cursor.close()


def _record_login_failure(connection: MySQLConnection, key_hash: str) -> None:
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


@app.get("/")
def home():
    return send_file(ROOT / "Untitled-1.html")


@app.get("/api/auth/session")
def session():
    try:
        user = _get_session_user(request.cookies.get(SESSION_COOKIE, ""))
    except DatabaseConfigurationError as error:
        current_app.logger.error("Session configuration error: %s", error)
        return _json_error("La conexión a la base de datos no está configurada.", 503)
    except mysql.connector.Error:
        current_app.logger.exception("Session database request failed")
        return _json_error("No se pudo comprobar la sesión. Inténtalo más tarde.", 503)
    return _json_success({"user": user})


@app.post("/api/auth/register")
def register():
    payload, error_response = _request_data()
    if error_response is not None:
        return error_response

    name = payload.get("name", "").strip() if isinstance(payload.get("name"), str) else ""
    email = _normalize_email(payload.get("email"))
    password = payload.get("password")
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
                    "INSERT INTO users (full_name, email, password_hash) VALUES (%s, %s, %s)",
                    (name, email, password_hash.decode("ascii")),
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
            token = _create_session(connection, user_id)
    except DatabaseConfigurationError as error:
        current_app.logger.error("Registration configuration error: %s", error)
        return _json_error("La conexión a la base de datos no está configurada.", 503)
    except mysql.connector.Error:
        current_app.logger.exception("Registration database request failed")
        return _json_error("No se pudo crear la cuenta. Inténtalo más tarde.", 503)

    response = _json_success({"user": {"name": name, "email": email}}, 201)
    return _set_session_cookie(response, token)


@app.post("/api/auth/login")
def login():
    payload, error_response = _request_data()
    if error_response is not None:
        return error_response

    email = _normalize_email(payload.get("email"))
    password = payload.get("password")
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
                    SELECT id, full_name AS name, email, password_hash
                    FROM users WHERE email = %s LIMIT 1
                    """,
                    (email,),
                )
                user = cursor.fetchone()
            finally:
                cursor.close()

            password_matches = bool(
                user
                and bcrypt.checkpw(
                    password.encode("utf-8"),
                    user["password_hash"].encode("ascii"),
                )
            )
            if not password_matches:
                _record_login_failure(connection, attempt_key)
                return _json_error("Correo o contraseña incorrectos.", 401)

            cursor = connection.cursor()
            try:
                cursor.execute("DELETE FROM auth_attempts WHERE key_hash = %s", (attempt_key,))
                connection.commit()
            finally:
                cursor.close()
            token = _create_session(connection, user["id"])
    except DatabaseConfigurationError as error:
        current_app.logger.error("Login configuration error: %s", error)
        return _json_error("La conexión a la base de datos no está configurada.", 503)
    except mysql.connector.Error:
        current_app.logger.exception("Login database request failed")
        return _json_error("No se pudo iniciar sesión. Inténtalo más tarde.", 503)

    response = _json_success({"user": {"name": user["name"], "email": user["email"]}})
    return _set_session_cookie(response, token)


@app.post("/api/auth/logout")
def logout():
    token = request.cookies.get(SESSION_COOKIE, "")
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


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    app.run(host="127.0.0.1", port=int(os.getenv("PORT", "5000")), debug=False)
