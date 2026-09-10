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

export class DuplicateError extends AppError {
  constructor(message) {
    super(400, message);
    this.name = 'DuplicateError';
  }
}

export class NotFoundError extends AppError {
  constructor(message) {
    super(404, message);
    this.name = 'NotFoundError';
  }
}
