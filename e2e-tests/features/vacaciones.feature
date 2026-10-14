# language: es

Característica: Vacaciones y ciclo de vida de la cuenta
  Como equipo de automatización
  Quiero verificar la programación de vacaciones y la suspensión de la cuenta
  Para asegurar que las validaciones son reales y que el scheduler del ciclo
  de vida se observa sin esperas fijas ni dependencia de su frecuencia

  Antecedentes:
    # Pasos reutilizados del Punto 3: login ADMIN y departamento idempotente.
    Dado que inicio sesión como "admin"
    Y que existe el departamento "E2E-P5-DEPT"
    # Precondición compleja del Punto 5: empleado + credenciales activas
    # creadas desde cero con el flujo real del Punto 3/4 (alta ADMIN,
    # notificación SEGURIDAD con token, reset y login 200).
    Y que existe un empleado activo con credenciales establecidas

  Escenario: La programación exitosa de vacaciones se notifica eventualmente
    Cuando programo un período de vacaciones futuro
    Entonces respuesta código 201
    Y la respuesta confirma el período programado
    Y eventualmente llega la notificación de vacaciones programadas

  Escenario: Las fechas incoherentes son rechazadas
    Cuando programo un período de vacaciones con fechaFin anterior a fechaInicio
    Entonces respuesta código 400
    Y la respuesta explica que fechaFin no puede ser anterior a fechaInicio

  Escenario: El solapamiento de períodos es rechazado
    Cuando programo un período de vacaciones futuro
    Y programo otro período de vacaciones que se solapa con el anterior
    Entonces respuesta código 400
    Y la respuesta incluye el período en conflicto

  Escenario: La cuenta se suspende al iniciar las vacaciones y se reactiva al finalizar
    Cuando programo un período de vacaciones que inicia de inmediato
    Entonces eventualmente el empleado no puede iniciar sesión
    Y eventualmente el empleado puede iniciar sesión nuevamente
    Y el período de vacaciones quedó finalizado
    Y eventualmente se notificó la suspensión temporal por vacaciones
    Y eventualmente se notificó la reactivación al finalizar las vacaciones
