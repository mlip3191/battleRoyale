// The broadcast page (D07): the ticker while research and the simulation run, then the intro card
// with captions, the fight replay with play-by-play captions, and the verdict reveal.
// The show's logic lives in broadcast-flow.ts; this file only lays it out.
import { useEffect, useRef, useState, type Ref } from "react";
import { Link, useParams } from "react-router-dom";
import { NOT_FOUND, useBattle } from "../api/useBattle.ts";
import AudioBar, { type AudioBarHandle } from "../components/AudioBar.tsx";
import {
  ErrorPanel,
  LoadingTicker,
  LowerThird,
  MAIN_ID,
  srOnly,
} from "../components/Broadcast.tsx";
import { useFocusRescue } from "../components/focus-rescue.ts";
import { usePageTitle } from "../components/page-title.ts";
import PhaserStage from "../game/PhaserStage.tsx";
import type { Speed } from "../game/timeline.ts";
import {
  FIGHT_VOICE_WAIT_MS,
  SPEAKERS,
  START,
  audioPlan,
  canSkip,
  captionsAt,
  holdingUp,
  lineMs,
  linesOf,
  nextShow,
  placeLines,
  sideNames,
  shownStage,
  tooFastToTalk,
  unavailableNote,
  voiceCue,
  verdictReveal,
  type AudioPlan,
  type Show,
  type ShowAction,
} from "./broadcast-flow.ts";
import { calledOff } from "./failure-reason.ts";
import type { ScriptLine } from "../api/client.ts";
import styles from "./battle.module.css";

// A way out of any dead end.
const BackHome = ({ linkRef }: { linkRef: Ref<HTMLAnchorElement> }) => (
  <p>
    <Link ref={linkRef} to="/">
      Back to the studio
    </Link>
  </p>
);

// What the ticker says while a stage is running and has no detail of its own (#493): the audio
// stage can take about a minute with the cloned voice, so it must not read "Researching…". The
// show waits only for the intro's voice (#592), so a first-time viewer is told what comes next
// (#579). Kept short: a longer message crawls faster across the ticker.
const RECORDING_ANNOUNCER =
  "Recording the announcer… the show starts as soon as the intro is ready.";
// What the ticker says while the intro's card holds for the fight's voice (#592).
const RECORDING_FIGHT =
  "Recording the play-by-play… the fight starts in a moment.";
// What it says while only the pictures hold up the show (#592).
const DRAWING_PICTURES =
  "Drawing the fighters… the show starts as soon as the pictures are ready.";
