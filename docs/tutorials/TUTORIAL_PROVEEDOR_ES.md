# Tutorial para Proveedores de Laboratorio (Espanol)

Este tutorial explica como publicar y operar un laboratorio remoto con DecentraLabs Gateway.

## 1. Requisitos previos

- Gateway desplegado y saludable (`/health` y `/gateway/health`).
- Acceso a credenciales admin de Guacamole.
- Token valido para rutas protegidas (`SECURITY_ACCESS_TOKEN` y opcional `LAB_MANAGER_TOKEN`).
- Inventario de hosts configurado en ops-worker si se requiere control remoto de energia/sesion.

## 2. Configurar conexiones Guacamole

1. Abrir `https://<dominio-gateway>/guacamole`.
2. Iniciar sesion con `GUAC_ADMIN_USER` y `GUAC_ADMIN_PASS`.
3. Crear conexiones RDP/VNC/SSH para cada laboratorio.
4. Verificar login de prueba en cada conexion.

Referencia: `configuring-lab-connections/guacamole-connections.md`.

## 3. Preparar capa de autenticacion/wallet

1. Abrir `https://<dominio-gateway>/wallet-dashboard`.
2. Configurar o importar wallet institucional cuando aplique.
3. Validar endpoints de autenticacion:
   - `/.well-known/openid-configuration`
   - `/auth/jwks`
4. Confirmar que el acceso por reserva esta habilitado en tu politica.

## 4. Configurar Ops Worker (opcional, recomendado)

1. Editar archivo de hosts con el inventario de laboratorios.
2. Definir credenciales WinRM por variables de entorno.
3. Configurar `MYSQL_DSN` y automatizacion de reservas si aplica.
4. Verificar:
   - `GET /ops/health`
   - `POST /ops/api/wol`
   - `POST /ops/api/winrm`

## 5. Publicar y validar flujo extremo a extremo

1. Simular o crear una reserva.
2. Autenticarse por wallet/SSO.
3. Confirmar acceso a la sesion Guacamole.
4. Revisar logs de OpenResty, blockchain-services y ops-worker.

## 6. Checklist operativo

- Rotar credenciales admin y base de datos.
- Monitorizar expiracion y renovacion de certificados.
- Mantener actualizado submodulo y versiones de contenedores.
- Ejecutar pruebas de integracion/smoke antes de cambios productivos.
