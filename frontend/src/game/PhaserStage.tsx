// The battle replay on the page (D05, D07): loads Phaser only when needed, mounts one game in a box,
// destroys it on unmount, and renders the replay controls and notes in React.
import type Phaser from "phaser";
import { useEffect, useRef, useState } from "react";
import type { Asset, Matchup, SimulationResult } from "../api/client.ts";
import { useFocusRescue } from "../components/focus-rescue.ts";
import { howMany } from "../components/Verdict.tsx";
import type { BattleStage } from "./BattleScene.ts";
import { STAGE, battlefieldUrl, layoutStage, spriteUrls } from "./layout.ts";
import { buildTimeline, type Speed } from "./timeline.ts";
import styles from "./stage.module.css";

export interface PhaserStageProps {
  battleId?: string; // a different battle always starts a fresh replay
  result: SimulationResult;
  matchup: Pick<Matchup, "fighters">;
  assets?: Asset[];
  onEvent?: (index: number) => void; // each replay event index, once, in order (D07 captions)
  onFinish?: () => void; // the replay reached its last event (D07 verdict)
  onReplay?: () => void; // the viewer pressed Replay; events start again from 0
  autoPlay?: boolean; // start playing as soon as the stage is ready
  claimFocus?: () => boolean; // asked once ready: true moves keyboard focus to Play/Pause
  reducedMotion?: boolean; // defaults to the browser's prefers-reduced-motion setting
}

// Whether the viewer asked the browser for less motion.
export const prefersReducedMotion = () =>
  typeof window !== "undefined" &&
  typeof window.matchMedia === "function" &&
  window.matchMedia("(prefers-reduced-motion: reduce)").matches;

type Game = { destroy: (removeCanvas: boolean) => void };
const NO_ASSETS: Asset[] = []; // one shared empty list, so a missing prop never rebuilds the game

// What makes one replay different from another. A refreshed battle record (a late server update,
// the polling fallback) brings new objects with the same values, and must not restart the game.
// The pictures count too: the scene reads them only when it starts, so a viewer who skipped to the
// verdict before the images were made gets a fresh stage with them as soon as they arrive.
export const replayKey = (
  battleId: string | undefined,
  result: SimulationResult,
  fighters: Pick<Matchup, "fighters">["fighters"],
  motionless: boolean,
  assets: readonly Asset[] = NO_ASSETS,
) =>
  JSON.stringify([
    battleId ?? null,
    result.seed,
    result.runs,
    result.outcome,
    result.representative_log.length,
    fighters.map((f) => [f.entity, f.count ?? 1]),
    motionless,
    spriteUrls(assets, fighters),
    battlefieldUrl(assets),
  ]);

