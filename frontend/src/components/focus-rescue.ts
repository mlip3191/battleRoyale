// Keeps keyboard focus from falling to the top of the page when the control in use disappears
// (the show moved on, or a button was disabled). Used by the Battle page and the replay stage.
import { useState, type FocusEvent } from "react";

// Whether keyboard focus has nowhere to be: on the page itself, or on a removed or disabled control.
export function focusIsLost(): boolean {
  const el = document.activeElement;
  return (
    !el ||
    el === document.body ||
    !el.isConnected ||
    (el as HTMLButtonElement).disabled === true
  );
}

export interface FocusRescue {
  onFocus: () => void; // put on the group of controls
  onBlur: (e: FocusEvent<HTMLElement>) => void; // put on the group of controls
  claim: () => boolean; // true (once) if focus was in the group and is now lost
  rescue: (target: HTMLElement | null) => boolean; // claim, then move focus to the target
}

// Remember whether keyboard focus is inside one group of controls, so that a control vanishing
// under the viewer sends focus to the next sensible place. Nothing moves if focus was elsewhere.
export function useFocusRescue(): FocusRescue {
  const [rescuer] = useState<FocusRescue>(() => {
    let inside = false;
    const claim = () => {
      if (!inside || !focusIsLost()) return false;
      inside = false;
      return true;
    };
    return {
      onFocus: () => {
        inside = true;
      },
      // Focus moving to another element outside the group means the viewer moved on. So does
      // focus leaving for nothing while the control is still there (a click on a blank part of
      // the page). A removed control fires no blur, and the window losing focus keeps the claim.
      onBlur: (e) => {
        const next = e.relatedTarget;
        const movedOn = next
          ? !e.currentTarget.contains(next)
          : document.hasFocus() && e.target.isConnected;
        if (movedOn) inside = false;
      },
      claim,
      rescue: (target) => {
        if (!target || !claim()) return false;
        target.focus();
        return true;
      },
    };
  });
  return rescuer;
}
