# Barrica

La aplicación usa Python (Flask) para servir la página y exponer la API de
registro e inicio de sesión. El navegador conserva HTML, CSS y JavaScript para
mostrar la interfaz y comunicarse con el backend.

## Ejecutar localmente

1. Instala Python 3.12 o posterior.
2. Desde esta carpeta, crea el entorno virtual y las dependencias:

   ```powershell
   py -m venv .venv
   .\.venv\Scripts\python.exe -m pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

3. Abre `.env` y completa los datos de una base MySQL accesible desde tu PC:
   `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME` y `DB_SSL`.
   Coloca el certificado CA del proveedor en `ca.pem` junto a `app.py`;
   `DB_SSL_CA` puede indicar una ruta diferente. No uses `localhost` en
   Vercel; allí se necesita un host de MySQL accesible desde internet.
4. Ejecuta el esquema de `database/schema.sql` en esa base.
5. Inicia el sitio:

   ```powershell
   .\.venv\Scripts\python.exe app.py
   ```

   Abre `http://127.0.0.1:5000`.

## Desplegar en Vercel

1. Ejecuta `database/schema.sql` en la base MySQL alojada.
2. En Vercel, configura las variables `DB_HOST`, `DB_PORT`, `DB_USER`,
   `DB_PASSWORD`, `DB_NAME` y `DB_SSL` en **Settings → Environment Variables**.
   Usa los datos del proveedor de MySQL; no subas `.env` al repositorio.
   Incluye también `ca.pem` en el despliegue (o configura `DB_SSL_CA` con la
   ruta del certificado que hayas incluido).
3. En **Settings → Build and Deployment**, configura la raíz del proyecto a
   esta carpeta (la que contiene `app.py` y `requirements.txt`), sin un
   directorio de salida personalizado.
4. Despliega de nuevo el proyecto. Vercel detecta Flask desde `app.py` y las
   dependencias de `requirements.txt`.
5. Comprueba `https://TU-DOMINIO/api/auth/session`: sin una cookie de sesión
   debe responder `{"user":null}`. Esto verifica que Flask está publicado,
   pero no prueba la conexión a MySQL; crea una cuenta de prueba para validar
   también la base de datos.

## API

- `POST /api/auth/register` recibe `{ "name": "...", "email": "...", "password": "..." }`.
- `POST /api/auth/login` recibe `{ "email": "...", "password": "..." }`.
- `GET /api/auth/session` comprueba la cookie de sesión.
- `POST /api/auth/logout` cierra la sesión.
- `POST /api/payments/simulate` valida un pago **ficticio** y devuelve un
  comprobante de prueba (`simulated: true`). Recibe `plan` (`basico`, `pro` o
  `multilocal`), `currency` (`USD` o `COP`), `payer_name`, `email`,
  `document_type` (`CC`, `CE` o `NIT`), `document_number`, `phone`,
  `card_holder`, `card_last4` y `card_brand`.

## Precios y pago de prueba

- Los planes se muestran en dólares y en pesos colombianos con una tasa de
  referencia fija: `COP_PER_USD = 4000` en `app.py`. Si la cambias, actualiza
  también `data-cop` de cada plan en `Untitled-1.html`; la prueba
  `test_html_prices_match_server_plans` falla si los dos no coinciden.
- El servidor calcula el monto con su propia tabla de precios (`PLANS`); nunca
  confía en un monto enviado por el navegador.
- El pago no cobra nada ni guarda nada. El número completo de la tarjeta, el
  vencimiento y el CVV se validan en el navegador y **no se envían**: al servidor
  solo llegan los últimos 4 dígitos para mostrarlos en el comprobante.
- El comprobante está marcado como "Pago de prueba, sin validez".
- Campos solo numéricos (documento, teléfono, tarjeta, vencimiento y código de
  seguridad) y nombres sin números: se filtran al escribir o pegar y el servidor
  vuelve a validarlos.

Las contraseñas se almacenan con bcrypt; la sesión usa una cookie `HttpOnly`,
`SameSite=Strict`, y el token se guarda en MySQL como hash. Las contraseñas
requieren al menos 12 caracteres y no pueden superar 72 bytes UTF-8.
El registro no confirma el correo ni crea una suscripción. La página actual
tampoco incluye el panel operativo del bar ni procesa pagos.

## Pruebas

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```
