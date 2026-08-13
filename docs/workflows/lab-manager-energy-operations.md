# Gestión energética de laboratorios desde Lab Manager

Esta guía describe el flujo implementado para registrar controladores de
alimentación, guardar sus credenciales, definir outlets y asociarlos a
políticas energéticas de un laboratorio. Los nombres de los controles se
mantienen en inglés porque son los que aparecen actualmente en Lab Manager.

## Qué se configura y dónde se guarda

| Elemento | Sección de Lab Manager | Persistencia actual |
| --- | --- | --- |
| Credenciales APC/SNMP/NETIO | `Energy Credentials` | Almacén JSON local cifrado en `OPS_POWER_CREDENTIALS_PATH`. Solo se devuelven referencias y tipos. |
| Controladores y outlets | `Power Controllers` | Catálogo JSON local en `OPS_POWER_CONFIG`. |
| Políticas por laboratorio | `Lab Power Control` → `Lab power policy` | El mismo catálogo JSON local. |
| Resultado e idempotencia de operaciones | `Lab Power Control`, timeline y APIs de Ops | MySQL, principalmente `power_operations`; la migración es `mysql/003-energy-policies.sql`. |
| WoL, WinRM y apagado de la estación | `Lab Station Ops` | Ops Worker, Lab Station y sus registros operativos; no son controladores PDU. |

En el MVP, `controllers`, `outlets` y `policies` siguen siendo JSON-backed. La
tabla MySQL no sustituye ese catálogo: conserva el detalle y la idempotencia
de las operaciones ejecutadas.

## Antes de empezar

1. Publica el laboratorio en la pestaña `Labs`, dentro de `Publish remote labs
   and FMU simulations from this Gateway`. El selector `Laboratory` de la
   política se rellena con esos laboratorios; no se debe escribir a mano el
   nombre visible.
2. Comprueba que el Ops Worker está habilitado y que el Gateway puede alcanzar
   la red privada del controlador. El controlador no debe estar detrás de la
   regleta que se va a apagar.
3. Configura una clave estable `OPS_SECRETS_KEY` y los valores habituales:

   ```env
   OPS_POWER_CONFIG=/app/data/power-controllers.json
   OPS_POWER_CREDENTIALS_PATH=/app/data/power-credentials.json
   ```

   En Compose, `/app/data` corresponde al volumen `ops-data`. Estos archivos
   no deben entrar en Git ni exponerse mediante una copia de seguridad sin
   protección.
4. En instalaciones existentes, aplica `mysql/003-energy-policies.sql`
   antes de activar el control físico. Sin esa migración, el worker puede
   funcionar con idempotencia limitada al proceso y no habrá historial
   durable completo.
5. Verifica WoL, WinRM y el heartbeat de Lab Station por separado siguiendo
   [Gateway and Lab Station operations](gateway-lab-station-operations.md).

El control energético usa el token de Lab Manager (`LAB_MANAGER_TOKEN`). No
requiere el token de wallet/admin que se solicita al entrar en `Notifications`.
En modo Lite, el backend remoto sigue siendo la autoridad del plano de
control, pero los controladores, el Ops Worker y la red del laboratorio siguen
siendo locales al Gateway Lite.

## Procedimiento recomendado

### 1. Registrar la credencial del dispositivo

En `Energy` → `Energy Credentials`:

1. Deja `Existing credential` en `New credential`.
2. Introduce una `Credential reference` estable, por ejemplo
   `pdu-lab-01-snmp`. Debe empezar por minúscula o número y solo usar
   minúsculas, números, `.`, `_`, `:` o `-`.
3. Elige el tipo que corresponde al driver:

   | Tipo | Uso |
   | --- | --- |
   | `NETIO HTTP Basic` | Usuario y contraseña de la API HTTP(S) de NETIO. |
   | `SNMP v1` / `SNMP v2c` | Comunidad SNMP y versión correspondiente. |
   | `SNMP v3` | Usuario, autenticación, privacidad y, si aplica, `context name`. |

4. Pulsa `Save Credential`.

La referencia sí puede aparecer en el catálogo y en la interfaz; la comunidad,
las contraseñas y los tokens no. El API devuelve únicamente metadatos. Si se
selecciona una referencia existente, se está iniciando una rotación: introduce
el nuevo secreto y vuelve a pulsar `Save Credential`. El controlador conserva
la misma referencia y el runtime se recarga cuando es posible.

### 2. Registrar el controlador y sus outlets

En `Energy` → `Power Controllers`, pulsa `New controller` y completa:

- `Controller ID`: identificador estable usado por las políticas, por ejemplo
  `pdu-lab-01`.
- `Name`: nombre legible para el operador.
- `Driver`: `APC PowerNet SNMP`, `NETIO REST JSON` o `Mock (development)`.
- `Enabled`, `Host / IP address`, `Port` y `Credential reference`.
- `Timeout (seconds)` y `Retries` adecuados para la red privada.

