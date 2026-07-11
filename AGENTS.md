## IMPORTANT

NEVER edit files outside this directory!
IGNORE the deployment directory!

NEVER use `uv` and never suggest to use `uv`. This project exclusively uses `poetry`.

## Environment

**Python version management** uses Poetry (`pyproject.toml` + `poetry.lock` at repo root). Python dependencies are defined in `pyproject.toml` under `[project]` and `[dependency-groups]`. To run Django management commands, use `poetry run` (which reads Poetry's `pyproject.toml` directly):


```
cd dbtrials && poetry run manage.py <command>
```

For example: `poetry run manage.py test`, `poetry run manage.py migrate`, `poetry run manage.py check`, `poetry run manage.py createsuperuser`.

## Project Overview

**Kistentracker** (German: "crate tracker") is a rental/inventory tracking system for cooking camps. It tracks which items (e.g. computers, flipcharts) are rented by which cooking groups stationed at packstreets (physical streets/areas). The stack is a Django REST API backend + React SPA frontend.

---

## Backend (`dbtrials/`)

- **Framework:** Django 6.0 with Django Ninja (`ninja` + `ninja-extra` extension), SQLite database
- **Auth:** Dual auth — Django session cookies for the browser SPA, JWT (via `ninja-jwt`) for programmatic/server access
- **Static files:** WhiteNoise middleware

### Models (`dbtrials/models.py`)

| Model | Purpose | Key Fields |
|---|---|---|
| `User` (extends `AbstractUser`) | Custom user with `role` (USER/ADMIN) and `show_consumables` preference | `role`, `show_consumables` |
| `Packstreet` | Physical location where cooking groups are stationed | `name` (unique) |
| `Cookinggroup` | A rental group belonging to a Packstreet | `name`, `internal_id`, `packstreet` (FK, PROTECT) |
| `ItemType` | Admin-managed item categories (rentable or consumable); `key` is a stable slug | `key`, `label`, `item_class` |
| `Rental` | Current quantity of an item type rented by a group | `group` (FK), `item_type` (string), `quantity` — unique on (group, item_type) |
| `RentalAction` | Audit log of every rent/return/correction | `group`, `user` (nullable), `action` (rent/return/correct), `item_type`, `quantity` (signed), `timestamp` |

### Permissions (`dbtrials/permissions.py`)

Declarative, fail-closed authorization:
- **`AllowAny`** — no auth required
- **`IsAuthenticated`** — any logged-in user
- **`IsAdmin`** — admin role required
- **`@require_permissions`** decorator attaches a permission policy to a view
- **`PermissionRouter`** (subclass of Ninja's `Router`) enforces policies on every endpoint; views with **no** declared policy are denied (HTTP 500 — fail-closed)

### API Endpoints (`dbtrials/api.py`)

All endpoints registered on a `PermissionRouter` on `/api/`:

| Endpoint | Auth | Method | Purpose |
|---|---|---|---|
| `/auth/csrf` | AllowAny | GET | Sets CSRF cookie for browser SPA |
| `/auth/login` | AllowAny | POST | Browser cookie login |
| `/auth/logout` | AllowAny | POST | End session |
| `/token/pair`, `/token/refresh` | JWT controller | POST | JWT access/refresh tokens |
| `/me` | IsAuthenticated | GET/PATCH | Current user info & preferences |
| `/packstreets` | IsAuthenticated (list), IsAdmin (mutate) | GET/POST | Packstreet CRUD |
| `/packstreets/{id}` | IsAdmin | PUT/DELETE | Rename/delete packstreet |
| `/item-types` | IsAuthenticated (list), IsAdmin (mutate) | GET/POST | Item type CRUD |
| `/item-types/{id}` | IsAdmin | PUT/DELETE | Edit/delete item type |
| `/groups` | IsAuthenticated (list), IsAdmin (create) | GET/POST | List/create groups |
| `/groups/{id}` | IsAuthenticated | GET/PUT | Single group summary / update |
| `/groups/{id}/overview` | IsAuthenticated | GET | Detailed overview with all item types + recent actions |
| `/groups/{id}/history` | IsAuthenticated | GET | Stock-over-time data for charting |
| `/groups/{id}/change-quantity` | IsAuthenticated | POST | Rent/return/correct item quantity |
| `/groups/stock.csv` | IsAuthenticated | GET | CSV stock export |
| `/groups/import` | IsAdmin | POST | CSV bulk group import |

### Configuration (`dbtrials/settings.py`)

All env-var driven: `SECRET_KEY`, `DJANGO_DEBUG`, `ALLOWED_HOSTS`, `DJANGO_DB_PATH`, `DJANGO_STATIC_ROOT`, `DJANGO_CSRF_TRUSTED_ORIGINS`. Debug off by default. CSRF cookie is **not** HttpOnly so the SPA can read it.

---

## Frontend (`frontend/`)

- **Stack:** React 19, TypeScript 5.6 (strict mode), Vite 6
- **Charts:** Recharts 2.15
- **Routing:** Manual hash-based (no router library) — 3 views: list (`#`), overview (`#/group/{id}`), history (`#/group/{id}/history`)
- **State:** React `useState`/hooks only; no external state library
- **HTTP:** Native `fetch` with CSRF header injection
- **Auth:** Cookie-based Django sessions; 401 responses trigger logout via `"auth:logout"` DOM event
- **Dev:** Vite dev server on port 5173 proxies `/api` to Django on port 8080
- **CSS:** Single `styles.css` with CSS custom properties (BEM-like naming), German-language UI

### Components (`frontend/src/components/`)

| Component | Purpose | Admin-only? |
|---|---|---|
| `LoginForm` | Username/password login form | No |
| `PackstreetManager` | CRUD for Packstreets (expandable card) | Yes |
| `ItemTypeManager` | CRUD for ItemTypes (expandable card) | Yes |
| `CreateGroupForm` | Create new Group | Yes |
| `DataImport` | CSV bulk import of Groups | Yes |
| `GroupsTable` | HTML table listing all Groups with item-type quantity columns | No |
| `GroupOverview` | Detail view: edit group, item rows with rent/return, audit log | No (edit: admin) |
| `OverviewItemRow` | Single row in GroupOverview for rent/return/correct actions | No |
| `GroupHistory` | Line charts (Recharts) of item stock over time | No |

### Key Files

| File | Purpose |
|---|---|
| `src/main.tsx` | React bootstrap (`createRoot`) |
| `src/App.tsx` | Root component: auth state, route parsing, global state, renders all views |
| `src/api.ts` | All backend API calls via `fetch`, CSRF injection, 401 detection |
| `src/auth.ts` | CSRF token reading from cookie, `notifyLogout()` event dispatch |
| `src/types.ts` | All TypeScript interfaces (User, Group, ItemType, etc.) |
| `src/styles.css` | All application CSS |

---

## Key Behaviors
- **CSRF:** The SPA reads the `csrftoken` cookie (non-HttpOnly), sends it as `X-CSRFToken` header on all unsafe requests. On first load, if no CSRF cookie exists, it fetches `/api/auth/csrf`.
- **Consumable toggling:** Users can show/hide consumable items via a toggle; preference is persisted on the backend (`User.show_consumables`).
- **Debounced search:** 250ms debounce on the group search input.
- **Stock history:** `GET /groups/{id}/history` returns per-item-type time-series data (cumulative quantity after each action), rendered as Recharts line charts with stepAfter interpolation.
- **CSV import:** Heuristic header detection; skips rows with too many columns; requires internal_id and group_name columns.
- **Create superuser:** `cd dbtrials && poetry run manage.py createsuperuser`
