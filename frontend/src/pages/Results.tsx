// The results page (D04): the verdict, each fighter's stat sheet with sources, the fair fight,
// the next challenger, and every source used. Every number on it comes from the battle record.
import { Link, useParams } from "react-router-dom";
import { NOT_FOUND, useBattle } from "../api/useBattle.ts";
import {
  ErrorPanel,
  LoadingTicker,
  LowerThird,
} from "../components/Broadcast.tsx";
import { SourceList, StatSheetCard } from "../components/StatSheet.tsx";
import {
  FairFightCard,
  NextChallengerCard,
  sideName,
  VerdictBanner,
  winnerOf,
} from "../components/Verdict.tsx";

export default function Results() {
  const { id = "" } = useParams();
  const { battle, error } = useBattle(id);
  const result = battle?.result;
  // Sheets come one per side, in side order.
  const names =
    battle?.matchup.fighters.map((f, i) =>
      sideName(f, battle.stat_sheets[i]),
    ) ?? [];
  const waiting = !error && (!battle || battle.status === "running");
  // Only a fight with a winner has a champ for the next challenger to face.
  const winner = result ? winnerOf(result) : null;

  return (
    <main>
      <LowerThird decorative>Tale of the tape</LowerThird>
      <h1>Results{battle && `: ${battle.matchup.raw_text}`}</h1>
      {battle?.status === "failed" ? (
        <ErrorPanel message="This fight was called off. Try another matchup." />
      ) : (
        error && (
          <ErrorPanel
            title={error === NOT_FOUND ? "Battle not found" : undefined}
            message={error}
          />
        )
      )}
      <LoadingTicker message={waiting ? "Tallying the scorecards…" : ""} />
      {result && <VerdictBanner result={result} names={names} />}
      {battle?.status === "done" && !result && (
        <ErrorPanel
          title="No verdict"
          message="The fight finished, but its result is missing. Try running the matchup again."
        />
      )}
      {battle && battle.stat_sheets.length > 0 && (
        <section aria-labelledby="tape-title">
          <h2 id="tape-title">Tale of the tape</h2>
          {battle.stat_sheets.map((sheet) => (
            <StatSheetCard key={sheet.fighter_id} sheet={sheet} />
          ))}
        </section>
      )}
      {/* A no-contest has no fair count to find (the sides can't engage). */}
      {battle?.fair_fight && result?.outcome !== "no_contest" && (
        <FairFightCard fairFight={battle.fair_fight} matchup={battle.matchup} />
      )}
      {battle?.challenger && winner !== null && (
        <NextChallengerCard
          challenger={battle.challenger}
          matchup={battle.matchup}
          winner={winner}
        />
      )}
      {battle && battle.stat_sheets.length > 0 && (
        <SourceList sheets={battle.stat_sheets} />
      )}
      <p>
        <Link to={`/battle/${id}`}>Back to the broadcast</Link>
      </p>
    </main>
  );
}
