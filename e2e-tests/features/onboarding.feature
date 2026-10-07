# language: es

Característica: Onboarding asíncrono de empleados
  Como equipo de automatización
  Quiero verificar que el alta de un empleado se propaga de forma asíncrona
  Para asegurar que auth crea la cuenta y que el medio email simulado registra
  la notificación, sin esperas fijas y con evidencia observable

  Antecedentes:
    # Pasos reutilizados del Punto 3: login ADMIN y departamento idempotente.
    Dado que inicio sesión como "admin"
    Y que existe el departamento "E2E-P4-DEPT"

  Escenario: El alta crea la cuenta del usuario en auth (eventualmente)
    Cuando registro el empleado de onboarding "E2E-P4"
    Entonces eventualmente auth creó el usuario para el email del empleado

  Escenario: El alta genera la notificación de bienvenida por el medio simulado (eventualmente)
    Cuando registro el empleado de onboarding "E2E-P4"
    Entonces eventualmente llega la notificación de bienvenida al email del empleado
    Y la notificación de bienvenida es un correo simulado al email del empleado

  Escenario: El empleado nuevo establece su contraseña y puede iniciar sesión
    Cuando registro el empleado de onboarding "E2E-P4"
    Entonces eventualmente auth creó el usuario para el email del empleado
    Cuando el empleado establece su contraseña con el token de la notificación
    Entonces puede iniciar sesión con la contraseña establecida
    Y su cuenta quedó activa para el rol "USER"

  Escenario: El alta con un departamento inexistente es rechazada
    Cuando registro el empleado de onboarding "E2E-P4" con un departamento inexistente
    Entonces respuesta código 400
    Y la respuesta explica que el departamento no existe

  Escenario: El alta con campos obligatorios faltantes es rechazada
    Cuando registro el empleado de onboarding "E2E-P4" con campos obligatorios faltantes
    Entonces respuesta código 400
    Y la respuesta lista los campos obligatorios
