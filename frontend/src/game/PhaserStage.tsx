// The battle replay on the page (D05): loads Phaser only when needed, mounts one game in a box,
// destroys it on unmount, and renders the replay controls in React.
import type Phaser from "phaser";
import { useEffect, useRef, useState } from "react";
import type { Asset, Matchup, SimulationResult } from "../api/client.ts";
import type { BattleStage } from "./BattleScene.ts";
import { STAGE, battlefieldUrl, layoutStage } from "./layout.ts";
import { buildTimeline, type Speed } from "./timeline.ts";
import styles from "./stage.module.css";

export interface PhaserStageProps {
  battleId?: string; // a different battle always starts a fresh replay
  result: SimulationResult;
  matchup: Pick<Matchup, "fighters">;
  assets?: Asset[];
  onEvent?: (index: number) => void; // each replay event index, once, in order (D07 captions)
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
export const replayKey = (
  battleId: string | undefined,
  result: SimulationResult,
  fighters: Pick<Matchup, "fighters">["fighters"],
  motionless: boolean,
) =>
  JSON.stringify([
    battleId ?? null,
    result.seed,
    result.runs,
    result.outcome,
    result.representative_log.length,
    fighters.map((f) => [f.entity, f.count ?? 1]),
    motionless,
  ]);

export default function PhaserStage({
  battleId,
  result,
  matchup,
  assets = NO_ASSETS,
  onEvent,
  reducedMotion,
}: PhaserStageProps) {
  const host = useRef<HTMLDivElement>(null);
  const stage = useRef<BattleStage | null>(null);
  const onEventRef = useRef(onEvent);
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [playing, setPlaying] = useState(false);
  const [speed, setSpeedState] = useState<Speed>(1);
  const [done, setDone] = useState(false);
  const motionless = reducedMotion ?? prefersReducedMotion();

  const { fighters } = matchup;
  const key = replayKey(battleId, result, fighters, motionless);
  // The latest props, read when a game starts; changing them alone never restarts the game.
  const latest = useRef({ result, fighters, assets, motionless });

  // Keep the latest callback and props without rebuilding the game when the parent re-renders.
  useEffect(() => {
    onEventRef.current = onEvent;
    latest.current = { result, fighters, assets, motionless };
  });

  // Load Phaser, start one game, and destroy it on unmount (safe under StrictMode's double mount).
  // It restarts only when the replay itself changes (see replayKey).
  useEffect(() => {
    let cancelled = false;
    let game: Game | null = null;
    const { result, fighters, assets, motionless } = latest.current;
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
      setPlaying(false);
      setDone(timeline.beats.length === 0);
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
  }, [key]);

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

  const names = `${fighters[0]?.entity ?? "?"} versus ${fighters[1]?.entity ?? "?"}`;
  return (
    <section className={styles.stage} aria-label="Fight replay">
      <div
        ref={host}
        className={styles.canvas}
        role="img"
        aria-label={`Animated replay of ${names}`}
      />
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
      >
        <button
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
      </div>
    </section>
  );
}
