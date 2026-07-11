import type { GroupSummary, ItemTypeDef } from "../types";
import { quantityOf } from "../types";

interface Props {
  groups: GroupSummary[];
  itemTypes: ItemTypeDef[];
  showPackstreet?: boolean;
  onOpenOverview: (group: GroupSummary) => void;
}

export function GroupsTable({
  groups,
  itemTypes,
  showPackstreet = false,
  onOpenOverview,
}: Props) {
  return (
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
              <td key={itemType.key} className="num">
                {quantityOf(group, itemType.key)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
