// The results page frame (D02). Stat sheet cards with sources arrive with D04.
import { Link, useParams } from "react-router-dom";
import { LowerThird } from "../components/Broadcast.tsx";

export default function Results() {
  const { id = "" } = useParams();
  return (
    <main>
      <LowerThird>Tale of the tape</LowerThird>
      <h1>Results</h1>
      <p>
        <Link to={`/battle/${id}`}>Back to the broadcast</Link>
      </p>
    </main>
  );
}
