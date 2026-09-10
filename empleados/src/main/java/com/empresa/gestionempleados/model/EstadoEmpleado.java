package com.empresa.gestionempleados.model;

/**
 * Estados posibles de un empleado.
 * En el Reto 1 solo se usa ACTIVO.
 * Las transiciones se implementarán en retos posteriores.
 *
 * ACTIVO ──────────► EN_VACACIONES ──────────► ACTIVO
 *   │                      │
 *   └──────────────────────┴──────────────────► RETIRADO (estado final)
 */
public enum EstadoEmpleado {
    /** Empleado vinculado y con acceso al sistema. */
    ACTIVO,

    /** Vinculado, pero con acceso suspendido temporalmente (Reto 4 y 5). */
    EN_VACACIONES,

    /** Desvinculado. Estado final: el registro se conserva para auditoría, nunca se borra. */
    RETIRADO
}
