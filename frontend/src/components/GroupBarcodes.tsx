import { useCallback, useEffect, useState } from "react";

import { ApiError, fetchGroupBarcodes } from "../api";
import type { GroupBarcodes as GroupBarcodesData } from "../types";
import { formatTimestamp } from "./utils";

interface Props {
  groupId: number;
  onBack: () => void;
}

export function GroupBarcodes({ groupId, onBack }: Props) {
  const [data, setData] = useState<GroupBarcodesData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchGroupBarcodes(groupId));
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Barcodes konnten nicht geladen werden.",
      );
    } finally {
      setLoading(false);
    }
  }, [groupId]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="barcodes-page">
      <button type="button" className="link" onClick={onBack}>
        ← Zurück zur Gruppenübersicht
      </button>

      {loading && <p className="empty">Ladevorgang…</p>}
      {error && <p className="banner banner--error">{error}</p>}

      {data && (
        <>
          {data.barcodes.length === 0 ? (
            <p className="empty">Keine Barcodes bei dieser Gruppe.</p>
          ) : (
            <div className="table-scroll">
              <table className="groups-table">
                <thead>
                  <tr>
                    <th>Barcode</th>
                    <th>Zuletzt gesehen</th>
                  </tr>
                </thead>
                <tbody>
                  {data.barcodes.map((entry) => (
                    <tr key={entry.barcode}>
                      <td className="barcodes-page__barcode">
                        {entry.barcode}
                      </td>
                      <td>{formatTimestamp(entry.last_seen_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </section>
  );
}