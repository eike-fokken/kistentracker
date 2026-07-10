# dbtrials frontend

A small React + TypeScript single-page app (built with [Vite](https://vite.dev/))
for the dbtrials Django/django-ninja backend. It lists rental groups and lets you
create groups and rent/return computers and flipcharts.

## Develop

```bash
cd frontend
npm install
npm run dev          # serves on http://localhost:5173
```

Start the backend separately so the dev proxy has something to talk to:

```bash
cd dbtrials && poetry run python manage.py runserver 8080
```

The Vite dev server proxies all `/api` requests to `http://localhost:8080`
(see [vite.config.ts](vite.config.ts)), so no CORS configuration is needed during
development.

## Build

```bash
npm run build        # type-checks and outputs static files to dist/
npm run preview      # serves the production build locally
```

## Structure

- `src/types.ts` — TypeScript types mirroring the backend `schemas.py`.
- `src/api.ts` — typed `fetch` wrapper for the `/api` endpoints.
- `src/components/` — `CreateGroupForm`, `GroupCard`, `RentReturnForm`.
- `src/App.tsx` — top-level state and layout.
