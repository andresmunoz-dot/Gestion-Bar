# Barrica · Sistema de Gestión y Punto de Venta (POS) para Bares

**Barrica** es una plataforma integral conectada en tiempo real a **MySQL** para controlar la operación de un bar: mapa visual de mesas, toma de comandas, descuento automático de inventario de licores, división de cuentas, cálculo de cambio, auditoría de sesiones y administración de usuarios por roles (**Administrador** y **Vendedor**).

El ecosistema incluye **tres interfaces sincronizadas** contra la misma base de datos MySQL:
1. **Página Web Principal (`Untitled-1.html`):** Portal informativo, simulador de planes, acceso por rol y centro de descargas (`/`).
2. **Aplicación Operativa Móvil / Web PWA (`bar_app.html`):** Interfaz táctil independiente para celulares, tablets y navegador (`/app` y descargable como `Barrica-Movil.html`).
3. **Aplicación Nativa de Escritorio para Windows (`downloads/BarricaDesktop.exe`):** Ejecutable real en C# WinForms compilado sin dependencias externas, con renderizado de alta definición (DPI-aware), doble búfer gráfico y peticiones asíncronas sin bloqueos.

> **Documentación de Ingeniería y Base de Datos:** Consulta [`docs/DOCUMENTACION_TECNICA.md`](docs/DOCUMENTACION_TECNICA.md) para ver el **Diagrama Entidad-Relación (DER)**, **Modelo Relacional (MR)**, **Diccionario de Datos**, **Diagramas UML** (Casos de Uso, Clases, Actividades y Secuencias), **Especificación de Casos de Uso** y **Mockups**.

---

## Estructura del Proyecto

```text
├── app.py                        # Servidor Flask, pool MySQL SSL, autenticación y API REST POS
├── Untitled-1.html               # Página web principal con login por rol y centro de descargas
├── bar_app.html                  # Aplicación operativa independiente (Móvil / PWA / Web)
├── conection.py                  # Script CLI para consultar usuarios, roles y sesiones en MySQL
├── requirements.txt              # Dependencias de Python (Flask, bcrypt, mysql-connector, dotenv)
├── database/
│   ├── schema.sql                # Script DDL de tablas MySQL
│   ├── backup_barrica.sql        # Backup SQL (estructura + catálogo base)
│   └── run_schema.py             # Ejecutor automático de esquema y migraciones en Aiven MySQL
├── desktop/
│   └── BarricaDesktop.cs         # Código fuente C# de la aplicación nativa de escritorio
├── downloads/
│   └── BarricaDesktop.exe        # Ejecutable nativo optimizado para Windows
├── docs/
│   └── DOCUMENTACION_TECNICA.md  # DER, MR, Diccionario de datos, UML, Casos de Uso y Mockups
└── tests/
    └── test_app.py               # Suite de 22 pruebas unitarias automatizadas
```

---

## Perfiles de Acceso (Roles)

Al abrir cualquiera de las aplicaciones (`http://127.0.0.1:5000`, `http://127.0.0.1:5000/app` o `BarricaDesktop.exe`) se presenta el **inicio de sesión por perfil**:

| Módulo / Permiso | Vendedor | Administrador |
| :--- | :---: | :---: |
| Iniciar sesión / Crear cuenta | Sí | Sí |
| Mapa visual de mesas, pedidos y comandas | Sí | Sí |
| Dividir cuentas, calcular cambio y registrar cobros | Sí | Sí |
| Consultar carta de precios y existencias en vivo | Solo lectura | Completo |
| Crear, ajustar stock (`-1`, `+1`, `+10`) y eliminar productos | No | Sí |
| Crear y eliminar mesas del salón | No | Sí |
| Panel de Administración (usuarios, sesiones, ventas y cambio de roles) | No | Sí |

---

## Instalación y Ejecución Local

### 1. Requisitos previos
- **Python 3.12+**
- Base de datos **MySQL 8.0+** (local o en la nube como **Aiven MySQL**)

### 2. Configurar entorno virtual y variables `.env`

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` con las credenciales de tu instancia MySQL (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_SSL=true` y `ca.pem` si usas SSL en Aiven). Nunca subas el archivo `.env` al repositorio.

