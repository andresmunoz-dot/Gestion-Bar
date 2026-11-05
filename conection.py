"""Compatibilidad para conexiones MySQL fuera de la aplicación Flask.

La configuración se lee desde variables de entorno o desde un archivo .env;
no se guardan credenciales en el código fuente.
"""

import os
from pathlib import Path
from typing import Any, cast

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


if __name__ == "__main__":
    listar_registros()
