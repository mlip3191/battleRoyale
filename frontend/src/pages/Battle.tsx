// The broadcast page frame (D02). The intro card, Phaser arena, and captions arrive with D05 and D07.
import { Link, useParams } from "react-router-dom";
import { NOT_FOUND, useBattle } from "../api/useBattle.ts";
import {
  ErrorPanel,
  LoadingTicker,
  LowerThird,
  srOnly,
} from "../components/Broadcast.tsx";

// A way out of any dead end.
const BackHome = () => (
  <p>
    <Link to="/">Back to the studio</Link>
  </p>
);

export default function Battle() {
  const { id = "" } = useParams();
  const { battle, error } = useBattle(id);

  if (!battle) {
    return (
      <main>
        <h1 className={srOnly}>Battle</h1>
        {error ? (
          <>
            <ErrorPanel
              title={error === NOT_FOUND ? "Battle not found" : undefined}
              message={error}
            />
            <BackHome />
          </>
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
      <h1 className={srOnly}>{battle.matchup.raw_text}</h1>
      <LowerThird>{battle.matchup.raw_text}</LowerThird>
      {error && <ErrorPanel message={error} />}
      {battle.status === "running" && (
        <LoadingTicker
          message={running?.detail ?? `Researching the ${first}…`}
        />
      )}
      {battle.status === "failed" && (
        <>
          <ErrorPanel message="This fight was called off. Try another matchup." />
          <BackHome />
        </>
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
