package com.empresa.gestionempleados.config;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * Configuración de OpenAPI / Swagger UI.
 * La interfaz queda disponible en /swagger-ui.html.
 */
@Configuration
public class OpenApiConfig {

    @Bean
    public OpenAPI gestionEmpleadosOpenAPI() {
        return new OpenAPI()
                .info(new Info()
                        .title("API de Gestión de Empleados")
                        .description("Servicio REST para el registro y consulta de empleados - Reto 2")
                        .version("2.0.0"));
    }
}
