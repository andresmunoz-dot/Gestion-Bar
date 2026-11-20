import os
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
import mysql.connector

DB_DIR = Path(__file__).resolve().parent
ROOT = DB_DIR.parent
load_dotenv(ROOT / ".env")


def main() -> None:
    # Conexión usando las mismas credenciales seguras que ya funcionan
    conn: Any = mysql.connector.connect(
        host=os.getenv("DB_HOST") or "",
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER") or "",
        password=os.getenv("DB_PASSWORD") or "",
        database=os.getenv("DB_NAME") or "",
        ssl_ca=os.getenv("DB_SSL_CA", str(ROOT / "ca.pem")),
    )

    cursor = conn.cursor()
    try:
        # Lee y ejecuta el archivo schema.sql
        with open(DB_DIR / "schema.sql", "r", encoding="utf-8") as f:
            sql_script = f.read()

        for statement in sql_script.split(";"):
            if statement.strip():
                cursor.execute(statement)
                print(f"Ejecutado: {statement.strip()[:40]}...")

        # Migraciones seguras para bases de datos existentes
        cursor.execute("SHOW COLUMNS FROM users LIKE 'role'")
        if cursor.fetchone() is None:
            cursor.execute(
                "ALTER TABLE users ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'vendedor' AFTER password_hash"
            )
            print("Columna users.role agregada.")

        cursor.execute("SHOW COLUMNS FROM sessions LIKE 'role'")
        if cursor.fetchone() is None:
            cursor.execute(
                "ALTER TABLE sessions ADD COLUMN role VARCHAR(20) NOT NULL DEFAULT 'vendedor' AFTER user_id"
            )
            print("Columna sessions.role agregada.")

        # Garantiza que el usuario principal / admin tenga rol de administrador
        cursor.execute(
            "UPDATE users SET role = 'administrador' WHERE id = 1 OR email = 'admin@gmail.com'"
        )
        cursor.execute(
            """
            UPDATE sessions s
            INNER JOIN users u ON u.id = s.user_id
            SET s.role = u.role
            WHERE u.role = 'administrador'
            """
        )

        conn.commit()
        print("¡Tablas y roles actualizados exitosamente en Aiven!")
    finally:
        cursor.close()
        conn.close()


if __name__ == "__main__":
    main()
