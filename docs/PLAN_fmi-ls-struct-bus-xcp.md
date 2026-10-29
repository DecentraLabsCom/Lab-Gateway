# Plan: añadir FMI-LS-STRUCT, FMI-LS-BUS y FMI-LS-XCP

**Estado:** propuesta de implementación

**Fecha:** 2026-10-30

**Ámbito:** FMU Executor, Lab Gateway y Marketplace; Lab Station cuando publique el nuevo Executor.

## Decisión resumida

Implementar los tres estándares por capacidad, sin confundir detectar una extensión con soportarla por completo:

1. **STRUCT primero:** interpretar los mapas declarados en FMI 3.0 y hacerlos utilizables en los formularios y resultados de simulación.
2. **XCP después, inicialmente de solo lectura:** describir interfaces y permitir obtener sus ficheros A2L con autorización. No abrir ni retransmitir XCP en la primera entrega.
3. **BUS en dos pasos:** publicar y entender sus descriptores; dejar la ejecución de redes para cuando exista composición de varios FMU. Un FMU aislado no ofrece la simulación de red que define esta extensión.

La portada oficial del FMI enumera actualmente XCP 1.0.0, BUS 1.3.0-beta.1 y STRUCT 1.0.0-rc.1. Antes de implementar cada lector se fijará una versión concreta y se comprobará el estado de su esquema; BUS y STRUCT siguen teniendo partes en pre-release. [Estado de los Layered Standards](https://fmi-standard.org/).

## Punto de partida de DecentraLabs

- El Executor interpreta FMI y FMI-LS-REF para descubrir recursos relacionados y conjuntos SSP; Marketplace permite seleccionar un preset de proveedor en el formulario de simulación.
- Gateway proyecta los recursos REF en el submodelo AAS versionado `FmiLsRelatedResources`; el FMU continúa siendo la fuente de verdad y AAS publica descriptores, no los valores de parámetros ni los bytes de los recursos.
- El flujo de simulación actual se centra en ejecutar un FMU por trabajo. No hay todavía un importador de sistemas SSP que conecte instancias de FMU ni un servicio XCP.

La extensión debe encajar en ese flujo: Executor interpreta los metadatos y ofrece capacidades; Gateway conserva el límite de autorización, crea las referencias AAS y sirve artefactos protegidos; Marketplace presenta los metadatos y controles que el Executor pueda ejecutar.

## Diseño común

### Descubrimiento y degradación segura

- Buscar cada manifiesto únicamente en la ruta prescrita por su estándar, dentro del FMU:
  - `extra/org.fmi-standard.fmi-ls-struct/fmi-ls-manifest.xml`
  - `extra/org.fmi-standard.fmi-ls-bus/fmi-ls-manifest.xml`
  - `extra/org.fmi-standard.fmi-ls-xcp/fmi-ls-manifest.xml`
- Mantener separados el resultado de detección, la validez del manifiesto y las capacidades realmente ejecutables. Versiones futuras o elementos desconocidos se conservan como “detectados, no interpretados” y no habilitan controles.
- Reutilizar los límites de lectura del ZIP y XML ya aplicados a FMU/AASX. No resolver referencias remotas, URI absolutas ni rutas que salgan del archivo; imponer límites de tamaño y cantidad de elementos.
- El manifiesto del Layered Standard se combina con `modelDescription.xml` y, donde corresponda, `terminalsAndIcons/terminalsAndIcons.xml`. Ningún manifiesto por sí solo basta para prometer que una operación funciona.

### Proyección AAS

Añadir proyecciones generadas y opcionales, solo cuando se detecte cada extensión: `FmiLsStruct`, `FmiLsBus` y `FmiLsXcp`, con semantic IDs DecentraLabs versionados y contratos documentados. Cada proyección debe incluir el nombre y versión del estándar, el estado de interpretación y sus referencias FMI relevantes.

Publicar estructura, nombres de interfaz, tipos de bus, aplicabilidad y disponibilidad de artefactos solo según la política de publicación del laboratorio. No copiar a AAS los valores de calibración/mapa, binarios de red, ficheros A2L ni direcciones de memoria. Los artefactos se entregan mediante rutas autenticadas y autorizadas por reserva. El FMU sigue siendo la fuente de verdad y la sincronización vuelve a generar la proyección.

REF puede seguir dando un índice uniforme de archivos que el proveedor haya descrito allí. No se asumirá que todos los A2L o ficheros de red estén declarados en REF: cada extensión conserva sus propias referencias y reglas de resolución.

## FMI-LS-STRUCT: mapas en formularios y simulación

STRUCT usa los terminales FMI 3.0 para agrupar variables de mapas. Define mapas en rejilla rectilínea y en rejilla irregular, con miembros `domain`, `domainInput`, `codomain` y `codomainOutput`. El manifiesto indica que debe interpretarse esta semántica; la información detallada está en `terminalsAndIcons.xml`. [Especificación FMI-LS-STRUCT](https://modelica.github.io/fmi-ls-struct/main/).

### Alcance de la primera entrega

1. **Executor:** leer de forma conjunta el manifiesto, los terminales y las definiciones de variables; producir un descriptor normalizado por mapa con su tipo, ejes, variables miembro, dimensiones, tipo de dato, unidades disponibles, anotaciones de orden y variables de punto de operación/salida.
2. **Validación:** comprobar referencias a variables existentes, compatibilidad entre miembros, dimensiones de arrays y reglas de orden cuando estén declaradas. Si una agrupación está incompleta o no se entiende, mostrar sus variables de forma convencional y devolver un diagnóstico; no impedir la simulación base.
3. **Valores:** verificar primero que el contrato existente de Executor puede leer y escribir arrays FMI 3.0 en todos los caminos usados por los formularios y trabajos. Completar esa capacidad solo donde falte, con las restricciones de causalidad y política ya aplicadas a variables escalares.
4. **Marketplace:** agrupar las variables de mapa en el formulario en vez de mostrarlas como campos planos. Ofrecer una vista tabular para editar las tablas de parámetros y presentar los puntos de operación y resultados vinculados. Mantener el formulario escalar para variables que no formen parte de un mapa y el selector acordado de presets REF.
5. **AAS:** proyectar el agrupamiento, el tipo de mapa y sus relaciones semánticas para uso público/M2M, con arrays y valores sujetos a la política de publicación y acceso vigente.

La primera UI debe editar y visualizar datos del mapa; no implementará un interpolador o solver nuevo. El formato describe la estructura y los valores que consume el FMU, no reemplaza su lógica de ejecución.

### Criterios de salida

- Un FMU de ejemplo de cada tipo de mapa aparece agrupado correctamente; el usuario puede modificar los parámetros permitidos, ejecutar y ver los resultados.
- Los metadatos inválidos o desconocidos no habilitan controles incorrectos ni bloquean las funciones FMI existentes.
- La salida de Marketplace y el descriptor AAS no filtran valores que no estén permitidos por la política del laboratorio.

## FMI-LS-XCP: catálogo de calibración antes de servicio XCP

XCP declara una o más interfaces ligadas a ficheros A2L. El manifiesto distingue un servicio XCP interno (`containsXCPService`) del acceso directo a memoria (`supportsDirectMemoryAccess`) y puede asignar roles XCP a variables FMI. La resolución de A2L puede depender de si se utiliza FMU de código fuente o un binario de plataforma. [Especificación FMI-LS-XCP](https://fmi-standard.org/fmi-ls-xcp/1.0.0/).

### Primera entrega: descripción y descarga protegida

1. Executor lee interfaces, descripciones, tipos FMI aplicables, indicadores de servicio/acceso directo, asociaciones de variables y referencias A2L.
2. Resuelve el fichero A2L para el artefacto/plataforma elegido según la regla normativa. Rechaza dot-segments, escapes de directorio y referencias no locales.
3. Gateway incluye el resumen en `FmiLsXcp` y ofrece A2L solamente con reserva/autorización válida, a través de una ruta de descarga limitada a los archivos del FMU y con MIME/nombre seguros.
4. Marketplace indica si el FMU declara XCP y permite descargar el A2L autorizado para abrirlo con la herramienta MCD del usuario. No presenta “conectar” mientras la plataforma no provea esa función.

### Fuera de la primera entrega

No implementar un XCP master, un XCP slave externo, acceso directo a memoria ni un túnel TCP/UDP hacia el FMU. Esos caminos requieren administrar puertos y ciclo de vida dentro del contenedor/estación, concurrencia, exposición de endpoints, aislamiento entre reservas y tratamiento de permisos de calibración. La indicación de soporte del FMU no autoriza por sí sola ese acceso.

Una fase interactiva posterior necesitaría una decisión de arquitectura y seguridad, una integración XCP interoperable con la herramienta cliente y controles de acceso diferenciados para medida y escritura. Mantener fuera de esa fase las afirmaciones de conformidad hasta cubrir ambas variantes del estándar que se decida soportar.

### Criterios de salida

- Interfaces y variables quedan ligadas al A2L correcto para el target ejecutado.
- Una reserva válida puede descargar el A2L correspondiente; sin autorización no se entrega ni se inicia tráfico XCP.
- Los datos de dirección/memoria del A2L no se publican indiscriminadamente en el submodelo AAS.

## FMI-LS-BUS: metadatos ahora, composición de red como fase separada

BUS define dos niveles de abstracción: Physical Signal Abstraction (High-Cut), que intercambia señales físicas, y Network Abstraction (Low-Cut), que expone operaciones y payloads de red. Define tres arquitecturas: comunicación directa entre dos FMU, composición con un FMU de simulación de bus, o importador con simulación integrada. La versión 1.0.0 publicada cubre CAN, CAN FD y CAN XL en Network Abstraction; las versiones posteriores amplían el alcance y siguen siendo pre-release según el catálogo oficial. [Especificación BUS 1.0.0](https://fmi-standard.org/fmi-ls-bus/1.0.0/) · [Guía BUS en desarrollo](https://modelica.github.io/fmi-ls-bus/main/).

### Paso A: descubrimiento y catálogo

1. Executor detecta el manifiesto, `isBusSimulationFMU`, interfaces FMI 3.0 y tipos de terminales BUS.
2. Interpreta los terminales de High-Cut y Low-Cut con sus clocks y variables miembro, y resume si el FMU declara un simulador de bus.
3. Gateway refleja esa capacidad en `FmiLsBus`; las señales de red y descriptores como DBC/LDF/FIBEX/ARXML no se copian como valores ni se descargan sin autorización.
4. Marketplace indica la composición requerida y diferencia “descrito” de “ejecutable aquí”. No ofrece un botón de simulación BUS hasta que la composición de sistemas esté implementada.

### Paso B: ejecución de sistemas, condicionada a un caso piloto

BUS real requiere aceptar y validar una composición de componentes, instanciar más de un FMU, conectar terminals de forma compatible, coordinar FMI 3.0 clocks y tipos `Binary`, y hacer que el sistema respete el tiempo/semántica del nivel de red. Para una simulación detallada puede necesitarse un FMU dedicado de bus. Eso no se puede resolver solo exponiendo los inputs y outputs de un FMU individual.

Antes de esta fase hay que elegir un artefacto de composición soportado (por ejemplo, un sistema SSP), un tipo de bus inicial y la arquitectura de ejecución. Propuesta para el piloto: FMI 3.0 Co-Simulation con dos FMU y CAN High-Cut; ampliar a Network Abstraction/CAN mediante un bus simulation FMU cuando la ejecución multi-componente pase sus criterios. No prometer FlexRay, Ethernet o LIN basándose en una rama draft; fijar soporte por versión normativa probada.

### Criterios para autorizar el paso B

- Existe un sistema real de usuario que requiere ejecutar más de un FMU conectado, con los FMU de ejemplo y sus licencias disponibles.
- La composición preserva aislamiento, límites de CPU/memoria, cancelación, autorización de recursos y registro por reserva como los trabajos actuales.
- Se valida la composición con fixtures oficiales para la versión fijada, incluida sincronización de clocks, matching de terminales y diagnósticos de conexión incompatible.

## Orden de implementación y responsabilidades

| Fase | Cambio principal | Componentes |
|---|---|---|
| 0 | Fijar versiones/esquemas de STRUCT, XCP y BUS; incorporar FMU fixtures oficiales con permisos/licencias documentados; acordar el contrato de capacidades normalizadas. | Executor |
| 1 | Crear los parsers y modelos de descriptor; validar referencias, tamaños, rutas y compatibilidad sin afectar a la simulación base. | Executor |
| 2 | Completar la lectura/escritura de arrays si hace falta; añadir formularios de mapas STRUCT y salidas. | Executor, Marketplace |
| 3 | Proyectar mapas y recursos A2L/BUS a submodelos AAS; añadir descargas de artefactos protegidas donde proceda. | Gateway, Marketplace |
| 4 | Publicar descubrimiento BUS y el resumen AAS/UI, dejando explícito que no implica poder ejecutar una composición. | Executor, Gateway, Marketplace |
| 5 | Prototipo y producto de composición multi-FMU BUS, solo tras acordar el caso piloto y la topología. | Executor, Gateway, Lab Station |
| 6 | Evaluar ejecución XCP interactiva por separado; no incluirla en el despliegue hasta cerrar arquitectura, permisos y aislamiento. | Executor, Gateway, Lab Station, Marketplace |

Al publicar el Executor con las fases aplicables, actualizar el artefacto/pin que distribuye Lab Station y documentar la versión mínima requerida. Marketplace debe consumir solo capacidades publicadas por Gateway/Executor, no inferirlas por el nombre del archivo ni ofrecer opciones que no puedan ejecutarse.

## Riesgos y límites

- **Estándares en evolución:** especialmente BUS y STRUCT. Los parsers deben estar versionados y probarse contra el release objetivo; pre-release nuevo no debe cambiar silenciosamente la semántica desplegada.
- **Sensibilidad de metadatos:** los nombres de calibración, mapas, señales y A2L pueden revelar diseño o direcciones internas; la proyección pública necesita campos explícitos permitidos.
- **Superficie de archivo:** A2L y bases de red son entradas del paquete. Toda extracción y descarga debe reutilizar validación de ZIP, límites de tamaño y autorización por reserva.
- **Alcance de producto:** BUS introduce simulación de sistemas, no una opción visual de un único FMU. XCP agrega interacción con herramientas externas y servicios de red. Mantener esas dos fases de ejecución separadas del trabajo acotado de metadatos.
- **AAS generado e importado:** definir una única regla de autoridad. La sincronización desde FMU deriva las proyecciones; una importación AASX no debe poder sustituir referencias FMU o elevar capacidades declaradas sin validarlas contra el artefacto actual.

## Fuentes normativas

- [Catálogo oficial de FMI Layered Standards](https://fmi-standard.org/)
- [FMI-LS-STRUCT, especificación en desarrollo](https://modelica.github.io/fmi-ls-struct/main/)
- [FMI-LS-BUS 1.0.0, especificación publicada](https://fmi-standard.org/fmi-ls-bus/1.0.0/)
- [FMI-LS-BUS, especificación e implementers’ guide en desarrollo](https://modelica.github.io/fmi-ls-bus/main/)
- [FMI-LS-XCP 1.0.0](https://fmi-standard.org/fmi-ls-xcp/1.0.0/)
