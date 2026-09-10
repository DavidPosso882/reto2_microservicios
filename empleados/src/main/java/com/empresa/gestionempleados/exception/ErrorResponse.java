package com.empresa.gestionempleados.exception;

/**
 * Envoltorio JSON para todas las respuestas de error.
 * Ejemplo: {"status":404,"error":"Recurso no encontrado"}
 */
public record ErrorResponse(int status, String error) {}
