// Shown for any address the app doesn't know.
import { Link } from "react-router-dom";
import { ErrorPanel } from "../components/Broadcast.tsx";

export default function NotFound() {
  return (
    <main>
      <ErrorPanel
        title="404: we lost the signal"
        message="That page isn't on tonight's card."
      />
      <p>
        <Link to="/">Back to the studio</Link>
      </p>
    </main>
  );
}
