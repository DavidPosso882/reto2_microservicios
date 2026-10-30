# Dashboards de Grafana — pendiente T3

Placeholder: **T1 sólo deja la carpeta y el aprovisionamiento listos**.

El proveedor `reto8-ecosistema` (ver
`../provisioning/dashboards/dashboards.yml`) escanea esta carpeta cada 30s y
carga como dashboard cada `*.json` que aparezca aquí.

Qué debe poner T3 en esta carpeta:

- El/los dashboards JSON exportados desde Grafana (S4: consolidado de varios
  microservicios).
- Los paneles deben referenciar los datasources aprovisionados por
  `uid: prometheus`, `uid: loki` y `uid: zipkin` (ver
  `../provisioning/datasources/datasources.yml`), no por nombre.
- Las series llegan con la etiqueta `service` (definida en
  `../../prometheus/prometheus.yml`), así que los queries pueden filtrar por
  servicio, por ejemplo `rate(http_requests_total{service="vacaciones-service"}[5m])`.

Nota: esta carpeta se monta `read-only` en el contenedor, porque la fuente de
verdad es el JSON del repositorio. Ediciones hechas en la UI no se persisten.
