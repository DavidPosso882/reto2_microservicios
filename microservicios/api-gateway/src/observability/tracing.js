import { context, propagation, trace } from '@opentelemetry/api';

/** Service tracer (no-op until telemetry.js starts the SDK). */
export function tracer(service, version = '1.0.0') {
  return trace.getTracer(service, version);
}

/** Inject W3C traceparent/tracestate/baggage into a plain object. */
export function injectContext(carrier = {}) {
  propagation.inject(context.active(), carrier);
  return carrier;
}

/** Extract the W3C context received in AMQP/HTTP headers. */
export function extractContext(carrier = {}) {
  return propagation.extract(context.active(), carrier || {});
}

export function withExtractedContext(carrier, fn) {
  return context.with(extractContext(carrier), fn);
}
