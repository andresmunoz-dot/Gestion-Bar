# Barrica · Sistema de Gestión y Punto de Venta (POS) para Bares

**Barrica** es una plataforma integral conectada en tiempo real a **MySQL** para controlar la operación de un bar: mapa visual de mesas, toma de comandas, descuento automático de inventario de licores, división de cuentas, cálculo de cambio, auditoría de sesiones y administración de usuarios por roles (**Administrador** y **Vendedor**).

El ecosistema incluye **tres interfaces sincronizadas** contra la misma base de datos MySQL:
1. **Página Web Principal (`Untitled-1.html`):** Portal informativo, registro/inicio de sesión, precios y flujo de checkout (`/`). El formulario existente es de prueba; no cobra dinero real.
2. **Aplicación Operativa Móvil / Web PWA (`bar_app.html`):** Interfaz táctil independiente para celulares, tablets y navegador (`/app` y descargable como `Barrica-Movil.html`).
3. **Aplicación Nativa de Escritorio para Windows (`downloads/BarricaDesktop.exe`):** Ejecutable real en C# WinForms compilado sin dependencias externas, con renderizado de alta definición (DPI-aware), doble búfer gráfico y peticiones asíncronas sin bloqueos.

> **Documentación de Ingeniería y Base de Datos:** Consulta [`docs/DOCUMENTACION_TECNICA.md`](docs/DOCUMENTACION_TECNICA.md) (o descarga el documento Word [`docs/Trabajo_Escrito_Barrica_POS.docx`](docs/Trabajo_Escrito_Barrica_POS.docx)) para ver el **Diagrama Entidad-Relación (DER)**, **Modelo Relacional (MR)**, **Diccionario de Datos**, **Diagramas UML** (Casos de Uso, Clases, Actividades y Secuencias), **Especificación de Casos de Uso**, **Scripts y Backup SQL**, **Mockups** y **Enlaces del Repositorio Git**.
>
> **Enlace del Repositorio Git (GitHub):** https://github.com/andresmunoz-dot/Gestion-Bar (`https://github.com/andresmunoz-dot/Gestion-Bar.git`)

---

## Estructura del Proyecto

```text
├── app.py                                    # Servidor Flask, pool MySQL SSL, autenticación, turnos y API REST POS
├── Untitled-1.html                           # Página web principal con login, checkout, mapa y canales de contacto
├── bar_app.html                              # Aplicación operativa independiente (Móvil / PWA / Web / Demo Local JSON)
├── conection.py                              # CLI para consultar usuarios/sesiones y configurar administrador
├── iniciar_bar_app.bat                       # Iniciador portable Windows (modo conectado MySQL)
├── iniciar_demo_local_json.bat               # Iniciador portable Windows (modo Demo Local JSON sin MySQL)
├── requirements.txt                          # Dependencias de Python (Flask, bcrypt, mysql-connector, dotenv)
├── .env.example                              # Plantilla de variables de entorno MySQL y entorno de ejecución
├── ca.pem                                    # Certificado CA para conexión TLS/SSL con Aiven MySQL
├── database/
│   ├── schema.sql                            # Script DDL completo de tablas MySQL (incluye subscriptions)
│   ├── backup_barrica.sql                    # Backup SQL (estructura completa + catálogo semilla)
│   └── run_schema.py                         # Ejecutor automático de esquema y migraciones en Aiven MySQL
├── desktop/
│   └── BarricaDesktop.cs                     # Código fuente C# de la aplicación nativa de escritorio
├── downloads/
│   └── BarricaDesktop.exe                    # Ejecutable nativo optimizado para Windows
├── static/
│   └── product_images/optimized/             # Catálogo de imágenes optimizadas de productos del bar
├── docs/
│   ├── DOCUMENTACION_TECNICA.md              # DER, MR, Diccionario de datos, UML, Casos de Uso y Mockups
│   └── INTEGRACION_FUNCIONES_ADICIONALES.md  # Notas de integración de CRM local, turnos, facturas y portal
└── tests/
    ├── test_app.py                           # Suite de 39 pruebas unitarias de API, POS, turnos y demo JSON
    └── test_conection.py                     # Suite de 4 pruebas unitarias del gestor CLI de administrador
```

---

## Novedades y Módulos Integrados

