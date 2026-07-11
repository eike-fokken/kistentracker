import { useCallback, useEffect, useState } from "react";

import { ApiError, getGroupOverview, updateCurrentUser, updateGroup } from "../api";
import type {
  Packstreet,
  GroupOverview as GroupOverviewData,
  GroupSummary,
  RentalActionLog,
} from "../types";
import { OverviewItemRow } from "./OverviewItemRow";

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

function describeAction(
  entry: RentalActionLog,
  labels: Record<string, string>,
) {
  const verb =
    entry.action === "rent"
      ? "ausgegeben"
      : entry.action === "correct"
        ? "korrigiert"
        : "zurückgenommen";
  const label = labels[entry.item_type] ?? entry.item_type;
  const isCorrect = entry.action === "correct";
  const isNegative = entry.quantity < 0;

  const cssClass =
    entry.action === "correct"
      ? "action-log__verb--correct"
      : entry.action === "rent"
        ? "action-log__verb--rent"
        : "action-log__verb--return";

  return (
    <>
      <span className={cssClass}>
        {verb}
      </span>{" "}
      {isNegative && <span className="action-log__verb--minus">−</span>}
      <span
        className={
          isNegative
            ? "action-log__verb--minus"
            : isCorrect && entry.quantity >= 0
              ? "action-log__verb--plus"
              : ""
        }
      >
        {Math.abs(entry.quantity)}
      </span>{" "}
      × {label}
    </>
  );
}

interface Props {
  groupId: number;
  isAdmin: boolean;
  packstreets: Packstreet[];
  showConsumables: boolean;
  onBack: () => void;
  onViewHistory: () => void;
  onGroupChanged: (group: GroupSummary) => void;
}

export function GroupOverview({
  groupId,
  isAdmin,
  packstreets,
  showConsumables: showConsumablesProp,
  onBack,
  onViewHistory,
  onGroupChanged,
}: Props) {
  const [data, setData] = useState<GroupOverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editNumber, setEditNumber] = useState("");
  const [editPackstreetId, setEditPackstreetId] = useState<number | "">("");
