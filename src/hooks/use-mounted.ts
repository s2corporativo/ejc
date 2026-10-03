import * as React from "react";

const emptySubscribe = () => () => {};

/**
 * Returns `true` only after the component has mounted on the client.
 * SSR-safe: returns `false` on the server and during the first client render,
 * avoiding hydration mismatches without calling setState in an effect.
 */
export function useMounted() {
  return React.useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false
  );
}