- **Login Obligatorio y Control de Suscripciones (Paywall POS):** El acceso operativo valida sesión por pestaña (`Bearer` en `sessionStorage`) y estado del plan. Las cuentas con rol **Administrador** cuentan con acceso **Multi-local vitalicio** automático; las cuentas de **Vendedor** requieren suscripción activa en modo conectado.
- **Modo Demo Local JSON (`iniciar_demo_local_json.bat` / `/bar_app?mode=local`):** Permite operar el POS 100% en el navegador sin configurar MySQL, con cuenta administradora local (`admin@gmail.com`) preconfigurada y exportación/importación de respaldo `.json`.
- **Apertura y Cierre de Turnos de Caja:** Registro de datos del encargado (nombre, tipo y número de documento, teléfono, correo, cargo y base inicial en efectivo) y generación de un **único recibo consolidado de cierre de turno** (`CIERRE-TURNO-XXXXX`) con desglose de productos vendidos, métodos de pago y efectivo esperado en caja.
- **Facturación Fantasma y CRM Local de Clientes:** Directorio de clientes con clasificación imprimible por país, selector de cliente al cobrar mesa y emisión/impresión de comprobantes detallados (`FAC-FANTASMA-XXXXX`) restringidos al panel administrador.
- **Bodega de Reserva e Imágenes de Productos:** Soporte para stock en barra (`stock`), bodega de reserva (`reserve_stock`) con traslado rápido e imágenes locales optimizadas (`image_url`).
- **Portal Público Enriquecido (`Untitled-1.html`):** Incluye botón flotante de atención por WhatsApp, enlaces e iconos de redes sociales, aviso flotante de eventos/mantenimiento, mapa interactivo del Corredor Ecológico de Villavicencio y guía de lugares recomendados.

---

## Perfiles de Acceso (Roles)

Al abrir cualquiera de las aplicaciones (`http://127.0.0.1:5000`, `http://127.0.0.1:5000/bar_app` o `BarricaDesktop.exe`) se presenta el **inicio de sesión por perfil**:

| Módulo / Permiso | Vendedor | Administrador |
| :--- | :---: | :---: |
| Iniciar sesión / Crear cuenta | Sí (requiere plan activo en POS) | Sí (Acceso Multi-local vitalicio) |
| Mapa visual de mesas, pedidos y comandas | Sí | Sí |
| Abrir y cerrar turnos de caja con arqueo consolidado | Sí | Sí |
| Dividir cuentas, calcular cambio, asociar cliente y registrar cobros | Sí | Sí |
| Consultar carta de precios y existencias en vivo | Solo lectura | Completo |
| Crear, ajustar stock (`-1`, `+1`, `+10`), trasladar reserva y eliminar productos | No | Sí |
| Crear y eliminar mesas del salón | No | Sí |
| Consultar historial de facturas fantasma (`FAC-FANTASMA`) | No | Sí |
| Panel de Administración (usuarios, sesiones, ventas y cambio de roles) | No | Sí |

---

## Instalación y Ejecución Local

### 1. Requisitos previos
- **Python 3.12+** para ejecutar el servidor local.
- **MySQL 8.0+** solo para uso operativo con datos compartidos y suscripción validada. No hace falta MySQL para la demo local JSON.

### 2. Configurar entorno virtual y variables `.env`

```powershell
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Edita `.env` con las credenciales de tu instancia MySQL (`DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`, `DB_SSL=true` y `ca.pem` si usas SSL en Aiven). Para una prueba local sin cobro real, activa `ALLOW_SIMULATED_SUBSCRIPTIONS=1`. En producción establece `APP_ENV=production` y `ALLOW_SIMULATED_SUBSCRIPTIONS=0`. Nunca subas el archivo `.env` al repositorio.

### 3. Crear / actualizar las tablas en MySQL

```powershell
.\.venv\Scripts\python.exe database\run_schema.py
```

### Configurar el acceso administrador

Con `.env` configurado y MySQL accesible, puedes crear o restablecer la cuenta administrativa. El comando pide la contraseña dos veces sin mostrarla, guarda únicamente su hash, asigna el rol Administrador y revoca sus sesiones anteriores:

```powershell
.\.venv\Scripts\python.exe conection.py --reset-admin --email admin@gmail.com
```

El correo por defecto también es `admin@gmail.com`, por lo que `--email` es opcional. No pongas la contraseña en el comando ni en el archivo `.env`.

### 4. Encender y apagar el servidor (o abrir en otro PC al descomprimir)

- **Demo local sin SQL ni servicios externos:** haz doble clic en `iniciar_demo_local_json.bat`. Abre `http://127.0.0.1:5000/bar_app?mode=local` y trabaja con JSON guardado en el navegador. La demo incluye la cuenta local `admin@gmail.com`, con el rol Administrador y acceso Multi-local vitalicio; ingresa con la contraseña que configuraste para esta cuenta. No tienes que crearla, comprar un plan ni conectar MySQL. Si ya tenías datos JSON, el administrador se incorpora sin borrar inventario, ventas ni mesas. Usa siempre el mismo navegador y esta misma dirección para conservar la información.
  - El inventario, ventas, turnos, clientes y usuarios de prueba se guardan localmente en el navegador como JSON. En **Ajustes** puedes descargar o restaurar una copia `.json`. Los datos quedan en ese navegador/equipo; borrar los datos del navegador los elimina.
  - También puedes abrir `bar_app.html` directamente para probar el POS. Para compartir cuenta y datos entre la página pública y el POS, usa el iniciador `iniciar_demo_local_json.bat`.
