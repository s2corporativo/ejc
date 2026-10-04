import * as React from "react";

/**
 * Hook que lê a contagem de favoritos do localStorage sem causar
 * "set-state-in-effect". Usa useSyncExternalStore para subscrição segura.
 */
export function useFavoritesCount(deps: unknown[] = []): number {
  // Key for snapshotting - we re-read when deps change
  const depsKey = JSON.stringify(deps);
  const subscribe = React.useCallback((onStoreChange: () => void) => {
    const handler = () => onStoreChange();
    window.addEventListener("storage", handler);
    window.addEventListener("juridia-favorites-changed", handler);
    return () => {
      window.removeEventListener("storage", handler);
      window.removeEventListener("juridia-favorites-changed", handler);
    };
  }, []);

  const getSnapshot = React.useCallback(() => {
    // Include depsKey to invalidate when deps change (docs reload)
    try {
      const stored = localStorage.getItem("juridia-favorites");
      const favs = stored ? JSON.parse(stored) : [];
      const count = Array.isArray(favs) ? favs.length : 0;
      return `${depsKey}:${count}`;
    } catch {
      return `${depsKey}:0`;
    }
  }, [depsKey]);

  const getServerSnapshot = React.useCallback(() => `${depsKey}:0`, [depsKey]);

  const snapshot = React.useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
  return parseInt(snapshot.split(":").slice(-1)[0] || "0", 10);
}
