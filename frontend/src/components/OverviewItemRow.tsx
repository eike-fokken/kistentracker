import { forwardRef, useImperativeHandle, useRef, useState } from "react";

import { ApiError, changeQuantity } from "../api";
import type { GroupOverviewItem, GroupSummary } from "../types";

export interface OverviewItemRowHandle {
  focusRent: () => void;
  focusReturn: () => void;
}

interface Props {
  groupId: number;
  item: GroupOverviewItem;
  preferRent: boolean;
  onUpdated: (group: GroupSummary) => void;
  readonly?: boolean;
}

export const OverviewItemRow = forwardRef<OverviewItemRowHandle, Props>(
  function OverviewItemRow({ groupId, item, preferRent, onUpdated, readonly = false }, ref) {
    const [amount, setAmount] = useState("0");
    const [busy, setBusy] = useState(false);
    const [error, setError] = useState<string | null>(null);
    const isConsumable = item.item_class === "consumable";

    const inputRef = useRef<HTMLInputElement>(null);

    useImperativeHandle(ref, () => ({
      focusRent() {
        if (preferRent) inputRef.current?.focus();
      },
      focusReturn() {
        if (!preferRent) inputRef.current?.focus();
      },
    }));

    function normalize(value: string): string {
      const parsed = Math.floor(Number(value));
      return Number.isFinite(parsed) && parsed >= 1 ? String(parsed) : "0";
    }

    async function act(raw: string) {
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
          action: preferRent ? "rent" : "return",
        });
        onUpdated(updated);
        setAmount("0");
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "Aktion fehlgeschlagen.");
      } finally {
        setBusy(false);
      }
    }

    const parsed = Math.floor(Number(amount));
    const exceeds =
      !preferRent &&
      Number.isFinite(parsed) &&
      parsed >= 1 &&
      parsed > item.quantity;

    const hasAction = !readonly && (preferRent || !isConsumable);

    return (
      <tr>
        <td>{item.label}</td>
        <td className={`num ${item.quantity < 0 ? "num--negative" : ""}`}>
          {item.quantity}
        </td>
        <td>
          {!readonly && hasAction && (
          <div className={`row-actions__group row-actions__group--${preferRent ? "rent" : "return"}`}>
            <input
              ref={inputRef}
              type="number"
              min={1}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              onFocus={(e) => e.target.select()}
              onBlur={() => setAmount((v) => normalize(v))}
              onKeyDown={(e) => {
                if (e.key === "Enter") void act(amount);
              }}
              disabled={busy}
              aria-label={`Menge ${item.label} zum ${preferRent ? "Ausgeben" : "Zurücknehmen"}`}
            />
            <button
              type="button"
              className={`btn ${preferRent ? "btn--rent" : "btn--return"}`}
              onClick={() => void act(amount)}
              disabled={busy}
            >
              {preferRent ? "Ausgeben" : "Zurücknehmen"}
            </button>
          </div>
          )}
          {(readonly || !hasAction) && <div className="overview-cell-spacer" />}
          {!readonly && exceeds && !error && (
            <p className="banner banner--warning">
              Achtung: die Gruppe hat nur {item.quantity} Stück ausgeliehen. Die
              Rückgabe führt zu einem negativen Bestand.
            </p>
          )}
          {!readonly && error && <p className="banner banner--error">{error}</p>}
        </td>
      </tr>
    );
  },
);