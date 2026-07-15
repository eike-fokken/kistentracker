import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  deleteAction,
  deleteGroup,
  getCurrentUser,
  getGroupOverview,
  listRecentActions,
  updateActionQuantity,
  updateCurrentUser,
  updateGroup,
} from "../api";
import type {
  Packstreet,
  GroupOverview as GroupOverviewData,
  GroupSummary,
  RecentAction,
  RentalActionLog,
} from "../types";
import { OverviewItemRow } from "./OverviewItemRow";
import type { OverviewItemRowHandle } from "./OverviewItemRow";

function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

function describeAction(
  entry: RentalActionLog | RecentAction,
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
  showConsumables: showConsumablesProp,
  preferRent: preferRentProp,
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
  const [showConsumables, setShowConsumables] = useState(showConsumablesProp);
  const [preferRent, setPreferRent] = useState(preferRentProp);

  const [correctionActions, setCorrectionActions] = useState<RecentAction[] | null>(null);
  const [correctionLoading, setCorrectionLoading] = useState(false);
  const [correctionError, setCorrectionError] = useState<string | null>(null);
  const [correctionDay, setCorrectionDay] = useState(() => {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return today;
  });
  const [allActions, setAllActions] = useState<RecentAction[] | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);
  const [deleteError, setDeleteError] = useState<string | null>(null);
  const [groupDeleteError, setGroupDeleteError] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingQuantity, setEditingQuantity] = useState("");

  useEffect(() => {
    setShowConsumables(showConsumablesProp);
  }, [showConsumablesProp]);

  useEffect(() => {
    setPreferRent(preferRentProp);
  }, [preferRentProp]);

  useEffect(() => {
    getCurrentUser()
      .then((user) => {
        setShowConsumables(user.show_consumables);
        setPreferRent(user.prefer_rent);
      })
      .catch(() => {
        /* ignore — keep the prop values */
      });
  }, []);

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
    setAllActions(null);
    setCorrectionActions(null);
    setCorrectionError(null);
    setDeleteError(null);
    setCorrectionLoading(true);
    try {
      if (isAdmin) {
        const actions = await listRecentActions(groupId);
        setAllActions(actions);
        setCorrectionActions(filterActionsForDay(actions, correctionDay));
      } else {
        setCorrectionActions(await listRecentActions(groupId));
      }
    } catch (err) {
      setCorrectionError(
        err instanceof ApiError ? err.message : "Aktionen konnten nicht geladen werden.",
      );
    } finally {
      setCorrectionLoading(false);
    }
  }

  function filterActionsForDay(actions: RecentAction[], day: Date): RecentAction[] {
    const dayStart = new Date(day);
    const dayEnd = new Date(day);
    dayEnd.setDate(dayEnd.getDate() + 1);
    return actions.filter((a) => {
      const ts = new Date(a.timestamp);
      return ts >= dayStart && ts < dayEnd;
    });
  }

  function changeCorrectionDay(delta: number) {
    const next = new Date(correctionDay);
    next.setDate(next.getDate() + delta);
    setCorrectionDay(next);
    setCorrectionActions(
      allActions ? filterActionsForDay(allActions, next) : null,
    );
  }

  async function handleDelete(actionId: number) {
    setDeletingId(actionId);
    setDeleteError(null);
    try {
      const updated = await deleteAction(groupId, actionId);
      onGroupChanged(updated);
      await load();
      setAllActions(null);
      setCorrectionLoading(true);
      setCorrectionError(null);
      try {
        const actions = await listRecentActions(groupId);
        setAllActions(actions);
        setCorrectionActions(filterActionsForDay(actions, correctionDay));
      } catch (err) {
        setCorrectionError(
          err instanceof ApiError ? err.message : "Aktionen konnten nicht geladen werden.",
        );
      } finally {
        setCorrectionLoading(false);
      }
    } catch (err) {
      setDeleteError(
        err instanceof ApiError ? err.message : "Aktion konnte nicht gelöscht werden.",
      );
    } finally {
      setDeletingId(null);
    }
  }

  function startEditAction(entry: RecentAction) {
    setEditingId(entry.id);
    setEditingQuantity(String(entry.quantity));
    setDeleteError(null);
  }

  function cancelEditAction() {
    setEditingId(null);
    setEditingQuantity("");
  }

  async function saveEditAction(actionId: number) {
    const quantity = Math.floor(Number(editingQuantity));
    if (!Number.isFinite(quantity) || quantity === 0) {
      setDeleteError("Menge muss eine ganze Zahl ungleich 0 sein.");
      return;
    }

    setDeletingId(actionId);
    setDeleteError(null);
    try {
      const updated = await updateActionQuantity(groupId, actionId, quantity);
      onGroupChanged(updated);
      await load();
      setAllActions(null);
      setCorrectionLoading(true);
      setCorrectionError(null);
      try {
        const actions = await listRecentActions(groupId);
        setAllActions(actions);
        setCorrectionActions(filterActionsForDay(actions, correctionDay));
      } catch (err) {
        setCorrectionError(
          err instanceof ApiError ? err.message : "Aktionen konnten nicht geladen werden.",
        );
      } finally {
        setCorrectionLoading(false);
      }
      setEditingId(null);
      setEditingQuantity("");
    } catch (err) {
      setDeleteError(
        err instanceof ApiError ? err.message : "Aktion konnte nicht bearbeitet werden.",
      );
    } finally {
      setDeletingId(null);
    }
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
            {isAdmin && !editing && (
              <button
                type="button"
                className="btn btn--ghost"
                onClick={startEdit}
              >
                Bearbeiten
              </button>
            )}
            {isAdmin && (
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
            <button
              type="button"
              className="btn btn--ghost"
              onClick={onViewHistory}
            >
              Diagramme anzeigen
            </button>
            <button
              type="button"
              className={`btn ${showCorrection ? "btn--primary" : "btn--ghost"}`}
              onClick={() => showCorrection ? setShowCorrection(false) : openCorrection()}
            >
              {showCorrection ? "Korrektur schließen" : "Korrektur"}
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
            <button
              type="button"
              className={`btn ${preferRent ? "btn--primary" : "btn--ghost"}`}
              onClick={() => {
                const next = !preferRent;
                setPreferRent(next);
                void updateCurrentUser(undefined, next);
              }}
            >
              {preferRent
                ? "Ausgeben bevorzugt"
                : "Zurücknehmen bevorzugt"}
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

          <table className="groups-table overview-table">
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
                .map((item, index) => (
                  <OverviewItemRow
                    key={item.item_type}
                    ref={index === 0 ? firstRowRef : undefined}
                    groupId={groupId}
                    item={item}
                    onUpdated={handleUpdated}
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

      {showCorrection && (
        <div className="modal-overlay" onClick={() => setShowCorrection(false)}>
          <div className="modal" onClick={(e) => e.stopPropagation()}>
            <div className="modal__header">
              <h2>Korrektur von Gruppe {data?.internal_id ?? "…"}</h2>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => setShowCorrection(false)}
              >
                Schließen
              </button>
            </div>

            {isAdmin && (
              <div className="modal__timeframe">
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => changeCorrectionDay(-1)}
                >
                  ◀
                </button>
                <span className="modal__day-label">
                  {correctionDay.toLocaleDateString(undefined, {
                    weekday: "short",
                    day: "numeric",
                    month: "short",
                    year: "numeric",
                  })}
                </span>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => changeCorrectionDay(1)}
                  disabled={
                    new Date().toDateString() === correctionDay.toDateString()
                  }
                >
                  ▶
                </button>
                <button
                  type="button"
                  className="btn btn--ghost"
                  onClick={() => {
                    const today = new Date();
                    today.setHours(0, 0, 0, 0);
                    setCorrectionDay(today);
                    setCorrectionActions(
                      allActions ? filterActionsForDay(allActions, today) : null,
                    );
                  }}
                >
                  Heute
                </button>
              </div>
            )}

            {correctionLoading && <p className="empty">Ladevorgang…</p>}
            {correctionError && <p className="banner banner--error">{correctionError}</p>}
            {deleteError && <p className="banner banner--error">{deleteError}</p>}

            {correctionActions && correctionActions.length === 0 && (
              <p className="empty">{isAdmin ? "Keine Aktionen an diesem Tag." : "Keine eigenen Aktionen in den letzten 10 Minuten."}</p>
            )}

            {correctionActions && correctionActions.length > 0 && (
              <ul className="action-log__list correction__list">
                {correctionActions.map((entry) => (
                  <li
                    key={entry.id}
                    className={`action-log__item action-log__item--${entry.action}`}
                  >
                    {editingId === entry.id ? (
                      <span className="action-log__desc">
                        <strong>{entry.username ?? "(unbekannter Benutzer)"}</strong>{" "}
                        <span
                          className={
                            entry.action === "rent"
                              ? "action-log__verb--rent"
                              : "action-log__verb--return"
                          }
                        >
                          {entry.action === "rent" ? "ausgegeben" : "zurückgenommen"}
                        </span>{" "}
                        <input
                          type="number"
                          className="correction__edit-input"
                          value={editingQuantity}
                          onChange={(e) => setEditingQuantity(e.target.value)}
                          onFocus={(e) => e.target.select()}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") void saveEditAction(entry.id);
                            if (e.key === "Escape") cancelEditAction();
                          }}
                          disabled={deletingId === entry.id}
                          aria-label="Neue Menge"
                        />{" "}
                        × {labels[entry.item_type] ?? entry.item_type}
                      </span>
                    ) : (
                      <span className="action-log__desc">
                        <strong>{entry.username ?? "(unbekannter Benutzer)"}</strong>{" "}
                        {describeAction(entry, labels)}
                      </span>
                    )}
                    <div className="correction__row-right">
                      <time className="action-log__time" dateTime={entry.timestamp}>
                        {formatTimestamp(entry.timestamp)}
                      </time>
                      {editingId === entry.id ? (
                        <>
                          <button
                            type="button"
                            className="btn btn--primary"
                            onClick={() => void saveEditAction(entry.id)}
                            disabled={deletingId === entry.id}
                          >
                            {deletingId === entry.id ? "Speichere…" : "Speichern"}
                          </button>
                          <button
                            type="button"
                            className="btn btn--ghost"
                            onClick={cancelEditAction}
                            disabled={deletingId === entry.id}
                          >
                            Abbrechen
                          </button>
                        </>
                      ) : (
                        <>
                          <button
                            type="button"
                            className="btn btn--ghost"
                            onClick={() => startEditAction(entry)}
                            disabled={deletingId === entry.id || editingId !== null}
                          >
                            Bearbeiten
                          </button>
                          <button
                            type="button"
                            className="btn btn--danger"
                            onClick={() => void handleDelete(entry.id)}
                            disabled={deletingId === entry.id || editingId !== null}
                          >
                            {deletingId === entry.id ? "Löschen…" : "Löschen"}
                          </button>
                        </>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </div>
        </div>
      )}
    </section>
  );
}
