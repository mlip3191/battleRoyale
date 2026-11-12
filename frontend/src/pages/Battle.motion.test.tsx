// Reduced motion on the broadcast page (Mike's #48 note): the CSS rule in index.css stops CSS
// animations, so every JavaScript animation must check prefers-reduced-motion itself. The page's
// only JavaScript animation is the Phaser replay; here it runs on the stand-in Phaser.
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import done from "../fixtures/battle-record-done.json";
import type { BattleStage } from "../game/BattleScene.ts";
import { games } from "../game/fake-phaser.ts";
import indexCss from "../index.css?raw";
import pageCss from "./battle.module.css?raw";
import Battle from "./Battle.tsx";

vi.mock(
  "phaser",
  async () => (await import("../game/fake-phaser.ts")).fakePhaser,
);
vi.mock("../api/useBattle.ts", async (original) => ({
  ...(await original<typeof import("../api/useBattle.ts")>()),
  useBattle: () => ({ battle: done, error: null }),
}));

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
  games.length = 0;
});

// Open the broadcast with the browser's reduced-motion setting on or off, and start the fight.
async function fightWith(reduce: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn((q: string) => ({ matches: reduce && q.includes("reduce") })),
  );
  render(
    <MemoryRouter initialEntries={["/battle/b1"]}>
      <Routes>
        <Route path="/battle/:id" element={<Battle />} />
      </Routes>
    </MemoryRouter>,
  );
  fireEvent.click(screen.getByRole("button", { name: "Start the fight" }));
  await waitFor(() => expect(games).toHaveLength(1));
  const scene = games[0].config.scene[0] as BattleStage & {
    opts: { reducedMotion: boolean };
    tweens: { add: ReturnType<typeof vi.fn> };
    cameras: { main: { shake: ReturnType<typeof vi.fn> } };
  };
  await waitFor(() => expect(scene.clock.playing).toBe(true));
  return scene;
}

test("reduced motion: the replay plays key frames only, with no tweens or shaking", async () => {
  const scene = await fightWith(true);
  expect(scene.opts.reducedMotion).toBe(true);
  for (let i = 0; i < 100_000 && scene.clock.playing; i += 1)
    scene.update(0, 50);
  expect(scene.tweens.add).not.toHaveBeenCalled();
  expect(scene.cameras.main.shake).not.toHaveBeenCalled();
  const note = screen.getByText(/key moments only/);
  expect(note.closest('[role="img"]')).toBeNull();
});

test("normal motion: the replay animates", async () => {
  const scene = await fightWith(false);
  expect(scene.opts.reducedMotion).toBe(false);
  expect(screen.queryByText(/key moments only/)).toBeNull();
});

// This one only reads the stylesheet text, so it is a tripwire for someone deleting the global
// rule, not proof that nothing moves. The Phaser tests above are the real reduced-motion guard.
test("the page's own animations are CSS only, so the global reduced-motion rule stops them", () => {
  expect(indexCss).toMatch(
    /@media \(prefers-reduced-motion: reduce\)[\s\S]*animation: none !important/,
  );
  expect(pageCss).toMatch(/animation: pop-in/);
});
