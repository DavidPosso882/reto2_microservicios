import 'dotenv/config';
import { createGateway } from './app.js';

const port = Number(process.env.PORT || 8080);
// Inside the Docker network these resolve via the Compose service names.
// Defaults keep `npm run dev` working outside Docker only if the services
// are reachable under those names (e.g. via /etc/hosts entries).
const empleadosUrl = process.env.EMPLEADOS_URL || 'http://empleados-service:8081';
const departamentosUrl = process.env.DEPARTAMENTOS_URL || 'http://departamentos-service:8082';
const perfilesUrl = process.env.PERFILES_URL || 'http://perfiles-service:8083';
const notificacionesUrl = process.env.NOTIFICACIONES_URL || 'http://notificaciones-service:8084';
const vacacionesUrl = process.env.VACACIONES_URL || 'http://vacaciones-service:8085';

const app = createGateway({
  empleadosUrl,
  departamentosUrl,
  perfilesUrl,
  notificacionesUrl,
  vacacionesUrl,
});

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`API Gateway listening on http://localhost:${port}`);
});
