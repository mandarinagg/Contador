# Instrucciones para Claude en este proyecto

## Forma de trabajo: orquestador y agentes

- La sesión principal (Opus) es el **jefe orquestador**: entiende el pedido, decide el plan, reparte las tareas, revisa lo que devuelven los agentes, integra, verifica y hace commit.
- **Lectura → agentes con `model: haiku`**: buscar en el código, leer archivos, logs o documentos, mapear un flujo, resumir.
- **Escritura → agentes con `model: sonnet`**: todo lo que escriba código, pruebas o texto (documentación, traspaso en `docs/PROJECT_STATUS.md`, decisiones).
- Cada encargo lleva el contexto completo: archivos, causa encontrada, criterio de aceptación y qué pruebas correr. El agente no ve la conversación.
- El orquestador no da por buena una tarea sin revisar el diff y ver pasar las pruebas.
