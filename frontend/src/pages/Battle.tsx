// The broadcast page frame (D02) with the fight replay (D05). The intro card and captions arrive with D07.
import { Link, useParams } from "react-router-dom";
import { NOT_FOUND, useBattle } from "../api/useBattle.ts";
import {
  ErrorPanel,
  LoadingTicker,
  LowerThird,
  srOnly,
} from "../components/Broadcast.tsx";
import PhaserStage from "../game/PhaserStage.tsx";

// A way out of any dead end.
const BackHome = () => (
  <p>
    <Link to="/">Back to the studio</Link>
  </p>
);

export default function Battle() {
  const { id = "" } = useParams();
  const { battle, error } = useBattle(id);

  const failed = battle?.status === "failed";
  const running = battle?.stages.find((s) => s.status === "running");
  const first = battle?.matchup.fighters[0]?.entity ?? "the fighters";
  // One ticker for every state, so its status region stays mounted and only its text changes.
  const tickerMessage = !battle
    ? error
      ? ""
      : "Warming up the studio lights…"
    : battle.status === "running"
      ? (running?.detail ?? `Researching the ${first}…`)
      : "";

  return (
    <main>
      <h1 className={srOnly}>{battle ? battle.matchup.raw_text : "Battle"}</h1>
      {battle && <LowerThird decorative>{battle.matchup.raw_text}</LowerThird>}
      {/* At most one alert: a called-off fight says so, otherwise show the fetch error. */}
      {failed ? (
        <ErrorPanel message="This fight was called off. Try another matchup." />
      ) : (
        error && (
          <ErrorPanel
            title={error === NOT_FOUND ? "Battle not found" : undefined}
            message={error}
          />
        )
      )}
      <LoadingTicker message={tickerMessage} />
      {(failed || (!battle && error)) && <BackHome />}
      {battle?.status === "done" && battle.result && (
        <PhaserStage
          battleId={id}
          result={battle.result}
          matchup={battle.matchup}
          assets={battle.assets}
        />
      )}
      {battle?.status === "done" && (
        <p>
          The verdict is in.{" "}
          <Link to={`/battle/${id}/results`}>See the results</Link>
        </p>
      )}
      {battle && (
        <ol aria-label="Show progress">
          {battle.stages.map((s) => (
            <li key={s.stage}>
              {s.stage}: {s.status}
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
