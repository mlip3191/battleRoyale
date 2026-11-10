// The verdict pieces for the results page (D04): who won, the fair fight, and the next challenger.
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  createBattle,
  type ChallengerSuggestion,
  type FairFight,
  type Matchup,
  type SimulationResult,
} from "../api/client.ts";
import { ErrorPanel } from "./Broadcast.tsx";
import styles from "./verdict.module.css";

// A probability as a whole percent, e.g. 0.62 -> "62%".
const pct = (p: number) => `${Math.round(p * 100)}%`;

// One side's win chance with its 95% interval, e.g. "62% (58–66%)".
export const winRange = (result: SimulationResult, side: 0 | 1) => {
  const [low, high] = result.win_prob_ci95[side];
  return `${pct(result.win_prob[side])} (${Math.round(low * 100)}–${pct(high)})`;
};

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
                {result.mean_survivors[side].toLocaleString("en-US")} left
                standing on average
              </dd>
            </div>
          ))}
          <div>
            <dt>Draw</dt>
            <dd className={styles.value}>{pct(result.draw_prob)}</dd>
            <dd className={styles.muted}>
              fights last {result.mean_duration_s.toLocaleString("en-US")} s on
              average
            </dd>
          </div>
        </dl>
      )}
      <p>
        <strong>Deciding factor:</strong> {result.deciding_factor_explainer}
      </p>
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
  const entity = matchup.fighters[fairFight.varied_side]?.entity;
  return (
    <section className={styles.card} aria-labelledby="fair-title">
      <h2 id="fair-title">{count === null ? "No fair fight" : "Fair fight"}</h2>
      <p>{fairFight.message}</p>
      {count !== null && (
        <p className={styles.muted}>
          Tested with {count.toLocaleString("en-US")} × {entity}
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
  winner: 0 | 1 | null;
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
        It won {pct(challenger.tested_win_prob)} of our test fights against the
        champ.
      </p>
      {failed && (
        <ErrorPanel message="We couldn't book that fight. Check your connection and try again." />
      )}
      {winner !== null && (
        <button
          type="button"
          className={styles.fight}
          onClick={() => fight(winner)}
          disabled={starting}
        >
          {starting ? "Ringing the bell…" : "Fight them!"}
        </button>
      )}
    </section>
  );
}
