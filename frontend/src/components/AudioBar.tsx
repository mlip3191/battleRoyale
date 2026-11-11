// The broadcast's sound controls (D07): play/pause, mute, and volume for the narration and music.
// Sound never starts on its own (browsers block it, and captions carry the show); the viewer opts in.
import { useEffect, useRef, useState } from "react";
import styles from "./audio-bar.module.css";

export interface AudioBarProps {
  narration: string | null; // the announcer's voice track, if one can be played
  music: string | null; // the background music, if any
}

const MUSIC_UNDER_VOICE = 0.4; // music sits under the announcer when both play

export default function AudioBar({ narration, music }: AudioBarProps) {
  const voice = useRef<HTMLAudioElement>(null);
  const song = useRef<HTMLAudioElement>(null);
  const [playing, setPlaying] = useState(false);
  const [muted, setMuted] = useState(false);
  const [volume, setVolume] = useState(80); // percent

  // Apply mute and volume to both tracks whenever they change.
  useEffect(() => {
    const level = volume / 100;
    if (voice.current) {
      voice.current.muted = muted;
      voice.current.volume = level;
    }
    if (song.current) {
      song.current.muted = muted;
      song.current.volume = narration ? level * MUSIC_UNDER_VOICE : level;
    }
  }, [muted, volume, narration]);

  // Stop the sound when the bar goes away (leaving the page). The tracks are picked up again
  // whenever they change, so ones that arrive after the bar appears are stopped too. (React has
  // already let go of the elements when this cleanup runs, so it can't read the refs then.)
  useEffect(() => {
    const tracks = [voice.current, song.current];
    return () => tracks.forEach((t) => t && !t.paused && t.pause());
  }, [narration, music]);

  if (!narration && !music) return null;

  // The tracks on the page right now.
  const tracks = () =>
    [voice.current, song.current].filter(
      (t): t is HTMLAudioElement => t !== null,
    );

  // Start or stop every track together. The button says "Pause sound" only once the browser
  // really plays something; a track it refuses to play just stays quiet.
  const toggle = () => {
    if (playing) {
      tracks().forEach((t) => t.pause());
      setPlaying(false);
      return;
    }
    const starts = tracks().map((t) => Promise.resolve().then(() => t.play()));
    void Promise.allSettled(starts).then((results) => {
      if (results.some((r) => r.status === "fulfilled")) setPlaying(true);
    });
  };

  // A track that ends (the announcer is done) leaves the button on Play once nothing is left playing.
  const onEnded = () => setPlaying(tracks().some((t) => !t.paused && !t.ended));

  return (
    <div className={styles.bar} role="group" aria-label="Sound controls">
      {narration && (
        <audio ref={voice} src={narration} preload="none" onEnded={onEnded} />
      )}
      {music && (
        <audio ref={song} src={music} preload="none" loop onEnded={onEnded} />
      )}
      <button type="button" className={styles.button} onClick={toggle}>
        {playing ? "Pause sound" : "Play sound"}
      </button>
      <button
        type="button"
        className={styles.button}
        aria-pressed={muted}
        onClick={() => setMuted(!muted)}
      >
        Mute
      </button>
      <label className={styles.volume}>
        Volume
        <input
          type="range"
          min={0}
          max={100}
          step={5}
          value={volume}
          onChange={(e) => setVolume(Number(e.target.value))}
        />
      </label>
      <span className={styles.what}>
        {narration && music
          ? "Announcer and music"
          : narration
            ? "Announcer only"
            : "Music only"}
      </span>
    </div>
  );
}
