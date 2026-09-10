package com.empresa.gestionempleados.model;

import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;

/**
 * Modelo canónico del empleado.
 * Este modelo acompaña todos los retos del semestre.
 *
 * Desde el Reto 2 es una entidad JPA persistida en PostgreSQL.
 * El esquema físico (tabla + restricciones UNIQUE) se define en empleados/init.sql.
 */
@Entity
@Table(name = "empleado")
@Schema(description = "Representación canónica de un empleado")
public class Empleado {

    @Id
    @Column(name = "id", nullable = false)
    @NotBlank(message = "El campo id es obligatorio")
    @Schema(description = "Identificador único del empleado", example = "E001")
    private String id;

    @Column(name = "nombre", nullable = false)
    @NotBlank(message = "El campo nombre es obligatorio")
    @Schema(description = "Nombre del empleado", example = "Juan")
    private String nombre;

    @Column(name = "apellido", nullable = false)
    @NotBlank(message = "El campo apellido es obligatorio")
    @Schema(description = "Apellido del empleado", example = "Pérez")
    private String apellido;

    @Column(name = "email", nullable = false, unique = true)
    @NotBlank(message = "El campo email es obligatorio")
    @Email(message = "El email no tiene un formato válido")
    @Schema(description = "Email único del empleado", example = "juan.perez@empresa.com")
    private String email;

    @Column(name = "numero_empleado", nullable = false, unique = true)
    @NotBlank(message = "El campo numeroEmpleado es obligatorio")
    @Schema(description = "Número de empleado único", example = "EMP-2026-001")
    private String numeroEmpleado;

    @Column(name = "cargo", nullable = false)
    @NotBlank(message = "El campo cargo es obligatorio")
    @Schema(description = "Cargo o puesto", example = "Desarrollador Senior")
    private String cargo;

    @Column(name = "area", nullable = false)
    @NotBlank(message = "El campo area es obligatorio")
    @Schema(description = "Área de trabajo", example = "Tecnología")
    private String area;

    @Column(name = "departamento_id", nullable = false)
    @NotBlank(message = "El campo departamentoId es obligatorio")
    @Schema(description = "ID del departamento validado contra el servicio de departamentos", example = "IT")
    private String departamentoId;

    @Column(name = "fecha_ingreso", nullable = false)
    @NotBlank(message = "El campo fechaIngreso es obligatorio")
    // Validación de forma, no de calendario: 2026-99-99 pasaría la regex
    @Pattern(regexp = "^\\d{4}-\\d{2}-\\d{2}$", message = "El campo fechaIngreso debe tener formato YYYY-MM-DD")
    @Schema(description = "Fecha de ingreso (formato YYYY-MM-DD)", example = "2026-02-10")
    private String fechaIngreso;

    // En el Reto 2 solo se maneja ACTIVO; las transiciones se implementan en retos posteriores.
    // Se persiste como String (EnumType.STRING) para mantener el nombre legible en la base de datos.
    @Enumerated(EnumType.STRING)
    @Column(name = "estado", nullable = false, length = 20)
    @NotNull(message = "El campo estado es obligatorio")
    @Schema(description = "Estado del empleado (siempre ACTIVO en el Reto 2)", example = "ACTIVO")
    private EstadoEmpleado estado = EstadoEmpleado.ACTIVO;

    public Empleado() {}

    public Empleado(String id, String nombre, String apellido, String email,
                    String numeroEmpleado, String cargo, String area,
                    String departamentoId, String fechaIngreso, EstadoEmpleado estado) {
        this.id = id;
        this.nombre = nombre;
        this.apellido = apellido;
        this.email = email;
        this.numeroEmpleado = numeroEmpleado;
        this.cargo = cargo;
        this.area = area;
        this.departamentoId = departamentoId;
        this.fechaIngreso = fechaIngreso;
        this.estado = estado != null ? estado : EstadoEmpleado.ACTIVO;
    }

    // Getters y Setters
    public String getId() { return id; }
    public void setId(String id) { this.id = id; }

    public String getNombre() { return nombre; }
    public void setNombre(String nombre) { this.nombre = nombre; }

    public String getApellido() { return apellido; }
    public void setApellido(String apellido) { this.apellido = apellido; }

    public String getEmail() { return email; }
    public void setEmail(String email) { this.email = email; }

    public String getNumeroEmpleado() { return numeroEmpleado; }
    public void setNumeroEmpleado(String numeroEmpleado) { this.numeroEmpleado = numeroEmpleado; }

    public String getCargo() { return cargo; }
    public void setCargo(String cargo) { this.cargo = cargo; }

    public String getArea() { return area; }
    public void setArea(String area) { this.area = area; }

    public String getDepartamentoId() { return departamentoId; }
    public void setDepartamentoId(String departamentoId) { this.departamentoId = departamentoId; }

    public String getFechaIngreso() { return fechaIngreso; }
    public void setFechaIngreso(String fechaIngreso) { this.fechaIngreso = fechaIngreso; }

    public EstadoEmpleado getEstado() { return estado; }
    public void setEstado(EstadoEmpleado estado) { this.estado = estado; }
}
