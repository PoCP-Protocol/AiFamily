import type { Href } from "expo-router";

/** Canonical fallback for the legacy UI registry until every route is semantic. */
export function routeForUi(screenId: string): Href {
  return `/ui/${screenId}` as Href;
}
