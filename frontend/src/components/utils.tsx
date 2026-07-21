import type { RentalActionLog } from "../types";

export function formatTimestamp(iso: string): string {
  return new Date(iso).toLocaleString();
}

export function describeAction(
  entry: RentalActionLog | { action: string; item_type: string; quantity: number },
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