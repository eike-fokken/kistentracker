import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  deleteGroup,
  getGroupOverview,
  updateGroup,
} from "../api";
import type {
  Packstreet,
  GroupOverview as GroupOverviewData,
  GroupSummary,
} from "../types";
import { OverviewItemRow } from "./OverviewItemRow";
import type { OverviewItemRowHandle } from "./OverviewItemRow";
import { CorrectionModal } from "./CorrectionModal";
import { describeAction, formatTimestamp } from "./utils";

interface Props {
  groupId: number;
  isAdmin: boolean;
  packstreets: Packstreet[];
  showConsumables: boolean;
  preferRent: boolean;
  onBack: () => void;
  onViewHistory: () => void;
  onGroupChanged: (group: GroupSummary) => void;
  onDeleted: (deletedId: number) => void;
}

export function GroupOverview({
  groupId,
  isAdmin,
  packstreets,
  showConsumables,
  preferRent,
  onBack,
  onViewHistory,
  onGroupChanged,
  onDeleted,
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
  const [showCorrection, setShowCorrection] = useState(false);

  const [groupDeleteError, setGroupDeleteError] = useState<string | null>(null);

  const firstRowRef = useRef<OverviewItemRowHandle | null>(null);
  const focusedRef = useRef(false);

  useEffect(() => {
    if (data && !focusedRef.current) {
      focusedRef.current = true;
      if (preferRent) {
        firstRowRef.current?.focusRent();
      } else {
        firstRowRef.current?.focusReturn();
      }
    }
  }, [data, preferRent]);

  useEffect(() => {
    if (!data) {
      focusedRef.current = false;
    }
  }, [data]);

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

  const handleUpdated = useCallback(
    (group: GroupSummary) => {
      onGroupChanged(group);
      void load();
    },
    [onGroupChanged, load],
  );

  async function handleDeleteGroup() {
    if (!data) return;
    const confirmed = window.confirm(
      `Gruppe „${data.name}“ löschen? Eine Gruppe, die noch ausleihbare Artikel ausgeliehen hat, kann nicht gelöscht werden.`,
    );
    if (!confirmed) return;
    try {
      await deleteGroup(groupId);
      onDeleted(groupId);
    } catch (err) {
      setGroupDeleteError(
        err instanceof ApiError ? err.message : "Fehler beim Löschen der Gruppe.",
      );
    }
  }

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

  async function openCorrection() {
    setShowCorrection(true);
  }

  const labels = data
    ? Object.fromEntries(data.items.map((i) => [i.item_type, i.label]))
    : {};

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
            <span className="overview__id">{data.internal_id}</span>
            <span className="overview__name">{data.name}</span>
            <span className="overview__subtitle">{data.packstreet.name}</span>
          </header>

          <div className="overview__actions">
            {isAdmin && !editing && !data.packstreet.is_stock && (
              <button
                type="button"
                className="btn btn--ghost"
                onClick={startEdit}
              >
                Bearbeiten
              </button>
            )}
            {isAdmin && !data.packstreet.is_stock && (
              <button
                type="button"
                className="btn btn--danger"
                onClick={handleDeleteGroup}
              >
                Gruppe löschen
              </button>
            )}
            {groupDeleteError && (
              <p className="banner banner--error">{groupDeleteError}</p>
            )}
            {!data.packstreet.is_stock && (
            <button
              type="button"
              className="btn btn--ghost"
              onClick={onViewHistory}
            >
              Diagramme anzeigen
            </button>
            )}
            {!data.packstreet.is_stock && (
            <button
              type="button"
              className={`btn ${showCorrection ? "btn--primary" : "btn--ghost"}`}
              onClick={() => showCorrection ? setShowCorrection(false) : openCorrection()}
            >
              {showCorrection ? "Korrektur schließen" : "Korrektur"}
            </button>
            )}
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
                  {packstreets.filter((p) => !p.is_stock).map((p) => (
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

          <div className="table-scroll">
          <table className="groups-table overview-table">
            <thead>
              <tr>
                <th>Artikel</th>
                <th className="num">Ausgeliehen</th>
                {!data.packstreet.is_stock && <th>Ausgeben / Zurücknehmen</th>}
              </tr>
            </thead>
            <tbody>
              {data.items
                .filter((it) => showConsumables || it.item_class !== "consumable")
                .map((item, index) => (
                  <OverviewItemRow
                    key={item.item_type}
                    ref={index === 0 ? firstRowRef : undefined}
                    groupId={groupId}
                    item={item}
                    onUpdated={handleUpdated}
                    readonly={data.packstreet.is_stock}
                  />
                ))}
            </tbody>
          </table>
          </div>

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
                      {describeAction(entry, labels)}
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

      {showCorrection && data && (
        <CorrectionModal
          groupId={groupId}
          isAdmin={isAdmin}
          internalId={data.internal_id}
          labels={labels}
          onClose={() => setShowCorrection(false)}
          onGroupChanged={handleUpdated}
        />
      )}
    </section>
  );
}
