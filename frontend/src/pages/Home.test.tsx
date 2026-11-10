// The intake desk (D03): ok, clarify, and blocked replies; terrain; showcase; keyboard and labels.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import okResult from "../fixtures/intake-result.json";
import * as client from "../api/client.ts";
import { SHOWCASE } from "../api/fixtures.ts";
import Home, { EXAMPLES } from "./Home.tsx";

vi.mock("../api/client.ts", async (original) => ({
  ...(await original<typeof import("../api/client.ts")>()),
  postIntake: vi.fn(),
  answerIntake: vi.fn(),
  createBattle: vi.fn(),
  listShowcase: vi.fn(),
}));
const api = vi.mocked(client);

const ok = okResult as unknown as client.IntakeResult;
const clarify = {
  status: "clarify",
  matchup: null,
  question: "Which kind of bear?",
  options: ["Grizzly bear", "Polar bear"],
  pending_id: "p-123",
  blocked_reason: null,
  message: null,
} as unknown as client.IntakeResult;
const blocked = {
  status: "blocked",
  matchup: null,
  question: null,
  options: [],
  pending_id: null,
  blocked_reason: "real_person",
  message: "We only book animals, machines, and legends, not real people.",
} as unknown as client.IntakeResult;

beforeEach(() => {
  api.listShowcase.mockResolvedValue(SHOWCASE);
  api.createBattle.mockResolvedValue({ battle_id: "b-new" });
});

afterEach(() => {
  cleanup();
  vi.clearAllMocks();
});

// Render the home page with a stand-in broadcast page to land on.
function open() {
  render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route path="/" element={<Home />} />
        <Route path="/battle/:id" element={<p>broadcast page</p>} />
      </Routes>
    </MemoryRouter>,
  );
  return screen.getByLabelText("Who would win?") as HTMLTextAreaElement;
}

// Type a matchup and press Enter.
function ask(box: HTMLTextAreaElement, text: string) {
  fireEvent.change(box, { target: { value: text } });
  fireEvent.keyDown(box, { key: "Enter" });
}

test("ok: Enter submits, shows the confirmation card, and FIGHT! starts the battle", async () => {
  api.postIntake.mockResolvedValue(ok);
  const box = open();
  ask(box, "a grizzly bear vs 6 gray wolves in a forest");
  expect(api.postIntake).toHaveBeenCalledWith(
    "a grizzly bear vs 6 gray wolves in a forest",
  );

  const card = await screen.findByRole("region", { name: "Tonight's card" });
  expect(within(card).getByText("6 × gray wolf")).toBeTruthy();
  expect(within(card).getByText("Assumed adult male grizzly")).toBeTruthy();
  expect(
    (screen.getByLabelText("Battlefield") as HTMLSelectElement).value,
  ).toBe("forest");

  fireEvent.click(within(card).getByRole("button", { name: "FIGHT!" }));
  expect(api.createBattle).toHaveBeenCalledWith(ok.matchup);
  expect(await screen.findByText("broadcast page")).toBeTruthy();
});

test("Shift+Enter adds a line instead of submitting", () => {
  const box = open();
  fireEvent.change(box, { target: { value: "a goose" } });
  fireEvent.keyDown(box, { key: "Enter", shiftKey: true });
  expect(api.postIntake).not.toHaveBeenCalled();
});

test("changing the terrain changes the matchup sent to POST /api/battles", async () => {
  api.postIntake.mockResolvedValue(ok);
  ask(open(), "a grizzly bear vs 6 gray wolves");
  const card = await screen.findByRole("region", { name: "Tonight's card" });
  fireEvent.change(screen.getByLabelText("Battlefield"), {
    target: { value: "water" },
  });
  fireEvent.click(within(card).getByRole("button", { name: "FIGHT!" }));
  expect(api.createBattle).toHaveBeenCalledWith({
    ...ok.matchup,
    terrain: "water",
  });
});

test("clarify: shows the question with option buttons and a free-text answer", async () => {
  api.postIntake.mockResolvedValue(clarify);
  api.answerIntake.mockResolvedValue(ok);
  ask(open(), "a bear vs 6 wolves");

  const card = await screen.findByRole("region", { name: "Quick question" });
  expect(within(card).getByText("Which kind of bear?")).toBeTruthy();
  expect(within(card).getByRole("button", { name: "Polar bear" })).toBeTruthy();
  expect(within(card).getByLabelText("Or type your answer")).toBeTruthy();

  fireEvent.click(within(card).getByRole("button", { name: "Grizzly bear" }));
  expect(api.answerIntake).toHaveBeenCalledWith("p-123", "Grizzly bear");
  expect(
    await screen.findByRole("region", { name: "Tonight's card" }),
  ).toBeTruthy();
});

test("clarify: a typed answer is sent too", async () => {
  api.postIntake.mockResolvedValue(clarify);
  api.answerIntake.mockResolvedValue(ok);
  ask(open(), "a bear vs 6 wolves");
  const answer = await screen.findByLabelText("Or type your answer");
  fireEvent.change(answer, { target: { value: "a sloth bear" } });
  fireEvent.click(screen.getByRole("button", { name: "Answer" }));
  expect(api.answerIntake).toHaveBeenCalledWith("p-123", "a sloth bear");
});

test("blocked: shows the friendly message and keeps the typed text", async () => {
  api.postIntake.mockResolvedValue(blocked);
  const box = open();
  ask(box, "my neighbor vs a goose");
  expect((await screen.findByRole("alert")).textContent).toContain(
    "not real people",
  );
  expect(box.value).toBe("my neighbor vs a goose");
});

test("a network failure shows a way to retry and keeps the text", async () => {
  api.postIntake.mockRejectedValue(new Error("offline"));
  const box = open();
  ask(box, "a goose vs a toaster");
  expect((await screen.findByRole("alert")).textContent).toContain(
    "couldn't reach the studio",
  );
  expect(box.value).toBe("a goose vs a toaster");
  expect(
    screen
      .getAllByRole("button", { name: "FIGHT!" })[0]
      .hasAttribute("disabled"),
  ).toBe(false);
});

test("the Showcase row lists five battles that link to their broadcasts", async () => {
  open();
  const row = await screen.findByRole("region", { name: "Showcase" });
  const links = within(row).getAllByRole("link");
  expect(links).toHaveLength(5);
  expect(links[1].getAttribute("href")).toBe(
    `/battle/${SHOWCASE[1].battle_id}`,
  );
});

test("example chips fill the box", () => {
  const box = open();
  fireEvent.click(screen.getByRole("button", { name: EXAMPLES[0] }));
  expect(box.value).toBe(EXAMPLES[0]);
});

test("every control is labeled and reachable with Tab", async () => {
  api.postIntake.mockResolvedValue(ok);
  ask(open(), "a grizzly bear vs 6 gray wolves");
  await screen.findByRole("region", { name: "Tonight's card" });
  await waitFor(() => expect(screen.getAllByRole("link").length).toBe(5));

  const controls = Array.from(
    document.querySelectorAll("button, a, input, select, textarea"),
  );
  for (const el of controls) {
    expect(el.getAttribute("tabindex"), el.outerHTML).not.toBe("-1");
    if (el.matches("input, select, textarea")) {
      expect(
        document.querySelector(`label[for="${el.id}"]`),
        el.outerHTML,
      ).not.toBeNull();
    } else {
      expect(el.textContent?.trim(), el.outerHTML).toBeTruthy();
    }
  }
});
