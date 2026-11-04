import { context, trace } from '@opentelemetry/api';

const SERVICE = process.env.OTEL_SERVICE_NAME || 'departamentos-service';

/** 32-hex trace id of the active span, or null outside a trace. */
export function traceId() {
  const span = trace.getSpan(context.active());
  if (!span) return null;
  const id = span.spanContext().traceId;
  return id && /^[0-9a-f]{32}$/i.test(id) ? id : null;
}

/**
 * Structured JSON log line: timestamp, level, service, traceId, message and
 * optional domain fields. Never pass tokens, passwords or request bodies.
 */
export function log(level, message, fields = {}) {
  const entry = {
    timestamp: new Date().toISOString(),
    level,
    service: SERVICE,
    traceId: traceId(),
    message,
    ...fields,
  };
  const line = JSON.stringify(entry);
  if (level === 'error') {
    // eslint-disable-next-line no-console
    console.error(line);
  } else if (level === 'warn') {
    // eslint-disable-next-line no-console
    console.warn(line);
  } else {
    // eslint-disable-next-line no-console
    console.log(line);
  }
}

export const logger = {
  debug: (message, fields) => log('debug', message, fields),
  info: (message, fields) => log('info', message, fields),
  warn: (message, fields) => log('warn', message, fields),
  error: (message, fields) => log('error', message, fields),
};
