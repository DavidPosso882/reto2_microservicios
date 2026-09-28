/**
 * Application error types.
 *
 * Every error carries an HTTP status and a descriptive Spanish message. The
 * global error handler in `app.js` serializes them using the JSON envelope:
 *
 *   { "status": <http-code>, "error": "<descriptive Spanish message>" }
 */
export class AppError extends Error {
  constructor(status, message) {
    super(message);
    this.name = 'AppError';
    this.status = status;
  }
}

export class ValidationError extends AppError {
  constructor(message) {
    super(400, message);
    this.name = 'ValidationError';
  }
}

export class CredencialesInvalidasError extends AppError {
  constructor() {
    // Uniform 401 for unknown email, disabled account and wrong password:
    // never reveal which one failed (defense against user enumeration).
    super(401, 'Credenciales inválidas o cuenta no activa');
    this.name = 'CredencialesInvalidasError';
  }
}

export class TokenInvalidoError extends AppError {
  constructor(message) {
    super(401, message);
    this.name = 'TokenInvalidoError';
  }
}

export class NotFoundError extends AppError {
  constructor(message) {
    super(404, message);
    this.name = 'NotFoundError';
  }
}
