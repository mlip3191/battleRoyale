// Names the browser tab after the page on screen, so tabs and screen readers say where you are.
import { useEffect } from "react";

export const SHOW_NAME = "Battle Royale";

// The tab title for one page: "<page> · Battle Royale", or just the show's name with no page.
export const pageTitle = (page?: string) =>
  page ? `${page} · ${SHOW_NAME}` : SHOW_NAME;

// Set the tab title while this page is on screen; it updates when the page name changes.
export function usePageTitle(page?: string) {
  useEffect(() => {
    document.title = pageTitle(page);
  }, [page]);
}
