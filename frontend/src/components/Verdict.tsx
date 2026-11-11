// The verdict pieces for the results page (D04): who won, the fair fight, and the next challenger.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createBattle,
  type ChallengerSuggestion,
  type FairFight,
  type Matchup,
  type SimulationResult,
  type StatSheet,
} from "../api/client.ts";
import { ErrorPanel, srOnly } from "./Broadcast.tsx";
import styles from "./verdict.module.css";

// A probability as a whole percent, e.g. 0.62 -> "62%".
const pct = (p: number) => `${Math.round(p * 100)}%`;

// One side's win chance with its 95% interval, labeled, e.g. "62% - range 58-66%".
export const winRange = (result: SimulationResult, side: 0 | 1) => {
  const [low, high] = result.win_prob_ci95[side];
  return `${pct(result.win_prob[side])} - range ${Math.round(low * 100)}-${pct(high)}`;
};

// The explainer an explain=False run leaves behind; the guide says never to show it.
export const PLACEHOLDER_EXPLAINER = "Deciding factor not computed.";

// The engine's "why" sentence, or null when it is empty or only the placeholder.
export const explainerOf = (result: SimulationResult) => {
  const text = result.deciding_factor_explainer.trim();
  return text && text !== PLACEHOLDER_EXPLAINER ? text : null;
};

type Fighter = Matchup["fighters"][number];

// Plurals that don't just add "s"; anything else follows the rules in pluralOf.
const IRREGULAR: Record<string, string> = {
  bison: "bison",
  deer: "deer",
  fish: "fish",
  goose: "geese",
  moose: "moose",
  mouse: "mice",
  ox: "oxen",
  sheep: "sheep",
};

// "gray wolf" -> "gray wolves", "fox" -> "foxes", "moose" -> "moose" (last word only).
export function pluralOf(name: string) {
  const [, head, last] = /^(.*?)(\S+)$/.exec(name) ?? ["", "", name];
  const word = IRREGULAR[last.toLowerCase()];
  if (word) return head + word;
  if (/(s|x|z|sh|ch)$/i.test(last)) return `${head}${last}es`;
  if (/[^aeiou]y$/i.test(last)) return `${head}${last.slice(0, -1)}ies`;
  if (/lf$/i.test(last)) return `${head}${last.slice(0, -1)}ves`;
  return `${head}${last}s`;
}

// "4 gray wolves": a count of one fighter, reusing the plural the user typed when there is one.
export function howMany(count: number, fighter: Fighter) {
  if (count === 1) return `1 ${fighter.entity}`;
  const typed =
    fighter.count > 1 ? /^\d+\s+(.+)$/.exec(fighter.raw)?.[1] : null;
  return `${count.toLocaleString("en-US")} ${typed ?? pluralOf(fighter.entity)}`;
}

// A side's name: the stat sheet's display name for a single fighter, "6 gray wolves" for a group.
export const sideName = (fighter: Fighter, sheet?: StatSheet) =>
  fighter.count > 1
    ? howMany(fighter.count, fighter)
    : (sheet?.display_name ?? fighter.raw);

// An average over many runs, to one decimal place, e.g. 2.738 -> "2.7".
export const average = (value: number) =>
  value.toLocaleString("en-US", { maximumFractionDigits: 1 });

// The side that won, or null for a draw or no contest.
export const winnerOf = (result: SimulationResult) =>
  result.outcome === "win_0" ? 0 : result.outcome === "win_1" ? 1 : null;

// The big headline, the odds per side, and why it went that way.
export function VerdictBanner({
  result,
  names,
}: {
  result: SimulationResult;
  names: string[];
}) {
  const winner = winnerOf(result);
  const explainer = explainerOf(result);
  const headline =
    winner !== null
      ? `Winner: ${names[winner]}`
      : result.outcome === "draw"
        ? "It's a draw"
        : "No contest";
  return (
    <section
      className={`${styles.card} ${styles.verdict}`}
      aria-labelledby="verdict-title"
    >
      <h2 id="verdict-title">{headline}</h2>
      {result.outcome !== "no_contest" && (
        <dl className={styles.odds}>
          {([0, 1] as const).map((side) => (
            <div key={side}>
              <dt>{names[side]}</dt>
              <dd className={styles.value}>{winRange(result, side)}</dd>
              <dd className={styles.muted}>
                about {average(result.mean_survivors[side])} left standing on
                average
              </dd>
            </div>
          ))}
          <div>
            <dt>Draw</dt>
            <dd className={styles.value}>{pct(result.draw_prob)}</dd>
          </div>
        </dl>
      )}
      {result.outcome !== "no_contest" && (
        <p className={styles.muted}>
          Fights last about {average(result.mean_duration_s)} s on average.
        </p>
      )}
      {explainer && (
        <p>
          <strong>Deciding factor:</strong> {explainer}
        </p>
      )}
      <p className={styles.muted}>
        Based on {result.runs.toLocaleString("en-US")} simulated fights.
      </p>
    </section>
  );
}

// How many it takes to make it a coin flip, or why no count can.
export function FairFightCard({
  fairFight,
  matchup,
}: {
  fairFight: FairFight;
  matchup: Matchup;
}) {
  const { count, win_prob_at_count: chance } = fairFight;
  const fighter = matchup.fighters[fairFight.varied_side];
  return (
    <section className={styles.card} aria-labelledby="fair-title">
      <h2 id="fair-title">{count === null ? "No fair fight" : "Fair fight"}</h2>
      <p>{fairFight.message}</p>
      {count !== null && fighter && (
        <p className={styles.muted}>
          Tested with {howMany(count, fighter)}
          {chance !== null && `: ${pct(chance)} win chance`}.
        </p>
      )}
    </section>
  );
}

// A new matchup: the winner, as it was, against the suggested challenger.
export const rematch = (
  matchup: Matchup,
  winner: 0 | 1,
  entity: string,
): Matchup => ({
  fighters: [
    matchup.fighters[winner],
    { entity, count: 1, variant: null, size_reference: null, raw: entity },
  ],
  terrain: matchup.terrain,
  raw_text: `${matchup.fighters[winner].raw} vs ${entity}`,
  assumptions: [],
});

// Who the winner should face next, with a button that books that fight.
export function NextChallengerCard({
  challenger,
  matchup,
  winner,
}: {
  challenger: ChallengerSuggestion;
  matchup: Matchup;
  winner: 0 | 1;
}) {
  const [starting, setStarting] = useState(false);
  const [failed, setFailed] = useState(false);
  const navigate = useNavigate();

  const fight = (side: 0 | 1) => {
    setStarting(true);
    setFailed(false);
    createBattle(rematch(matchup, side, challenger.entity))
      .then(({ battle_id }) => navigate(`/battle/${battle_id}`))
      .catch(() => {
        setStarting(false);
        setFailed(true);
      });
  };

  return (
    <section className={styles.card} aria-labelledby="next-title">
      <h2 id="next-title">Next challenger: {challenger.entity}</h2>
      <p>{challenger.reason}</p>
      <p className={styles.muted}>
        It won {pct(challenger.tested_win_prob)} of our one-on-one test fights
        against the champ.
      </p>
      {failed && (
        <ErrorPanel message="We couldn't book that fight. Check your connection and try again." />
      )}
      <button
        type="button"
        className={styles.fight}
        onClick={() => fight(winner)}
        disabled={starting}
      >
        {starting ? "Ringing the bell…" : "Fight them!"}
      </button>
      <p role="status" aria-live="polite" className={srOnly}>
        {starting ? "Ringing the bell… booking the fight." : ""}
      </p>
    </section>
  );
}
