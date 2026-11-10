// Keeps a battle up to date: listens for live stage updates (Server-Sent Events) and, if that
// connection fails or isn't available (fixtures mode, old browsers), checks every POLL_MS instead.
import { useEffect, useState } from "react";
import {
  ApiError,
  battleEventsUrl,
  fixturesMode,
  getBattle,
  type BattleRecord,
} from "./client.ts";

export const POLL_MS = 1000;
export const NOT_FOUND =
  "We couldn't find that battle. The link may have a typo, or the battle has expired.";
export const RETRYING = "We lost the feed for a moment. Retrying…";

type View = { id: string; battle: BattleRecord | null; error: string | null };
// What a refresh learned: keep going, stop (battle over or not found), or switch to polling.
type Next = "running" | "stop" | "retry";

export function useBattle(id: string) {
  const [view, setView] = useState<View>({ id, battle: null, error: null });

  useEffect(() => {
    let stopped = false;
    let polling = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let source: EventSource | undefined;
    let issued = 0; // requests sent
    let shown = 0; // newest request whose reply is on screen
    let running = true;

    // Fetch the latest record. Replies can arrive out of order, so a reply older than the one
    // already shown is ignored (otherwise a slow "running" reply could undo "done").
    const refresh = async (): Promise<Next> => {
      const mine = ++issued;
      try {
        const record = await getBattle(id);
        if (stopped) return "stop";
        if (mine > shown) {
          shown = mine;
          running = record.status === "running";
          setView({ id, battle: record, error: null });
        }
        return running ? "running" : "stop";
      } catch (e) {
        if (stopped) return "stop";
        if (e instanceof ApiError && e.status === 404) {
          setView({ id, battle: null, error: NOT_FOUND });
          return "stop";
        }
        setView((v) => ({
          id,
          battle: v.id === id ? v.battle : null,
          error: RETRYING,
        }));
        return "retry";
      }
    };

    // Polling: check once a second until the battle ends.
    const poll = async () => {
      if (stopped) return;
      if ((await refresh()) !== "stop" && !stopped)
        timer = setTimeout(poll, POLL_MS);
    };
    const startPolling = (now: boolean) => {
      if (polling || stopped) return;
      polling = true;
      if (now) void poll();
      else timer = setTimeout(poll, POLL_MS);
    };

    // Live updates: close the stream and poll instead whenever it breaks or a fetch fails.
    const fallBack = () => {
      source?.close();
      startPolling(true);
    };
    const onUpdate = () => {
      void refresh().then((next) => {
        if (next === "stop") source?.close();
        else if (next === "retry") fallBack();
      });
    };
    const listen = () => {
      source = new EventSource(battleEventsUrl(id));
      source.onopen = onUpdate; // catch anything that changed before the stream opened
      source.onmessage = onUpdate; // unnamed events
      source.addEventListener("stage", onUpdate); // named events, if A05 sends them
      source.addEventListener("end", onUpdate);
      source.onerror = fallBack;
    };

    void refresh().then((next) => {
      if (next === "stop" || stopped) return;
      if (
        next === "running" &&
        !fixturesMode() &&
        typeof EventSource !== "undefined"
      )
        listen();
      else startPolling(false);
    });

    return () => {
      stopped = true;
      clearTimeout(timer);
      source?.close();
    };
  }, [id]);

  // A new id shows nothing until its own first reply, never the previous battle.
  return view.id === id
    ? { battle: view.battle, error: view.error }
    : { battle: null, error: null };
}
