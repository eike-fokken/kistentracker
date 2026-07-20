import { useState, type FormEvent } from "react";

import { ApiError, createGroup } from "../api";
import type { Packstreet, GroupSummary } from "../types";

interface Props {
  packstreets: Packstreet[];
  defaultPackstreetId: number | null;
  onCreated: (group: GroupSummary) => void;
}

export function CreateGroupForm({
  packstreets,
  defaultPackstreetId,
  onCreated,
}: Props) {
  const nonStockPackstreets = packstreets.filter((p) => !p.is_stock);
  const isDefaultStock = defaultPackstreetId != null
    && packstreets.some((p) => p.id === defaultPackstreetId && p.is_stock);

  const [name, setName] = useState("");
  const [groupNumber, setGroupNumber] = useState("");
  const [packstreetId, setPackstreetId] = useState<number | "">(
    isDefaultStock ? "" : (defaultPackstreetId ?? ""),
  );
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const trimmedName = name.trim();
    const trimmedNumber = groupNumber.trim();
    if (!trimmedName) {
      setError("Bitte gib einen Gruppennamen ein.");
      return;
    }
    if (!trimmedNumber) {
      setError("Bitte gib eine Kochgruppen-ID ein.");
      return;
    }
    if (packstreetId === "") {
      setError("Bitte wähle eine Packstraße aus.");
      return;
    }

    setSubmitting(true);
    setError(null);
    try {
      const group = await createGroup({
        name: trimmedName,
        internal_id: trimmedNumber,
        packstreet_id: packstreetId,
      });
      onCreated(group);
      setName("");
      setGroupNumber("");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Gruppe konnte nicht erstellt werden.",
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <form className="card create-group" onSubmit={handleSubmit}>
      <h2>Neue Gruppe</h2>
{nonStockPackstreets.length === 0 ? (
        <p className="empty">Erstelle zuerst eine Packstraße, bevor du Gruppen anlegst.</p>
      ) : (
        <div className="create-group__row">
          <input
            type="text"
            value={name}
            placeholder="Gruppenname"
            onChange={(e) => setName(e.target.value)}
            disabled={submitting}
            aria-label="Gruppenname"
          />
          <input
            type="text"
            value={groupNumber}
            placeholder="Kochgruppen-ID"
            onChange={(e) => setGroupNumber(e.target.value)}
            disabled={submitting}
            aria-label="Kochgruppen-ID"
          />
          <select
            value={packstreetId}
            onChange={(e) =>
              setPackstreetId(e.target.value === "" ? "" : Number(e.target.value))
            }
            disabled={submitting}
            aria-label="Packstraße"
          >
            <option value="">Packstraße…</option>
            {nonStockPackstreets.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
              </option>
            ))}
          </select>
          <button
            type="submit"
            className="btn btn--primary"
            disabled={submitting}
          >
            {submitting ? "Erstelle…" : "Erstellen"}
          </button>
        </div>
      )}
      {error && <p className="banner banner--error">{error}</p>}
    </form>
  );
}
