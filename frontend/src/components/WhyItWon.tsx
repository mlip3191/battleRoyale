// "Why it won" for the results page (#582): a few plain-language reasons from the stat sheets.
import type { StatSheet } from "../api/client.ts";
import { NO_CLEAR_EDGE, whyItWon } from "./why-it-won.ts";
import styles from "./verdict.module.css";

export default function WhyItWon({
  winnerName,
  winner,
  loser,
}: {
  winnerName: string;
  winner: StatSheet;
  loser: StatSheet;
}) {
  const reasons = whyItWon(winnerName, winner, loser);
  return (
    <section className={styles.card} aria-labelledby="why-title">
      <h2 id="why-title">Why {winnerName} won, in plain words</h2>
      {reasons.length > 0 ? (
        <ul>
          {reasons.map((r) => (
            <li key={r}>{r}</li>
          ))}
        </ul>
      ) : (
        <p>{NO_CLEAR_EDGE}</p>
      )}
      <p className={styles.muted}>
        These come straight from the stat sheets below. Estimates are marked,
        and every source is listed at the bottom of the page.
      </p>
    </section>
  );
}
