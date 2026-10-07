# language: es

Característica: Offboarding del empleado
  Como equipo de automatización
  Quiero verificar la desvinculación completa de un empleado
  Para asegurar que la baja se notifica, bloquea el acceso de forma
  permanente y queda conservada para auditoría

  Antecedentes:
    # Pasos reutilizados del Punto 3: login ADMIN y departamento idempotente.
    Dado que inicio sesión como "admin"
    Y que existe el departamento "E2E-P5-DEPT"
    # Precondición compleja del Punto 5: empleado + credenciales activas
    # creadas desde cero (el reset token se guarda para probar que un token
    # viejo ya no sirve tras el retiro).
    Y que existe un empleado activo con credenciales establecidas

  Escenario: La desvinculación se registra y se notifica eventualmente
    Cuando retiro al empleado activo
    Entonces respuesta código 200
    Y la respuesta confirma la desvinculación con fecha de retiro
    Y eventualmente llega la notificación de desvinculación al email del empleado
    Y eventualmente la cuenta quedó desactivada permanentemente

  Escenario: El empleado retirado no puede volver a iniciar sesión
    Cuando retiro al empleado activo
    Entonces eventualmente el empleado retirado no puede iniciar sesión
    Y el empleado retirado sigue sin poder iniciar sesión durante la ventana de observación

  Escenario: La recuperación de contraseña no reactiva al empleado retirado
    Cuando retiro al empleado activo
    Entonces eventualmente la cuenta quedó desactivada permanentemente
    Cuando el empleado retirado intenta recuperar su contraseña
    Entonces respuesta código 200
    Y la recuperación no emite un token nuevo
    Y el token de activación anterior ya no sirve
    Y el empleado retirado sigue sin poder iniciar sesión

  Escenario: El empleado retirado aparece en la consulta de auditoría
    Cuando retiro al empleado activo
    Y consulto los empleados con estado "RETIRADO"
    Entonces respuesta código 200
    Y la lista de auditoría incluye al empleado retirado con su fecha de retiro
