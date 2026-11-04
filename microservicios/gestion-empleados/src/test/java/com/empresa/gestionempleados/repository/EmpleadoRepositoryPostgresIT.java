package com.empresa.gestionempleados.repository;

import com.empresa.gestionempleados.model.Empleado;
import com.empresa.gestionempleados.model.EstadoEmpleado;
import org.junit.jupiter.api.DisplayName;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.jdbc.AutoConfigureTestDatabase;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.boot.test.autoconfigure.orm.jpa.TestEntityManager;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;
import org.testcontainers.utility.DockerImageName;
import org.testcontainers.utility.MountableFile;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Integración real contra PostgreSQL 16 en Testcontainers (Reto 6, Punto 1).
 *
 * <p>A diferencia de los tests con H2, aquí el esquema lo crea el script de
 * producción {@code empleados/init.sql} (montado en
 * {@code /docker-entrypoint-initdb.d/}): se verifica que las restricciones
 * UNIQUE declaradas a nivel de base de datos son las que hacen cumplir la
 * unicidad, no solo los finders de la aplicación.
 *
 * <p>No requiere un daemon de Docker en los tests unitarios; solo este *IT
 * lo necesita. La imagen usada es {@code postgres:16-alpine}.
 */
@DataJpaTest(properties = {
        // El esquema lo gestiona init.sql, no Hibernate (igual que producción).
        "spring.jpa.hibernate.ddl-auto=none",
        // src/test/resources/application.properties fija H2Dialect; aquí se
        // sobreescribe para que Hibernate hable PostgreSQL.
        "spring.jpa.database-platform=org.hibernate.dialect.PostgreSQLDialect"
})
@AutoConfigureTestDatabase(replace = AutoConfigureTestDatabase.Replace.NONE)
@Testcontainers
class EmpleadoRepositoryPostgresIT {

    static {
        // Docker Engine 25+ exige API de cliente >= 1.40; el docker-java que
        // embebe Testcontainers 1.19 negocia por defecto con 1.32 y el daemon
        // rechaza el ping ("client version 1.32 is too old"). Se fija 1.41
        // (aceptada por Docker 20.10+ y por el daemon actual) solo si el
        // entorno no definió ya una versión (por ejemplo, -Dapi.version).
        if (System.getProperty("api.version") == null && System.getenv("DOCKER_API_VERSION") == null) {
            System.setProperty("api.version", "1.41");
        }
    }

    @Container
    static final PostgreSQLContainer<?> POSTGRES =
            new PostgreSQLContainer<>(DockerImageName.parse("postgres:16-alpine"))
                    .withCopyFileToContainer(
                            MountableFile.forHostPath(scriptInit()),
                            "/docker-entrypoint-initdb.d/01-init.sql");

    @DynamicPropertySource
    static void datasource(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", POSTGRES::getJdbcUrl);
        registry.add("spring.datasource.username", POSTGRES::getUsername);
        registry.add("spring.datasource.password", POSTGRES::getPassword);
        registry.add("spring.datasource.driver-class-name", POSTGRES::getDriverClassName);
    }

    @Autowired
    private EmpleadoRepository repository;

    @Autowired
    private TestEntityManager entityManager;

    private static Empleado empleado(String id, String email, String numeroEmpleado) {
        return new Empleado(id, "Juan", "Perez", email, numeroEmpleado,
                "Desarrollador Senior", "Tecnologia", "IT", "2026-02-10", EstadoEmpleado.ACTIVO);
    }

    /**
     * Localiza empleados/init.sql tanto si surefire ejecuta con el basedir del
     * módulo como si se lanza mvn desde la raíz del repositorio.
     */
    private static Path scriptInit() {
        Path basedir = Path.of(System.getProperty("basedir", System.getProperty("user.dir", ".")));
        Path script = basedir.resolve("init.sql");
        if (!Files.isRegularFile(script)) {
            script = Path.of("init.sql").toAbsolutePath();
        }
        if (!Files.isRegularFile(script)) {
            throw new IllegalStateException(
                    "No se encontró empleados/init.sql desde " + Path.of("").toAbsolutePath());
        }
        return script;
    }

    private static String causa(DataIntegrityViolationException ex) {
        Throwable causa = ex.getMostSpecificCause();
        return causa != null ? String.valueOf(causa.getMessage()) : String.valueOf(ex.getMessage());
    }

    @Test
    @DisplayName("persistencia real: guarda y recupera el empleado desde PostgreSQL 16")
    void persisteYRecuperaEnPostgresReal() {
        Empleado guardado = repository.saveAndFlush(empleado("E001", "juan.perez@empresa.com", "EMP-2026-001"));
        assertNotNull(guardado);

        entityManager.flush();
        entityManager.clear();

        Empleado recuperado = repository.findById("E001").orElseThrow();
        assertEquals("juan.perez@empresa.com", recuperado.getEmail());
        assertEquals("EMP-2026-001", recuperado.getNumeroEmpleado());
        assertEquals(EstadoEmpleado.ACTIVO, recuperado.getEstado());
        assertEquals("2026-02-10", recuperado.getFechaIngreso());
        assertEquals(1, repository.count());
    }

    @Test
    @DisplayName("el esquema real (init.sql) define UNIQUE de email y numeroEmpleado")
    void elEsquemaRealDefineLasRestriccionesUnique() {
        @SuppressWarnings("unchecked")
        List<String> restricciones = entityManager.getEntityManager()
                .createNativeQuery("select constraint_name from information_schema.table_constraints "
                        + "where table_name = 'empleado' and constraint_type = 'UNIQUE'")
                .getResultList();

        assertTrue(restricciones.contains("uk_empleado_email"),
                "La tabla real debe declarar uk_empleado_email; encontradas: " + restricciones);
        assertTrue(restricciones.contains("uk_empleado_numero_empleado"),
                "La tabla real debe declarar uk_empleado_numero_empleado; encontradas: " + restricciones);
    }

    @Test
    @DisplayName("email duplicado: PostgreSQL rechaza el INSERT con DataIntegrityViolation")
    void emailDuplicadoLanzaDataIntegrityViolation() {
        repository.saveAndFlush(empleado("E001", "duplicado@empresa.com", "EMP-2026-001"));

        DataIntegrityViolationException ex = assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(empleado("E002", "duplicado@empresa.com", "EMP-2026-002")));

        assertTrue(causa(ex).contains("uk_empleado_email"),
                "La violación debe ser la restricción real uk_empleado_email; causa: " + causa(ex));
    }

    @Test
    @DisplayName("numeroEmpleado duplicado: PostgreSQL rechaza el INSERT con DataIntegrityViolation")
    void numeroEmpleadoDuplicadoLanzaDataIntegrityViolation() {
        repository.saveAndFlush(empleado("E001", "uno@empresa.com", "EMP-DUPLICADO"));

        DataIntegrityViolationException ex = assertThrows(
                DataIntegrityViolationException.class,
                () -> repository.saveAndFlush(empleado("E002", "dos@empresa.com", "EMP-DUPLICADO")));

        assertTrue(causa(ex).contains("uk_empleado_numero_empleado"),
                "La violación debe ser la restricción real uk_empleado_numero_empleado; causa: " + causa(ex));
    }
}
