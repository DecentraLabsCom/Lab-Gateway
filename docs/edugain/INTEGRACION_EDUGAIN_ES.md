# Guia Tecnica de Integracion eduGAIN

Este documento cubre la preparacion tecnica para el onboarding federado mediante eduGAIN/NREN.

## 1. Alcance

El gateway no se registra automaticamente en eduGAIN. El registro es un proceso externo de federacion que requiere:

- titularidad institucional del metadata
- flujo de federacion del NREN (por ejemplo RedIRIS en Espana)
- contactos operativos y de soporte

## 2. Entradas necesarias

1. URL publica del servicio y cadena TLS.
2. Definicion de EntityID y URL de metadata.
3. Claves de firma y politica de rotacion.
4. Politica de liberacion de atributos (nameID, ePPN, mail, scoped affiliation).
5. Contacto de seguridad/incidentes y contacto de soporte.

## 3. Checklist tecnico del gateway

1. Endpoints OpenID/OAuth accesibles via OpenResty:
   - `/.well-known/openid-configuration`
   - `/auth/jwks`
2. URL de issuer estable basada en `SERVER_NAME` y `HTTPS_PORT`.
3. Validacion de tokens y audiencias alineada con identidad federada.
4. CORS y callbacks alineados con dominios publicos finales.
5. Monitorizacion y logs habilitados para rutas de autenticacion.

## 4. Checklist de envio al NREN

1. Preparar paquete de metadata solicitado por el NREN.
2. Enviar endpoints de servicio y certificados.
3. Validar flujo de login en federacion de pruebas.
4. Resolver observaciones de validacion de metadata.
5. Solicitar propagacion al agregado eduGAIN.

## 5. Evidencia a guardar en el repositorio

Cuando se completen los pasos externos, anadir referencias en `docs/pilots/`:

- IDs de tickets de registro
- informes de validacion federada
- fecha de publicacion en metadata
- limitaciones/incidencias abiertas

## 6. Notas de seguridad

- No versionar claves privadas de firma.
- Documentar procedimiento de rotacion y revocacion.
- Mantener contactos propietarios para incidencias de confianza federada.
