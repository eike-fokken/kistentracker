import type {
  ActionType,
  Packstreet,
  CurrentUser,
  GroupHistory,
  GroupImportResult,
  GroupOverview,
  GroupSummary,
  ItemTypeDef,
  RentAction,
} from "./types";
import { notifyLogout, readCsrfToken } from "./auth";

// All requests are same-origin relative URLs; the Vite dev server proxies
// `/api` to the Django backend (see vite.config.ts).
const API_BASE = "/api";

const UNSAFE_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

/** Error carrying the HTTP status and the backend's message. */
export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

/** Ensure a CSRF cookie exists (fetching one if needed) and return its value. */
async function ensureCsrfToken(): Promise<string> {
  let token = readCsrfToken();
  if (!token) {
    await fetch(`${API_BASE}/auth/csrf`, { credentials: "include" });
    token = readCsrfToken();
  }
  if (!token) {
    throw new ApiError(0, "CSRF-Token konnte nicht bezogen werden.");
  }
  return token;
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const method = (init?.method ?? "GET").toUpperCase();
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(init?.headers as Record<string, string> | undefined),
  };
  // State-changing requests must carry the CSRF token (cookie auth).
  if (UNSAFE_METHODS.has(method)) {
    headers["X-CSRFToken"] = await ensureCsrfToken();
  }

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...init,
      credentials: "include",
      headers,
    });
  } catch {
    throw new ApiError(0, "Server nicht erreichbar. Läuft das Backend?");
  }

  if (response.status === 401) {
    notifyLogout();
    throw new ApiError(401, "Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.");
  }

  if (!response.ok) {
    let message = `Anfrage fehlgeschlagen (${response.status}).`;
    try {
      const body = await response.json();
      if (body && typeof body.detail === "string") {
        message = body.detail;
      }
    } catch {
      // Response had no JSON body; keep the default message.
    }
    throw new ApiError(response.status, message);
  }

  if (response.status === 204) {
    return undefined as T;
  }
  return (await response.json()) as T;
}

/**
 * Authenticate with username/password. The backend starts a Django session
 * (HttpOnly cookie) and returns the current user. CSRF-protected to prevent
 * login CSRF.
 */
export async function login(
  username: string,
  password: string,
): Promise<CurrentUser> {
  const csrf = await ensureCsrfToken();
  let response: Response;
  try {
    response = await fetch(`${API_BASE}/auth/login`, {
      method: "POST",
      credentials: "include",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf },
      body: JSON.stringify({ username, password }),
    });
  } catch {
    throw new ApiError(0, "Server nicht erreichbar. Läuft das Backend?");
  }
  if (!response.ok) {
    throw new ApiError(
      response.status,
      response.status === 401
        ? "Ungültiger Benutzername oder Passwort."
        : "Anmeldung fehlgeschlagen.",
    );
  }
  return (await response.json()) as CurrentUser;
}

/** Clear the session cookie. Best-effort; ignores network/auth errors. */
export async function logout(): Promise<void> {
  try {
    const csrf = await ensureCsrfToken();
    await fetch(`${API_BASE}/auth/logout`, {
      method: "POST",
      credentials: "include",
      headers: { "X-CSRFToken": csrf },
    });
  } catch {
    // Logging out should never surface an error to the user.
  }
}

export function getCurrentUser(): Promise<CurrentUser> {
  return request<CurrentUser>("/me");
}

export function updateCurrentUser(
  show_consumables: boolean,
): Promise<CurrentUser> {
  return request<CurrentUser>("/me", {
    method: "PATCH",
    body: JSON.stringify({ show_consumables }),
  });
}

export function listPackstreets(): Promise<Packstreet[]> {
  return request<Packstreet[]>("/packstreets");
}

export function createPackstreet(name: string): Promise<Packstreet> {
  return request<Packstreet>("/packstreets", {
    method: "POST",
    body: JSON.stringify({ name }),
  });
}

export function renamePackstreet(id: number, name: string): Promise<Packstreet> {
  return request<Packstreet>(`/packstreets/${id}`, {
    method: "PUT",
    body: JSON.stringify({ name }),
  });
}

