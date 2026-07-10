#!/usr/bin/env bash
set -u
b="https://localhost:8443"
printf 'SPA   /            -> %s\n' "$(curl -ksS -o /dev/null -w '%{http_code}' "$b/")"
printf 'API   /api/docs    -> %s\n' "$(curl -ksS -o /dev/null -w '%{http_code}' "$b/api/docs")"
printf 'API   /api         -> %s\n' "$(curl -ksS -o /dev/null -w '%{http_code}' "$b/api")"
printf 'Admin /admin/      -> %s\n' "$(curl -ksS -o /dev/null -w '%{http_code}' "$b/admin/")"
printf 'Static/admin css   -> %s\n' "$(curl -ksS -o /dev/null -w '%{http_code}' "$b/static/admin/css/base.css")"
printf 'HTTP  redirect     -> %s -> %s\n' "$(curl -sS -o /dev/null -w '%{http_code}' http://localhost:8080/)" "$(curl -sS -o /dev/null -w '%{redirect_url}' http://localhost:8080/)"
printf 'HTTP  follow (-L)   -> final=%s url=%s\n' "$(curl -ksSL -o /dev/null -w '%{http_code}' http://localhost:8080/)" "$(curl -ksSL -o /dev/null -w '%{url_effective}' http://localhost:8080/)"
printf 'caddy.service      -> %s\n' "$(systemctl --user is-active caddy.service)"
