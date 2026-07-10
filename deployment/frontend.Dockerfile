# Frontend build image. Compiles the Vite/React SPA to static files and copies
# them into a mounted volume (/output) that Caddy serves. This container runs
# once, publishes the build, and exits. Build context is the repository root.
FROM docker.io/library/node:22-alpine AS build
WORKDIR /app

# Install dependencies first for better layer caching.
COPY frontend/package.json ./
COPY frontend/package-lock.json* ./
RUN npm install

# Build the production bundle into /app/dist.
COPY frontend/ ./
RUN npm run build

# Minimal publish stage: hold the built assets and copy them onto the shared
# volume when the container starts.
FROM docker.io/library/alpine:3.20
COPY --from=build /app/dist /dist
CMD ["sh", "-c", "rm -rf /output/* && cp -a /dist/. /output/ && echo 'Frontend published to /output'"]
