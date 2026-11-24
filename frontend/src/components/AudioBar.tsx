// The broadcast's sound controls (D07, #499): a Sound on/off switch and volume for the narration and
// music. Sound turns on when the viewer starts the fight (a click, so browsers allow it) unless they
// switched it off earlier in this visit (#579: remembered for this tab only, so a new visit, or the
// next person on a shared laptop, starts with sound); once on, it follows the show from part to
// part until they switch it off. Captions carry the show whenever sound can't play.
import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type Ref,
} from "react";
import styles from "./audio-bar.module.css";
import { arrive, next, type VoiceCue } from "./voice-queue.ts";

export type { VoiceCue };

export interface AudioBarProps {
  narration: string | null; // the announcer's voice track, if one can be played
  music: string | null; // the background music, if any
  startSound?: boolean; // the viewer started the fight: turn the sound on, unless they switched it off
  hold?: boolean; // the announcer waits: the fight is paused or too fast to talk over (#577)
  holdNote?: string; // what the bar says while the announcer waits
  cue?: VoiceCue | null; // in sync with the fight (#576): the stretch of the file to play now
  rate?: number; // the fight's speed: the announcer talks at it (1x or 2x)
  finishing?: boolean; // the replay reached its last moment: say what is left, then call onSettled (#601)
  onSettled?: () => void; // the announcer has nothing left to say, or waited as long as it may (#601)
  ref?: Ref<AudioBarHandle>; // lets the page unlock the voice inside its own click (#579, #584)
}

// What the page can ask of the bar from inside a click of its own.
export interface AudioBarHandle {
  // Call inside the click that starts the fight: unless the sound is already on or the viewer
  // switched it off before, the announcer's track is unlocked for the lines to come (#579, #584).
  unlock: () => void;
}

// The longest the show waits at the end of the replay for the announcer to finish (#601), so a
// stalled voice can never hold up the verdict.
export const FINISH_WAIT_MS = 8000;

const WAIT_NOTE = "Announcer waits at this speed";

// The viewer's "off" choice, kept for this visit (session storage, #579). An "off" an older version
// left in the browser-wide store is ignored.
const OFF_KEY = "battle-royale-sound-off";

// Whether the viewer switched sound off earlier in this visit; storage may be blocked, then no.
const savedOff = () => {
  try {
    return sessionStorage.getItem(OFF_KEY) === "1";
  } catch {
    return false;
  }
};

