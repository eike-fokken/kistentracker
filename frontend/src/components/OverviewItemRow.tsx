import { useState } from "react";

import { ApiError, changeQuantity } from "../api";
import type { GroupOverviewItem, GroupSummary } from "../types";

interface Props {
  groupId: number;
  item: GroupOverviewItem;
  onUpdated: (group: GroupSummary) => void;
  showCorrect: boolean;
}

export function OverviewItemRow({ groupId, item, onUpdated, showCorrect }: Props) {
  const [rentAmount, setRentAmount] = useState("0");
  const [returnAmount, setReturnAmount] = useState("0");
  const [correctAmount, setCorrectAmount] = useState("0");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isConsumable = item.item_class === "consumable";

  function normalize(value: string): string {
    const parsed = Math.floor(Number(value));
    return Number.isFinite(parsed) && parsed >= 1 ? String(parsed) : "0";
  }

  async function rent(raw: string) {
    const quantity = Math.floor(Number(raw));
    if (!Number.isFinite(quantity) || quantity < 1) {
      setError("Menge muss eine positive Zahl sein.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const updated = await changeQuantity(groupId, {
        item_type: item.item_type,
        quantity,
        action: "rent",
      });
      onUpdated(updated);
      setRentAmount("0");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Aktion fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  async function returnItem(raw: string) {
    const quantity = Math.floor(Number(raw));
    if (!Number.isFinite(quantity) || quantity < 1) {
      setError("Menge muss eine positive Zahl sein.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const updated = await changeQuantity(groupId, {
        item_type: item.item_type,
        quantity,
        action: "return",
      });
      onUpdated(updated);
      setReturnAmount("0");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Aktion fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  async function correct(raw: string) {
    const quantity = Math.floor(Number(raw));
    if (!Number.isFinite(quantity) || quantity === 0) {
      setError("Menge muss eine positive oder negative Zahl sein.");
      return;
    }

    setBusy(true);
    setError(null);
    try {
      const updated = await changeQuantity(groupId, {
        item_type: item.item_type,
        quantity,
        action: "correct",
      });
      onUpdated(updated);
      setCorrectAmount("0");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Aktion fehlgeschlagen.");
    } finally {
      setBusy(false);
    }
  }

  if (showCorrect) {
    return (
      <tr>
        <td>{item.label}</td>
        <td className="num">{item.quantity}</td>
        <td>
          <div className="row-actions">
<div className="row-actions__group row-actions__group--correct">
              <input
                type="number"
                value={correctAmount}
                onChange={(e) => setCorrectAmount(e.target.value)}
                onFocus={(e) => e.target.select()}
                onKeyDown={(e) => {
                  if (e.key === "Enter") void correct(correctAmount);
                }}
                disabled={busy}
                aria-label={`Menge ${item.label} zum Korrigieren`}
              />
              <button
                type="button"
                className="btn btn--primary"
                onClick={() => void correct(correctAmount)}
                disabled={busy}
              >
Korrigieren
              </button>
            </div>
          </div>
          {error && <p className="banner banner--error">{error}</p>}
        </td>
      </tr>
    );
  }

  return (
    <tr>
      <td>{item.label}</td>
      <td className="num">{item.quantity}</td>
      <td>
        <div className="row-actions">
          <div className="row-actions__group row-actions__group--rent">
            <input
              type="number"
              min={1}
              value={rentAmount}
              onChange={(e) => setRentAmount(e.target.value)}
              onFocus={(e) => e.target.select()}
              onBlur={() => setRentAmount((v) => normalize(v))}
              onKeyDown={(e) => {
                if (e.key === "Enter") void rent(rentAmount);
              }}
              disabled={busy}
              aria-label={`Menge ${item.label} zum Ausgeben`}
            />
            <button
              type="button"
              className="btn btn--primary"
              onClick={() => void rent(rentAmount)}
              disabled={busy}
            >
Ausgeben
            </button>
          </div>
          {!isConsumable && (
          <div className="row-actions__group row-actions__group--return">
            <input
              type="number"
              min={1}
              value={returnAmount}
              onChange={(e) => setReturnAmount(e.target.value)}
              onFocus={(e) => e.target.select()}
              onBlur={() => setReturnAmount((v) => normalize(v))}
              onKeyDown={(e) => {
                if (e.key === "Enter") void returnItem(returnAmount);
              }}
              disabled={busy}
              aria-label={`Menge ${item.label} zum Zurücknehmen`}
            />
            <button
              type="button"
              className="btn btn--secondary"
              onClick={() => void returnItem(returnAmount)}
              disabled={busy}
            >
Zurücknehmen
            </button>
          </div>
        )}
        </div>
        {error && <p className="banner banner--error">{error}</p>}
      </td>
    </tr>
  );
}