Para APC:

- Usa normalmente el puerto SNMP `161`.
- Selecciona el `APC profile`: `Auto-detect`, `Legacy PowerNet` o `rPDU2`.
- Fija `SNMP version` si no se quiere dejar el valor por defecto del driver.
- La credencial debe ser de tipo SNMP y coincidir con esa versión.

Para NETIO:

- Usa `NETIO REST JSON` y el puerto HTTP/HTTPS que exponga el dispositivo.
- Mantén `NETIO API path` en `/netio.json`, salvo que el firmware requiera
  otro path.
- Activa `Use HTTPS` y deja `Verify TLS certificate` activado cuando el
  certificado sea verificable. Desactivarlo debe limitarse a un caso local
  controlado.
- La credencial debe ser de tipo `NETIO HTTP Basic`.

Después, en `Outlets`, pulsa `Add outlet` por cada toma que vaya a usar una
política. Para cada una define:

- el identificador real de la toma (`outlet`), tal como lo espera el driver;
- `Display name` y `Logical name` para que el operador reconozca el equipo;
- `Default state`, normalmente `Off`;
- `Critical` para equipos necesarios para arrancar o cerrar el laboratorio;
- `Protected` para tomas que no deben accionarse accidentalmente.

Los identificadores de outlet deben ser únicos dentro del controlador. Pulsa
`Save Controller`. El catálogo se guarda en `OPS_POWER_CONFIG` y el worker
recarga el runtime. Si el controlador real no responde durante la recarga, la
configuración puede persistir, pero las operaciones fallarán hasta corregir la
conectividad o las credenciales.

### 3. Crear la política del laboratorio

En `Energy` → `Lab Power Control` → `Lab power policy`:

1. Deja `Existing policy` en `New policy`.
2. Selecciona el laboratorio en `Laboratory`. Este selector solo muestra los
   laboratorios publicados en `Labs`.
3. Define `Policy name` y activa `Enabled`.
4. Mantén `Respect local mode` activado salvo que exista un procedimiento de
   mantenimiento explícito. Así se evita que una automatización remota
   interfiera con el modo local de la estación.
5. Usa `Maintenance mode` solo para una política de mantenimiento controlada.
6. Como valor inicial, usa `Fail reservation start` para acciones críticas de
   arranque y `Warn and continue` para la limpieza de fin de reserva cuando
   el apagado no deba bloquear el resto del flujo.
7. Pulsa `Add step` y define las acciones.

Cada step contiene, como mínimo, `Phase`, `Sequence`, `Controller`, `Outlet`
y `Action`. Las acciones son `on`, `off` y `cycle`. También se pueden ajustar
`Desired state`, tiempos de ciclo, retrasos, timeout, reintentos y las opciones
`Required`, `Read back state` y `Allow protected outlet`. `Conditions` es un
campo JSON avanzado y opcional; debe contener un objeto JSON válido.

Las fases disponibles son:

| Fase | Uso habitual |
| --- | --- |
| `pre_start` | Encender PLC, HMI u otros equipos antes de despertar/preparar la estación. |
| `start` / `post_start` | Acciones durante o después de la preparación. |
| `pre_end` | Preparar el apagado antes de liberar la reserva. |
| `end` / `post_end` | Apagar equipos no críticos y después los críticos. |
| `manual`, `maintenance`, `emergency_stop` | Procedimientos explícitos fuera del ciclo normal. |

El `Sequence` debe ser único dentro de cada fase. Una política inicial típica
es encender primero los outlets críticos en `pre_start` y apagarlos al final,
en orden inverso, en `post_end`. No incluyas en la política la regleta, el
switch, el Gateway, el host de Guacamole o cualquier equipo que mantenga la
conectividad y el control del laboratorio.

Pulsa `Save Policy`. La política se guarda asociada al `labId` seleccionado,
no al nombre del laboratorio. Cambiar posteriormente el nombre visible del
lab no debe generar otra política.

### 4. Probar de forma controlada

Empieza siempre con un outlet no crítico y una razón operativa clara en
`Operation reason`.

1. En la lista de `Lab Power Control`, comprueba que el controlador aparece,
   que los outlets tienen el nombre esperado y que el estado no es `unknown`.
2. Ejecuta `On`, espera a que el equipo arranque y comprueba el estado leído.
3. Ejecuta `Off` solo si el equipo tolera esa prueba.
4. Usa `Cycle` únicamente cuando el tiempo de apagado (`Cycle off time`) sea
   compatible con el equipo.
5. Para un outlet `Protected`, activa primero `Maintenance mode`. La UI y el
   API rechazan la acción si no existe ese override explícito.
6. Revisa la operación en el historial y en la timeline de la reserva.

