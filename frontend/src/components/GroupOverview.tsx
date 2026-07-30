import { useCallback, useEffect, useRef, useState } from "react";

import {
  ApiError,
  deleteGroup,
  scanCrate,
  updateGroup,
} from "../api";
import { playErrorBeep } from "../sounds";
import type {
  Packstreet,
  GroupOverview as GroupOverviewData,
  GroupSummary,
} from "../types";
import { CorrectionModal } from "./CorrectionModal";
import { OverviewHeader } from "./OverviewHeader";
import { OverviewItemRow } from "./OverviewItemRow";
import { describeAction, formatTimestamp } from "./utils";

interface Props {
  groupId: number;
  isAdmin: boolean;
  username: string | null;
  packstreets: Packstreet[];
  showConsumables: boolean;
  preferRent: boolean;
  barcodeView: boolean;
  data: GroupOverviewData | null;
  loading: boolean;
  error: string | null;
  onReload: () => void;
  onBack: () => void;
  onViewHistory: () => void;
  onViewBarcodes: () => void;
  onGroupChanged: (group: GroupSummary) => void;
  onDeleted: (deletedId: number) => void;
  onTogglePreferRent: () => void;
}

export function GroupOverview({
  groupId,
  isAdmin,
  username,
  packstreets,
  showConsumables,
  preferRent,
  barcodeView,
  data,
  loading,
  error,
  onReload,
  onBack,
  onViewHistory,
  onViewBarcodes,
  onGroupChanged,
  onDeleted,
  onTogglePreferRent,
}: Props) {
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState("");
  const [editNumber, setEditNumber] = useState("");
  const [editPackstreetId, setEditPackstreetId] = useState<number | "">("");
  const [saving, setSaving] = useState(false);
  const [editError, setEditError] = useState<string | null>(null);
  const [showCorrection, setShowCorrection] = useState(false);

  const [groupDeleteError, setGroupDeleteError] = useState<string | null>(null);

  const tableBodyRef = useRef<HTMLTableSectionElement>(null);

  useEffect(() => {
    if (!data || data.packstreet.is_stock || barcodeView) return;
    const timer = window.setTimeout(() => {
      tableBodyRef.current
        ?.querySelector<HTMLInputElement>("input[type='number']")
        ?.focus();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [data, preferRent, barcodeView, showConsumables]);

  const handleUpdated = useCallback(
    (group: GroupSummary) => {
      onGroupChanged(group);
      onReload();
    },
    [onGroupChanged, onReload],
  );

  async function handleDeleteGroup() {
    if (!data) return;
    const confirmed = window.confirm(
      `Grupppe „${data.name}“ löschen? Eine Gruppe, die noch ausleihbare Artikel ausgeliehen hat, kann nicht gelöscht werden.`,
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
      onReload();
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

  // ---- Barcode scan state ----

  const [barcode, setBarcode] = useState("");
  const [busy, setBusy] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanWarning, setScanWarning] = useState<string | null>(null);
  const [scanSuccess, setScanSuccess] = useState<string | null>(null);
  const barcodeInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setBarcode("");
  }, [groupId]);

  useEffect(() => {
    if (!data || !barcodeView) return;
    requestAnimationFrame(() => {
      barcodeInputRef.current?.focus();
    });
  }, [data, preferRent, barcodeView, scanError]);

  useEffect(() => {
    if (scanError) {
      document.body.classList.add("body--error");
      return () => document.body.classList.remove("body--error");
    }
    if (scanWarning) {
      document.body.classList.add("body--warning");
      return () => document.body.classList.remove("body--warning");
    }
  }, [scanError, scanWarning]);

  useEffect(() => {
    if (!scanSuccess) return;
    const timer = window.setTimeout(() => setScanSuccess(null), 3000);
    return () => window.clearTimeout(timer);
  }, [scanSuccess]);

  async function handleScan() {
    const value = barcode.trim().replace(/[()]/g, "");
    if (!value || busy) return;

    setBusy(true);
    setScanError(null);
    setScanWarning(null);
    setScanSuccess(null);
    setBarcode("");

    try {
      const result = await scanCrate(groupId, {
        barcode: value,
        action: preferRent ? "rent" : "return",
      });
      if (result.warning) {
        setScanWarning(
          `${result.warning} Bestand: ${result.quantity}`,
        );
      } else {
        setScanSuccess(
          `Kiste ${result.barcode} ${preferRent ? "ausgegeben" : "zurückgenommen"}. Bestand: ${result.quantity}`,
        );
      }
      void onReload();
    } catch (err) {
      setScanError(
        err instanceof ApiError ? err.message : "Scan fehlgeschlagen.",
      );
      playErrorBeep();
    } finally {
      setBusy(false);
      requestAnimationFrame(() => {
        barcodeInputRef.current?.focus();
      });
    }
  }

  // ---- / Barcode scan state ----

  const labels = data
    ? Object.fromEntries(data.items.map((i) => [i.item_type, i.label]))
    : {};

  const isStock = data?.packstreet?.is_stock ?? false;

  return (
    <section className="overview">
      <OverviewHeader
        onBack={onBack}
        onViewHistory={onViewHistory}
        onViewBarcodes={onViewBarcodes}
        isStock={isStock}
        preferRent={preferRent}
        barcodeView={barcodeView}
        showCorrection={showCorrection}
        onToggleCorrection={() => showCorrection ? setShowCorrection(false) : openCorrection()}
        onTogglePreferRent={onTogglePreferRent}
      />

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
            {isAdmin && !editing && !isStock && (
              <button
                type="button"
                className="btn btn--ghost"
                onClick={startEdit}
              >
                Bearbeiten
              </button>
            )}
            {isAdmin && !isStock && (
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

          {!isStock && (
            barcodeView ? (
              <div className="barcode-input-area">
                <input
                  ref={barcodeInputRef}
                  type="text"
                  className="barcode-input"
                  value={barcode}
                  onChange={(e) => setBarcode(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") void handleScan();
                  }}
                  placeholder="Barcode einscannen…"
                  disabled={busy}
                  autoFocus
                />
              </div>
            ) : (
              <div className="barcode-input-area">
                <input className="barcode-input barcode-input--spacer" disabled readOnly />
              </div>
            )
          )}

          {scanSuccess && (
            <p className="banner banner--success">{scanSuccess}</p>
          )}
          {scanWarning && (
            <div className="banner banner--warning">
              <span>{scanWarning}</span>
              <button
                type="button"
                className="btn btn--ghost banner__dismiss"
                onClick={() => { setScanWarning(null); setScanError(null); }}
              >
                Ausblenden
              </button>
            </div>
          )}
          {scanError && (
            <div className="banner banner--error">
              <span>{scanError}</span>
              <button
                type="button"
                className="btn btn--ghost banner__dismiss"
                onClick={() => { setScanWarning(null); setScanError(null); }}
              >
                Ausblenden
              </button>
            </div>
          )}

          <div className="table-scroll">
          <table className="groups-table overview-table">
            <thead>
              <tr>
                <th>Artikel</th>
                <th className="num">Ausgeliehen</th>
                <th>{!isStock && !barcodeView ? (preferRent ? "Ausgeben" : "Zurücknehmen") : ""}</th>
              </tr>
            </thead>
            <tbody ref={tableBodyRef}>
              {data.items
                .filter((it) => showConsumables || it.item_class !== "consumable")
                .map((item) => (
                  <OverviewItemRow
                    key={item.item_type}
                    groupId={groupId}
                    item={item}
                    preferRent={preferRent}
                    onUpdated={handleUpdated}
                    readonly={isStock || barcodeView}
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
                      {entry.barcode && (
                        <span className="action-log__barcode">
                          {entry.barcode}
                        </span>
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

      {showCorrection && data && (
        <CorrectionModal
          groupId={groupId}
          isAdmin={isAdmin}
          username={username}
          internalId={data.internal_id}
          labels={labels}
          onClose={() => setShowCorrection(false)}
          onGroupChanged={handleUpdated}
        />
      )}
    </section>
  );
}