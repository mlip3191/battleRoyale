import { cleanup, render, screen } from "@testing-library/react";
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
