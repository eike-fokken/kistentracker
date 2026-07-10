import { useState, type FormEvent } from "react";

import {
  ApiError,
  createItemType,
  deleteItemType,
  renameItemType,
} from "../api";
import type { ItemTypeDef } from "../types";

interface Props {
  itemTypes: ItemTypeDef[];
  onChanged: () => void;
}

export function ItemTypeManager({ itemTypes, onChanged }: Props) {
  const [open, setOpen] = useState(false);
  const [newLabel, setNewLabel] = useState("");
  const [newItemClass, setNewItemClass] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editLabel, setEditLabel] = useState("");
  const [editItemClass, setEditItemClass] = useState("");

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
    const label = newLabel.trim();
    if (!label) {
      setError("Bitte gib einen Artikeltyp-Namen ein.");
      return;
    }
    const ok = await run(() => createItemType(label, newItemClass));
    if (ok) {
      setNewLabel("");
      setNewItemClass("");
    }
  }

  function startEdit(itemType: ItemTypeDef) {
    setEditingId(itemType.id);
    setEditLabel(itemType.label);
    setEditItemClass(itemType.item_class);
    setError(null);
  }

  async function saveEdit(id: number, newItemClass: string, oldItemClass: string) {
    const label = editLabel.trim();
    if (!label) {
      setError("Bitte gib einen Artikeltyp-Namen ein.");
      return;
    }
    if (newItemClass !== oldItemClass) {
      if (
        !window.confirm(
          `Die Artikel-Klasse von „${editLabel}“ von „${oldItemClass}“ auf „${newItemClass}“ ändern?`,
        )
      ) {
        return;
      }
    }
    const ok = await run(() => renameItemType(id, label, newItemClass));
    if (ok) {
      setEditingId(null);
    }
  }

  async function handleDelete(itemType: ItemTypeDef) {
    if (
      !window.confirm(
        `Artikeltyp „${itemType.label}“ löschen? Dies ist nur möglich, wenn er von keiner Gruppe ausgeliehen ist.`,
      )
    ) {
      return;
    }
    await run(() => deleteItemType(itemType.id));
  }

  return (
    <section className="card packstreets">
      <div className="packstreets__bar">
        <h2>Artikeltypen</h2>
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
              value={newLabel}
              placeholder="Neuer Artikeltyp-Name"
              onChange={(e) => setNewLabel(e.target.value)}
              disabled={busy}
              aria-label="Neuer Artikeltyp-Name"
            />
            <select
              value={newItemClass}
              onChange={(e) => setNewItemClass(e.target.value)}
              disabled={busy}
              aria-label="Artikeltyp-Klasse"
            >
              <option value="">Bitte wählen…</option>
              <option value="rentable">Ausleihbar</option>
              <option value="consumable">Verbrauchbar</option>
            </select>
            <button type="submit" className="btn btn--primary" disabled={busy}>
Hinzufügen
            </button>
          </form>

          {itemTypes.length === 0 ? (
            <p className="empty">Noch keine Artikeltypen.</p>
          ) : (
            <ul className="packstreets__list">
              {itemTypes.map((itemType) => (
                <li key={itemType.id} className="packstreets__item">
                  {editingId === itemType.id ? (
                    <>
                      <input
                        type="text"
                        value={editLabel}
                        onChange={(e) => setEditLabel(e.target.value)}
                        disabled={busy}
                        aria-label={`${itemType.label} umbenennen`}
                      />
                      <select
                        value={editItemClass}
                        onChange={(e) => setEditItemClass(e.target.value)}
                        disabled={busy}
                        aria-label="Artikeltyp-Klasse bearbeiten"
                      >
                        <option value="rentable">Ausleihbar</option>
                        <option value="consumable">Verbrauchbar</option>
                      </select>
                      <div className="packstreets__actions">
                        <button
                          type="button"
                          className="btn btn--primary"
                          onClick={() =>
                            void saveEdit(itemType.id, editItemClass, itemType.item_class)
                          }
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
                      <span className="packstreets__name">{itemType.label}</span>
                      <div className="packstreets__actions">
                        <button
                          type="button"
                          className="link"
                          onClick={() => startEdit(itemType)}
                          disabled={busy}
                        >
                          Bearbeiten
                        </button>
                        <button
                          type="button"
                          className="link link--danger"
                          onClick={() => void handleDelete(itemType)}
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
