"""Compatibilidad para conexiones MySQL fuera de la aplicación Flask.

La configuración se lee desde variables de entorno o desde un archivo .env;
no se guardan credenciales en el código fuente.
"""

import os

import mysql.connector
from dotenv import load_dotenv

load_dotenv()


def get_connection():
    """Devuelve una conexión MySQL usando la configuración del entorno."""
    return mysql.connector.connect(
        host=os.getenv("DB_HOST"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        database=os.getenv("DB_NAME"),
        ssl_ca=os.getenv("DB_SSL_CA", "ca.pem"),
    )
