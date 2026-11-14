import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App.tsx";

beforeEach(() => {
  vi.stubEnv("VITE_USE_FIXTURES", "true");
  vi.stubGlobal(
    "fetch",
    vi.fn().mockResolvedValue(Response.json({ status: "ok" })),
  );
});

afterEach(() => {
  cleanup();
  vi.unstubAllEnvs();
  vi.unstubAllGlobals();
});

// Render the whole app at one address.
const at = (path: string) =>
  render(
    <MemoryRouter initialEntries={[path]}>
      <App />
    </MemoryRouter>,
  );

test("every page has the broadcast header", () => {
  at("/");
  expect(screen.getByRole("link", { name: "BATTLE ROYALE" })).toBeTruthy();
});

test("/ renders the home page", () => {
  at("/");
  expect(
    screen.getByRole("heading", { level: 1, name: "Who would win?" }),
  ).toBeTruthy();
});

test("/battle/:id renders the broadcast frame", async () => {
  at("/battle/b-7f3k2q");
  expect(
    await screen.findByRole("heading", {
      level: 1,
      name: "a grizzly bear vs 6 gray wolves in a forest",
    }),
  ).toBeTruthy();
  expect(screen.getByText("● LIVE")).toBeTruthy();
});

test("the LIVE badge shows only during a broadcast", () => {
  at("/");
  expect(screen.queryByText("● LIVE")).toBeNull();
});

test("/battle/:id/results renders the results frame", () => {
  at("/battle/b-7f3k2q/results");
  expect(screen.getByRole("heading", { name: "Results" })).toBeTruthy();
});

test("an unknown address renders the 404 page", () => {
  at("/no-such-page");
  expect(screen.getByText("404: we lost the signal")).toBeTruthy();
});

// Everything a keyboard user can Tab to, in page order.
const tabStops = () =>
  Array.from(
    document.querySelectorAll<HTMLElement>(
      "a[href], button, input, select, textarea, [tabindex]",
    ),
  ).filter((el) => el.tabIndex >= 0 && !(el as HTMLButtonElement).disabled);

const ROUTES = [
  "/",
  "/battle/b-7f3k2q",
  "/battle/b-7f3k2q/results",
  "/no-such-page",
];

test.each(ROUTES)(
  "%s: the skip link is the first thing Tab reaches",
  async (path) => {
    at(path);
    await screen.findByRole("main");
    expect(tabStops()[0]).toBe(
      screen.getByRole("link", { name: "Skip to main content" }),
    );
  },
);

test.each(ROUTES)(
  "%s: the skip link moves keyboard focus to the main content",
  async (path) => {
    at(path);
    const main = await screen.findByRole("main");
    const skip = screen.getByRole("link", { name: "Skip to main content" });
    skip.focus();
    fireEvent.click(skip); // Enter on a focused link fires a click
    expect(document.activeElement).toBe(main);
    // The link points at the page's own content, which can take focus without becoming a Tab stop.
    expect(skip.getAttribute("href")).toBe(`#${main.id}`);
    expect(main.tabIndex).toBe(-1);
  },
);

test("the home page's tab title is the show's name", () => {
  at("/");
  expect(document.title).toBe("Battle Royale");
});

test("the battle page's tab title names the matchup once it loads", async () => {
  at("/battle/b-7f3k2q");
  expect(document.title).toBe("Battle · Battle Royale");
  await waitFor(() =>
    expect(document.title).toBe(
      "a grizzly bear vs 6 gray wolves in a forest · Battle Royale",
    ),
  );
});

test("the results page's tab title names the matchup once it loads", async () => {
  at("/battle/b-7f3k2q/results");
  expect(document.title).toBe("Results · Battle Royale");
  await waitFor(() =>
    expect(document.title).toBe(
      "Results: a grizzly bear vs 6 gray wolves in a forest · Battle Royale",
    ),
  );
});

test("the 404 page's tab title says the page wasn't found", () => {
  at("/no-such-page");
  expect(document.title).toBe("Page not found · Battle Royale");
});
