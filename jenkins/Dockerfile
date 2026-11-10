FROM jenkins/jenkins:lts-jdk17

# Pre-instalar plugins (P1 + reportes P2/P4 + Sonar P3).
# Referencia: https://github.com/jenkinsci/docker#preinstalling-plugins
RUN jenkins-plugin-cli --plugins \
    workflow-aggregator \
    docker-workflow \
    pipeline-stage-view \
    git \
    configuration-as-code \
    job-dsl \
    sonar \
    junit \
    coverage \
    cucumber-reports \
    htmlpublisher \
    lockable-resources

# Cliente Docker para construir imágenes vía socket del host (Docker Socket Mount).
USER root
# Solo el cliente (el daemon es el del host vía socket); docker-cli explícito
# porque con --no-install-recommends docker.io no lo trae (es recomendado).
RUN apt-get update && \
    apt-get install -y --no-install-recommends docker-cli curl && \
    rm -rf /var/lib/apt/lists/*

# Grupo docker con GID del host (983 en esta máquina) para acceder al socket.
# Si el GID ya existe en la imagen, -f evita el fallo.
RUN getent group docker || groupadd -g 983 docker; \
    usermod -aG docker jenkins

# Proyecto Final: el permiso del socket se ajusta solo en cada arranque (ver
# el script). El contenedor arranca como root solo para eso y Jenkins corre
# como el usuario jenkins (el script baja privilegios con setpriv).
COPY --chmod=755 docker-socket-entrypoint.sh /usr/local/bin/docker-socket-entrypoint.sh
ENTRYPOINT ["/usr/local/bin/docker-socket-entrypoint.sh"]
