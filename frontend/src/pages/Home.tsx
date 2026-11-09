import { useEffect, useState } from "react";
import { fetchHealth } from "../api/health.ts";

// Landing page; for now it only shows whether the backend is reachable.
export default function Home() {
  const [status, setStatus] = useState("checking…");

  useEffect(() => {
    fetchHealth()
      .then(setStatus)
      .catch(() => setStatus("unreachable"));
  }, []);

  return (
    <main>
      <h1>Battle Royale</h1>
      <p>Backend: {status}</p>
    </main>
  );
}
