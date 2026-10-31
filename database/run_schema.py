import os
from dotenv import load_dotenv
import mysql.connector

load_dotenv()

# Conexión usando las mismas credenciales seguras que ya funcionan
conn = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    ssl_ca="ca.pem"
)

cursor = conn.cursor()

# Lee y ejecuta el archivo schema.sql
with open("database/schema.sql", "r") as f:
    sql_script = f.read()

for statement in sql_script.split(';'):
    if statement.strip():
        cursor.execute(statement)
        print(f"Ejecutado: {statement.strip()[:30]}...")

conn.commit()
cursor.close()
conn.close()
print("¡Tablas creadas exitosamente en Aiven!")