// The broadcast page frame (D02). The intro card, Phaser arena, and captions arrive with D05 and D07.
import { Link, useParams } from "react-router-dom";
import { useBattle } from "../api/useBattle.ts";
import {
  ErrorPanel,
  LoadingTicker,
  LowerThird,
} from "../components/Broadcast.tsx";

export default function Battle() {
  const { id = "" } = useParams();
  const { battle, error } = useBattle(id);

  if (!battle) {
    return (
      <main>
        {error ? (
          <ErrorPanel message={error} />
        ) : (
          <LoadingTicker message="Warming up the studio lights…" />
        )}
      </main>
    );
  }

  const running = battle.stages.find((s) => s.status === "running");
  const first = battle.matchup.fighters[0]?.entity ?? "the fighters";
  return (
    <main>
      <LowerThird>{battle.matchup.raw_text}</LowerThird>
      {error && <ErrorPanel message={error} />}
      {battle.status === "running" && (
        <LoadingTicker
          message={running?.detail ?? `Researching the ${first}…`}
        />
      )}
      {battle.status === "failed" && (
        <ErrorPanel message="This fight was called off. Try another matchup." />
      )}
      {battle.status === "done" && (
        <p>
          The verdict is in.{" "}
          <Link to={`/battle/${id}/results`}>See the results</Link>
        </p>
      )}
      <ol aria-label="Show progress">
        {battle.stages.map((s) => (
          <li key={s.stage}>
            {s.stage}: {s.status}
          </li>
        ))}
      </ol>
    </main>
  );
}
