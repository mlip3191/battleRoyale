// The waiting room's sound controls (#592): while the announcer records, a quiet crowd plays,
// unless the viewer switched sound off this visit. Its Sound on/off is the same choice as the
// show's (AudioBar). The page shows this bar only while it waits for the announcer, so the crowd
// stops when the show starts, on Skip, or on leaving the page.
import { useState } from "react";
import styles from "./audio-bar.module.css";
import { saveOff, savedOff } from "./AudioBar.tsx";
import { useCrowdBed } from "./crowd-bed.ts";
import type { FocusRescue } from "./focus-rescue.ts";

export default function CrowdBar({
  focusGroup,
}: {
  focusGroup?: Pick<FocusRescue, "onFocus" | "onBlur">; // so focus isn't lost when the bar goes
}) {
  const [wanted, setWanted] = useState(() => !savedOff());
  const [volume, setVolume] = useState(80); // percent, as in the show's bar
  const crowd = useCrowdBed(wanted, volume);

  // Switch the crowd off (remembered for the visit) or on; "on" is a click, so it wakes the audio.
  const toggle = () => {
    saveOff(crowd.playing);
    setWanted(!crowd.playing);
    if (!crowd.playing) crowd.wake();
  };

  return (
    <div
      className={styles.bar}
      role="group"
      aria-label="Sound controls"
      onFocus={focusGroup?.onFocus}
      onBlur={focusGroup?.onBlur}
    >
      <button type="button" className={styles.button} onClick={toggle}>
        <span aria-hidden="true">{crowd.playing ? "🔊 " : "🔇 "}</span>
        {crowd.playing ? "Sound on" : "Sound off"}
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
      <span className={styles.what}>Crowd while the announcer records</span>
    </div>
  );
}