const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [correctingConsumables, setCorrectingConsumables] = useState(false);
  const [showConsumables, setShowConsumables] = useState(showConsumablesProp);

  useEffect(() => {
    setShowConsumables(showConsumablesProp);
  }, [showConsumablesProp]);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getGroupOverview(groupId));
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Übersicht konnte nicht geladen werden.",
      );
    } finally {
      setLoading(false);
    }
  }, [groupId]);

  useEffect(() => {
    void load();
  }, [load]);

  // After a rent/return/correct action: keep the groups table in sync (using the
  // GroupSummary returned by the endpoint) and reload the per-item overview.
  const handleUpdated = useCallback(
    (group: GroupSummary) => {
      onGroupChanged(group);
      void load();
    },
    [onGroupChanged, load],
  );

  function startEdit() {
    if (!data) {
      return;
    }
    setEditName(data.name);
    setEditNumber(data.internal_id);
    setEditPackstreetId(data.packstreet.id);
    setEditError(null);
    setEditing(true);
  }

  async function saveEdit() {
    const name = editName.trim();
    const number = editNumber.trim();
    if (!name) {
      setEditError("Bitte gib einen Gruppennamen ein.");
      return;
    }
    if (!number) {
      setEditError("Bitte gib eine Kochgruppen-ID ein.");
      return;
    }
    if (editPackstreetId === "") {
      setEditError("Bitte wähle eine Packstraße aus.");
      return;
    }
    setSaving(true);
    setEditError(null);
    try {
      const updated = await updateGroup(groupId, {
        name,
        internal_id: number,
        packstreet_id: editPackstreetId,
      });
      onGroupChanged(updated);
      setEditing(false);
      await load();
    } catch (err) {
      setEditError(
        err instanceof ApiError ? err.message : "Gruppe konnte nicht aktualisiert werden.",
      );
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="overview">
      <button type="button" className="link" onClick={onBack}>
        ← Zurück zu allen Gruppen
      </button>

      {loading && !data && <p className="empty">Ladevorgang…</p>}
      {error && <p className="banner banner--error">{error}</p>}

      {data && (
        <>
          <header className="overview__header">
            <h2>
              <span className="overview__id">{data.internal_id}</span>
              <span className="overview__name">{data.name}</span>
              <span className="overview__subtitle">{data.packstreet.name}</span>
            </h2>
          </header>

          <div className="overview__actions">
            {isAdmin && !editing && (
              <button
                type="button"
                className="btn btn--ghost"
                onClick={startEdit}
              >
                Bearbeiten
              </button>
            )}
            <button
              type="button"
              className="btn btn--ghost"
              onClick={onViewHistory}
            >
              Diagramme anzeigen
            </button>
            <button
              type="button"
              className={`btn ${correctingConsumables ? "btn--primary" : "btn--ghost"}`}
              onClick={() => setCorrectingConsumables((v) => !v)}
            >
              {correctingConsumables
                ? "Korrektur ausblenden"
                : "Korrektur anzeigen"}
            </button>
            <button
              type="button"
              className={`btn ${showConsumables ? "btn--ghost" : "btn--primary"}`}
              onClick={() => {
              const next = !showConsumables;
              setShowConsumables(next);
              void updateCurrentUser(next);
            }}
            >
              {showConsumables
                ? "Verbrauchsartikel ausblenden"
                : "Verbrauchsartikel anzeigen"}
            </button>
          </div>

          {isAdmin && editing && (
            <div className="card overview__edit">
              <h3>Gruppe bearbeiten</h3>
              <div className="create-group__row">
                <input
                  type="text"
                  value={editName}
                  placeholder="Gruppenname"
                  onChange={(e) => setEditName(e.target.value)}
                  disabled={saving}
                  aria-label="Gruppenname"
                />
                <input
                  type="text"
                  value={editNumber}
                  placeholder="Kochgruppen-ID"
                  onChange={(e) => setEditNumber(e.target.value)}
                  disabled={saving}
                  aria-label="Kochgruppen-ID"
                />
                <select
                  value={editPackstreetId}
                  onChange={(e) =>
                    setEditPackstreetId(
                      e.target.value === "" ? "" : Number(e.target.value),
                    )
                  }
                  disabled={saving}
                  aria-label="Packstraße"
                >
                  <option value="">Packstraße…</option>
                  {packstreets.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
                <button
                  type="button"
                  className="btn btn--primary"
                  onClick={() => void saveEdit()}
                  disabled={saving}
                >
                  {saving ? "Speichere…" : "Speichern"}
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => setEditing(false)}
                  disabled={saving}
                >
                  Abbrechen
                </button>
              </div>
              {editError && <p className="banner banner--error">{editError}</p>}
            </div>
          )}

          <table className="groups-table">
            <thead>
              <tr>
                <th>Artikel</th>
                <th className="num">Ausgeliehen</th>
                <th>Ausgeben / Zurücknehmen</th>
              </tr>
            </thead>
            <tbody>
              {data.items
                .filter((it) => showConsumables || it.item_class !== "consumable")
                .map((item) => (
                <OverviewItemRow
                  key={item.item_type}
                  groupId={groupId}
                  item={item}
                  onUpdated={handleUpdated}
                  showCorrect={correctingConsumables}
                />
              ))}
            </tbody>
          </table>

          <section className="action-log">
            <h3>Letzte Aktivitäten</h3>
            {data.recent_actions.length === 0 ? (
              <p className="empty">Noch keine Aktionen aufgezeichnet.</p>
            ) : (
              <ul className="action-log__list">
                {data.recent_actions.map((entry, index) => (
                  <li
                    key={`${entry.timestamp}-${index}`}
                    className={`action-log__item action-log__item--${entry.action}`}
                  >
                    <span className="action-log__desc">
                      <strong>{entry.username ?? "(unbekannter Benutzer)"}</strong>{" "}
                      {describeAction(
                        entry,
                        Object.fromEntries(
                          data.items.map((i) => [i.item_type, i.label]),
                        ),
                      )}
                    </span>
                    <time className="action-log__time" dateTime={entry.timestamp}>
                      {formatTimestamp(entry.timestamp)}
                    </time>
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </section>
  );
}