### 3. Crear / actualizar las tablas en MySQL

```powershell
.\.venv\Scripts\python.exe database\run_schema.py
```

### 4. Encender y apagar el servidor (o abrir en otro PC al descomprimir)

- **Inicio rápido en cualquier PC (1 clic):**
  - **Con servidor automático:** haz doble clic en `iniciar_bar_app.bat` (detecta o recrea `.venv` automáticamente para la ruta de ese computador, instala dependencias y abre `http://127.0.0.1:5000/bar_app`).
  - **Sin servidor / sin Python (Modo Local):** abre `bar_app.html` con doble clic y pulsa **«Abrir sin servidor (Modo Local)»** para ver y probar todas las funciones desde el navegador.
- **Encender manualmente por terminal:**
  ```powershell
  .\.venv\Scripts\python.exe app.py
  ```
  - Web principal: `http://127.0.0.1:5000`
  - App operativa POS (`bar_app`): `http://127.0.0.1:5000/bar_app` (o `http://127.0.0.1:5000/app`)
  - Desde otro equipo en la misma red Wi-Fi/LAN: usa la URL `http://<IP-LOCAL>:5000/bar_app` que aparece en la consola al encender `app.py`.
  - App nativa Windows: ejecuta `downloads\BarricaDesktop.exe`
- **Apagar:** Presiona `Ctrl + C` en la terminal donde corre `app.py`.

### 5. Consultar usuarios y sesiones por consola

```powershell
.\.venv\Scripts\python.exe conection.py
```

---

## Compilar `BarricaDesktop.exe` (Opcional)

El ejecutable ya viene listo en `downloads/BarricaDesktop.exe`. Si modificas `desktop/BarricaDesktop.cs`, puedes recompilarlo en Windows sin instalar SDKs adicionales ejecutando:

```powershell
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /optimize+ /warn:4 /warnaserror /target:winexe /out:downloads\BarricaDesktop.exe /r:System.Web.Extensions.dll desktop\BarricaDesktop.cs
```

---

## Resumen de la API REST

### Autenticación y Sesiones
- `POST /api/auth/register` — Registra usuario (`name`, `email`, `password` mín. 12 caracteres, `role`: `administrador` | `vendedor`).
- `POST /api/auth/login` — Inicia sesión validando `bcrypt`, bloqueo anti-fuerza bruta y permiso de rol; emite cookie `HttpOnly` y token `Bearer`.
- `GET /api/auth/session` — Devuelve la sesión activa y su rol.
- `POST /api/auth/logout` — Revoca la sesión en MySQL.

### Operación del Bar (POS e Inventario MySQL)
- `GET /api/bar/dashboard` — Estado en tiempo real de mesas, comandas, productos y (para Administrador) usuarios, sesiones y ventas.
- `POST /api/bar/tables/<id>/orders` — Agrega consumo a una mesa y descuenta stock automáticamente.
- `DELETE /api/bar/orders/<id>` — Quita un ítem de la comanda y restaura su stock.
- `POST /api/bar/tables/<id>/status` — Actualiza el estado de una mesa (`libre`, `ocupada`, `por_cobrar`).
- `POST /api/bar/tables/<id>/checkout` — Registra la venta en `sales`, limpia la comanda y libera la mesa.
- `POST /api/bar/products` *(Admin)* — Crea un nuevo producto en MySQL.
- `POST /api/bar/products/<id>/stock` *(Admin)* — Ajusta unidades de inventario.
- `DELETE /api/bar/products/<id>` *(Admin)* — Elimina un producto del catálogo.
- `POST /api/bar/tables` y `DELETE /api/bar/tables/<id>` *(Admin)* — Crea o elimina mesas libres.
- `POST /api/bar/users/<id>/role` *(Admin)* — Cambia el rol de un usuario entre `administrador` y `vendedor`.

---

## Pruebas Automatizadas

Ejecuta las **22 pruebas unitarias** (autenticación, validación de roles, permisos de endpoints, manifiesto PWA, descargas y simulación de recibos):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
