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
    htmlpublisher

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

USER jenkins
