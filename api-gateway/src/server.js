import 'dotenv/config';
import { createGateway } from './app.js';

const port = Number(process.env.PORT || 8080);
// Inside the Docker network these resolve via the Compose service names.
// Defaults keep `npm run dev` working outside Docker only if the services
// are reachable under those names (e.g. via /etc/hosts entries).
const empleadosUrl = process.env.EMPLEADOS_URL || 'http://empleados-service:8081';
const departamentosUrl = process.env.DEPARTAMENTOS_URL || 'http://departamentos-service:8082';

const app = createGateway({ empleadosUrl, departamentosUrl });

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`API Gateway listening on http://localhost:${port}`);
});
