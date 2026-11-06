# Integración sobre Gestion-Bar-master

Esta versión se construyó sobre el archivo original modificado recibido, sin reemplazar sus funciones existentes.

## Se conservaron

- `bar_app.html` como aplicación operativa real.
- Descarga de `BarricaDesktop.exe` para Windows.
- Descarga de `Barrica-Movil.html`.
- Instalación PWA en `/app` con manifest, icono y service worker.
- Inicio de sesión real con perfiles Administrador y Vendedor.
- Mesas, pedidos, división de cuentas y cobros.
- Inventario MySQL y alertas de stock.
- Panel de usuarios, sesiones y ventas.
- Pago de prueba y comprobante ficticio.
- `desktop/BarricaDesktop.cs` y `downloads/BarricaDesktop.exe`.
- `database/schema.sql`, `database/backup_barrica.sql`, `database/run_schema.py` y `conection.py` sin cambios.

## Agregado sin tocar SQL

- Iconos visuales para WhatsApp, Instagram, TikTok, Gmail, Facebook y X.
- Botón flotante de atención al cliente por WhatsApp.
- Mapa de Google Maps del Corredor Ecológico de Villavicencio.
- Aviso flotante de novedades/mantenimiento/eventos.
- Recomendaciones de lugares de Villavicencio.
- Módulo local de clientes en la aplicación operativa.
- Campos de cliente: nombre, correo, teléfono, dirección, ciudad y país.
- Clasificación imprimible de clientes por país.
- Selector de cliente para una cuenta cobrada.
- Factura ficticia local generada al cobrar una mesa.
- Historial e impresión de facturas ficticias.

## Límite intencional

Clientes y facturas nuevas se guardan en `localStorage` bajo `barrica-crm-local-v1`, porque la solicitud indicó dejar SQL quieto. No reemplazan las tablas MySQL. Los cobros, mesas, productos, ventas y usuarios existentes siguen utilizando las rutas Flask y la base de datos original.

No se hizo ningún `git push` ni se modificó GitHub.
