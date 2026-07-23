import { useEffect, useState } from "react";
import { ApiError, listGroups } from "../api";
import type { GroupSummary, ItemTypeDef } from "../types";
import { GroupsTable } from "./GroupsTable";

interface Props {
  q: string;
  itemTypes: ItemTypeDef[];
  isAdmin: boolean;
  onOpenGroup: (group: GroupSummary) => void;
  onDeleteGroup: (group: GroupSummary) => void;
}

export function SearchResults({
  q,
  itemTypes,
  isAdmin,
  onOpenGroup,
  onDeleteGroup,
}: Props) {
  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);
    listGroups({ q })
      .then((results) => {
        if (!cancelled) {
          if (results.length === 1) {
            onOpenGroup(results[0]);
            return;
          }
          setGroups(results);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(
            err instanceof ApiError
              ? err.message
              : "Suche fehlgeschlagen.",
          );
          setLoading(false);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [q, onOpenGroup]);

  if (loading) return <p className="empty">Suche…</p>;
  if (error) return <p className="banner banner--error">{error}</p>;
  if (groups.length === 0) return (
    <section className="groups">
      <button
        type="button"
        className="link"
        onClick={() => {
          window.location.hash = "";
        }}
      >
        ← Zurück zu allen Gruppen
      </button>
      <p className="empty">Keine Ergebnisse für die Suche.</p>
    </section>
  );

  return (
    <section className="groups">
      <button
        type="button"
        className="link"
        onClick={() => {
          window.location.hash = "";
        }}
      >
        ← Zurück zu allen Gruppen
      </button>
      <div className="groups__bar">
        <h2>{`Suchergebnisse für „${q}“`}</h2>
      </div>
      <GroupsTable
        groups={groups}
        itemTypes={itemTypes.filter((it) => it.item_class !== "consumable")}
        showPackstreet={true}
        isAdmin={isAdmin}
        onOpenOverview={onOpenGroup}
        onDeleteGroup={onDeleteGroup}
      />
    </section>
  );
}