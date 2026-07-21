import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, getGroupOverview, scanCrate } from "../api";
import type {
  GroupOverview as GroupOverviewData,
  RentalActionLog,
} from "../types";

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
  preferRent: boolean;
  onBack: () => void;
}

export function BarcodeView({ groupId, preferRent, onBack }: Props) {
  const [data, setData] = useState<GroupOverviewData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [barcode, setBarcode] = useState("");
  const [busy, setBusy] = useState(false);
  const [scanError, setScanError] = useState<string | null>(null);
  const [scanWarning, setScanWarning] = useState<string | null>(null);
  const [scanSuccess, setScanSuccess] = useState<string | null>(null);
  const [crateQuantity, setCrateQuantity] = useState<number | null>(null);

  const inputRef = useRef<HTMLInputElement>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const overview = await getGroupOverview(groupId);
      setData(overview);
      const kisteItem = overview.items.find((it) => it.item_type === "kiste");
      setCrateQuantity(kisteItem?.quantity ?? 0);
    } catch (err) {
      setError(
        err instanceof ApiError
          ? err.message
          : "Übersicht konnte nicht geladen werden.",
      );
    } finally {
      setLoading(false);
    }
  }, [groupId]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    setBarcode("");
  }, [groupId]);

  useEffect(() => {
    if (!data) return;
    requestAnimationFrame(() => {
      inputRef.current?.focus();
    });
  }, [data]);

  useEffect(() => {
    if (!scanSuccess) return;
    const timer = window.setTimeout(() => setScanSuccess(null), 3000);
    return () => window.clearTimeout(timer);
  }, [scanSuccess]);

  async function handleScan() {
    const value = barcode.trim();
    if (!value || busy) return;

    setBusy(true);
    setScanError(null);
    setScanWarning(null);
    setScanSuccess(null);

    try {
      const result = await scanCrate(groupId, {
        barcode: value,
        action: preferRent ? "rent" : "return",
      });
      setCrateQuantity(result.quantity);
      if (result.warning) {
        setScanWarning(result.warning);
      } else {
        setScanSuccess(
          `Kiste ${result.barcode} ${preferRent ? "ausgegeben" : "zurückgenommen"}. Bestand: ${result.quantity}`,
        );
      }
      setBarcode("");
      void load();
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

          <div
            className={`barcode-mode-banner barcode-mode-banner--${preferRent ? "rent" : "return"}`}
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

          {crateQuantity !== null && (
            <div className="barcode-crate-count">
              Kisten derzeit: <strong>{crateQuantity}</strong>
            </div>
          )}

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

          {scanSuccess && (
            <p className="banner banner--success">{scanSuccess}</p>
          )}
          {scanWarning && (
            <p className="banner banner--warning">{scanWarning}</p>
          )}
          {scanError && (
            <p className="banner banner--error">{scanError}</p>
          )}

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
    </section>
  );
}