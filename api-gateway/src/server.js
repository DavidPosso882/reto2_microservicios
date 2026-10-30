import 'dotenv/config';
import { startTelemetry, shutdownTelemetry } from './observability/telemetry.js';
import { logger } from './observability/logger.js';

// Reto 8: OpenTelemetry debe arrancar ANTES de cargar express/pg/amqplib para
// que la auto-instrumentación parchee esos módulos. Por eso app.js se importa
// dinámicamente después de startTelemetry().
startTelemetry('api-gateway');

const { createGateway } = await import('./app.js');

const port = Number(process.env.PORT || 8080);
// Inside the Docker network these resolve via the Compose service names.
// Defaults keep `npm run dev` working outside Docker only if the services
// are reachable under those names (e.g. via /etc/hosts entries).
const empleadosUrl = process.env.EMPLEADOS_URL || 'http://empleados-service:8081';
const departamentosUrl = process.env.DEPARTAMENTOS_URL || 'http://departamentos-service:8082';
const perfilesUrl = process.env.PERFILES_URL || 'http://perfiles-service:8083';
const notificacionesUrl = process.env.NOTIFICACIONES_URL || 'http://notificaciones-service:8084';
const vacacionesUrl = process.env.VACACIONES_URL || 'http://vacaciones-service:8085';
// Reto 5: auth-service queda dentro de la red de Docker (:8086, sin puerto
// publicado al host); el gateway monta /auth contra él.
const authUrl = process.env.AUTH_URL || 'http://auth-service:8086';

const app = createGateway({
  empleadosUrl,
  departamentosUrl,
  perfilesUrl,
  notificacionesUrl,
  vacacionesUrl,
  authUrl,
});

const server = app.listen(port, () => {
  logger.info('api_gateway_listening', { port });
});

async function shutdown(signal) {
  logger.info('shutdown_started', { signal });
  server.close(async () => {
    await shutdownTelemetry();
    logger.info('shutdown_completed', { signal });
    process.exit(0);
  });
}

process.on('SIGTERM', () => shutdown('SIGTERM'));
process.on('SIGINT', () => shutdown('SIGINT'));
