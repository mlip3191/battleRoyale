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

  // Stop the sound when the bar goes away (leaving the page).
  useEffect(() => {
    const tracks = [voice.current, song.current];
    return () => tracks.forEach((t) => t && !t.paused && t.pause());
  }, []);

  if (!narration && !music) return null;

  // Start or stop every track together; a track the browser refuses to play just stays quiet.
  const toggle = () => {
    const tracks = [voice.current, song.current].filter(
      (t): t is HTMLAudioElement => t !== null,
    );
    if (playing) tracks.forEach((t) => t.pause());
    else tracks.forEach((t) => void t.play()?.catch(() => undefined));
    setPlaying(!playing);
  };

  return (
    <div className={styles.bar} role="group" aria-label="Sound controls">
      {narration && <audio ref={voice} src={narration} preload="none" />}
      {music && <audio ref={song} src={music} preload="none" loop />}
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
