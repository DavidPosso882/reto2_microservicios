import 'dotenv/config';
import { createPool } from './config/db.js';
import { PgUsuarioStore } from './store/UsuarioStore.js';
import { createApp } from './app.js';
import { iniciarConsumidor, crearPublicadorEventos } from './rabbit.js';

const port = Number(process.env.PORT || 8086);

const pool = createPool();
const store = new PgUsuarioStore(pool);

// App first (HTTP readiness does not depend on the broker); the service lives
// in app.locals so app.js stays the single wiring point.
const app = createApp({ store });
const service = app.locals.authService;

app.listen(port, () => {
  // eslint-disable-next-line no-console
  console.log(`auth-service listening on http://localhost:${port}`);
  // eslint-disable-next-line no-console
  console.log(`Swagger UI available at http://localhost:${port}/docs`);

  iniciarConsumidor(service)
    .then(({ channel }) => {
      service.setEventPublisher(crearPublicadorEventos(() => channel));
      // eslint-disable-next-line no-console
      console.log('[auth] Publicador de eventos conectado al canal RabbitMQ.');
    })
    .catch((err) => {
      // eslint-disable-next-line no-console
      console.error(
        '[auth] Sin consumidor RabbitMQ; el ciclo de vida por eventos queda inactivo:',
        err.message
      );
      process.exit(1);
    });
});