function stageTicker(stage: string | undefined, first: string): string {
  if (stage === "audio") return RECORDING_ANNOUNCER;
  return stage === "images" ? DRAWING_PICTURES : `Researching the ${first}…`;
}

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
  // The heading names the matchup once it loads; the tab title says the same.
  const heading = battle ? battle.matchup.raw_text : "Battle";
  usePageTitle(heading);
  const [stored, setShow] = useState(START);
  const [eventIndex, setEventIndex] = useState(-1); // last replay event reached
  const [line, setLine] = useState({ phase: START.phase, index: 0 }); // intro/outro line on screen
  // The part of the show whose captions the viewer paused. Every step of the show is a new object,
  // so a pause belongs to one part only: the outro never starts out paused from the intro.
  const [pausedIn, setPausedIn] = useState<Show | null>(null);
  const [fightSpeed, setFightSpeed] = useState<Speed>(1); // the replay's speed button (#577)
  const [fightMoving, setFightMoving] = useState(false); // the replay is playing (#576)
  // The replay reached its last moment and the announcer is finishing what it is saying; the
  // verdict follows when it is done, or after a short wait at most (#601).
  const [finishing, setFinishing] = useState(false);
  const controls = useFocusRescue();
  const startButton = useRef<HTMLButtonElement>(null);
  const soundBar = useRef<AudioBarHandle>(null);
  const verdictTitle = useRef<HTMLHeadingElement>(null);
  const backHome = useRef<HTMLAnchorElement>(null);

  // A newer battle record can start the show; adjust during render, not in an effect.
  const show = nextShow(stored, { type: "update", battle });
  if (show !== stored) setShow(show);
  const act = (action: ShowAction) => setShow((s) => nextShow(s, action));
  const captionsPaused = pausedIn === show;
  // The latest record, for the intro's line timer: a fresh record must not restart that timer.
  const latest = useRef(battle);
  useEffect(() => {
    latest.current = battle;
  });
  // Each part of the show keeps the sound it started with: a voice file that lands later, while
  // the rest of the announcer is recorded, waits for the next part or a replay (#592, D07).
  const [heard, setHeard] = useState<{ show: Show; plan: AudioPlan | null }>({
    show: START,
    plan: null,
  });
  if (battle && heard.show !== show)
    setHeard({ show, plan: audioPlan(battle.assets, show.phase) });

  // The fight waits for its voice only so long, then starts with captions (#592).
  useEffect(() => {
    if (show.phase !== "standby") return;
    const late = () => setShow((s) => nextShow(s, { type: "voice-late" }));
    const timer = setTimeout(late, FIGHT_VOICE_WAIT_MS);
    return () => clearTimeout(timer);
  }, [show.phase]);

  // The show's buttons (and the ticker's Pause button) go away as it moves on. If the viewer was
  // on one, focus goes to the new part of the show: the verdict's heading, or Start the fight. In
  // the fight the stage takes it, on its Play/Pause button once ready (claimFocus below). A fight
  // called off under the ticker sends it to the way home. Focus elsewhere on the page, or given
  // up by a click on a blank part of it, is left alone.
  const failed = battle?.status === "failed";
  useEffect(() => {
    if (show.phase === "verdict") controls.rescue(verdictTitle.current);
    else if (show.phase === "intro") controls.rescue(startButton.current);
    else if (failed) controls.rescue(backHome.current);
  });

  // Intro and outro lines step along on a timer; the line count restarts with each phase.
  // The last intro line hands over to the fight; the last outro line simply stays up.
  const timed =
    show.phase === "intro"
      ? linesOf(battle?.scripts ?? [], "intro")
      : show.phase === "verdict"
        ? linesOf(battle?.scripts ?? [], "outro")
        : [];
  const lineIndex = line.phase === show.phase ? line.index : 0;
  const current = timed[lineIndex];
  const isLast = lineIndex >= timed.length - 1;
  // The line's text, not the line: each refresh of the record brings new line objects, and the
  // timer must not start over on every one (#592).
  const text = current?.text;
  useEffect(() => {
    if (text === undefined || captionsPaused) return;
    if (isLast && show.phase !== "intro") return;
    const timer = setTimeout(() => {
      if (!isLast) setLine({ phase: show.phase, index: lineIndex + 1 });
      else
        setShow((s) =>
          nextShow(s, { type: "intro-done", battle: latest.current }),
        );
    }, lineMs(text));
    return () => clearTimeout(timer);
  }, [text, captionsPaused, isLast, lineIndex, show.phase]);

  const running = battle ? holdingUp(battle) : undefined;
  const first = battle?.matchup.fighters[0]?.entity ?? "the fighters";
  // One ticker for every state, so its status region stays mounted and only its text changes.
  const tickerMessage = !battle
    ? error
      ? ""
      : "Warming up the studio lights…"
    : show.phase === "standby"
      ? RECORDING_FIGHT
      : battle.status === "running" && show.phase === "waiting"
        ? (running?.detail ?? stageTicker(running?.stage, first))
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
  const sound = heard.show === show ? heard.plan : null;
  // During the fight the announcer follows the replay (#576): each moment's lines play when the
  // replay reaches them, and it waits while the replay is paused or too fast to talk over (#577).
  const fighting = show.phase === "fight";
  const tooFast = tooFastToTalk(fightSpeed);
  const cue =
    fighting && sound?.lineTimes
      ? voiceCue(placed, eventIndex, sound.lineTimes)
      : undefined;
  const note = battle ? unavailableNote(battle.stages) : null;
  const reveal = result && show.revealed ? verdictReveal(result, names) : null;

  return (
    <main id={MAIN_ID} tabIndex={-1}>
      <h1 className={srOnly}>{heading}</h1>
      {battle && <LowerThird decorative>{battle.matchup.raw_text}</LowerThird>}
      {/* At most one alert: a called-off fight says so, otherwise show the fetch error. */}
      {failed ? (
        <ErrorPanel {...calledOff(battle.stages)} />
      ) : (
        error && (
          <ErrorPanel
            title={error === NOT_FOUND ? "Battle not found" : undefined}
            message={error}
          />
        )
      )}
      <LoadingTicker message={tickerMessage} focusGroup={controls} />
      {(failed || (!battle && error)) && <BackHome linkRef={backHome} />}
      {note && <p className={styles.note}>{note}</p>}

      {(show.phase === "intro" || show.phase === "standby") && (
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
          claimFocus={controls.claim}
          onEvent={setEventIndex}
          onSpeedChange={setFightSpeed}
          onPlayingChange={setFightMoving}
          onFinish={(skipped) => {
            // The verdict waits for the announcer's last lines, unless there is no voice in sync with
            // the fight to wait for, or the viewer jumped to the end (#601).
            if (skipped || !sound?.lineTimes) act({ type: "fight-done" });
            else setFinishing(true);
          }}
          onReplay={() => {
            setFinishing(false);
            setEventIndex(-1);
            act({ type: "replay" });
          }}
        />
      )}

      <Captions lines={captions} />

      <div
        className={styles.controls}
        onFocus={controls.onFocus}
        onBlur={controls.onBlur}
      >
        {current && (show.phase === "intro" || !isLast) && (
          <button
            type="button"
            className={styles.button}
            onClick={() => setPausedIn(captionsPaused ? null : show)}
          >
            {captionsPaused ? "Resume captions" : "Pause captions"}
          </button>
        )}
        {show.phase === "intro" && (
          <button
            ref={startButton}
            type="button"
            className={styles.button}
            onClick={() => {
              // Inside this click, so browsers that only allow sound a click started (Safari)
              // let the announcer speak when the fight reaches its first line (#579, #584).
              soundBar.current?.unlock();
              act({ type: "intro-done", battle });
            }}
          >
            Start the fight
          </button>
        )}
        {canSkip(show, battle) && (
          <button
            type="button"
            className={styles.button}
            onClick={() => {
              setFinishing(false);
              act({ type: "skip" });
            }}
          >
            Skip to verdict
          </button>
        )}
      </div>
      {show.phase !== "waiting" && sound && (
        <AudioBar
          ref={soundBar}
          narration={sound.narration}
          music={sound.music}
          startSound={show.phase === "fight" || show.phase === "verdict"}
          // The replay stops moving when it ends; that is not a pause, so the announcer keeps
          // saying its closing lines instead of being held mid-line (#601).
          hold={fighting && (tooFast || (!fightMoving && !finishing))}
          holdNote={tooFast ? undefined : "Announcer paused with the fight"}
          cue={cue}
          rate={fighting ? fightSpeed : 1}
          finishing={fighting && finishing}
          onSettled={() => {
            setFinishing(false);
            act({ type: "fight-done" });
          }}
        />
      )}

      {reveal && (
        <section className={styles.verdict} aria-labelledby="reveal-title">
          <h2 id="reveal-title" ref={verdictTitle} tabIndex={-1}>
            {reveal.headline}
          </h2>
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
          {battle.stages.filter(shownStage).map((s) => (
            <li key={s.stage}>
              {s.stage}: {s.status}
            </li>
          ))}
        </ol>
      )}
    </main>
  );
}
