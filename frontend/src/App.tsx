import { useCallback, useEffect, useState } from "react";

import {
  ApiError,
  checkIntegrity,
  downloadStockCsv,
  getCurrentUser,
  listPackstreets,
  listGroups,
  listItemTypes,
  logout,
  updateCurrentUser,
} from "./api";
import { LOGOUT_EVENT } from "./auth";
import type { CurrentUser, GroupSummary, IntegrityCheckResult, ItemTypeDef, Packstreet } from "./types";
import { PackstreetManager } from "./components/PackstreetManager";
import { CreateGroupForm } from "./components/CreateGroupForm";
import { DataImport } from "./components/DataImport";
import { GroupHistory } from "./components/GroupHistory";
import { GroupOverview } from "./components/GroupOverview";
import { GroupsTable } from "./components/GroupsTable";
import { ItemTypeManager } from "./components/ItemTypeManager";
import { LoginForm } from "./components/LoginForm";

type Route =
  | { view: "list" }
  | { view: "overview"; id: number }
  | { view: "history"; id: number };

/** Read the current view from the URL hash. */
function parseRoute(hash: string): Route {
  const history = hash.match(/^#\/group\/(\d+)\/history$/);
  if (history) {
    return { view: "history", id: Number(history[1]) };
  }
  const overview = hash.match(/^#\/group\/(\d+)$/);
  if (overview) {
    return { view: "overview", id: Number(overview[1]) };
  }
  return { view: "list" };
}

export default function App() {
  const [authChecked, setAuthChecked] = useState(false);
  const [authed, setAuthed] = useState(false);
  const [isAdmin, setIsAdmin] = useState(false);
  const [username, setUsername] = useState<string | null>(null);
  const [showConsumables, setShowConsumables] = useState(true);
  const [preferRent, setPreferRent] = useState(true);

  const [packstreets, setPackstreets] = useState<Packstreet[]>([]);
  const [itemTypes, setItemTypes] = useState<ItemTypeDef[]>([]);
  const [selectedPackstreetId, setSelectedPackstreetId] = useState<number | null>(
    null,
  );
  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");

  const [groups, setGroups] = useState<GroupSummary[]>([]);
  const [route, setRoute] = useState<Route>(() =>
    parseRoute(window.location.hash),
  );
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [csvError, setCsvError] = useState<string | null>(null);
  const [integrityResult, setIntegrityResult] =
    useState<IntegrityCheckResult | null>(null);
  const [integrityOpen, setIntegrityOpen] = useState(false);
  const [integrityError, setIntegrityError] = useState<string | null>(null);
  const [reloadNonce, setReloadNonce] = useState(0);

  const searching = debouncedSearch.trim().length > 0;

  // Apply the current user to local auth state.
  const applyUser = useCallback((user: CurrentUser) => {
    setAuthed(true);
    setIsAdmin(user.is_admin);
    setUsername(user.username);
    setShowConsumables(user.show_consumables);
    setPreferRent(user.prefer_rent);
    if (user.selected_packstreet_id !== null) {
      setSelectedPackstreetId(user.selected_packstreet_id);
    }
    window.location.hash = "";
  }, []);

  // Log the user out when the session expires (refresh failed).
  useEffect(() => {
    function onLogout() {
      setAuthed(false);
      setIsAdmin(false);
      setUsername(null);
    }
    window.addEventListener(LOGOUT_EVENT, onLogout);
    return () => window.removeEventListener(LOGOUT_EVENT, onLogout);
  }, []);

  // On load, ask the backend who we are (the session cookie is HttpOnly).
  useEffect(() => {
    let cancelled = false;
    getCurrentUser()
      .then((user) => {
        if (!cancelled) {
          applyUser(user);
        }
      })
      .catch(() => {
        /* Not logged in; show the login form. */
      })
      .finally(() => {
        if (!cancelled) {
          setAuthChecked(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [applyUser]);

  // Keep the view in sync with the URL hash so a browser refresh (or the
  // back/forward buttons) preserves the current view.
  useEffect(() => {
    function onHashChange() {
      setRoute(parseRoute(window.location.hash));
    }
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  // Debounce the search box so typing doesn't hit the server on every keypress.
  useEffect(() => {
    const handle = window.setTimeout(() => setDebouncedSearch(search), 250);
    return () => window.clearTimeout(handle);
  }, [search]);

  const loadPackstreets = useCallback(async () => {
    const loaded = await listPackstreets();
    setPackstreets(loaded);
    setSelectedPackstreetId((current) => {
      if (current !== null && loaded.some((b) => b.id === current)) {
        return current;
      }
      return loaded[0]?.id ?? null;
    });
  }, []);

  const loadItemTypes = useCallback(async () => {
    setItemTypes(await listItemTypes());
  }, []);

  useEffect(() => {
    if (authed) {
      loadPackstreets().catch(() => {
        /* Packstreet load failures surface via the groups error below. */
      });
    }
  }, [authed, loadPackstreets]);

  useEffect(() => {
    if (authed) {
      loadItemTypes().catch(() => {
        /* Item type load failures surface via the groups error below. */
      });
    }
  }, [authed, loadItemTypes]);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const term = debouncedSearch.trim();
      const loaded = term
        ? await listGroups({ q: term })
        : await listGroups({ packstreetId: selectedPackstreetId });
      setGroups(loaded);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Gruppen konnten nicht geladen werden.");
    } finally {
      setLoading(false);
    }
  }, [debouncedSearch, selectedPackstreetId]);

  useEffect(() => {
    if (authed && selectedPackstreetId !== null) {
      void refresh();
    }
  }, [authed, refresh, reloadNonce]);

  // Replace a single group in local state after a rent/return/correct action.
  const handleGroupUpdated = useCallback((updated: GroupSummary) => {
    setGroups((prev) => prev.map((g) => (g.id === updated.id ? updated : g)));
  }, []);

  const handleGroupCreated = useCallback((created: GroupSummary) => {
    setSearch("");
    setDebouncedSearch("");
    setSelectedPackstreetId(created.packstreet.id);
    setReloadNonce((n) => n + 1);
  }, []);

  const handleGroupDeleted = useCallback((deletedId: number) => {
    setGroups((prev) => prev.filter((g) => g.id !== deletedId));
  }, []);

  const handleItemTypesChanged = useCallback(() => {
    void loadItemTypes();
    setReloadNonce((n) => n + 1);
  }, [loadItemTypes]);

  const handleGroupsImported = useCallback(() => {
    setSearch("");
    setDebouncedSearch("");
    setReloadNonce((n) => n + 1);
  }, []);

  function handleLogout() {
    void logout();
    setAuthed(false);
    setIsAdmin(false);
    setUsername(null);
  }

  async function handleDownloadCsv() {
    setCsvError(null);
    try {
      await downloadStockCsv();
    } catch (err) {
      setCsvError(
        err instanceof ApiError ? err.message : "CSV konnte nicht heruntergeladen werden.",
      );
    }
  }

  async function handleIntegrityCheck() {
    setIntegrityError(null);
    setIntegrityResult(null);
    try {
      const result = await checkIntegrity();
      setIntegrityResult(result);
      setIntegrityOpen(true);
    } catch (err) {
      setIntegrityError(
        err instanceof ApiError ? err.message : "Integritätsprüfung fehlgeschlagen.",
      );
    }
  }

  if (!authChecked) {
    return (
      <div className="app">
        <header className="app__header">
          <h1>Kisten-Tracker</h1>
        </header>
        <p className="empty">Ladevorgang…</p>
      </div>
    );
  }

  if (!authed) {
    return (
      <div className="app app--login">
        <header className="app__header">
          <h1>Kisten-Tracker</h1>
        </header>
        <LoginForm onSuccess={applyUser} />
      </div>
    );
  }

  return (
    <div className="app">
      <header className="app__header">
        <div className="app__titlebar">
          <h1>Kisten-Tracker</h1>
          <div className="app__user">
            {username && (
              <span className="user-badge" title={`Angemeldet als ${username}`}>
                <svg
                  className="user-badge__icon"
                  viewBox="0 0 24 24"
                  width="18"
                  height="18"
                  aria-hidden="true"
                >
                  <path
                    fill="currentColor"
                    d="M12 12a5 5 0 1 0 0-10 5 5 0 0 0 0 10Zm0 2c-4.42 0-8 2.69-8 6v2h16v-2c0-3.31-3.58-6-8-6Z"
                  />
                </svg>
                <span className="user-badge__name">{username}</span>
              </span>
            )}
            <button type="button" className="btn btn--ghost" onClick={handleLogout}>
              Abmelden
            </button>
          </div>
        </div>
      </header>

      {!searching && packstreets.length > 0 && (
        <div className="packstreet-tabs" role="tablist">
          {packstreets.map((p) => (
            <button
              key={p.id}
              type="button"
              role="tab"
              aria-selected={p.id === selectedPackstreetId}
              className={
                p.id === selectedPackstreetId
                  ? "packstreet-tab is-active"
                  : "packstreet-tab"
              }
              onClick={() => {
                window.location.hash = "";
                setSelectedPackstreetId(p.id);
                void updateCurrentUser(undefined, undefined, p.id);
              }}
            >
              {p.name}
            </button>
          ))}
        </div>
      )}

      <div className="groups__toolbar">
        <input
          type="search"
          className="groups__search"
          value={search}
          placeholder="Gruppenname oder -ID suchen…"
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Gruppen durchsuchen"
        />
      </div>

      {route.view === "history" ? (
        <GroupHistory
          groupId={route.id}
          onBack={() => {
            window.location.hash = `/group/${route.id}`;
          }}
        />
      ) : route.view === "overview" ? (
        <GroupOverview
          groupId={route.id}
          isAdmin={isAdmin}
          packstreets={packstreets}
          showConsumables={showConsumables}
          preferRent={preferRent}
          onBack={() => {
            window.location.hash = "";
          }}
          onViewHistory={() => {
            window.location.hash = `/group/${route.id}/history`;
          }}
          onGroupChanged={handleGroupUpdated}
          onDeleted={(deletedId) => {
            handleGroupDeleted(deletedId);
            window.location.hash = "";
          }}
        />
      ) : (
        <>
          {isAdmin && (
            <PackstreetManager packstreets={packstreets} onChanged={loadPackstreets} />
          )}
          {isAdmin && (
            <ItemTypeManager
              itemTypes={itemTypes}
              onChanged={handleItemTypesChanged}
            />
          )}
          {isAdmin && (
            <CreateGroupForm
              packstreets={packstreets}
              defaultPackstreetId={selectedPackstreetId}
              onCreated={handleGroupCreated}
            />
          )}
          {isAdmin && <DataImport onImported={handleGroupsImported} />}

          {isAdmin && (
            <details
              className="card integrity-check"
              open={integrityOpen}
              onToggle={(e) =>
                setIntegrityOpen((e.target as HTMLDetailsElement).open)
              }
            >
              <summary className="integrity-check__summary">
                Integritätsprüfung
              </summary>
              <div className="integrity-check__body">
                <button
                  type="button"
                  className="btn"
                  onClick={() => void handleIntegrityCheck()}
                >
                  Prüfen
                </button>
                {integrityError && (
                  <p className="banner banner--error">{integrityError}</p>
                )}
                {integrityResult && (
                  <div className="integrity-check__result">
                    {integrityResult.ok ? (
                      <p className="banner banner--success">
                        Keine Unstimmigkeiten gefunden.
                      </p>
                    ) : (
                      <>
                        <p className="banner banner--error">
                          {integrityResult.mismatches.length} Unstimmigkeit
                          {integrityResult.mismatches.length !== 1 ? "en" : ""}{" "}
                          gefunden:
                        </p>
                        <div className="table-scroll">
                        <table className="overview-table">
                          <thead>
                            <tr>
                              <th>Gruppe</th>
                              <th>Artikeltyp</th>
                              <th>Gespeichert</th>
                              <th>Berechnet</th>
                            </tr>
                          </thead>
                          <tbody>
                            {integrityResult.mismatches.map((m, i) => (
                              <tr key={i}>
                                <td>{m.group_name}</td>
                                <td>{m.item_type}</td>
                                <td>{m.rental_quantity}</td>
                                <td>{m.computed_quantity}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                        </div>
                      </>
                    )}
                  </div>
                )}
              </div>
            </details>
          )}

          <section className="groups">
            <div className="groups__toolbar">
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => void handleDownloadCsv()}
              >
                Bestands-CSV herunterladen
              </button>
            </div>
            {csvError && <p className="banner banner--error">{csvError}</p>}

            <div className="groups__bar">
              <h2>
                {searching
                  ? `Suchergebnisse für „${debouncedSearch.trim()}“`
                  : (packstreets.find((p) => p.id === selectedPackstreetId)?.name ??
                    "Gruppen")}
              </h2>
              <button
                type="button"
                className="btn btn--ghost"
                onClick={() => void refresh()}
                disabled={loading}
              >
                {loading ? "Aktualisiere…" : "Aktualisieren"}
              </button>
            </div>

            {error && <p className="banner banner--error">{error}</p>}

            {!error && !loading && packstreets.length === 0 && (
              <p className="empty">
                {isAdmin
                  ? "Noch keine Packstraßen. Füge oben eine hinzu."
                  : "Noch keine Packstraßen."}
              </p>
            )}

            {!error && !loading && packstreets.length > 0 && groups.length === 0 && (
              <p className="empty">
                {searching
                  ? "Keine Gruppen gefunden."
                  : isAdmin
                    ? "Noch keine Gruppen in dieser Packstraße. Erstelle eine oben."
                    : "Noch keine Gruppen in dieser Packstraße."}
              </p>
            )}

            {groups.length > 0 && (
              <GroupsTable
                groups={groups}
                itemTypes={itemTypes.filter((it) => it.item_class !== "consumable")}
                showPackstreet={searching}
                isAdmin={isAdmin}
                onOpenOverview={(group) => {
                  window.location.hash = `/group/${group.id}`;
                }}
                onDeleteGroup={(group) => handleGroupDeleted(group.id)}
              />
            )}
          </section>
        </>
      )}
    </div>
  );
}
