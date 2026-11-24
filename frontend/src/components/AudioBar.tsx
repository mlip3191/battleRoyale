// The broadcast's sound controls (D07, #499): a Sound on/off switch and volume for the narration and
// music. Sound turns on when the viewer starts the fight (a click, so browsers allow it) unless they
// switched it off before (remembered in this browser); once on, it follows the show from part to
// part until they switch it off. Captions carry the show whenever sound can't play.
import { useEffect, useRef, useState } from "react";
import styles from "./audio-bar.module.css";

export interface AudioBarProps {
  narration: string | null; // the announcer's voice track, if one can be played
  music: string | null; // the background music, if any
  startSound?: boolean; // the viewer started the fight: turn the sound on, unless they switched it off
  hold?: boolean; // the fight runs too fast to talk over (5x and 10x, #577): the announcer waits
}

const OFF_KEY = "battle-royale-sound-off"; // the viewer's "off" choice, kept in this browser

// Whether the viewer switched sound off earlier; storage may be blocked, then the answer is no.
const savedOff = () => {
  try {
    return localStorage.getItem(OFF_KEY) === "1";
  } catch {
    return false;
  }
};

// Remember (or forget) the viewer's "off" choice; a blocked store is fine, the choice lasts the visit.
const saveOff = (off: boolean) => {
  try {
    if (off) localStorage.setItem(OFF_KEY, "1");
    else localStorage.removeItem(OFF_KEY);
  } catch {
    /* nothing to do */
  }
};

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

export default function AudioBar({
  narration,
  music,
  startSound = false,
  hold = false,
}: AudioBarProps) {
  const voice = useRef<HTMLAudioElement>(null);
  const song = useRef<HTMLAudioElement>(null);
  const soundOn = useRef(false); // sound is wanted: turned on by the viewer or the fight starting
  const autoStarted = useRef(false); // the fight's start has already had its say
  const held = useRef(hold); // the latest hold, for the effects and the button below
  const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(80); // percent

  // Apply the volume to both tracks whenever it changes.
  useEffect(() => {
    const level = volume / 100;
    if (voice.current) voice.current.volume = level;
    if (song.current)
      song.current.volume = narration ? level * MUSIC_UNDER_VOICE : level;
  }, [volume, narration]);

  // At 5x and 10x the announcer waits; once the fight slows down it picks up where it stopped,
  // if the sound is on (#577). The music, if any, plays on.
  useEffect(() => {
    held.current = hold;
    const track = voice.current;
    if (!track) return;
    if (hold) {
      track.pause(); // a no-op if it was not playing
    } else if (soundOn.current && track.paused && !track.ended) {
      void Promise.resolve()
        .then(() => track.play())
        .then(
          () => setPlaying(true),
          () => {
            if (held.current) return; // told to wait mid-load: cut short, not refused
            soundOn.current = false; // refused: stay quiet, as on any other start
            setPlaying(false);
          },
        );
    }
  }, [hold]);

  // The tracks change with the part of the show (each part has its own announcer file). The old
  // ones stop. If the viewer turned the sound on, the new ones carry on: the next announcer file
  // from its start, the music where it was; with nothing left to play, the button goes back to
  // "Sound off". Sound the viewer switched off stays off. The first time the fight starts, the
  // sound turns on unless the viewer switched it off in an earlier visit. Leaving the page stops
  // everything. (React has already let go of the elements when the cleanup runs, so it can't read
  // the refs then; the tracks are picked up again whenever they change.)
  useEffect(() => {
    const all = present([voice.current, song.current]);
    const tracks = present([held.current ? null : voice.current, song.current]);
    if (startSound && !autoStarted.current) {
      autoStarted.current = true;
      if (!savedOff()) soundOn.current = true;
    }
    if (soundOn.current)
      void startAll(tracks).then((on) => {
        // Refused: don't keep retrying. A voice the hold paused mid-load was cut short instead,
        // and while the announcer waits the sound is still on (#577).
        if (tracks.length > 0 && !on && !held.current) soundOn.current = false;
        setPlaying(on || held.current);
      });
    return () => all.forEach((t) => !t.paused && t.pause());
  }, [narration, music, startSound]);

  if (!narration && !music) return null;

  // The tracks on the page right now.
  const tracks = () => present([voice.current, song.current]);

  // Start or stop every track together, and remember an "off". The button says "Sound on" only
  // once the browser really plays something.
  const toggle = () => {
    if (playing) {
      tracks().forEach((t) => t.pause());
      soundOn.current = false;
      saveOff(true);
      setPlaying(false);
      return;
    }
    saveOff(false);
    if (held.current && !song.current) {
      soundOn.current = true; // only the announcer, who waits until the fight slows down
      setPlaying(true);
      return;
    }
    const startable = present([
      held.current ? null : voice.current,
      song.current,
    ]);
    void startAll(startable).then((on) => {
      soundOn.current = on;
      setPlaying(on);
    });
  };

  // A track that ends (the announcer is done) leaves the button on Sound off once nothing is left playing.
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
        <span aria-hidden="true">{playing ? "🔊 " : "🔇 "}</span>
        {playing ? "Sound on" : "Sound off"}
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
      <span className={styles.what} aria-live="polite">
        {hold && narration
          ? "Announcer waits at this speed"
          : narration && music
            ? "Announcer and music"
            : narration
              ? "Announcer only"
              : "Music only"}
      </span>
    </div>
  );
}
