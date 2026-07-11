// Types mirroring the django-ninja schemas in dbtrials/dbtrials/schemas.py.

/** The authenticated user's identity and admin status (matches `UserOut`). */
export interface CurrentUser {
  username: string;
  is_admin: boolean;
  show_consumables: boolean;
  selected_packstreet_id: number | null;
}

/** The key identifying an item type (matches the backend `ItemType.key`). */
export type ItemType = string;

/** An admin-managed item type (matches `ItemTypeOut`). */
export interface ItemTypeDef {
  id: number;
  key: string;
  label: string;
  item_class: string;
}

/** A rented item type and its quantity (matches `RentalItemOut`). */
export interface RentalItem {
  item_type: ItemType;
  quantity: number;
}

/** A packstreet that groups belong to (matches `PackstreetOut`). */
export interface Packstreet {
  id: number;
  name: string;
}

/** A cooking group summary (matches `GroupSummaryOut`). */
export interface GroupSummary {
  id: number;
  name: string;
  internal_id: string;
  packstreet: Packstreet;
  total_items: number;
  rentals: RentalItem[];
}

/** Payload for renting/returning items (matches `RentActionIn`). */
export interface RentAction {
  item_type: ItemType;
  quantity: number;
}

/** One possible item type and the group's quantity (matches `GroupOverviewItemOut`). */
export interface GroupOverviewItem {
  item_type: ItemType;
  label: string;
  item_class: string;
  quantity: number;
}

/** A rent or return action recorded in the audit log (matches `ActionType`). */
export type ActionType = "rent" | "return" | "correct";

/** A single rental audit-log entry (matches `RentalActionOut`). */
export interface RentalActionLog {
  id: number;
  action: ActionType;
  item_type: ItemType;
  quantity: number;
  username: string | null;
  timestamp: string;
}

/** A rental action shown in the correction/deletion dialog (matches `RecentActionOut`). */
export interface RecentAction {
  id: number;
  action: ActionType;
  item_type: ItemType;
  quantity: number;
  username: string | null;
  timestamp: string;
}

/** Detailed group overview listing every item type (matches `GroupOverviewOut`). */
export interface GroupOverview {
  id: number;
  name: string;
  internal_id: string;
  packstreet: Packstreet;
  items: GroupOverviewItem[];
  recent_actions: RentalActionLog[];
}

/** One point in an item type's stock-over-time series (matches `HistoryPointOut`). */
export interface HistoryPoint {
  timestamp: string;
  quantity: number;
}

/** Cumulative stock over time for one item type (matches `ItemHistoryOut`). */
export interface ItemHistory {
  item_type: ItemType;
  label: string;
  points: HistoryPoint[];
}

/** A group's stock-over-time series for every item type (matches `GroupHistoryOut`). */
export interface GroupHistory {
  id: number;
  name: string;
  internal_id: string;
  series: ItemHistory[];
}

/** A single group row processed during a CSV import (matches `GroupImportRowOut`). */
export interface GroupImportRow {
  name: string;
  internal_id: string;
  packstreet: string;
}

/** The outcome of a bulk group CSV import (matches `GroupImportResultOut`). */
export interface GroupImportResult {
  created: GroupImportRow[];
  skipped: GroupImportRow[];
  errors: string[];
}

/** Quantity of a given item type rented out to a group (0 if none). */
export function quantityOf(group: GroupSummary, itemType: ItemType): number {
  return group.rentals.find((r) => r.item_type === itemType)?.quantity ?? 0;
}
