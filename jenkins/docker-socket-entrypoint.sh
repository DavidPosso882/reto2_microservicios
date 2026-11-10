#!/bin/sh
# Proyecto Final — despliegue con un solo comando.
#
# Jenkins construye imágenes y levanta el stack E2E con el Docker del host
# (socket montado en /var/run/docker.sock). En Docker Desktop el socket llega
# como root:root, y el usuario jenkins no puede usarlo. Antes había que correr
# a mano, tras cada arranque:
#   docker exec -u root jenkins sh -c "chgrp 983 /var/run/docker.sock && chmod 660 /var/run/docker.sock"
#
# Este entrypoint lo hace solo: arranca como root, entrega el socket al grupo
# docker de la imagen (GID 983, del que jenkins es miembro) y luego baja los
# privilegios al usuario jenkins con el entrypoint original de la imagen.
set -e

SOCK=/var/run/docker.sock
if [ -S "$SOCK" ]; then
  chgrp docker "$SOCK" && chmod 660 "$SOCK" \
    && echo ">>> docker.sock entregado al grupo docker" \
    || echo ">>> AVISO: no se pudo ajustar el permiso de $SOCK"
fi

exec setpriv --reuid=jenkins --regid=jenkins --init-groups \
  /usr/bin/tini -- /usr/local/bin/jenkins.sh "$@"