Para una prueba de política sin conmutar hardware se puede usar el endpoint
protegido de Ops con `dryRun`:

```http
POST /ops/api/labs/<labId>/power/start
Content-Type: application/json

{"reservationId":"energy-dry-run-001","actor":"lab-manager","dryRun":true}
```

La fase equivalente de cierre es `POST /ops/api/labs/<labId>/power/end`.
Para revisar operaciones de una reserva:

```http
GET /ops/api/power/operations?reservationId=energy-dry-run-001
```

El driver `Mock (development)` está destinado a desarrollo y CI. Su estado se
puede reiniciar con `POST /ops/api/power/mock/reset`; no debe usarse como
validación de conectividad de un dispositivo físico.

## Integración con reservas, WoL y Lab Station

Cuando `OPS_RESERVATION_AUTOMATION=true` y existe una política habilitada, el
flujo normal es:

| Momento | Operación |
| --- | --- |
| Antes de comenzar | Fase `pre_start` de la política. |
| Preparación | WoL y `prepare-session` de Lab Station; las fases `start`/`post_start` se ejecutan según el scheduler. |
| Antes de terminar | Fase `pre_end`, si está definida. |
| Liberación | `release-session` y la operación de cierre configurada. |
| Después de terminar | Fase `post_end`, normalmente para apagar outlets. |

La automatización energética no reemplaza WoL, WinRM, heartbeat ni el control
de sesión de Lab Station. Son capas complementarias. `respectLocalMode` evita
aplicar la política cuando el heartbeat indica que la estación está siendo
operada localmente, de acuerdo con el flujo implementado.

## Rotación y mantenimiento de credenciales

Para rotar una credencial de un APC, NETIO u otro controlador compatible:

1. Entra en `Energy` → `Energy Credentials`.
2. Selecciona la referencia existente.
3. Introduce el nuevo secreto, manteniendo el tipo correcto.
4. Guarda y ejecuta una lectura de estado o una prueba manual no crítica.

No hace falta editar `power-controllers.json`: el `credentialRef` no cambia.
La UI no carga el secreto anterior en el navegador y el API no lo devuelve.

La rotación de la clave maestra `OPS_SECRETS_KEY` es una operación distinta de
la rotación de una contraseña de dispositivo. Debe hacerse en una ventana de
mantenimiento, conservando juntos una copia protegida de la clave nueva y del
almacén cifrado. El script existente `rotate_secrets.py` documentado en
`ops-worker/README.md` valida el formato del almacén de credenciales WinRM;
no debe ejecutarse a ciegas sobre un almacén de energía que contenga entradas
SNMP. Para el MVP, la interfaz de Lab Manager cubre la rotación de secretos de
dispositivo, que es la operación habitual.

## Diagnóstico rápido

| Síntoma | Comprobaciones |
| --- | --- |
| `Laboratory` no muestra el lab | Publicarlo en `Labs`, comprobar que la sesión usa el Lab Manager token y recargar la lista. |
| No aparecen credenciales | `OPS_POWER_CREDENTIALS_PATH`, `OPS_SECRETS_KEY`, permisos del volumen y logs del Ops Worker. |
| El controlador aparece pero está `unknown` | Host/IP, puerto, ruta privada, driver, perfil/versiones y referencia de credencial. |
| No aparece un outlet en la política | Guardarlo dentro del controlador y usar el identificador real del outlet. |
| Se rechaza un outlet protegido | Activar `Maintenance mode` para una prueba autorizada; no desprotegerlo solo para evitar el control. |
| La política se guarda pero no se ejecuta | `Enabled`, `labId`, migración `003`, automatización de reservas y `Respect local mode`. |
| Una acción requerida aborta el arranque | Revisar conectividad, lectura de estado, timeout/reintentos y `Start failure mode`. |
| No hay historial durable | Verificar que `power_operations` existe y que el worker puede conectarse al MySQL del Gateway. |
| Lab Manager funciona remotamente pero Ops no | `/ops/` está restringido a loopback y redes RFC1918; acceder desde el Gateway o la red privada. |

## Referencias relacionadas

- [Ops Worker README](../../ops-worker/README.md): variables, drivers, almacenes y límites de seguridad.
- [Gateway and Lab Station operations](gateway-lab-station-operations.md): WoL, WinRM, heartbeat, reservas y timeline.
- [Laboratory connectivity](laboratory-connectivity.md): topología y segmentación de la red privada.
- [Lab Station WoL and energy playbook](../../../Lab Station/docs/bios-wol-playbook.md): BIOS, NIC, WoL y diagnósticos de la estación.
- [`power-controllers.sample.json`](../../ops-worker/power-controllers.sample.json): estructura JSON de ejemplo.
- [`003-energy-policies.sql`](../../mysql/003-energy-policies.sql): historial durable e idempotencia.
