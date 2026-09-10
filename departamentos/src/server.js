import 'dotenv/config';
import { createPool } from './config/db.js';
import { PgDepartamentoStore } from './store/PgDepartamentoStore.js';
import { createApp } from './app.js';

const port = Number(process.env.PORT || 8081);

const pool = createPool();
const store = new PgDepartamentoStore(pool);
const app = createApp({ store });

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`Departamentos service listening on http://localhost:${port}`);
  // eslint-disable-next-line no-console
  console.log(`Swagger UI available at http://localhost:${port}/api-docs`);
});
