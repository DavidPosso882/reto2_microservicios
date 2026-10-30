import { NodeSDK } from '@opentelemetry/sdk-node';
import { ZipkinExporter } from '@opentelemetry/exporter-zipkin';
import {
  AlwaysOffSampler,
  AlwaysOnSampler,
  BatchSpanProcessor,
  ParentBasedSampler,
  TraceIdRatioBasedSampler,
} from '@opentelemetry/sdk-trace-base';
import { Resource } from '@opentelemetry/resources';
import {
  CompositePropagator,
  W3CBaggagePropagator,
  W3CTraceContextPropagator,
} from '@opentelemetry/core';
import { getNodeAutoInstrumentations } from '@opentelemetry/auto-instrumentations-node';

let sdk = null;

/**
 * Starts OpenTelemetry before the instrumented modules (http, express, pg,
 * amqplib) are imported. server.js calls this and then dynamically imports
 * the application, so auto-instrumentation patches the real modules.
 *
 * OTEL_SERVICE_NAME, OTEL_EXPORTER_ZIPKIN_ENDPOINT and OTEL_SDK_DISABLED are
 * honored.
 */
export function startTelemetry(defaultServiceName) {
  if (sdk) return sdk;
  if ((process.env.OTEL_SDK_DISABLED || '').toLowerCase() === 'true') return null;

  const serviceName = process.env.OTEL_SERVICE_NAME || defaultServiceName;
  const endpoint = zipkinEndpoint();

  sdk = new NodeSDK({
    resource: new Resource({
      'service.name': serviceName,
      'service.version': '1.0.0',
    }),
    spanProcessor: new BatchSpanProcessor(new ZipkinExporter({ url: endpoint })),
    sampler: samplerFromEnv(),
    textMapPropagator: new CompositePropagator({
      propagators: [new W3CTraceContextPropagator(), new W3CBaggagePropagator()],
    }),
    instrumentations: [
      getNodeAutoInstrumentations({
        '@opentelemetry/instrumentation-fs': { enabled: false },
      }),
    ],
  });

  sdk.start();
  return sdk;
}

function zipkinEndpoint() {
  const raw =
    process.env.OTEL_EXPORTER_ZIPKIN_ENDPOINT || 'http://zipkin:9411/api/v2/spans';
  return raw.endsWith('/api/v2/spans')
    ? raw
    : `${raw.replace(/\/+$/, '')}/api/v2/spans`;
}

function samplerFromEnv() {
  const name = (process.env.OTEL_TRACES_SAMPLER || 'parentbased_always_on').toLowerCase();
  if (name === 'always_off') return new AlwaysOffSampler();
  if (name === 'traceidratio') return new TraceIdRatioBasedSampler(ratioFromEnv());
  if (name === 'parentbased_traceidratio') {
    return new ParentBasedSampler({ root: new TraceIdRatioBasedSampler(ratioFromEnv()) });
  }
  return new ParentBasedSampler({ root: new AlwaysOnSampler() });
}

function ratioFromEnv() {
  const ratio = Number(process.env.OTEL_TRACES_SAMPLER_ARG || '1');
  return Number.isFinite(ratio) && ratio >= 0 && ratio <= 1 ? ratio : 1;
}

export async function shutdownTelemetry() {
  if (!sdk) return;
  const current = sdk;
  sdk = null;
  await current.shutdown();
}
