# language: es

Característica: Verificación del sistema
  Como equipo de automatización
  Quiero comprobar que el sistema está desplegado y operativo a través del gateway
  Para detectar fallos de despliegue antes de automatizar los flujos de negocio

  Escenario: Sistema responde
    Dado sistema desplegado y operativo
    Entonces respuesta código 200
