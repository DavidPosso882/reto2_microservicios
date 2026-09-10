import swaggerJsdoc from 'swagger-jsdoc';

const options = {
  definition: {
    openapi: '3.0.0',
    info: {
      title: 'Departamentos Service API',
      version: '1.0.0',
      description: 'API de gestión de departamentos (Reto 2).',
    },
    servers: [
      {
        url: 'http://localhost:8081',
        description: 'Servidor local',
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
