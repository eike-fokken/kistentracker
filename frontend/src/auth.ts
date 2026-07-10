// Browser session helpers for the cookie-based auth flow.
//
// The Django session lives in an HttpOnly cookie set by the backend, so JS
// cannot (and need not) read it. The only cookie we read here is the CSRF
// token, which the backend keeps JS-readable so we can echo it back as the
// `X-CSRFToken` header on unsafe requests.

/** Read the CSRF token from `document.cookie`, or null if not set yet. */
export function readCsrfToken(): string | null {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : null;
}

/** Event dispatched when the session ends (logged out / expired). */
export const LOGOUT_EVENT = "auth:logout";

export function notifyLogout(): void {
  window.dispatchEvent(new Event(LOGOUT_EVENT));
}
