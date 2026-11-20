"""Compatibilidad para conexiones MySQL fuera de la aplicación Flask.

La configuración se lee desde variables de entorno o desde un archivo .env;
no se guardan credenciales en el código fuente.
"""

import argparse
import getpass
import os
from pathlib import Path
from typing import Any, cast

import bcrypt
from dotenv import load_dotenv
import mysql.connector

ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")


def get_connection() -> Any:
    """Devuelve una conexión MySQL usando la configuración del entorno."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST") or "",
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER") or "",
        password=os.getenv("DB_PASSWORD") or "",
        database=os.getenv("DB_NAME") or "",
        ssl_ca=os.getenv("DB_SSL_CA", str(ROOT / "ca.pem")),
    )


def listar_registros() -> None:
    """Muestra en consola los usuarios registrados y las sesiones iniciadas."""
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    try:
        cursor.execute(
            "SELECT id, full_name, email, role, created_at FROM users ORDER BY created_at DESC"
        )
        users = cast(list[dict[str, Any]], cursor.fetchall())
        print(f"\n=== USUARIOS REGISTRADOS ({len(users)}) ===")
        for u in users:
            rol = str(u.get("role") or "vendedor").upper()
            print(
                f"  ID {u['id']} | {u['full_name']} | {u['email']} | Rol: {rol} | Registro (UTC): {u['created_at']}"
            )

        cursor.execute(
            """
            SELECT u.full_name, u.email, s.role AS rol_sesion, s.created_at AS inicio_sesion,
                   (s.expires_at > UTC_TIMESTAMP()) AS activa
            FROM sessions s
            INNER JOIN users u ON u.id = s.user_id
            ORDER BY s.created_at DESC
            """
        )
        sessions = cast(list[dict[str, Any]], cursor.fetchall())
        print(f"\n=== INICIOS DE SESIÓN ({len(sessions)}) ===")
        for s in sessions:
            estado = "ACTIVA" if s["activa"] else "EXPIRADA"
            rol_sesion = str(s.get("rol_sesion") or "vendedor").upper()
            print(
                f"  {s['full_name']} ({s['email']}) | Perfil: {rol_sesion} | Inicio (UTC): {s['inicio_sesion']} | {estado}"
            )
    finally:
        cursor.close()
        conn.close()


def actualizar_contrasena_admin(email: str = "admin@gmail.com") -> None:
    """Crea o actualiza la cuenta administradora y revoca sus sesiones.

    La contraseña se solicita sin mostrarla en consola y nunca se guarda en el código.
    """
    email = email.strip().lower()
    if not email or "@" not in email:
        raise ValueError("Ingresa un correo de administrador válido.")

    pwd1 = getpass.getpass("Contraseña nueva del administrador (mínimo 12 caracteres): ")
    pwd2 = getpass.getpass("Confirma la contraseña: ")
    if pwd1 != pwd2:
        raise ValueError("Las contraseñas no coinciden.")
    if len(pwd1.encode("utf-8")) < 12 or len(pwd1.encode("utf-8")) > 72:
        raise ValueError("La contraseña debe tener entre 12 y 72 bytes UTF-8.")

    pwd_hash = bcrypt.hashpw(pwd1.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE email = %s LIMIT 1", (email,))
        row = cursor.fetchone()
        if row:
            user_id = row[0] if isinstance(row, tuple) else row["id"]
            cursor.execute(
                "UPDATE users SET password_hash = %s, role = %s WHERE id = %s",
                (pwd_hash, "administrador", user_id),
            )
        else:
            cursor.execute(
                "INSERT INTO users (full_name, email, password_hash, role) VALUES (%s, %s, %s, %s)",
                ("Administrador Barika", email, pwd_hash, "administrador"),
            )
            user_id = cursor.lastrowid
            if user_id is None:
                raise RuntimeError("No se obtuvo el ID de la cuenta administradora creada.")

        cursor.execute("DELETE FROM sessions WHERE user_id = %s", (user_id,))
        conn.commit()
        print(f"Cuenta administradora lista: {email}.")
        print("La contraseña quedó guardada como hash y las sesiones anteriores fueron revocadas.")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Administración de usuarios de Barika")
    parser.add_argument(
        "--reset-admin",
        action="store_true",
        help="Crear o actualizar el acceso administrador (solicita la contraseña sin mostrarla)",
    )
    parser.add_argument(
        "--email",
        default=os.getenv("ADMIN_EMAIL", "admin@gmail.com"),
        help="Correo del administrador (por defecto: admin@gmail.com)",
    )
    args = parser.parse_args()
    if args.reset_admin:
        actualizar_contrasena_admin(args.email)
    else:
        listar_registros()
