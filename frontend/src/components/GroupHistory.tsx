import { useCallback, useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import { ApiError, getGroupHistory } from "../api";
import type { GroupHistory as GroupHistoryData, ItemHistory } from "../types";

interface Props {
  groupId: number;
  onBack: () => void;
}

function formatTick(time: number): string {
  return new Date(time).toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
  });
}

function formatFull(time: number): string {
  return new Date(time).toLocaleString();
}

interface ItemChartProps {
  series: ItemHistory;
  startDate?: string;
  endDate?: string;
}

function ItemChart({ series, startDate, endDate }: ItemChartProps) {
  const data = series.points.map((point) => ({
    time: new Date(point.timestamp).getTime(),
    quantity: point.quantity,
  }));

  const xDomain: [number, number] | ["dataMin", "dataMax"] =
    startDate && endDate
      ? [new Date(startDate).getTime(), new Date(endDate).getTime()]
      : ["dataMin", "dataMax"];

  return (
    <section className="history__chart">
      <h3>{series.label}</h3>
      {data.length === 0 ? (
        <p className="empty">Noch keine Ausgaben oder Rückgaben aufgezeichnet.</p>
      ) : (
        <ResponsiveContainer width="100%" height={260}>
          <LineChart
            data={data}
            margin={{ top: 8, right: 16, bottom: 8, left: 0 }}
          >
            <CartesianGrid strokeDasharray="3 3" stroke="#e2e4e9" />
            <XAxis
              dataKey="time"
              type="number"
              domain={xDomain}
              tickFormatter={formatTick}
              minTickGap={24}
              fontSize={14}
            />
            <YAxis allowDecimals={false} width={36} fontSize={14} />
            <Tooltip
              labelFormatter={(label) => formatFull(Number(label))}
              formatter={(value) => [value as number, "Ausgeliehen"]}
            />
            <Line
              type="stepAfter"
              dataKey="quantity"
              stroke="#2563eb"
              strokeWidth={2}
              dot={{ r: 3 }}
              isAnimationActive={false}
            />
          </LineChart>
        </ResponsiveContainer>
      )}
    </section>
  );
}

export function GroupHistory({ groupId, onBack }: Props) {
  const [data, setData] = useState<GroupHistoryData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getGroupHistory(groupId, startDate || undefined, endDate || undefined));
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Verlauf konnte nicht geladen werden.",
      );
    } finally {
      setLoading(false);
    }
  }, [groupId, startDate, endDate]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <section className="history">
      <button
        type="button"
        className="link"
        onClick={onBack}
      >
        ← Zurück zur Gruppenübersicht
      </button>

      <div className="history__dates">
        <label className="history__date-label">
          Von:
          <input
            type="date"
            className="input"
            value={startDate}
            onChange={(e) => setStartDate(e.target.value)}
          />
        </label>
        <label className="history__date-label">
          Bis:
          <input
            type="date"
            className="input"
            value={endDate}
            onChange={(e) => setEndDate(e.target.value)}
          />
        </label>
      </div>

      {loading && !data && <p className="empty">Ladevorgang…</p>}
      {error && <p className="banner banner--error">{error}</p>}

      {data && (
        <>
          <header className="overview__header">
            <h2>
              {data.name} <span className="overview__number">#{data.internal_id}</span>
            </h2>
            <p className="overview__subtitle">Ausgeben und Rückgaben im Zeitverlauf</p>
          </header>

          {data.series.map((series) => (
            <ItemChart
              key={series.item_type}
              series={series}
              startDate={startDate || undefined}
              endDate={endDate || undefined}
            />
          ))}
        </>
      )}
    </section>
  );
}