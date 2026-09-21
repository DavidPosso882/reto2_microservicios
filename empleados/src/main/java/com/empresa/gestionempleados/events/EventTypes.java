package com.empresa.gestionempleados.events;

/**
 * Nombres canónicos de los eventos del ecosistema (Reto 4).
 * Los nombres son case-sensitive y con punto, según CATALOGO_EVENTOS.md.
 */
public final class EventTypes {

    /** Se publica tras POST /empleados exitoso (ACTIVO o PENDIENTE_VALIDACION). */
    public static final String EMPLEADO_CREADO = "empleado.creado";

    /** Se publica tras PUT /empleados/{id} exitoso (foto completa). */
    public static final String EMPLEADO_ACTUALIZADO = "empleado.actualizado";

    /** Se publica tras DELETE /empleados/{id} (baja lógica: estado RETIRADO + fechaRetiro). */
    public static final String EMPLEADO_RETIRADO = "empleado.retirado";

    private EventTypes() {
        // Constantes: no instanciar.
    }
}