- **Uso con MySQL/suscripción:** haz doble clic en `iniciar_bar_app.bat` para modo conectado (instala dependencias y abre `/bar_app`); configura `.env` y prepara el esquema según los pasos siguientes. No confundas la demo local con una compra o una cuenta en producción.
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

El ejecutable ya viene listo en `downloads/BarricaDesktop.exe`. El fuente del cliente se actualizó para pedir el propósito POS y abrir el portal cuando el servidor requiere un plan; recompila el `.exe` en Windows para incorporar ese cambio visual. Si modificas `desktop/BarricaDesktop.cs`, puedes recompilarlo sin instalar SDKs adicionales ejecutando:

```powershell
C:\Windows\Microsoft.NET\Framework64\v4.0.30319\csc.exe /nologo /optimize+ /warn:4 /warnaserror /target:winexe /out:downloads\BarricaDesktop.exe /r:System.Web.Extensions.dll desktop\BarricaDesktop.cs
```

---

## Resumen de la API REST

### Autenticación y Sesiones
- `POST /api/auth/register` — Registra usuario (`name`, `email`, `password` mín. 12 caracteres) aunque aún no tenga plan, y emite una sesión para poder continuar al checkout. En producción la cuenta pública se crea como Vendedor; la promoción a Administrador solo puede hacerla un administrador autenticado.
- `POST /api/auth/login` — Valida correo y contraseña existentes (no crea cuentas ni cambia claves desde el login). Con `purpose: "pos"`, exige una suscripción activa para iniciar sesión en el POS.
- `GET /api/auth/session` — Devuelve la sesión activa y su rol.
- `GET /api/auth/subscription` — Devuelve estado/plan vigente para una cuenta autenticada.
- `POST /api/auth/logout` — Revoca la sesión en MySQL.

### Operación del Bar (POS e Inventario MySQL)
- `GET /api/bar/dashboard` — Estado en tiempo real de mesas, comandas, productos y (para Administrador) usuarios, sesiones y ventas.
- `POST /api/bar/tables/<id>/orders` — Agrega consumo a una mesa y descuenta stock automáticamente.
- `DELETE /api/bar/orders/<id>` — Quita un ítem de la comanda y restaura su stock.
- `POST /api/bar/tables/<id>/status` — Actualiza el estado de una mesa (`libre`, `ocupada`, `por_cobrar`).
- `POST /api/bar/tables/<id>/checkout` — Registra la venta en `sales`, limpia la comanda y libera la mesa.
- `POST /api/bar/products` *(Admin)* — Crea un nuevo producto en MySQL.
- `POST /api/bar/products/<id>/stock` *(Admin)* — Ajusta unidades de inventario.
- `POST /api/bar/products/<id>/reserve` *(Admin)* — Traslada unidades de la bodega de reserva al stock disponible.

El inventario permite registrar una URL de imagen de referencia y unidades en bodega; el panel de administración resume ventas del día, semana, mes y año. Las APIs operativas verifican una suscripción vigente en MySQL para cada solicitud. La nueva tabla `subscriptions` se crea con `database/run_schema.py` y también se crea de forma idempotente al consultar el estado de suscripción.
- `DELETE /api/bar/products/<id>` *(Admin)* — Elimina un producto del catálogo.
- `POST /api/bar/tables` y `DELETE /api/bar/tables/<id>` *(Admin)* — Crea o elimina mesas libres.
- `POST /api/bar/users/<id>/role` *(Admin)* — Cambia el rol de un usuario entre `administrador` y `vendedor`.

