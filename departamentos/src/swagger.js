import swaggerJsdoc from 'swagger-jsdoc';

const options = {
  definition: {
    openapi: '3.0.0',
    info: {
      title: 'Departamentos Service API',
      version: '1.0.0',
      description: 'API de gestión de departamentos (Reto 2). Vía gateway: http://localhost:8080/departamentos/api-docs.',
    },
    servers: [
      {
        url: 'http://localhost:8080/departamentos',
        description: 'Vía API Gateway (canónico para la entrega)',
      },
      {
        url: 'http://localhost:8082',
        description: 'Directo (solo con port-forward)',
      },
    ],
    components: {
      schemas: {
        Departamento: {
          type: 'object',
          required: ['id', 'nombre', 'descripcion'],
          properties: {
            id: { type: 'string', description: 'Identificador único del departamento.' },
            nombre: { type: 'string', description: 'Nombre del departamento.' },
            descripcion: { type: 'string', description: 'Descripción del departamento.' },
          },
        },
        ErrorEnvelope: {
          type: 'object',
          required: ['status', 'error'],
          properties: {
            status: { type: 'integer', description: 'Código de estado HTTP.' },
            error: { type: 'string', description: 'Mensaje de error descriptivo.' },
          },
        },
      },
    },
  },
  apis: ['./src/routes/*.js'],
};

export function buildSwaggerSpec() {
  return swaggerJsdoc(options);
}
