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
- Factura ficticia / fantasma generada al cobrar una mesa (`FAC-FANTASMA-XXXXX`) y panel de consulta para Administrador.
- Apertura y cierre de turnos de caja con datos completos del encargado y generación de un único recibo consolidado (`CIERRE-TURNO-XXXXX`).
- Modo Demo Local JSON (`iniciar_demo_local_json.bat` / `/bar_app?mode=local`) con exportación/importación de respaldo `.json` y acceso Multi-local vitalicio para `admin@gmail.com`.
- Bodega de reserva (`reserve_stock`), catálogo de imágenes optimizadas (`static/product_images/optimized/`) y control de suscripciones (`subscriptions`).

## Límite intencional

En modo local JSON y para el CRM de clientes del navegador, los registros locales se guardan en `localStorage` sin reemplazar las tablas MySQL del modo conectado. En modo conectado, los cobros, mesas, productos, ventas, suscripciones y usuarios utilizan las rutas Flask y la base de datos MySQL.
