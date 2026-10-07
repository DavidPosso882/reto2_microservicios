# language: es

Característica: Seguridad RBAC en el gateway
  Como equipo de automatización
  Quiero verificar el control de acceso del gateway por rol
  Para asegurar que sin identidad no se accede y que solo ADMIN escribe

  Antecedentes:
    Dado que inicio sesión como "admin"
    Y que existe el departamento "E2E-P3-DEPT"

  Escenario: Acceso denegado sin token
    # Escenario base del PDF (Punto 3): la ruta de negocio exige JWT.
    Cuando consulto el listado de empleados sin token
    Entonces respuesta código 401

  Escenario: Token inválido o malformado es rechazado
    # 401 confirmado contra el gateway real: authenticate falla antes del RBAC.
    Cuando consulto el listado de empleados con un token inválido
    Entonces respuesta código 401
    Cuando consulto el listado de empleados con un token malformado
    Entonces respuesta código 401

  Escenario: USER puede consultar pero no puede escribir
    Dado que tengo un token de usuario activo
    Cuando consulto el listado de empleados como "USER"
    Entonces respuesta código 200
    Cuando intento registrar un empleado como "USER"
    Entonces respuesta código 403
    Cuando intento retirar el empleado del usuario como "USER"
    Entonces respuesta código 403

  Escenario: ADMIN puede consultar, registrar y retirar
    Cuando consulto el listado de empleados como "ADMIN"
    Entonces respuesta código 200
    Cuando registro un empleado como "ADMIN"
    Entonces respuesta código 201
    Y la respuesta confirma el empleado registrado
    Cuando retiro el empleado registrado como "ADMIN"
    Entonces respuesta código 200