export default function PhaserStage({
  battleId,
  result,
  matchup,
  assets = NO_ASSETS,
  onEvent,
  onFinish,
  onReplay,
  autoPlay = false,
  reducedMotion,
  claimFocus,
}: PhaserStageProps) {
  const host = useRef<HTMLDivElement>(null);
  const stage = useRef<BattleStage | null>(null);
  const onEventRef = useRef(onEvent);
  const onFinishRef = useRef(onFinish);
  const claimFocusRef = useRef(claimFocus);
  const playButton = useRef<HTMLButtonElement>(null);
  const replayButton = useRef<HTMLButtonElement>(null);
  const controls = useFocusRescue();
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeedState] = useState<Speed>(1);
  const [done, setDone] = useState(false);
  const [round, setRound] = useState(0); // bumped by Replay to start a fresh game
  const motionless = reducedMotion ?? prefersReducedMotion();

  const { fighters } = matchup;
  const key = replayKey(battleId, result, fighters, motionless, assets);
  // The latest props, read when a game starts; changing them alone never restarts the game.
  const latest = useRef({ result, fighters, assets, motionless, autoPlay });

  // Keep the latest callbacks and props without rebuilding the game when the parent re-renders.
  useEffect(() => {
    onEventRef.current = onEvent;
    onFinishRef.current = onFinish;
    claimFocusRef.current = claimFocus;
    latest.current = { result, fighters, assets, motionless, autoPlay };
  });

  // Load Phaser, start one game, and destroy it on unmount (safe under StrictMode's double mount).
  // It restarts only when the replay itself changes (see replayKey) or the viewer presses Replay.
  useEffect(() => {
    let cancelled = false;
    let game: Game | null = null;
    const { result, fighters, assets, motionless, autoPlay } = latest.current;
    const start = autoPlay || round > 0; // Replay plays right away
    const timeline = buildTimeline(result, [
      fighters[0]?.count ?? 1,
      fighters[1]?.count ?? 1,
    ]);
    (async () => {
      const [phaser, { createBattleScene }] = await Promise.all([
        import("phaser"),
        import("./BattleScene.ts"),
      ]);
      if (cancelled || !host.current) return;
      const P = phaser as unknown as typeof Phaser;
      const BattleScene = createBattleScene(P);
      const scene = new BattleScene({
        timeline,
        layouts: layoutStage(fighters, assets),
        battlefieldUrl: battlefieldUrl(assets),
        outcome: result.outcome,
        reducedMotion: motionless,
        onEvent: (index) => onEventRef.current?.(index),
        onFinish: () => {
          setPlaying(false);
          setDone(true);
          onFinishRef.current?.();
        },
      });
      game = new P.Game({
        type: P.AUTO,
        parent: host.current,
        width: STAGE.width,
        height: STAGE.height,
        backgroundColor: "#0b1026",
        banner: false,
        audio: { noAudio: true },
        scale: { mode: P.Scale.FIT, autoCenter: P.Scale.CENTER_HORIZONTALLY },
        scene: [scene],
      });
      stage.current = scene;
      const empty = timeline.beats.length === 0;
      if (start && !empty) scene.play();
      setPlaying(start && !empty);
      setDone(empty);
      setSpeedState(1);
      setReady(true);
    })().catch(() => {
      if (!cancelled) setFailed(true);
    });
    return () => {
      cancelled = true;
      stage.current = null;
      game?.destroy(true);
      game = null;
    };
  }, [key, round]);

  // Skip to end and the fight's end disable the button in use, and Replay removes itself. When the
  // viewer was on one of them, focus goes to Replay at the end, or to Play/Pause once a game is
  // ready. The page can hand focus over too (claimFocus), when its own button started the fight.
  useEffect(() => {
    if (!ready) return;
    if (done) controls.rescue(replayButton.current);
    else if (!controls.rescue(playButton.current) && claimFocusRef.current?.())
      playButton.current?.focus();
  }, [ready, done, controls]);

  const togglePlay = () => {
    if (!stage.current) return;
    if (playing) stage.current.pause();
    else stage.current.play();
    setPlaying(!playing);
  };
  const changeSpeed = (next: Speed) => {
    stage.current?.setSpeed(next);
    setSpeedState(next);
  };
  const skip = () => stage.current?.skipToEnd();
  const replay = () => {
    setReady(false);
    setDone(false);
    setRound((r) => r + 1);
    onReplay?.();
  };

  const side = (i: 0 | 1) =>
    fighters[i] ? howMany(fighters[i].count ?? 1, fighters[i]) : "?";
  const hasDamage = result.representative_log.some((e) => e.damage != null);
  return (
    <section className={styles.stage} aria-label="Fight replay">
      <div
        ref={host}
        className={styles.canvas}
        role="img"
        aria-label={`Animated fight replay: ${side(0)} versus ${side(1)}. The captions describe each moment.`}
      />
      {motionless && (
        <p className={styles.hint}>
          Reduced motion is on: the replay shows key moments only (the walk-in,
          each knock-out, and the end).
        </p>
      )}
      {!motionless && hasDamage && (
        <p className={styles.hint}>
          Floating minus numbers are damage in relative hit points, straight
          from the simulation log.
        </p>
      )}
      {failed && (
        <p className={styles.note} role="alert">
          The arena cameras are down, so the replay can't play. The results are
          still in.
        </p>
      )}
      <div
        className={styles.controls}
        role="group"
        aria-label="Replay controls"
        onFocus={controls.onFocus}
        onBlur={controls.onBlur}
      >
        <button
          ref={playButton}
          type="button"
          className={styles.button}
          onClick={togglePlay}
          disabled={!ready || done}
        >
          {playing ? "Pause" : "Play"}
        </button>
        {([1, 2] as const).map((s) => (
          <button
            key={s}
            type="button"
            className={styles.button}
            aria-pressed={speed === s}
            aria-label={`${s}× speed`}
            onClick={() => changeSpeed(s)}
            disabled={!ready}
          >
            {s}×
          </button>
        ))}
        <button
          type="button"
          className={styles.button}
          onClick={skip}
          disabled={!ready || done}
        >
          Skip to end
        </button>
        {done && ready && (
          <button
            ref={replayButton}
            type="button"
            className={styles.button}
            onClick={replay}
          >
            Replay
          </button>
        )}
      </div>
    </section>
  );
}
