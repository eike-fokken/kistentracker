# root_setup — socket-activated Caddy via systemd

This folder generates the **root-level** files that let systemd bind ports 80
and 443 and hand them to the rootless Caddy container through **socket
activation**. systemd owns the privileged ports; Podman forwards the sockets
into the container; Caddy binds the passed file descriptors instead of opening
its own listeners.

With socket activation you no longer need `net.ipv4.ip_unprivileged_port_start`
tweaks or `sudo` port publishing — only the tiny socket/service units run as
root.

## What gets generated

`generate.py` renders these from [templates/](templates) into `generated/`:

| File               | Purpose                                                                   |
| ------------------ | ------------------------------------------------------------------------- |
| `caddy.socket`     | One socket unit, two `ListenStream`s (HTTP then HTTPS).                    |
| `caddy.service`    | Podman unit running Caddy; inherits the activated sockets.                |
| `Caddyfile.socket` | Caddy config that binds `fd/3` (HTTP) and `fd/4` (HTTPS).                  |

The order of the two `ListenStream` lines is what maps them to descriptors:
first → `fd/3`, second → `fd/4`. The Caddyfile relies on exactly that order.

## Generate

Run as your normal user (writing files needs no root):

```bash
cd deployment/root_setup

# Local self-signed (defaults: localhost, backend on 8180):
./generate.py

# Internet with Let's Encrypt:
./generate.py --site-address rentals.example.com --acme-email you@example.com
```

Useful overrides (see `./generate.py --help` for all):

- `--backend-port` — must match `GUNICORN_PORT` / `BACKEND_PORT` in the stack (default `8180`).
- `--network`, `--frontend-volume`, `--caddy-data-volume`, `--caddy-config-volume` —
  the Podman resources created by `podman-compose` (defaults assume project name
  `deployment`; verify with `podman network ls` and `podman volume ls`).
- `--container-name`, `--image`, `--podman`, `--http-port`, `--https-port`,
  `--caddyfile-path`, `--output-dir`.

The script prints the exact `install` / `systemctl` commands to run.

## Rootless: `systemctl --user`

Because systemd (not the container) binds the ports, the whole thing runs under
a rootless **user** manager as long as both ports are unprivileged (>= 1024).
Pass `--user` (and high ports):

```bash
./generate.py --user --http-port 8080 --https-port 8443
```

This adjusts the units for the user manager (`WantedBy=default.target`, drops the
system-only `network-online.target`, defaults the Caddyfile to
`~/.config/caddy/`), and prints `systemctl --user` install steps — no root at
all. Use `loginctl enable-linger "$USER"` so it starts at boot without an active
login session. The referenced network/volumes must exist in your **rootless**
Podman (they do if you ran `podman-compose` as your user).

For convenience, [install-user.sh](install-user.sh) performs the user-mode
install from `generated/`. It is idempotent: each run first tears down anything a
previous run installed (stops/disables the units, removes the container, deletes
old files) so you always get a clean slate.

```bash
./generate.py --user --http-port 8080 --https-port 8443 --backend-port 8180
./install-user.sh
```

## Privileged ports 80/443 on a real machine

You have three ways to serve on 80/443; they trade off privilege vs. simplicity:

| Mode | Who binds 80/443 | Who runs Caddy | Notes |
| ---- | ---------------- | -------------- | ----- |
| **A** rootless + sysctl | user manager | the user | needs `net.ipv4.ip_unprivileged_port_start=80`, which is **system-wide** (any user may then bind low ports). Simplest but weakest isolation. |
| **B** `--run-as` (recommended) | **root** socket unit | an unprivileged user | root binds the ports and passes the sockets to a service that drops to `--run-as`. No system-wide sysctl. |
| **C** rootful | root socket unit | root | whole stack runs as root podman. Simplest privilege model, no rootless benefits. |

### Option B — root socket, unprivileged service (recommended)

```bash
./generate.py \
  --run-as appuser \
  --http-port 80 --https-port 443 --backend-port 8000 \
  --site-address app.example.com --acme-email you@example.com \
  --network app_dbtrials --frontend-volume app_frontend \
  --caddy-data-volume app_caddy_data --caddy-config-volume app_caddy_config
```

This produces **system** units where the `.socket` is root-owned (binds 80/443)
and the `.service` runs `podman` as `appuser` with `Environment=XDG_RUNTIME_DIR=/run/user/<uid>`,
ordered after `user@<uid>.service`. Setting `User=` alone is **not** enough —
rootless podman also needs that runtime dir and the user's lingering manager,
which these units and the printed steps set up. The `<uid>` is looked up from
`/etc/passwd`; pass `--run-as-uid` if generating on a different host.

Because the service uses `appuser`'s **rootless** podman, the backend + frontend
stack must also run as `appuser` so it owns the referenced network/volumes:

```bash
sudo loginctl enable-linger appuser
sudo machinectl shell appuser@ /bin/sh -c \
  'cd /path/to/app/deployment && podman-compose up -d backend frontend-build'
```

## Install (system manager, as root)

For a plain root-run service (Option C, or a root Caddy), after generating,
review the files, then:

```bash
# Place the Caddyfile where the service mounts it (default path is printed):
sudo install -D -m 0644 generated/Caddyfile.socket /etc/caddy/caddy.Caddyfile

# Install the units:
sudo install -m 0644 generated/caddy.socket  /etc/systemd/system/
sudo install -m 0644 generated/caddy.service /etc/systemd/system/

sudo systemctl daemon-reload
sudo systemctl enable --now caddy.socket
```

Bring up the rest of the stack (without the compose `caddy` service, which this
replaces):

