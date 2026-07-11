import { useRef, useState, type FormEvent } from "react";

import { ApiError, importGroups } from "../api";
import type { GroupImportResult } from "../types";

interface Props {
  onImported: () => void;
}

export function DataImport({ onImported }: Props) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<GroupImportResult | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  function reset() {
    setFile(null);
    setResult(null);
    setError(null);
    if (inputRef.current) {
      inputRef.current.value = "";
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    if (!file) {
      setError("Bitte wähle eine CSV-Datei zum Importieren aus.");
      return;
    }
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      const imported = await importGroups(file);
      setResult(imported);
      if (imported.created.length > 0) {
        onImported();
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Import fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card packstreets">
      <div className="packstreets__bar">
        <h2>Gruppen importieren</h2>
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
          <p className="import__hint">
            Lade eine CSV-Datei mit einer Gruppe pro Zeile hoch:{" "}
            <code>Gruppenname, Kochgruppen-ID, Packstraße</code> (eine optionale
            Kopfzeile wird ignoriert). Gruppen, deren Name oder ID bereits
            existieren, bleiben unverändert. Packstraßen müssen bereits vorhanden sein.
          </p>

          <form className="create-group__row" onSubmit={handleSubmit}>
            <input
              ref={inputRef}
              type="file"
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setResult(null);
                setError(null);
              }}
              disabled={busy}
              aria-label="Zu importierende CSV-Datei"
            />
            <button
              type="submit"
              className="btn btn--primary"
              disabled={busy || !file}
            >
              {busy ? "Importiere…" : "Importieren"}
            </button>
            {(file || result) && (
              <button
                type="button"
                className="btn btn--ghost"
                onClick={reset}
                disabled={busy}
              >
                Zurücksetzen
              </button>
            )}
          </form>

          {error && <p className="banner banner--error">{error}</p>}

          {result && (
            <div className="import__result">
              <p className="import__summary">
                Erstellt <strong>{result.created.length}</strong>, übersprungen{" "}
                <strong>{result.skipped.length}</strong>, Fehler{" "}
                <strong>{result.errors.length}</strong>.
              </p>

              {result.created.length > 0 && (
                <details open>
                  <summary>Erstellt ({result.created.length})</summary>
                  <ul className="import__list">
                    {result.created.map((row) => (
                      <li key={`created-${row.internal_id}-${row.name}`}>
                        {row.name} <span className="overview__number">
                          #{row.internal_id}
                        </span>{" "}
                        — {row.packstreet}
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              {result.skipped.length > 0 && (
                <details>
                  <summary>Übersprungen — bereits vorhanden ({result.skipped.length})</summary>
                  <ul className="import__list">
                    {result.skipped.map((row) => (
                      <li key={`skipped-${row.internal_id}-${row.name}`}>
                        {row.name} <span className="overview__number">
                          #{row.internal_id}
                        </span>{" "}
                        — {row.packstreet}
                      </li>
                    ))}
                  </ul>
                </details>
              )}

              {result.errors.length > 0 && (
                <details open>
                  <summary>Fehler ({result.errors.length})</summary>
                  <ul className="import__list import__list--errors">
                    {result.errors.map((message, index) => (
                      <li key={`error-${index}`}>{message}</li>
                    ))}
                  </ul>
                </details>
              )}
            </div>
          )}
        </>
      )}
    </section>
  );
}
