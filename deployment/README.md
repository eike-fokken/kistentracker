# Deployment

Serve **dbtrials** behind [Caddy](https://caddyserver.com/) using three containers:

| Container        | Role                                                                                     |
| ---------------- | ---------------------------------------------------------------------------------------- |
| `caddy`          | Public entrypoint. Terminates TLS, serves the built frontend, reverse-proxies the API.   |
| `backend`        | Django + gunicorn. Serves `/api`, `/admin` and its own `/static` assets (via WhiteNoise).|
| `frontend-build` | One-shot build container. Compiles the SPA and drops the static files into a volume.     |

The frontend is **built** in a container but not *run* in one: its output static
files land in a shared volume that Caddy serves directly. The `frontend-build`
container exits once the build is published.

```
                         ┌──────────────────────────────────────────┐
   browser  ── https ──▶ │ caddy                                     │
                         │  ├─ /api/*  /admin/*  /static/*  ─▶ backend│──▶ gunicorn (Django)
                         │  └─ everything else ─▶ /srv/www (SPA)      │        │
                         └──────────────────────────────────────────┘        │ sqlite
                                        ▲ frontend volume                     ▼
                            frontend-build ─(build once)                   data volume
```

## The plan (how we get there)

1. **Backend container** — [backend.Dockerfile](backend.Dockerfile) installs the
   runtime dependencies with Poetry and runs Django under gunicorn. On start,
   [entrypoint.sh](entrypoint.sh) applies migrations, runs `collectstatic`, then
   launches gunicorn. WhiteNoise (added to Django's middleware) serves the
   collected admin static files, so no static volume needs to be shared with
   Caddy. The SQLite database lives on the `data` volume.

2. **Frontend build** — [frontend.Dockerfile](frontend.Dockerfile) runs
   `npm run build` (Vite) in a Node image, then a tiny publish stage copies the
   resulting `dist/` onto the shared `frontend` volume and exits. The SPA already
   talks to the API with same-origin relative `/api` URLs
   ([frontend/src/api.ts](../frontend/src/api.ts)), so no rebuild-time config is
   needed — Caddy makes the API same-origin.

3. **Caddy container** — official `caddy:2-alpine` image. It serves the SPA from
   the `frontend` volume, falls back to `index.html` for client-side routing,
   and reverse-proxies `/api`, `/admin` and `/static` to the backend over a
   dedicated podman bridge network (`dbtrials`) using the service name
   `backend`. Which config file it mounts is chosen by the `CADDYFILE` variable.

4. **Local vs. Let's Encrypt** — two separate Caddy configs, selected via
   `CADDYFILE`:
   - [Caddyfile.local](Caddyfile.local) (`CADDYFILE=./Caddyfile.local`, the
     default) → `tls internal`, i.e. a **self-signed** certificate from Caddy's
     internal CA. Ideal for local deployment; no email needed.
   - [Caddyfile.internet](Caddyfile.internet) (`CADDYFILE=./Caddyfile.internet`)
     → **Let's Encrypt** with `ACME_EMAIL`. Requires `SITE_ADDRESS` set to your
     public domain, public DNS, and reachable ports 80 + 443.

Django is made deployment-ready via environment variables (no second settings
module): `DJANGO_DEBUG`, `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`,
`DJANGO_CSRF_TRUSTED_ORIGINS`, `DJANGO_DB_PATH`, `DJANGO_STATIC_ROOT`,
`DJANGO_BEHIND_PROXY`. Defaults preserve the existing local dev workflow.

## Files

- [compose.yml](compose.yml) — the three-service stack + volumes.
- [generate-env.py](generate-env.py) — writes a `.env` (derives hosts/CSRF/secret).
- [backend.Dockerfile](backend.Dockerfile) / [entrypoint.sh](entrypoint.sh) — Django image.
- [frontend.Dockerfile](frontend.Dockerfile) — SPA build/publish image.
- [Caddyfile.local](Caddyfile.local) — self-signed reverse proxy config (default).
- [Caddyfile.internet](Caddyfile.internet) — Let's Encrypt reverse proxy config.
- [.env.example](.env.example) — copy to `.env` and fill in.

The stack runs on **Podman**. The Containerfiles and the compose file are
OCI-standard, so `podman` reads them unchanged (it also reads the repo-root
`.containerignore`).

## Prerequisites

- Podman with `podman compose` (Podman 4.5+; it drives either the
  `docker-compose` or `podman-compose` provider). `podman-compose` also works —
  substitute it for `podman compose` in the commands below.
- **Ports 80/443 while rootless:** rootless Podman may not bind privileged
  ports. For a quick local test, publish high ports instead (set `HTTP_PORT` /
  `HTTPS_PORT`, e.g. `8080`/`8443`, in `.env`). For a real host, prefer the
  socket-activation units in [root_setup/](root_setup/README.md): systemd binds
  80/443 and hands the sockets to Caddy, so no ports are published by the
  container. `root_setup` Option B keeps that privilege in one root-owned socket
  unit while Caddy runs as an unprivileged user — safer than lowering
  `net.ipv4.ip_unprivileged_port_start` system-wide.
- Run every command below from this `deployment/` directory.

## Local deployment (self-signed certificate)

```bash
cd deployment
cp .env.example .env
# Edit .env: set a real DJANGO_SECRET_KEY. Keep SITE_ADDRESS=localhost.
# Or generate it: ./generate-env.py --http-port 8080 --https-port 8443 --backend-port 8180

podman compose up -d --build
```

Then open **https://localhost**. Your browser will warn about the self-signed
certificate — that is expected; accept it (or trust Caddy's local root CA, which
lives in the `caddy_data` volume at `/data/caddy/pki/authorities/local/root.crt`).

## Internet deployment (Let's Encrypt)

1. Point your domain's DNS `A`/`AAAA` record at the server.
2. Make sure ports **80** and **443** are open to the internet.
3. Configure `.env`:

   ```dotenv
   CADDYFILE=./Caddyfile.internet
   SITE_ADDRESS=rentals.example.com
   ACME_EMAIL=admin@example.com
   DJANGO_SECRET_KEY=<a long random value>
   DJANGO_ALLOWED_HOSTS=rentals.example.com
   DJANGO_CSRF_TRUSTED_ORIGINS=https://rentals.example.com
   ```

   Or generate all of that in one go:

   ```bash
   ./generate-env.py --domain rentals.example.com --acme-email admin@example.com
   ```

4. Launch:

   ```bash
   podman compose up -d --build
   ```

Caddy provisions the certificate on first start (watch `podman compose logs -f caddy`).

## Common tasks

Create the first admin user (note the nested package — `manage.py` is in `/app/dbtrials`):

```bash
podman compose exec backend sh -c "cd /app/dbtrials && python manage.py createsuperuser"
```

Rebuild the frontend after code changes:

```bash
podman compose up -d --build frontend-build caddy
```

Apply new migrations / redeploy the backend:

```bash
podman compose up -d --build backend
```

Back up the SQLite database (consistent online backup, even while running):

```bash
# Mount the data volume read-WRITE into a throwaway container (SQLite must be
# able to take locks and, in WAL mode, touch the -wal/-shm sidecars), use
# SQLite's online backup API, and write the copy straight to the host.
ts=$(date +%Y%m%d-%H%M%S)
podman run --rm \
  -v deployment_data:/data \
  -v "$PWD":/backup \
  docker.io/library/python:3.13-slim \
  python -c "import sqlite3; \
src=sqlite3.connect('/data/db.sqlite3'); \
dst=sqlite3.connect('/backup/db-$ts.sqlite3'); \
src.backup(dst); dst.close(); src.close(); print('wrote db-$ts.sqlite3')"
```

This produces `db-<timestamp>.sqlite3` in the current directory. `src.backup()`
is SQLite's online backup, so it's safe to run while the backend is serving —
the two containers share the volume, so their SQLite file locks coordinate. The
mount is **read-write on purpose**: a read-only mount can't acquire locks or open
a WAL-mode database (SQLite needs to write the `-shm`/`-wal` files), so it would
fail. The backup itself only copies data out; it does not modify your rows.

The volume name is `deployment_data` for compose project `deployment`; confirm
with `podman volume ls`. On SELinux hosts, append `,Z` to the `"$PWD":/backup`
mount. Alternatively, run the backup inside the live backend container (same
locking, no second mount) and copy it out:

```bash
podman compose exec backend python -c "import sqlite3; \
s=sqlite3.connect('/app/data/db.sqlite3'); d=sqlite3.connect('/app/data/backup.sqlite3'); \
s.backup(d); d.close(); s.close()"
podman compose cp backend:/app/data/backup.sqlite3 ./db-backup.sqlite3
```

Restore by stopping the backend and copying a backup back into the volume:
`podman run --rm -v deployment_data:/data -v "$PWD":/backup docker.io/library/python:3.13-slim cp /backup/db-<timestamp>.sqlite3 /data/db.sqlite3`.

View logs / stop:

```bash
podman compose logs -f
podman compose down          # keep data
podman compose down -v       # also delete the sqlite db + certs (destructive)
```

## Notes

- The SQLite database persists in the `data` volume; the Let's Encrypt / internal
  certificates persist in `caddy_data`. `podman compose down -v` deletes both.
- `frontend-build` uses compose's `service_completed_successfully` condition; if
  your provider is the older native `podman-compose`, run the build first
  (`podman compose up -d --build frontend-build`) then bring up the rest.
- Caddy terminates TLS and forwards plain HTTP to gunicorn; `DJANGO_BEHIND_PROXY=true`
  makes Django trust `X-Forwarded-Proto` so it recognises the request as HTTPS.
- For heavier workloads, switch the database from SQLite to PostgreSQL (add a
  `db` service and point `DATABASES` at it) — out of scope for this setup.
