package com.empresa.gestionempleados.exception;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.HttpRequestMethodNotSupportedException;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.servlet.resource.NoResourceFoundException;

import java.util.stream.Collectors;

/**
 * Manejador global de excepciones.
 * Todas las respuestas de error se devuelven en formato JSON:
 * {"status":404,"error":"Recurso no encontrado"}
 */
@RestControllerAdvice
public class GlobalExceptionHandler {

    /**
     * Empleado no encontrado -> 404 JSON con mensaje exacto requerido por el reto.
     */
    @ExceptionHandler(EmpleadoNotFoundException.class)
    public ResponseEntity<ErrorResponse> handleNotFound(EmpleadoNotFoundException ex) {
        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(new ErrorResponse(HttpStatus.NOT_FOUND.value(), ex.getMessage()));
    }

    /**
     * Email o numeroEmpleado duplicado -> 400 JSON con mensaje descriptivo.
     */
    @ExceptionHandler(EmpleadoDuplicadoException.class)
    public ResponseEntity<ErrorResponse> handleDuplicado(EmpleadoDuplicadoException ex) {
        return ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .body(new ErrorResponse(HttpStatus.BAD_REQUEST.value(), ex.getMessage()));
    }

    /**
     * Departamento inexistente (404 del servicio de departamentos) -> 400 JSON con mensaje del reto.
     */
    @ExceptionHandler(DepartamentoNoExisteException.class)
    public ResponseEntity<ErrorResponse> handleDepartamentoNoExiste(DepartamentoNoExisteException ex) {
        return ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .body(new ErrorResponse(HttpStatus.BAD_REQUEST.value(), ex.getMessage()));
    }

    /**
     * Servicio de departamentos no disponible tras agotar reintentos -> 503 JSON.
     */
    @ExceptionHandler(DepartamentoNoDisponibleException.class)
    public ResponseEntity<ErrorResponse> handleDepartamentoNoDisponible(DepartamentoNoDisponibleException ex) {
        return ResponseEntity
                .status(HttpStatus.SERVICE_UNAVAILABLE)
                .body(new ErrorResponse(HttpStatus.SERVICE_UNAVAILABLE.value(), ex.getMessage()));
    }

    /**
     * Validaciones de Bean Validation (@NotBlank, @Email, etc.) -> 400 JSON.
     */
    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ErrorResponse> handleValidacion(MethodArgumentNotValidException ex) {
        String errores = ex.getBindingResult().getFieldErrors()
                .stream()
                .map(e -> e.getField() + ": " + e.getDefaultMessage())
                .collect(Collectors.joining(", "));
        return ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .body(new ErrorResponse(HttpStatus.BAD_REQUEST.value(), "Datos inválidos: " + errores));
    }

    /**
     * Cualquier ruta no definida -> 404 JSON con "Recurso no encontrado".
     */
    @ExceptionHandler(NoResourceFoundException.class)
    public ResponseEntity<ErrorResponse> handleRutaNoEncontrada(NoResourceFoundException ex) {
        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(new ErrorResponse(HttpStatus.NOT_FOUND.value(), "Recurso no encontrado"));
    }

    /**
     * Método HTTP no soportado para una ruta existente (p. ej. DELETE /empleados) -> 404 JSON.
     */
    @ExceptionHandler(HttpRequestMethodNotSupportedException.class)
    public ResponseEntity<ErrorResponse> handleMetodoNoSoportado(HttpRequestMethodNotSupportedException ex) {
        return ResponseEntity
                .status(HttpStatus.NOT_FOUND)
                .body(new ErrorResponse(HttpStatus.NOT_FOUND.value(), "Recurso no encontrado"));
    }

    /**
     * Cuerpo de solicitud ilegible (JSON malformado o estado desconocido) -> 400 JSON.
     */
    @ExceptionHandler(HttpMessageNotReadableException.class)
    public ResponseEntity<ErrorResponse> handleMensajeNoLegible(HttpMessageNotReadableException ex) {
        return ResponseEntity
                .status(HttpStatus.BAD_REQUEST)
                .body(new ErrorResponse(HttpStatus.BAD_REQUEST.value(),
                        "Datos inválidos: el cuerpo de la solicitud no es un JSON válido o contiene un estado desconocido"));
    }

    /**
     * Fallback para cualquier otro error no contemplado.
     */
    @ExceptionHandler(Exception.class)
    public ResponseEntity<ErrorResponse> handleGeneral(Exception ex) {
        return ResponseEntity
                .status(HttpStatus.INTERNAL_SERVER_ERROR)
                .body(new ErrorResponse(HttpStatus.INTERNAL_SERVER_ERROR.value(), "Error interno del servidor"));
    }
}