// Remember (or forget) the viewer's "off" choice for this visit; a blocked store is fine.
const saveOff = (off: boolean) => {
  try {
    if (off) sessionStorage.setItem(OFF_KEY, "1");
    else sessionStorage.removeItem(OFF_KEY);
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

// Inside a click, play a waiting track muted and pause it at once (#584). Safari lets a track
// play later on its own, as the fight reaches each line, only once a click has played it. It is
// paused before any sound can come out; a refusal is fine (the captions carry the show).
function wake(track: HTMLAudioElement | null) {
  if (!track || !track.paused || track.ended) return; // playing or played: nothing to unlock
  const muted = track.muted;
  track.muted = true;
  try {
    void track.play().catch(() => {}); // cut short by the pause below, or refused
  } catch {
    /* an older browser refuses by throwing */
  }
  track.pause();
  track.muted = muted;
}

// Whether the cued lines, ending at `end` in the file, still have something left to say.
const linesLeft = (track: HTMLAudioElement, end: number | null) =>
  end !== null && track.currentTime < end;

type Timer = { current: ReturnType<typeof setTimeout> | null };

// Cancel the timer that stops the voice at the end of its cued lines.
function cancel(timer: Timer) {
  if (timer.current !== null) clearTimeout(timer.current);
  timer.current = null;
}

const STOP_SLACK_S = 0.02; // this close to the end of the cued lines, stop now

// In sync, stop the playing voice where its cued lines end (#584): a timer for the time left at
// its speed, so the next line never slips out early; the timeupdate check is the backstop. A voice
// that fell behind (it stalled to load) is given the rest of its time instead of being cut short.
// `done` is told when the lines have ended, so the next waiting moment can start (#601).
function stopAtEnd(
  track: HTMLAudioElement,
  end: { current: number | null },
  timer: Timer,
  done?: () => void,
) {
  cancel(timer);
  if (end.current === null || track.paused) return;
  const left = (end.current - track.currentTime) / (track.playbackRate || 1);
  if (left <= STOP_SLACK_S) {
    track.pause();
    done?.();
  } else
    timer.current = setTimeout(
      () => stopAtEnd(track, end, timer, done),
      left * 1000,
    );
}

export default function AudioBar({
  narration,
  music,
  startSound = false,
  hold = false,
  holdNote = WAIT_NOTE,
  cue,
  rate = 1,
  finishing = false,
  onSettled,
  ref,
}: AudioBarProps) {
  const voice = useRef<HTMLAudioElement>(null);
  const song = useRef<HTMLAudioElement>(null);
  const soundOn = useRef(false); // sound is wanted: turned on by the viewer or the fight starting
  const autoStarted = useRef(false); // the fight's start has already had its say
  const held = useRef(hold); // the latest hold, for the effects and the button below
  // In sync with the fight (#576): the announcer only plays the cued lines, never the whole file.
  const cued = useRef(cue !== undefined);
  const cueNow = useRef(cue ?? null);
  const speed = useRef(rate);
  const stopAt = useRef<number | null>(null); // where the cued lines end in the file
  const stopTimer = useRef<Timer["current"]>(null); // stops the voice right there (#584)
  // Moments whose lines arrived while earlier lines were still talking wait their turn (#601).
  const waiting = useRef<VoiceCue[]>([]);
  const speaking = useRef(false); // cued lines have been started and have not ended yet
  const settle = useRef(onSettled); // the latest onSettled, for the finish wait
  const idle = useRef<(() => void) | null>(null); // runs when nothing is left to say (#601)
  const [playing, setPlaying] = useState(false);
  const [volume, setVolume] = useState(80); // percent

  // Tell whoever is waiting at the end of the replay that the announcer has nothing left to say.
  const flushIdle = useCallback(() => idle.current?.(), []);
  const cueDoneRef = useRef<() => void>(() => {}); // the latest cueDone, for the stop timer

  // Start a moment's lines: jump to them and, with the sound on and the fight moving, play them.
  // Where they end, the next waiting moment starts, or the finish wait is over (#601).
  const startCue = useCallback(
    (track: HTMLAudioElement, lines: VoiceCue) => {
      cancel(stopTimer);
      stopAt.current = lines.end;
      track.currentTime = lines.start;
      speaking.current = false;
      if (!soundOn.current || held.current) return;
      speaking.current = true;
      track.playbackRate = speed.current;
      void Promise.resolve()
        .then(() => track.play())
        .then(
          () => {
            setPlaying(true);
            stopAtEnd(track, stopAt, stopTimer, () => cueDoneRef.current());
          },
          () => {
            if (held.current) return; // told to wait mid-load: cut short, not refused
            speaking.current = false;
            waiting.current = [];
            soundOn.current = false;
            setPlaying(false);
            flushIdle();
          },
        );
    },
    [flushIdle],
  );

  // The talking lines ended: the next waiting moment starts, or nothing is left to say.
  const cueDone = useCallback(() => {
    if (!speaking.current) return; // already handled (the timer and timeupdate can both land)
    speaking.current = false;
    const track = voice.current;
    const turn = next(waiting.current);
    waiting.current = turn.waiting;
    if (turn.play && track) startCue(track, turn.play);
    else flushIdle();
  }, [startCue, flushIdle]);
  useEffect(() => {
    cueDoneRef.current = cueDone;
  }, [cueDone]);

  // The page's click that starts the fight unlocks the voice for its first line (#579, #584).
  useImperativeHandle(
    ref,
    () => ({
      unlock: () => {
        if (!soundOn.current && !savedOff()) wake(voice.current);
      },
    }),
    [],
  );

  // Apply the volume to both tracks whenever it changes.
  useEffect(() => {
    const level = volume / 100;
    if (voice.current) voice.current.volume = level;
    if (song.current)
      song.current.volume = narration ? level * MUSIC_UNDER_VOICE : level;
  }, [volume, narration]);

  // The latest props for the effects below (they run in this order, after this one).
  useEffect(() => {
    cued.current = cue !== undefined;
    cueNow.current = cue ?? null;
    speed.current = rate;
    settle.current = onSettled;
  });

  // The announcer talks at the fight's speed (1x or 2x; it waits at 5x and 10x), so the time left
  // to the end of its cued lines changes too.
  useEffect(() => {
    const track = voice.current;
    if (!track) return;
    track.playbackRate = rate;
    if (stopTimer.current !== null)
      stopAtEnd(track, stopAt, stopTimer, cueDone);
  }, [rate, cueDone]);

  // While the fight is paused or too fast, the announcer waits; then it picks up where it stopped,
  // if the sound is on (#577) and, in sync, its cued lines are not done yet (#576). The music, if
  // any, plays on.
  useEffect(() => {
    held.current = hold;
    const track = voice.current;
    if (!track) return;
    const unfinished = !cued.current || linesLeft(track, stopAt.current);
    if (hold) {
      cancel(stopTimer);
      track.pause(); // a no-op if it was not playing
    } else if (soundOn.current && track.paused && !track.ended && unfinished) {
      track.playbackRate = speed.current;
      void Promise.resolve()
        .then(() => track.play())
        .then(
          () => {
            setPlaying(true);
            if (cued.current) stopAtEnd(track, stopAt, stopTimer, cueDone);
          },
          () => {
            if (held.current) return; // told to wait mid-load: cut short, not refused
            soundOn.current = false; // refused: stay quiet, as on any other start
            setPlaying(false);
          },
        );
    } else if (soundOn.current && speaking.current && cued.current) {
      cueDone(); // the lines ended while the fight was held: the next waiting moment starts (#601)
    }
  }, [hold, cueDone]);

  // The tracks change with the part of the show (each part has its own announcer file). The old
  // ones stop. If the viewer turned the sound on, the new ones carry on: the next announcer file
  // from its start, the music where it was; with nothing left to play, the button goes back to
  // "Sound off". Sound the viewer switched off stays off. The first time the fight starts, the
  // sound turns on unless the viewer switched it off earlier in this visit. Leaving the page stops
  // everything. (React has already let go of the elements when the cleanup runs, so it can't read
  // the refs then; the tracks are picked up again whenever they change.)
  useEffect(() => {
    stopAt.current = null; // a new announcer file has no cued lines yet
    const all = present([voice.current, song.current]);
    const quiet = held.current || cued.current; // in sync, the voice waits for its cue
    const tracks = present([quiet ? null : voice.current, song.current]);
    if (startSound && !autoStarted.current) {
      autoStarted.current = true;
      if (!savedOff()) soundOn.current = true;
    }
    if (soundOn.current)
      void startAll(tracks).then((on) => {
        // Refused: don't keep retrying. A voice the hold paused mid-load was cut short instead,
        // and while the announcer waits the sound is still on (#577).
        if (tracks.length > 0 && !on && !held.current) soundOn.current = false;
        setPlaying(on || quiet);
      });
    return () => {
      cancel(stopTimer);
      speaking.current = false; // a new file has nothing queued from the old one (#601)
      waiting.current = [];
      idle.current = null;
      all.forEach((t) => !t.paused && t.pause());
    };
  }, [narration, music, startSound]);

  // In sync with the fight (#576): at each moment with lines, jump to them in the announcer's file
  // and play them, stopping where they end (#584). Lines that arrive while earlier lines are still
  // talking wait their turn rather than cutting them off (#601). A moment that arrives while the
  // voice is silent, paused or off replaces the one before. With no moment (the replay started
  // over), nothing is left to say: the stop timer, the queue and the old lines all end (#601).
  const cueAt = cue ? cue.at : null;
  useEffect(() => {
    const track = voice.current;
    const lines = cueNow.current;
    if (!lines) {
      cancel(stopTimer);
      waiting.current = [];
      if (speaking.current) track?.pause();
      speaking.current = false;
      return;
    }
    if (!track) return;
    const talking =
      speaking.current &&
      soundOn.current &&
      !held.current &&
      linesLeft(track, stopAt.current);
    const turn = arrive(waiting.current, lines, talking);
    waiting.current = turn.waiting;
    if (turn.play) startCue(track, turn.play);
  }, [cueAt, narration, startCue]);

  // The replay reached its last moment (#601): the show waits for the announcer to finish what it
  // is saying (and what is lined up), for at most FINISH_WAIT_MS, then moves to the verdict. With
  // nothing being said (sound off, the fight held, no lines) it moves on at once. This effect
  // follows the cue one, so the last moment's lines have already been started.
  useEffect(() => {
    if (!finishing) return;
    const busy =
      soundOn.current &&
      !held.current &&
      (speaking.current || waiting.current.length > 0);
    if (!busy) {
      settle.current?.();
      return;
    }
    const timer = setTimeout(() => flushIdle(), FINISH_WAIT_MS);
    idle.current = () => {
      clearTimeout(timer);
      idle.current = null;
      settle.current?.();
    };
    return () => {
      clearTimeout(timer);
      idle.current = null;
    };
  }, [finishing, flushIdle]);

  // In sync, stop at the end of the cued lines; the next moment's lines start them again.
  const onVoiceTime = () => {
    const track = voice.current;
    if (cued.current && track && stopAt.current !== null)
      if (track.currentTime >= stopAt.current) {
        track.pause();
        cueDone();
      }
  };

  if (!narration && !music) return null;

  // The tracks on the page right now.
  const tracks = () => present([voice.current, song.current]);

  // Start or stop every track together, and remember an "off". The button says "Sound on" only
  // once the browser really plays something. In sync with a moving fight, this click unlocks the
  // announcer's track for the lines to come, and says the current moment's lines now if they
  // aren't finished (#584). While the fight is paused or too fast, nothing plays, not even muted.
  const toggle = () => {
    if (playing) {
      tracks().forEach((t) => t.pause());
      cancel(stopTimer);
      speaking.current = false;
      waiting.current = [];
      soundOn.current = false;
      saveOff(true);
      setPlaying(false);
      flushIdle(); // the viewer wants quiet: nothing left to wait for (#601)
      return;
    }
    saveOff(false);
    const track = voice.current;
    const waits = held.current || cued.current; // the announcer waits for the fight or its cue
    const inSync = cued.current && !held.current;
    // A muted play and pause makes no sound, so it can unlock the voice even while the fight is
    // paused or too fast; Safari then needs no second click when the fight moves on (#601).
    if (waits) wake(track);
    const finish = inSync && track !== null && linesLeft(track, stopAt.current);
    const quiet = waits && !finish;
    if (quiet && !song.current) {
      soundOn.current = true;
      setPlaying(true);
      return;
    }
    const startable = present([quiet ? null : track, song.current]);
    void startAll(startable).then((on) => {
      soundOn.current = on;
      setPlaying(on);
      if (on && finish) {
        speaking.current = true;
        stopAtEnd(track, stopAt, stopTimer, cueDone);
      }
    });
  };

  // A track that ends (the announcer is done) leaves the button on Sound off once nothing is left playing.
  const onEnded = () => {
    setPlaying(tracks().some((t) => !t.paused && !t.ended));
    cueDone(); // a cue that ran to the end of the file is over too (#601)
  };

  return (
    <div className={styles.bar} role="group" aria-label="Sound controls">
      {narration && (
        <audio
          ref={voice}
          src={narration}
          preload="none"
          onEnded={onEnded}
          onTimeUpdate={onVoiceTime}
        />
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
          ? holdNote
          : narration && music
            ? "Announcer and music"
            : narration
              ? "Announcer only"
              : "Music only"}
      </span>
    </div>
  );
}
