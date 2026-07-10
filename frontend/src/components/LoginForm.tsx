import { useState, type FormEvent } from "react";

import { ApiError, login } from "../api";
import type { CurrentUser } from "../types";

interface Props {
  onSuccess: (user: CurrentUser) => void;
}

export function LoginForm({ onSuccess }: Props) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const user = await login(username, password);
      onSuccess(user);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Anmeldung fehlgeschlagen.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card login" onSubmit={handleSubmit}>
      <h2>Anmelden</h2>
      <label className="login__field">
        <span>Benutzername</span>
        <input
          type="text"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          disabled={submitting}
          required
        />
      </label>
      <label className="login__field">
        <span>Passwort</span>
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          disabled={submitting}
          required
        />
      </label>
      <button type="submit" className="btn btn--primary" disabled={submitting}>
        {submitting ? "Anmelden…" : "Anmelden"}
      </button>
      {error && <p className="banner banner--error">{error}</p>}
    </form>
  );
}
