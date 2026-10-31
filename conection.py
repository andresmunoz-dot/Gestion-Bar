import mysql.connector
import os
from dotenv import load_dotenv

# Esto lee las contraseñas de tu archivo .env
load_dotenv() 

# Conexión a la base de datos usando las variables protegidas
db = mysql.connector.connect(
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    database=os.getenv("DB_NAME"),
    ssl_ca="ca.pem"
)

print("¡Conectado exitosamente!")

import mysql.connector

#db = mysql.connector.connect(
 #   user="avnadmin",
  #  password="AVNS_Xwz-xFd9XKBAM6yls78",
   # host="mysql-2b0605e2-andresmu990-5982.k.aivencloud.com",
    #database="defaultdb",
#)

#cursor = db.cursor()
#cursor.execute("SELECT * FROM users")
#result = cursor.fetchall()

#Usuarios encontrados
#result = cursor.fetchall()
#print(f"Total de usuarios encontrados: {len(result)}") 



#for user in result:
 #   print(user)