import { useState } from "react";
import type { GroupSummary, ItemTypeDef } from "../types";
import { quantityOf } from "../types";
import { deleteGroup } from "../api";
import { ApiError } from "../api";

function QuantityCell({ value }: { value: number }) {
  return (
    <td className={`num ${value < 0 ? "num--negative" : ""}`}>
      {value}
    </td>
  );
}

interface Props {
  groups: GroupSummary[];
  itemTypes: ItemTypeDef[];
  showPackstreet?: boolean;
  isAdmin?: boolean;
  onOpenOverview: (group: GroupSummary) => void;
  onDeleteGroup?: (group: GroupSummary) => void;
}

export function GroupsTable({
  groups,
  itemTypes,
  showPackstreet = false,
  isAdmin = false,
  onOpenOverview,
  onDeleteGroup,
}: Props) {
  const [deleteError, setDeleteError] = useState<string | null>(null);

  async function handleDelete(group: GroupSummary) {
    const confirmed = window.confirm(
      `Gruppe „${group.name}“ löschen? Eine Gruppe, die noch ausleihbare Artikel ausgeliehen hat, kann nicht gelöscht werden.`,
    );
    if (!confirmed) return;

    setDeleteError(null);
    try {
      await deleteGroup(group.id);
      onDeleteGroup?.(group);
    } catch (err) {
      setDeleteError(
        err instanceof ApiError ? err.message : "Fehler beim Löschen der Gruppe.",
      );
    }
  }

  return (
    <>
      {deleteError && <p className="banner banner--error">{deleteError}</p>}
      <div className="table-scroll">
      <table className="groups-table">
        <thead>
          <tr>
            <th className="num">ID</th>
            <th>Gruppe</th>
            {showPackstreet && <th>Packstraße</th>}
            {itemTypes.map((itemType) => (
              <th key={itemType.key} className="num">
                {itemType.label}
              </th>
            ))}
            {isAdmin && <th></th>}
          </tr>
        </thead>
        <tbody>
          {groups.map((group) => (
            <tr key={group.id}>
              <td className="num">{group.internal_id}</td>
              <td>
                <button
                  type="button"
                  className="link"
                  onClick={(e) => {
                    e.stopPropagation();
                    onOpenOverview(group);
                  }}
                >
                  {group.name}
                </button>
              </td>
              {showPackstreet && <td>{group.packstreet.name}</td>}
              {itemTypes.map((itemType) => (
                <QuantityCell
                  key={itemType.key}
                  value={quantityOf(group, itemType.key)}
                />
              ))}
              {isAdmin && (
                <td>
                  <button
                    type="button"
                    className="btn--danger"
                    onClick={(e) => {
                      e.stopPropagation();
                      void handleDelete(group);
                    }}
                  >
                    Löschen
                  </button>
                </td>
              )}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </>
  );
}
