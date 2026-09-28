/**
 * OpenAPI 3.0 contract of auth-service, served by fetchable /openapi.yaml
 * and browsable Swagger UI /docs (same pattern as perfiles/vacaciones).
 */
const spec = {
  openapi: '3.0.3',
  info: {
    title: 'auth-service (Reto 5)',
    version: '1.0.0',
    description: [
      'Servicio de identidad del ecosistema: emite JWT de acceso (HMAC SHA-256),',
      'gestiona recuperación/establecimiento de contraseñas con tokens reset',
      'stateless (type: RESET_PASSWORD) y conduce el ciclo de vida de cuentas',
      '(ACTIVA | SUSPENDIDA_TEMPORAL | DESACTIVADA_PERMANENTE) mediante eventos',
      'del catálogo (usuario.creado, usuario.recuperacion, cuenta.activada,',
      'cuenta.desactivada). Contraseñas: BCrypt, jamás dentro del token.',
    ].join(' '),
  },
  components: {
    securitySchemes: {
      BearerAuth: { type: 'http', scheme: 'bearer', bearerFormat: 'JWT' },
    },
    schemas: {
      LoginRequest: {
        type: 'object',
        required: ['email', 'password'],
        properties: {
          email: { type: 'string', example: 'juan.perez@empresa.com' },
          password: { type: 'string', example: 'S3creto!' },
        },
      },
      LoginResponse: {
        type: 'object',
        properties: {
          accessToken: { type: 'string', example: 'eyJhbGciOiJIUzI1NiIs...' },
          tokenType: { type: 'string', example: 'Bearer' },
          expiresIn: { type: 'integer', example: 3600 },
          usuario: { $ref: '#/components/schemas/Usuario' },
        },
      },
      Usuario: {
        type: 'object',
        properties: {
          id: { type: 'string', example: 'E001' },
          email: { type: 'string', example: 'juan.perez@empresa.com' },
          role: { type: 'string', enum: ['ADMIN', 'USER'] },
          estado: {
            type: 'string',
            enum: ['ACTIVA', 'SUSPENDIDA_TEMPORAL', 'DESACTIVADA_PERMANENTE'],
          },
        },
      },
      RecoverRequest: {
        type: 'object',
        required: ['email'],
        properties: { email: { type: 'string' } },
      },
      ResetRequest: {
        type: 'object',
        required: ['token', 'nuevaPassword'],
        properties: {
          token: { type: 'string', description: 'Reset token (type: RESET_PASSWORD)' },
          nuevaPassword: { type: 'string', example: 'NuevaClave1' },
        },
      },
      ChangePasswordRequest: {
        type: 'object',
        required: ['passwordActual', 'passwordNueva'],
        properties: {
          passwordActual: { type: 'string' },
          passwordNueva: { type: 'string', example: 'NuevaClave9' },
        },
      },
      BootstrapRequest: {
        type: 'object',
        required: ['email', 'password'],
        properties: {
          email: { type: 'string', example: 'admin@empresa.com' },
          password: { type: 'string', example: 'AdminClave1' },
        },
      },
      Error: {
        type: 'object',
        properties: {
          status: { type: 'integer' },
          error: { type: 'string' },
        },
      },
    },
  },
  security: [{ BearerAuth: [] }],
  paths: {
    '/auth/bootstrap': {
      post: {
        summary: 'Crea el ADMIN semilla (solo con la tabla de usuarios vacía)',
        security: [],
        requestBody: {
          required: true,
          content: { 'application/json': { schema: { $ref: '#/components/schemas/BootstrapRequest' } } },
        },
        responses: {
          201: {
            description: 'ADMIN creado (la password se devuelve una única vez)',
            content: {
              'application/json': {
                schema: {
                  type: 'object',
                  properties: {
                    id: { type: 'string' },
                    email: { type: 'string' },
                    role: { type: 'string' },
                    estado: { type: 'string' },
                    password: { type: 'string' },
                  },
                },
              },
            },
          },
          400: { description: 'Ya existe el ADMIN o datos inválidos', content: { 'application/json': { schema: { $ref: '#/components/schemas/Error' } } } },
        },
      },
    },
    '/auth/login': {
      post: {
        summary: 'Autentica credenciales y retorna el JWT de acceso',
        security: [],
        requestBody: {
          required: true,
          content: { 'application/json': { schema: { $ref: '#/components/schemas/LoginRequest' } } },
        },
        responses: {
          200: {
            description: 'JWT emitido',
            content: { 'application/json': { schema: { $ref: '#/components/schemas/LoginResponse' } } },
          },
          400: { description: 'Faltan credenciales' },
          401: { description: 'Credenciales inválidas o cuenta no activa', content: { 'application/json': { schema: { $ref: '#/components/schemas/Error' } } } },
        },
      },
    },
    '/auth/recover-password': {
      post: {
        summary: 'Inicia la recuperación; publica usuario.recuperacion con reset token',
        security: [],
        requestBody: {
          required: true,
          content: { 'application/json': { schema: { $ref: '#/components/schemas/RecoverRequest' } } },
        },
        responses: {
          200: { description: 'Si el email existe, se publica el evento (respuesta uniforme)' },
          400: { description: 'Falta email' },
        },
      },
    },
    '/auth/reset-password': {
      post: {
        summary: 'Establece la contraseña con un reset token (activación o recuperación)',
        security: [],
        requestBody: {
          required: true,
          content: { 'application/json': { schema: { $ref: '#/components/schemas/ResetRequest' } } },
        },
        responses: {
          200: { description: 'Password establecida; activa la cuenta si estaba inactiva' },
          400: { description: 'Política de contraseña o campos faltantes' },
          401: { description: 'Token inválido o expirado' },
        },
      },
    },
    '/auth/change-password': {
      post: {
        summary: 'Cambio de contraseña autenticado (JWT o identidad del gateway)',
        requestBody: {
          required: true,
          content: { 'application/json': { schema: { $ref: '#/components/schemas/ChangePasswordRequest' } } },
        },
        responses: {
          200: { description: 'Contraseña actualizada' },
          401: { description: 'Token ausente o inválido' },
          400: { description: 'Contraseña actual incorrecta o nueva no cumple política' },
        },
      },
    },
    '/health': {
      get: {
        summary: 'Health check propio del servicio',
        security: [],
        responses: { 200: { description: 'Servicio vivo' } },
      },
    },
  },
};

/**
 * Options for swagger-ui-express (relative URLs work behind any base path).
 */
export function swaggerUiOptions() {
  return { swaggerOptions: { url: 'openapi.yaml' }, customSiteTitle: 'auth-service · Reto 5' };
}

export function openapiSpec() {
  return spec;
}
