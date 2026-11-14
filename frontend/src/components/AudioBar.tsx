// The broadcast's sound controls (D07): play/pause, mute, and volume for the narration and music.
// Sound never starts on its own (browsers block it, and captions carry the show); the viewer opts in,
// and once on, the sound follows the show from part to part until they pause it.
import { useEffect, useRef, useState } from "react";
import styles from "./audio-bar.module.css";

export interface AudioBarProps {
  narration: string | null; // the announcer's voice track, if one can be played
  music: string | null; // the background music, if any
}

const MUSIC_UNDER_VOICE = 0.4; // music sits under the announcer when both play

// The tracks that are on the page.
const present = (tracks: (HTMLAudioElement | null)[]) =>
  tracks.filter((t): t is HTMLAudioElement => t !== null);

// Start tracks together; true once the browser really plays one. A refused track stays quiet.
const startAll = async (tracks: HTMLAudioElement[]) => {
  const starts = tracks.map((t) => Promise.resolve().then(() => t.play()));
  const results = await Promise.allSettled(starts);
  return results.some((r) => r.status === "fulfilled");
};

export default function AudioBar({ narration, music }: AudioBarProps) {
  const voice = useRef<HTMLAudioElement>(null);
  const song = useRef<HTMLAudioElement>(null);
  const soundOn = useRef(false); // the viewer pressed Play sound, and not Pause sound since
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

  // The tracks change with the part of the show (each part has its own announcer file). The old
  // ones stop. If the viewer turned the sound on, the new ones carry on: the next announcer file
  // from its start, the music where it was; with nothing left to play, the button goes back to
  // "Play sound". Sound the viewer never turned on (or paused) stays off. Leaving the page stops
  // everything. (React has already let go of the elements when the cleanup runs, so it can't read
  // the refs then; the tracks are picked up again whenever they change.)
  useEffect(() => {
    const tracks = present([voice.current, song.current]);
    if (soundOn.current) void startAll(tracks).then(setPlaying);
    return () => tracks.forEach((t) => !t.paused && t.pause());
  }, [narration, music]);

  if (!narration && !music) return null;

  // The tracks on the page right now.
  const tracks = () => present([voice.current, song.current]);

  // Start or stop every track together. The button says "Pause sound" only once the browser
  // really plays something.
  const toggle = () => {
    if (playing) {
      tracks().forEach((t) => t.pause());
      soundOn.current = false;
      setPlaying(false);
      return;
    }
    void startAll(tracks()).then((on) => {
      soundOn.current = on;
      setPlaying(on);
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
