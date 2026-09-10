# ── Stage: runtime ──────────────────────────────────────────────────────────
FROM node:22-alpine

WORKDIR /app

# curl is required by the docker-compose healthcheck for this service
RUN apk add --no-cache curl

# Copy manifests first to leverage Docker layer caching
COPY package*.json ./
RUN npm install --omit=dev

# Copy application source
COPY . .

EXPOSE 8081

CMD ["node", "src/server.js"]