// Verdict helpers (D04): plural names for counts, side names, and the explainer guard.
import { expect, test } from "vitest";
import done from "../fixtures/battle-record-done.json";
import type { BattleRecord } from "../api/client.ts";
import { explainerOf, howMany, pluralOf, sideName } from "./Verdict.tsx";

const record = done as unknown as BattleRecord;
const [bear, wolves] = record.matchup.fighters;

test("pluralOf handles the common English rules and a few irregulars", () => {
  expect(pluralOf("gray wolf")).toBe("gray wolves");
  expect(pluralOf("grizzly bear")).toBe("grizzly bears");
  expect(pluralOf("red fox")).toBe("red foxes");
  expect(pluralOf("honey badger")).toBe("honey badgers");
  expect(pluralOf("butterfly")).toBe("butterflies");
  expect(pluralOf("monkey")).toBe("monkeys");
  expect(pluralOf("moose")).toBe("moose");
  expect(pluralOf("house mouse")).toBe("house mice");
});

test("howMany reuses the plural the user typed, or builds one", () => {
  expect(howMany(4, wolves)).toBe("4 gray wolves");
  expect(howMany(2, bear)).toBe("2 grizzly bears");
  expect(howMany(1, wolves)).toBe("1 gray wolf");
  expect(howMany(12000, bear)).toBe("12,000 grizzly bears");
});

test("sideName uses the display name for one fighter and a count for a group", () => {
  expect(sideName(bear, record.stat_sheets[0])).toBe(
    record.stat_sheets[0].display_name,
  );
  expect(sideName(bear)).toBe(bear.raw);
  expect(sideName(wolves, record.stat_sheets[1])).toBe("6 gray wolves");
});

test("explainerOf hides empty text and the explain=False placeholder", () => {
  const result = record.result!;
  expect(explainerOf(result)).toBe(result.deciding_factor_explainer);
  expect(explainerOf({ ...result, deciding_factor_explainer: " " })).toBeNull();
  expect(
    explainerOf({
      ...result,
      deciding_factor_explainer: "Deciding factor not computed.",
    }),
  ).toBeNull();
});