export function deletePackstreet(id: number): Promise<void> {
  return request<void>(`/packstreets/${id}`, { method: "DELETE" });
}

export function listItemTypes(): Promise<ItemTypeDef[]> {
  return request<ItemTypeDef[]>("/item-types");
}

export function createItemType(
  label: string,
  item_class?: string,
): Promise<ItemTypeDef> {
  return request<ItemTypeDef>("/item-types", {
    method: "POST",
    body: JSON.stringify({ label, item_class }),
  });
}

export function renameItemType(
  id: number,
  label: string,
  item_class: string,
): Promise<ItemTypeDef> {
  return request<ItemTypeDef>(`/item-types/${id}`, {
    method: "PUT",
    body: JSON.stringify({ label, item_class }),
  });
}

export function deleteItemType(id: number): Promise<void> {
  return request<void>(`/item-types/${id}`, { method: "DELETE" });
}

/** List groups, optionally filtered to a packstreet and/or a search term. */
export function listGroups(options?: {
  packstreetId?: number | null;
  q?: string | null;
}): Promise<GroupSummary[]> {
  const params = new URLSearchParams();
  if (options?.packstreetId != null) {
    params.set("packstreet_id", String(options.packstreetId));
  }
  const term = options?.q?.trim();
  if (term) {
    params.set("q", term);
  }
  const query = params.toString();
  return request<GroupSummary[]>(`/groups${query ? `?${query}` : ""}`);
}

export function getGroupOverview(groupId: number): Promise<GroupOverview> {
  return request<GroupOverview>(`/groups/${groupId}/overview`);
}

export function getGroupHistory(groupId: number): Promise<GroupHistory> {
  return request<GroupHistory>(`/groups/${groupId}/history`);
}

export function createGroup(payload: {
  name: string;
  group_number: string;
  packstreet_id: number;
}): Promise<GroupSummary> {
  return request<GroupSummary>("/groups", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

/** Update a group's name, number and packstreet. Admin only. */
export function updateGroup(
  groupId: number,
  payload: {
    name: string;
    group_number: string;
    packstreet_id: number;
  },
): Promise<GroupSummary> {
  return request<GroupSummary>(`/groups/${groupId}`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

/** Bulk-create groups from a CSV file. Admin only. */
export async function importGroups(file: File): Promise<GroupImportResult> {
  const csrf = await ensureCsrfToken();
  const body = new FormData();
  body.append("file", file);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}/groups/import`, {
      method: "POST",
      credentials: "include",
      // No Content-Type header: the browser sets the multipart boundary.
      headers: { "X-CSRFToken": csrf },
      body,
    });
  } catch {
    throw new ApiError(0, "Server nicht erreichbar. Läuft das Backend?");
  }

  if (response.status === 401) {
    notifyLogout();
    throw new ApiError(401, "Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.");
  }
  if (!response.ok) {
    let message = `Import fehlgeschlagen (${response.status}).`;
    try {
      const errorBody = await response.json();
      if (errorBody && typeof errorBody.detail === "string") {
        message = errorBody.detail;
      }
    } catch {
      // No JSON body; keep the default message.
    }
    throw new ApiError(response.status, message);
  }
  return (await response.json()) as GroupImportResult;
}

/** Download the per-group stock CSV, triggering a browser file save. */
export async function downloadStockCsv(): Promise<void> {
  const response = await fetch(`${API_BASE}/groups/stock.csv`, {
    credentials: "include",
  });
  if (response.status === 401) {
    notifyLogout();
    throw new ApiError(401, "Deine Sitzung ist abgelaufen. Bitte melde dich erneut an.");
  }
  if (!response.ok) {
    throw new ApiError(response.status, "Bestands-CSV konnte nicht heruntergeladen werden.");
  }
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = "gruppen-bestand.csv";
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}

export function changeQuantity(
  groupId: number,
  payload: RentAction & { action: ActionType },
): Promise<GroupSummary> {
  return request<GroupSummary>(`/groups/${groupId}/change-quantity`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