### Turnos de Caja, Facturas Fantasma y Pagos Simulados
- `GET /api/bar/shifts` — Consulta el turno de caja activo y el historial de turnos cerrados.
- `POST /api/bar/shifts/open` — Abre un turno registrando los datos del encargado y la base inicial en efectivo.
- `POST /api/bar/shifts/close` — Cierra el turno activo y genera un único recibo consolidado (`CIERRE-TURNO-XXXXX`) con totales por método de pago, unidades vendidas y arqueo de caja.
- `GET /api/bar/invoices` *(Admin)* — Lista las facturas fantasma generadas al cobrar mesas.
- `POST /api/bar/invoices` — Registra una factura fantasma asociada a un cobro y cliente.
- `POST /api/payments/simulate` — Procesa un checkout de prueba (cuando `ALLOW_SIMULATED_SUBSCRIPTIONS=1` en entorno de desarrollo) y devuelve un comprobante etiquetado como simulación.

---

## Pruebas Automatizadas

Ejecuta las **43 pruebas unitarias** (`tests/test_app.py` y `tests/test_conection.py`: autenticación, paywall por suscripción, acceso vitalicio de administrador, validación de roles, turnos de caja consolidados, facturas fantasma, modo demo local JSON, manifiesto PWA, descargas y CLI de administración):

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

### Notas de seguridad y alcance de la actualización

El administrador integrado con correo `admin@gmail.com` existe únicamente en la demo local JSON. Su verificador se guarda como hash PBKDF2 dentro del JSON del navegador, no como contraseña en texto. Esta facilidad es solo para pruebas locales: el código de una página web puede inspeccionarse y el almacenamiento local puede modificarse; no uses esta cuenta ni ese modo para un servicio publicado o datos sensibles. La contraseña no se repite en el repositorio; usa la que estableciste para la cuenta.

La sesión del POS se mantiene en `sessionStorage`: sobrevive a recargas y navegación en la misma pestaña, pero al cerrar sesión se revoca en el servidor y al cerrar la pestaña se pierde el token guardado. Los endpoints operativos requieren el token `Bearer` de esa pestaña; no aceptan solamente la cookie compartida entre pestañas. El registro de cuenta no requiere plan. El servidor exige una suscripción activa para vendedores antes de permitir el uso del POS. Las cuentas cuyo rol guardado en la base de datos sea Administrador reciben acceso vitalicio al plan Multi-local, sin crear una suscripción mensual. El correo y la contraseña se verifican normalmente y el rol almacenado es la autoridad: un email desconocido no inicia sesión, el login no crea usuarios y el registro público siempre crea vendedores; solo un administrador existente puede asignar ese rol.

El checkout que trae este proyecto es una simulación y no realiza cargos reales. En desarrollo, para probar el candado de suscripción, activa explícitamente `ALLOW_SIMULATED_SUBSCRIPTIONS=1`; el servidor registra ese plan con estado `test_active`, claramente distinto a `active`. En producción, configura `APP_ENV=production` y deja `ALLOW_SIMULATED_SUBSCRIPTIONS=0`: el endpoint de simulación no habilita el POS. Para aceptar pagos reales hay que integrar un proveedor (por ejemplo, Mercado Pago o Stripe) y activar una suscripción únicamente desde una confirmación de pago firmada del proveedor; este ZIP no contiene credenciales ni esa pasarela.

En modo conectado, un Vendedor sin suscripción es enviado al checkout y las APIs operativas exigen su plan activo; las cuentas de Administrador mantienen el acceso Multi-local vitalicio. La autorización se valida en el servidor. Solo en la demo explícita de `iniciar_demo_local_json.bat` o al abrir los HTML localmente, el checkout simulado guarda un plan local después de autenticar una cuenta ya registrada; sin ese pago simulado, el POS queda bloqueado. Esa ruta usa almacenamiento local y no acredita suscripciones reales. No uses la demo local para datos de clientes o ventas reales. Las contraseñas locales se guardan como hash; aun así, mantén las copias JSON privadas.

Ningún sitio web puede impedir de forma fiable que una persona use Guardar página, Ctrl+U o las herramientas de desarrollo: el navegador recibe y ejecuta el HTML, CSS y JavaScript. La protección real está en mantener reglas de negocio y permisos en el servidor, validar cada endpoint y no publicar credenciales.
