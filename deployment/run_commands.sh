cd deployment

# 1. Validate the compose config (optional)
podman-compose config

# 2. Build the images
podman-compose build

# 3. Start the stack (detached). First run also builds the SPA + runs migrations.
podman-compose up -d

# 4. Check status / logs
podman ps -a
podman-compose logs backend
podman-compose logs caddy
podman-compose logs frontend-build   # one-shot; should exit 0
