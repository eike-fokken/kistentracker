import { useState, type FormEvent } from "react";

import { ApiError, createPackstreet, deletePackstreet, renamePackstreet } from "../api";
import type { Packstreet } from "../types";

interface Props {
  packstreets: Packstreet[];
  onChanged: () => void;
}

export function PackstreetManager({ packstreets, onChanged }: Props) {
  const visiblePackstreets = packstreets.filter((p) => !p.is_stock);
  const [open, setOpen] = useState(false);
  const [newName, setNewName] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editName, setEditName] = useState("");

  async function run(action: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      onChanged();
      return true;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Aktion fehlgeschlagen.");
      return false;
    } finally {
      setBusy(false);
    }
  }

  async function handleAdd(event: FormEvent) {
    event.preventDefault();
    const name = newName.trim();
    if (!name) {
      setError("Bitte gib einen Packstraßennamen ein.");
      return;
    }
    const ok = await run(() => createPackstreet(name));
    if (ok) {
      setNewName("");
    }
  }

  function startEdit(p: Packstreet) {
    setEditingId(p.id);
    setEditName(p.name);
    setError(null);
  }

  async function saveEdit(id: number) {
    const name = editName.trim();
    if (!name) {
      setError("Bitte gib einen Packstraßennamen ein.");
      return;
    }
    const ok = await run(() => renamePackstreet(id, name));
    if (ok) {
      setEditingId(null);
    }
  }

  async function handleDelete(p: Packstreet) {
    if (
      !window.confirm(
        `Packstraße „${p.name}“ löschen? Dies ist nur möglich, wenn sie keine Gruppen enthält.`,
      )
    ) {
      return;
    }
    await run(() => deletePackstreet(p.id));
  }

  return (
    <section className="card packstreets">
      <div className="packstreets__bar">
        <h2>Packstraßen</h2>
        <button
          type="button"
          className="btn btn--ghost"
          onClick={() => setOpen((v) => !v)}
        >
          {open ? "Ausblenden" : "Verwalten"}
        </button>
      </div>

      {open && (
        <>
          <form className="create-group__row" onSubmit={handleAdd}>
            <input
              type="text"
              value={newName}
              placeholder="Neuer Packstraßenname"
              onChange={(e) => setNewName(e.target.value)}
              disabled={busy}
              aria-label="Neuer Packstraßenname"
            />
            <button type="submit" className="btn btn--primary" disabled={busy}>
              Hinzufügen
            </button>
          </form>

          {visiblePackstreets.length === 0 ? (
            <p className="empty">Noch keine Packstraßen.</p>
          ) : (
            <ul className="packstreets__list">
              {visiblePackstreets.map((p) => (
                <li key={p.id} className="packstreets__item">
                  {editingId === p.id ? (
                    <>
                      <input
                        type="text"
                        value={editName}
                        onChange={(e) => setEditName(e.target.value)}
                        disabled={busy}
                        aria-label={`${p.name} umbenennen`}
                      />
                      <div className="packstreets__actions">
                        <button
                          type="button"
                          className="btn btn--primary"
                          onClick={() => void saveEdit(p.id)}
                          disabled={busy}
                        >
                          Speichern
                        </button>
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() => setEditingId(null)}
                          disabled={busy}
                        >
                          Abbrechen
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <span className="packstreets__name">{p.name}</span>
                      <div className="packstreets__actions">
                        <button
                          type="button"
                          className="link"
                          onClick={() => startEdit(p)}
                          disabled={busy}
                        >
                          Umbenennen
                        </button>
                        <button
                          type="button"
                          className="link link--danger"
                          onClick={() => void handleDelete(p)}
                          disabled={busy}
                        >
                          Löschen
                        </button>
                      </div>
                    </>
                  )}
                </li>
              ))}
            </ul>
          )}
          {error && <p className="banner banner--error">{error}</p>}
        </>
      )}
    </section>
  );
}