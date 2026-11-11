// The broadcast page (D07): the ticker while research and the simulation run, then the intro card
// with captions, the fight replay with play-by-play captions, and the verdict reveal.
// The show's logic lives in broadcast-flow.ts; this file only lays it out.
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { NOT_FOUND, useBattle } from "../api/useBattle.ts";
import AudioBar from "../components/AudioBar.tsx";
import {
  ErrorPanel,
  LoadingTicker,
  LowerThird,
  srOnly,
} from "../components/Broadcast.tsx";
import PhaserStage from "../game/PhaserStage.tsx";
import {
  SPEAKERS,
  START,
  audioPlan,
  canSkip,
  captionsAt,
  lineMs,
  linesOf,
  nextShow,
  placeLines,
  sideNames,
  unavailableNote,
  verdictReveal,
  type ShowAction,
} from "./broadcast-flow.ts";
import type { ScriptLine } from "../api/client.ts";
import styles from "./battle.module.css";

// A way out of any dead end.
const BackHome = () => (
  <p>
    <Link to="/">Back to the studio</Link>
  </p>
);

// The captions box: one live region, always mounted, so screen readers hear each new line.
function Captions({ lines }: { lines: ScriptLine[] }) {
  return (
    <div
      className={styles.captions}
      role="region"
      aria-label="Captions"
      aria-live="polite"
    >
      {lines.map((l, i) => (
        <p key={i}>
          <span className={styles.speaker}>{SPEAKERS[l.speaker]}:</span>{" "}
          {l.text}
        </p>
      ))}
    </div>
  );
}

// A fresh show for every battle id.
export default function Battle() {
  const { id = "" } = useParams();
  return <Broadcast key={id} id={id} />;
}

function Broadcast({ id }: { id: string }) {
  const { battle, error } = useBattle(id);
  const [stored, setShow] = useState(START);
  const [eventIndex, setEventIndex] = useState(-1); // last replay event reached
  const [line, setLine] = useState({ phase: START.phase, index: 0 }); // intro/outro line on screen
  const [captionsPaused, setCaptionsPaused] = useState(false);

  // A newer battle record can start the show; adjust during render, not in an effect.
  const show = nextShow(stored, { type: "update", battle });
  if (show !== stored) setShow(show);
  const act = (action: ShowAction) => setShow((s) => nextShow(s, action));

  // Intro and outro lines step along on a timer; the line count restarts with each phase.
  const timed =
    show.phase === "intro"
      ? linesOf(battle?.scripts ?? [], "intro")
      : show.phase === "verdict"
        ? linesOf(battle?.scripts ?? [], "outro")
        : [];
  const lineIndex = line.phase === show.phase ? line.index : 0;
  const current = timed[lineIndex];
  const isLast = lineIndex >= timed.length - 1;
  useEffect(() => {
    if (!current || captionsPaused || (isLast && show.phase !== "intro"))
      return;
    const timer = setTimeout(() => {
      if (!isLast) setLine({ phase: show.phase, index: lineIndex + 1 });
      else setShow((s) => nextShow(s, { type: "intro-done" }));
    }, lineMs(current.text));
    return () => clearTimeout(timer);
  }, [current, captionsPaused, isLast, lineIndex, show.phase]);

  const failed = battle?.status === "failed";
  const running = battle?.stages.find((s) => s.status === "running");
  const first = battle?.matchup.fighters[0]?.entity ?? "the fighters";
  // One ticker for every state, so its status region stays mounted and only its text changes.
  const tickerMessage = !battle
    ? error
      ? ""
      : "Warming up the studio lights…"
    : battle.status === "running" && show.phase === "waiting"
      ? (running?.detail ?? `Researching the ${first}…`)
      : "";

  const result = battle?.result ?? null;
  const names = battle ? sideNames(battle.matchup, battle.stat_sheets) : [];
  const placed = result
    ? placeLines(
        linesOf(battle?.scripts ?? [], "play_by_play"),
        result.representative_log.length,
      )
    : [];
  const captions =
    show.phase === "fight"
      ? captionsAt(placed, eventIndex)
      : current
        ? [current]
        : [];
  const sound = battle ? audioPlan(battle.assets) : null;
  const note = battle ? unavailableNote(battle.stages) : null;
  const reveal = result && show.revealed ? verdictReveal(result, names) : null;

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
      {note && <p className={styles.note}>{note}</p>}

      {show.phase === "intro" && (
        <section className={styles.titleCard} aria-label="Tonight's matchup">
          <p className={styles.fighter}>{names[0]}</p>
          <p className={styles.vs}>
            <span aria-hidden="true">VS</span>
            <span className={srOnly}>versus</span>
          </p>
          <p className={styles.fighter}>{names[1]}</p>
        </section>
      )}
      {result && (show.phase === "fight" || show.phase === "verdict") && (
        <PhaserStage
          battleId={id}
          result={result}
          matchup={battle!.matchup}
          assets={battle!.assets}
          autoPlay={show.phase === "fight"}
          onEvent={setEventIndex}
          onFinish={() => act({ type: "fight-done" })}
          onReplay={() => {
            setEventIndex(-1);
            act({ type: "replay" });
          }}
        />
      )}

      <Captions lines={captions} />

      <div className={styles.controls}>
        {current && (show.phase === "intro" || !isLast) && (
          <button
            type="button"
            className={styles.button}
            onClick={() => setCaptionsPaused(!captionsPaused)}
          >
            {captionsPaused ? "Resume captions" : "Pause captions"}
          </button>
        )}
        {show.phase === "intro" && (
          <button
            type="button"
            className={styles.button}
            onClick={() => act({ type: "intro-done" })}
          >
            Start the fight
          </button>
        )}
        {canSkip(show, battle) && (
          <button
            type="button"
            className={styles.button}
            onClick={() => act({ type: "skip" })}
          >
            Skip to verdict
          </button>
        )}
      </div>
      {show.phase !== "waiting" && sound && (
        <AudioBar narration={sound.narration} music={sound.music} />
      )}

      {reveal && (
        <section className={styles.verdict} aria-labelledby="reveal-title">
          <h2 id="reveal-title">{reveal.headline}</h2>
          {reveal.odds && <p>{reveal.odds}</p>}
          {reveal.why && <p>{reveal.why}</p>}
          <Link className={styles.results} to={`/battle/${id}/results`}>
            See the full results
          </Link>
        </section>
      )}
      {battle?.status === "done" && !result && (
        <p>
          The verdict is in.{" "}
          <Link to={`/battle/${id}/results`}>See the results</Link>
        </p>
      )}
      {battle && (
        <ol aria-label="Show progress" className={styles.progress}>
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
