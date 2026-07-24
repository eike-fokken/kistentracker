import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, scanCrate } from "../api";
import type {
  GroupOverview as GroupOverviewData,
} from "../types";
import { CorrectionModal } from "./CorrectionModal";
import { describeAction, formatTimestamp } from "./utils";

interface Props {
  groupId: number;
  username: string | null;
  preferRent: boolean;
  data: GroupOverviewData | null;
  loading: boolean;
  error: string | null;
  onReload: () => void;
  onBack: () => void;
  onViewHistory: () => void;
  onToggleMode: () => void;
}

export function BarcodeView({ groupId, username, preferRent, data, loading, error, onReload, onBack, onViewHistory, onToggleMode }: Props) {
  const [barcode, setBarcode] = useState("");
  const [busy, setBusy] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanWarning, setScanWarning] = useState<string | null>(null);
  const [scanSuccess, setScanSuccess] = useState<string | null>(null);

  const [showCorrection, setShowCorrection] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setBarcode("");
  }, [groupId]);

  useEffect(() => {
    if (!data) return;
    requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
  }, [data, preferRent]);

  useEffect(() => {
    if (!scanSuccess) return;
    const timer = window.setTimeout(() => setScanSuccess(null), 3000);
    return () => window.clearTimeout(timer);
  }, [scanSuccess]);

  const handleUpdated = useCallback(() => {
      onReload();
    },
    [onReload],
  );

  async function handleScan() {
    const value = barcode.trim();
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
        setScanWarning(result.warning);
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
    } finally {
      setBusy(false);
      requestAnimationFrame(() => {
        inputRef.current?.focus();
      });
    }
  }

  const labels = data
    ? Object.fromEntries(data.items.map((i) => [i.item_type, i.label]))
    : {};

  return (
    <section className="barcode-view">
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

          {!data.packstreet.is_stock && (
            <div className="overview__actions">
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
                onClick={() =>
                  showCorrection ? setShowCorrection(false) : setShowCorrection(true)
                }
              >
                {showCorrection ? "Korrektur schließen" : "Korrektur"}
              </button>
            </div>
          )}

          {!data.packstreet.is_stock && (
          <div
            className={`barcode-mode-banner barcode-mode-banner--${preferRent ? "rent" : "return"}`}
            onClick={onToggleMode}
            role="button"
            tabIndex={0}
            onKeyDown={(e) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); onToggleMode(); } }}
          >
            <div className="barcode-mode-banner__label">
              {preferRent ? "AUSLEIHE-MODUS" : "RÜCKGABE-MODUS"}
            </div>
            <div className="barcode-mode-banner__desc">
              {preferRent
                ? "Gescannte Kisten werden ausgegeben"
                : "Gescannte Kisten werden zurückgenommen"}
            </div>
          </div>
          )}

          {!data.packstreet.is_stock && (
          <div className="barcode-input-area">
            <input
              ref={inputRef}
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
          )}

          {scanSuccess && (
            <p className="banner banner--success">{scanSuccess}</p>
          )}
          {scanWarning && (
            <p className="banner banner--warning">{scanWarning}</p>
          )}
          {scanError && (
            <p className="banner banner--error">{scanError}</p>
          )}

          <div className="table-scroll">
          <table className="groups-table overview-table">
            <thead>
              <tr>
                <th>Artikel</th>
                <th className="num">Ausgeliehen</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {data.items
                .map((item) => (
                  <tr key={item.item_type}>
                    <td>{item.label}</td>
                    <td className={`num ${item.quantity < 0 ? "num--negative" : ""}`}>
                      {item.quantity}
                    </td>
                    <td><div className="overview-cell-spacer" /></td>
                  </tr>
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
                      <strong>
                        {entry.username ?? "(unbekannter Benutzer)"}
                      </strong>{" "}
                      {describeAction(entry, labels)}
                      {entry.barcode && (
                        <span className="action-log__barcode">
                          {entry.barcode}
                        </span>
                      )}
                    </span>
                    <time
                      className="action-log__time"
                      dateTime={entry.timestamp}
                    >
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
          isAdmin={false}
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