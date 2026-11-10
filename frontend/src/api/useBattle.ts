// Keeps a battle up to date: listens for live stage updates (Server-Sent Events) and, if that
// connection fails or isn't available (fixtures mode, old browsers), checks every POLL_MS instead.
import { useEffect, useState } from "react";
import {
  battleEventsUrl,
  getBattle,
  fixturesMode,
  type BattleRecord,
} from "./client.ts";

export const POLL_MS = 1000;

export function useBattle(id: string) {
  const [battle, setBattle] = useState<BattleRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let source: EventSource | undefined;

    // Fetch the latest record; returns true while the battle is still running.
    const refresh = async () => {
      try {
        const record = await getBattle(id);
        if (stopped) return false;
        setBattle(record);
        setError(null);
        return record.status === "running";
      } catch {
        if (!stopped) setError("We lost the feed for a moment. Retrying…");
        return true;
      }
    };

    // Polling fallback: check once a second until the battle ends.
    const poll = async () => {
      if (stopped) return;
      if (await refresh()) timer = setTimeout(poll, POLL_MS);
    };

    // Live updates: every stage update triggers a fresh fetch; any connection error switches to polling.
    const listen = () => {
      source = new EventSource(battleEventsUrl(id));
      source.onmessage = () => {
        void refresh().then((running) => {
          if (!running) source?.close();
        });
      };
      source.onerror = () => {
        source?.close();
        void poll();
      };
    };

    void refresh().then((running) => {
      if (!running || stopped) return;
      if (!fixturesMode() && typeof EventSource !== "undefined") listen();
      else timer = setTimeout(poll, POLL_MS);
    });

    return () => {
      stopped = true;
      clearTimeout(timer);
      source?.close();
    };
  }, [id]);

  return { battle, error };
}
