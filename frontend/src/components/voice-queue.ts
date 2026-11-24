// How the announcer lines up the lines of each moment of the fight (#601). With a replay of about
// 20 s the moments' lines often arrive closer together than they take to say, so a moment whose
// lines come while earlier lines are still talking waits its turn instead of cutting them off.

// A stretch of the announcer's file, in seconds, for one moment of the fight (#576). `at` names the
// moment, so the same lines are not started twice.
export interface VoiceCue {
  at: number;
  start: number;
  end: number;
}

// A script has a handful of lines; this only stops a voice that has fallen far behind from piling
// up moments nobody can still follow. The oldest waiting moment is the one dropped.
export const MAX_WAITING = 6;

// What to do when a moment's lines arrive: `play` is the cue to start now, or null to leave the
// voice alone. While the voice is talking the new cue joins the line; otherwise it is the only
// one that matters (a stale moment from a paused or silent stretch is replaced, as before).
export function arrive(
  waiting: readonly VoiceCue[],
  cue: VoiceCue,
  talking: boolean,
): { waiting: VoiceCue[]; play: VoiceCue | null } {
  if (!talking) return { waiting: [], play: cue };
  return { waiting: [...waiting, cue].slice(-MAX_WAITING), play: null };
}

// The talking cue ended: the next waiting one starts, or none is left.
export function next(waiting: readonly VoiceCue[]): {
  waiting: VoiceCue[];
  play: VoiceCue | null;
} {
  const [play = null, ...rest] = waiting;
  return { waiting: rest, play };
}
