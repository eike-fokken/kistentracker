import { useEffect, useState } from "react";

import { ApiError, deleteAction, listRecentActions, updateActionQuantity } from "../api";
import type { GroupSummary, RecentAction } from "../types";
import { describeAction, formatTimestamp } from "./utils";

interface Props {
  groupId: number;
  isAdmin: boolean;
  /** The group's internal_id (e.g. "CG-001"), used in the modal title. */
  internalId: string;
  labels: Record<string, string>;
  onClose: () => void;
  /** Called after an action is changed/deleted so the parent can reload data. */
  onGroupChanged: (group: GroupSummary) => void;
}

export function CorrectionModal({
  groupId,
  isAdmin,
  internalId,
  labels,
  onClose,
  onGroupChanged,
}: Props) {
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
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editingQuantity, setEditingQuantity] = useState("");

  useEffect(() => {
    loadActions();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function loadActions() {
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
      await loadActions();
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
      await loadActions();
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

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal__header">
          <h2>Korrektur von Gruppe {internalId}</h2>
          <button
            type="button"
            className="btn btn--ghost"
            onClick={onClose}
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
                    {entry.barcode && (
                      <span className="action-log__barcode">
                        {entry.barcode}
                      </span>
                    )}
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
                      {!entry.barcode && (
                        <button
                          type="button"
                          className="btn btn--ghost"
                          onClick={() => startEditAction(entry)}
                          disabled={deletingId === entry.id || editingId !== null}
                        >
                          Bearbeiten
                        </button>
                      )}
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
  );
}