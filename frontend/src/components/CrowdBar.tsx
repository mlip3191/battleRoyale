// The waiting room's sound controls (#592): from the announcer's recording until the show starts,
// a quiet crowd plays, unless the viewer switched sound off this visit. Its Sound on/off is the
// same choice as the show's (AudioBar); there is no volume slider (one quiet level). The page
// shows this bar only in the waiting room, so the crowd stops when the show starts, on Skip, or on
// leaving the page.
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
  const crowd = useCrowdBed(wanted);

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
      <span className={styles.what}>Crowd while the announcer records</span>
    </div>
  );
}