```bash
cd ..
podman-compose up -d backend frontend-build
```

## Notes

- **One socket, two streams.** `caddy.socket` declares `ListenStream=80` then
  `ListenStream=443`; Caddy binds them as `fd/3` and `fd/4` respectively.
- **No published ports.** `caddy.service` runs `podman run` without `-p`; all
  listeners come from the socket unit.
- **SELinux.** If enforcing, either relabel the mounted Caddyfile
  (`restorecon -v /etc/caddy/caddy.Caddyfile`) or add `,Z` to that bind mount
  in the service unit.
- **System vs. rootful Podman.** The service runs `podman run` as root (system
  service). Ensure the referenced network/volumes exist in the same (root)
  Podman that the unit uses, or adjust names/paths accordingly.
- **`aardvark-dns` fd leak on the network.** If Caddy is the *first* container to
  touch the podman network, `podman` may spawn the network's `aardvark-dns`
  resolver while Caddy's socket-activated fds are open, and the resolver inherits
  them. It then holds `:80`/`:443` even after Caddy stops, so a restart fails with
  `Address already in use`. Avoid it by ordering Caddy *after* a plain
  network-internal container (the `backend`) so `aardvark-dns` is already running
  cleanly. If you hit it, `pkill -f aardvark-dns` (podman respawns it) and restart
  `caddy.socket`. Confirm with `ss -ltnp | grep -E ':80|:443'` — the holder should
  be `caddy`/`conmon`, never `aardvark-dns`.

## Serving multiple apps

Every app here is a Django backend + Vite SPA using this same deployment. Each is
its own compose project; give each a unique project name (own directory, or
`COMPOSE_PROJECT_NAME`) so its network/volumes/containers don't collide
(`app1_dbtrials`, `app1_frontend`, ...).

The hard constraint: only one process can own `:80`/`:443` on a host. So there
are two topologies.

### One Caddy per app (separate hosts)

Fine when each app runs on its **own** host/VM (or distinct ports/IPs). Just run
`generate.py` once per app, pointing `--network` / `--*-volume` /
`--site-address` at that app's resources. Nothing special beyond unique names.

### One shared Caddy for several apps on one host (recommended)

Run a **single** socket-activated Caddy on 80/443 and route by hostname. This is
a manual setup (the generator intentionally stays single-site); do it by hand:

1. Use a **subdomain per app** (`app1.example.com`, `app2.example.com`). This
   keeps every SPA at URL root `/`, so no Vite rebuild is needed (see the base
   path note below).
2. Put all backends and the shared Caddy on a **common network** (e.g. create a
   `web` network and have every app's backend join it), or attach Caddy to each
   app's network with repeated `--network app1_net --network app2_net ...`.
3. Mount each app's frontend volume into Caddy at a distinct path
   (`app1_frontend:/srv/app1:ro`, `app2_frontend:/srv/app2:ro`).
4. Write one Caddy site block per domain:

   ```caddyfile
   app1.example.com {
       @backend path /api/* /admin/* /static/*
       handle @backend { reverse_proxy app1_backend:8000 }
       handle { root * /srv/app1; try_files {path} /index.html; file_server }
   }
   app2.example.com {
       @backend path /api/* /admin/* /static/*
       handle @backend { reverse_proxy app2_backend:8000 }
       handle { root * /srv/app2; try_files {path} /index.html; file_server }
   }
   ```

5. Caddy auto-provisions a Let's Encrypt certificate per domain (one `email`
   global option). Adding an app = add a site block + its network/volume mount,
   then reload.

Prefer subdomains over path prefixes (`example.com/app1/`). A path prefix forces
a Vite rebuild with a matching `base`, a router `basename`, and a reworked API
base URL — see below.

### Why a path prefix needs a matching Vite `base`

`vite build` bakes the asset URLs into `index.html` using the `base` option
(default `/`), e.g. `<script src="/assets/index-abc.js">` — absolute from the
site root. Served at `https://example.com/app1/`, the browser would still fetch
`/assets/...` (i.e. `example.com/assets/...`), which 404s; it must be
`/app1/assets/...`. Setting Vite's `base` to `/app1/` makes the build emit
`/app1/assets/...`.

This is a **frontend build-time** setting, not a Django setting: set it in
`vite.config.ts` (`base: "/app1/"`) or pass `--base=/app1/` to `vite build`. You
would also need to set the SPA router's `basename` to `/app1` and change the API
base (`frontend/src/api.ts` uses a root-relative `/api`) to `/app1/api`, and
route that prefix to the backend in Caddy. Subdomains avoid all of this.

### Rebuilding the frontend per app (path-prefix case)

Because each app already has its own `frontend-build` container, giving an app a
matching `base` is just a per-app build — no shared state, so this is fine to do.
Two ways:

- **Per-app `vite.config.ts`:** set `base: "/app1/"` in that app's checkout and
  build as usual. Simplest when each app is a separate repo/copy.
- **Build arg (one shared Dockerfile):** thread the base through as a build
  argument so the same `frontend.Dockerfile` serves every app. For example add to
  it:

  ```dockerfile
  ARG VITE_BASE=/
  RUN npm run build -- --base "$VITE_BASE"
  ```

  and pass it per app in `compose.yml`:

  ```yaml
  frontend-build:
    build:
      context: ..
      dockerfile: deployment/frontend.Dockerfile
      args:
        VITE_BASE: /app1/
  ```

Rebuild that app's frontend after changing the base:

```bash
podman-compose up -d --build frontend-build
```

Remember to also update the router `basename` and the API base to the same
prefix (see above), then reload the shared Caddy. Subdomains remain the simpler
default since they need none of this.
