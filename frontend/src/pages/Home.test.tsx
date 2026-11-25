// The intake desk (D03): ok, clarify, and blocked replies; terrain; showcase; keyboard and labels.
import {
  act,
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import {
  afterEach,
  beforeEach,
  expect,
  onTestFinished,
  test,
  vi,
} from "vitest";
import okResult from "../fixtures/intake-result.json";
import * as client from "../api/client.ts";
import { SHOWCASE } from "../api/fixtures.ts";
import Home, { EXAMPLES, PLACEHOLDER, START_LABEL } from "./Home.tsx";

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
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
  vi.useRealTimers();
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

test("ok: Enter submits, shows the confirmation card, and its start button starts the battle", async () => {
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

  fireEvent.click(within(card).getByRole("button", { name: START_LABEL }));
  expect(api.createBattle).toHaveBeenCalledWith(ok.matchup);
  expect(await screen.findByText("broadcast page")).toBeTruthy();
});

test("the sky is one of the battlefields (D-70)", async () => {
  api.postIntake.mockResolvedValue(ok);
  ask(open(), "a grizzly bear vs 6 gray wolves");
  const card = await screen.findByRole("region", { name: "Tonight's card" });
  const field = screen.getByLabelText("Battlefield") as HTMLSelectElement;
  expect(within(field).getByRole("option", { name: "Sky" })).toBeTruthy();
  fireEvent.change(field, { target: { value: "sky" } });
  fireEvent.click(within(card).getByRole("button", { name: START_LABEL }));
  expect(api.createBattle).toHaveBeenCalledWith({
    ...ok.matchup,
    terrain: "sky",
  });
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
  fireEvent.click(within(card).getByRole("button", { name: START_LABEL }));
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
  const row = await screen.findByRole("region", {
    name: "Showcase (Ready Made)", // says these play instantly (#513)
  });
  const links = within(row).getAllByRole("link");
  expect(links).toHaveLength(5);
  expect(links[1].getAttribute("href")).toBe(
    `/battle/${SHOWCASE[1].battle_id}`,
  );
});

test("the example chips sit under a heading that says to try one (#511, #586)", () => {
  open();
  const examples = screen.getByRole("region", {
    name: "Stumped? Try one of the sample battles below",
  });
  const chips = within(examples).getAllByRole("button");
  expect(chips.map((chip) => chip.textContent)).toEqual(EXAMPLES);
  expect(
    within(examples).getByText(
      "Click one to fill in the box, then press FIGHT!",
    ),
  ).toBeTruthy();
});

test("example chips fill the box", () => {
  const box = open();
  fireEvent.click(screen.getByRole("button", { name: EXAMPLES[0] }));
  expect(box.value).toBe(EXAMPLES[0]);
});

// --- Cards that open below the fold (#462) ---

// Stand in for scrollIntoView (jsdom has none) and remove it again after the test.
function watchScrolling() {
  const scroll = vi.fn();
  Element.prototype.scrollIntoView = scroll;
  onTestFinished(() => {
    delete (Element.prototype as Partial<Element>).scrollIntoView;
  });
  return scroll;
}

test("tonight's card scrolls into view, takes focus, and its button isn't a second FIGHT!", async () => {
  const scroll = watchScrolling();
  api.postIntake.mockResolvedValue(ok);
  open();
  fireEvent.click(screen.getByRole("button", { name: EXAMPLES[0] }));
  fireEvent.click(screen.getByRole("button", { name: "FIGHT!" }));
  const card = await screen.findByRole("region", { name: "Tonight's card" });
  expect(document.activeElement).toBe(card);
  expect(scroll).toHaveBeenCalledTimes(1);
  expect(scroll.mock.contexts[0]).toBe(card);
  expect(START_LABEL).toBe("Start the fight!");
  expect(within(card).getByRole("button", { name: START_LABEL })).toBeTruthy();
  expect(screen.getAllByRole("button", { name: "FIGHT!" })).toHaveLength(1);
});

test("the quick question scrolls into view and takes focus, with no smooth scroll under reduced motion", async () => {
  const scroll = watchScrolling();
  vi.stubGlobal(
    "matchMedia",
    vi.fn((query: string) => ({
      matches: query === "(prefers-reduced-motion: reduce)",
    })),
  );
  api.postIntake.mockResolvedValue(clarify);
  ask(open(), "a bear vs 6 wolves");
  const card = await screen.findByRole("region", { name: "Quick question" });
  expect(document.activeElement).toBe(card);
  expect(scroll.mock.contexts[0]).toBe(card);
  expect(scroll).toHaveBeenCalledWith({ behavior: "auto", block: "start" });
});

// The fighters with a ready-made stat sheet in data/seed/fighters/ (singular or plural).
// Hand-copied: keep in sync with that folder's file names when a seed sheet is added or removed.
const SEED_FIGHTERS = [
  /\bafrican elephants?\b/,
  /\bafrican lions?\b/,
  /\bbald eagles?\b/,
  /\bbulldozers?\b/,
  /\bducks?\b/,
  /\bgorillas?\b/,
  /\bgray (wolf|wolves)\b/,
  /\bgrizzly bears?\b/,
  /\bhoney badgers?\b/,
  /\bhorses?\b/,
  /\bhouse cats?\b/,
  /\bking cobras?\b/,
  /\bmain battle tanks?\b/,
  /\broman legionar(y|ies)\b/,
  /\bsaltwater crocodiles?\b/,
];
const seedIn = (side: string) => SEED_FIGHTERS.filter((f) => f.test(side));

test("the box's placeholder names seed fighters on both sides (#361)", () => {
  const sides = PLACEHOLDER.split(" vs ");
  expect(sides).toHaveLength(2);
  // "horse-sized" only sets the duck's size; the fighter is the duck.
  for (const side of sides)
    expect(seedIn(side.replace(/\S+-sized /, "")), side).toHaveLength(1);
});

test("the six example chips use only seed fighters, with no size swaps (#205)", () => {
  expect(EXAMPLES).toHaveLength(6);
  expect(new Set(EXAMPLES).size).toBe(6);
  for (const example of EXAMPLES) {
    const sides = example.split(" vs ");
    expect(sides, example).toHaveLength(2);
    expect(example, example).not.toMatch(/sized/i);
    // Each side names exactly one seed fighter, and the two sides differ.
    const [left, right] = sides.map(seedIn);
    expect(left, example).toHaveLength(1);
    expect(right, example).toHaveLength(1);
    expect(left[0], example).not.toBe(right[0]);
    // Not yet calibrated (#47): gorilla vs grizzly bear stays off the list.
    expect(/gorilla/.test(example) && /grizzly/.test(example), example).toBe(
      false,
    );
  }
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

test("Enter that confirms an IME word (Japanese, Chinese, Korean input) doesn't submit", () => {
  const box = open();
  fireEvent.change(box, { target: { value: "くま vs おおかみ" } });
  fireEvent.keyDown(box, { key: "Enter", isComposing: true });
  expect(api.postIntake).not.toHaveBeenCalled();
});

test("clarify without a pending id shows an error instead of sending a broken request", async () => {
  api.postIntake.mockResolvedValue({ ...clarify, pending_id: null });
  ask(open(), "a bear vs 6 wolves");
  const card = await screen.findByRole("region", { name: "Quick question" });
  fireEvent.click(within(card).getByRole("button", { name: "Grizzly bear" }));
  expect(api.answerIntake).not.toHaveBeenCalled();
  expect(within(card).getByRole("alert").textContent).toContain("got lost");
});

test("while an answer is on its way the buttons are off, so a double click sends one request", async () => {
  api.postIntake.mockResolvedValue(clarify);
  api.answerIntake.mockReturnValue(new Promise(() => {}));
  ask(open(), "a bear vs 6 wolves");
  const card = await screen.findByRole("region", { name: "Quick question" });
  const option = within(card).getByRole("button", { name: "Grizzly bear" });
  fireEvent.click(option);
  fireEvent.click(option);
  expect(api.answerIntake).toHaveBeenCalledTimes(1);
  expect(option.hasAttribute("disabled")).toBe(true);
  expect(within(card).getByRole("button", { name: "Sending…" })).toBeTruthy();
});

test("a failed answer keeps the question on screen with an error", async () => {
  api.postIntake.mockResolvedValue(clarify);
  api.answerIntake.mockRejectedValue(new Error("offline"));
  ask(open(), "a bear vs 6 wolves");
  const card = await screen.findByRole("region", { name: "Quick question" });
  fireEvent.click(within(card).getByRole("button", { name: "Polar bear" }));
  expect((await within(card).findByRole("alert")).textContent).toContain(
    "couldn't reach the studio",
  );
  expect(within(card).getByText("Which kind of bear?")).toBeTruthy();
  expect(
    within(card)
      .getByRole("button", { name: "Polar bear" })
      .hasAttribute("disabled"),
  ).toBe(false);
});

test("if starting the battle fails, the card shows an error and its button works again", async () => {
  api.postIntake.mockResolvedValue(ok);
  api.createBattle.mockRejectedValue(new Error("offline"));
  ask(open(), "a grizzly bear vs 6 gray wolves");
  const card = await screen.findByRole("region", { name: "Tonight's card" });
  fireEvent.click(within(card).getByRole("button", { name: START_LABEL }));
  expect((await within(card).findByRole("alert")).textContent).toContain(
    "couldn't reach the studio",
  );
  expect(
    within(card)
      .getByRole("button", { name: START_LABEL })
      .hasAttribute("disabled"),
  ).toBe(false);
  expect(screen.queryByText("broadcast page")).toBeNull();
});

// --- Server error messages (#167, #201) and the still-working line (#201) ---

const EXPIRED =
  "That question has expired or was already answered. Please type your matchup again.";
const UNAVAILABLE =
  "Our matchup desk is having trouble right now. Please try again in a moment.";

// A fake fetch reply with a JSON body, the way the backend sends it.
const json = (body: unknown, status = 200) =>
  Promise.resolve(Response.json(body, { status }));

// Send intake calls through the real API client to a fake fetch that answers each address.
async function viaFetch(reply: (url: string) => Promise<Response>) {
  const real = await vi.importActual<typeof client>("../api/client.ts");
  vi.stubEnv("VITE_USE_FIXTURES", "false");
  api.postIntake.mockImplementation(real.postIntake);
  api.answerIntake.mockImplementation(real.answerIntake);
  vi.stubGlobal(
    "fetch",
    vi.fn((url: string) => reply(url)),
  );
}

// Ask a matchup that needs a question and wait for the question card.
async function question() {
  const box = open();
  ask(box, "a bear vs 6 wolves");
  const card = await screen.findByRole("region", { name: "Quick question" });
  return { box, card };
}

// Tap one of the question's options.
const tapOption = (card: HTMLElement) =>
  fireEvent.click(within(card).getByRole("button", { name: "Polar bear" }));

test("an expired question (404) shows the server's message and clears the card", async () => {
  await viaFetch((url) =>
    url.endsWith("/answer") ? json({ detail: EXPIRED }, 404) : json(clarify),
  );
  const { box, card } = await question();
  tapOption(card);
  expect((await screen.findByRole("alert")).textContent).toContain(EXPIRED);
  expect(screen.queryByText(/couldn't reach the studio/)).toBeNull();
  expect(screen.queryByRole("region", { name: "Quick question" })).toBeNull();
  expect(box.value).toBe("a bear vs 6 wolves");
});

test("a 404 without a server message still says the question was lost", async () => {
  api.postIntake.mockResolvedValue(clarify);
  api.answerIntake.mockRejectedValue(new client.ApiError(404));
  tapOption((await question()).card);
  expect((await screen.findByRole("alert")).textContent).toContain("got lost");
  expect(screen.queryByRole("region", { name: "Quick question" })).toBeNull();
});

test('a 404 from no route at all (a bare "Not Found") says the question was lost', async () => {
  await viaFetch((url) =>
    url.endsWith("/answer")
      ? json({ detail: "Not Found" }, 404)
      : json(clarify),
  );
  tapOption((await question()).card);
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain("got lost");
  expect(alert.textContent).not.toContain("Not Found");
});

test("a 500 on an answer still shows the offline message and keeps the card", async () => {
  api.postIntake.mockResolvedValue(clarify);
  api.answerIntake.mockRejectedValue(new client.ApiError(500, "Server error"));
  const { card } = await question();
  tapOption(card);
  expect((await within(card).findByRole("alert")).textContent).toContain(
    "couldn't reach the studio",
  );
  expect(within(card).getByText("Which kind of bear?")).toBeTruthy();
});

test("a 503 from /api/intake shows the server's try-again message", async () => {
  await viaFetch(() => json({ detail: UNAVAILABLE }, 503));
  const box = open();
  ask(box, "a goose vs a toaster");
  const alert = await screen.findByRole("alert");
  expect(alert.textContent).toContain(UNAVAILABLE);
  expect(alert.textContent).not.toContain("couldn't reach the studio");
  expect(box.value).toBe("a goose vs a toaster");
});

test("a 503 on an answer shows the server's message and keeps the question to retry", async () => {
  await viaFetch((url) =>
    url.endsWith("/answer")
      ? json({ detail: UNAVAILABLE }, 503)
      : json(clarify),
  );
  const { card } = await question();
  tapOption(card);
  expect((await within(card).findByRole("alert")).textContent).toContain(
    UNAVAILABLE,
  );
  expect(
    within(card)
      .getByRole("button", { name: "Polar bear" })
      .hasAttribute("disabled"),
  ).toBe(false);
});

test("a fetch that never reaches the server still shows the offline message", async () => {
  await viaFetch(() => Promise.reject(new TypeError("Failed to fetch")));
  ask(open(), "a goose vs a toaster");
  expect((await screen.findByRole("alert")).textContent).toContain(
    "couldn't reach the studio",
  );
});

test("after about 5 s a still-working line appears in a polite live region and goes with the reply", async () => {
  let reply: (response: Response) => void = () => {};
  await viaFetch(() => new Promise<Response>((resolve) => (reply = resolve)));
  vi.useFakeTimers();
  ask(open(), "a goose vs a toaster");
  const status = screen.getByRole("status");
  expect(status.getAttribute("aria-live")).toBe("polite");

  await act(() => vi.advanceTimersByTimeAsync(4_900));
  expect(status.textContent).toBe("");
  await act(() => vi.advanceTimersByTimeAsync(200));
  expect(status.textContent).toBe("Still sizing them up…");

  await act(async () => {
    reply(Response.json(ok));
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(status.textContent).toBe("");
  expect(screen.getByRole("region", { name: "Tonight's card" })).toBeTruthy();
});

test("a slow answer to the question shows the still-working line too", async () => {
  let reply: (result: client.IntakeResult) => void = () => {};
  api.postIntake.mockResolvedValue(clarify);
  api.answerIntake.mockReturnValue(new Promise((resolve) => (reply = resolve)));
  const { card } = await question();
  vi.useFakeTimers();
  tapOption(card);
  await act(() => vi.advanceTimersByTimeAsync(5_000));
  expect(screen.getByRole("status").textContent).toBe("Still sizing them up…");
  await act(async () => reply(ok));
  expect(screen.getByRole("status").textContent).toBe("");
});

test("a second request after a slow one starts its own 5 s wait", async () => {
  const replies: ((response: Response) => void)[] = [];
  await viaFetch(
    () => new Promise<Response>((resolve) => replies.push(resolve)),
  );
  vi.useFakeTimers();
  const box = open();
  const status = screen.getByRole("status");

  ask(box, "a goose vs a toaster");
  await act(() => vi.advanceTimersByTimeAsync(5_100));
  expect(status.textContent).toBe("Still sizing them up…");
  await act(async () => {
    replies[0](Response.json(ok));
    await vi.advanceTimersByTimeAsync(0);
  });
  expect(status.textContent).toBe("");

  ask(box, "a goose vs a kettle");
  await act(() => vi.advanceTimersByTimeAsync(4_900));
  expect(status.textContent).toBe("");
  await act(() => vi.advanceTimersByTimeAsync(200));
  expect(status.textContent).toBe("Still sizing them up…");
});

test("when two intake calls overlap, the first reply doesn't hide the line for the second", async () => {
  let replyAnswer: (result: client.IntakeResult) => void = () => {};
  api.postIntake.mockResolvedValueOnce(clarify);
  api.answerIntake.mockReturnValue(
    new Promise((resolve) => (replyAnswer = resolve)),
  );
  const { box, card } = await question();
  api.postIntake.mockReturnValue(new Promise(() => {}));
  vi.useFakeTimers();
  tapOption(card);
  fireEvent.keyDown(box, { key: "Enter" });
  expect(api.postIntake).toHaveBeenCalledTimes(2);

  await act(() => vi.advanceTimersByTimeAsync(1_000));
  await act(async () => replyAnswer(ok));
  await act(() => vi.advanceTimersByTimeAsync(4_100));
  expect(screen.getByRole("status").textContent).toBe("Still sizing them up…");
});

test("leaving the page mid-wait stops the still-working timer", async () => {
  await viaFetch(() => new Promise<Response>(() => {}));
  vi.useFakeTimers();
  ask(open(), "a goose vs a toaster");
  expect(vi.getTimerCount()).toBe(1);
  cleanup();
  expect(vi.getTimerCount()).toBe(0);
});

// #586: the instructions sit directly under "Who would win?", above the text box, in friendly
// words with an example; the box's accessible description is still that same text.
test("the instructions sit right under the heading, above the box, and describe it (#586)", () => {
  const box = open();
  const heading = screen.getByRole("heading", { level: 1 });
  const hint = document.getElementById("matchup-hint")!;
  expect(hint.textContent).toContain("Pick your dream showdown!");
  expect(hint.textContent).toContain(
    "a grizzly bear vs. 6 gray wolves in a forest",
  );
  expect(hint.textContent).toContain("press Enter or FIGHT!");
  expect(heading.nextElementSibling).toBe(hint); // directly under the heading
  expect(
    hint.compareDocumentPosition(box) & Node.DOCUMENT_POSITION_FOLLOWING,
  ).toBeTruthy(); // above the text box
  expect(box.getAttribute("aria-describedby")).toBe("matchup-hint");
  expect(screen.getByLabelText("Who would win?")).toBe(box); // the label is unchanged
});

// #581: T3 found the confirm card a confusing extra step. It stays, but says plainly that it is
// the last step and what to press, in the card and ahead of the button.
test("the card says it is the last step and points at the Start button (#581)", async () => {
  api.postIntake.mockResolvedValue(ok);
  open();
  fireEvent.click(screen.getByRole("button", { name: EXAMPLES[0] }));
  fireEvent.click(screen.getByRole("button", { name: "FIGHT!" }));
  const card = await screen.findByRole("region", { name: "Tonight's card" });
  expect(card.textContent).toContain(
    "Last step: check the card, then press the big button below.",
  );
  const text = card.textContent ?? "";
  expect(text.indexOf("Last step")).toBeLessThan(text.indexOf(START_LABEL));
});
