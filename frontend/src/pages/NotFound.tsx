// Shown for any address the app doesn't know.
import { Link } from "react-router-dom";
import { ErrorPanel, MAIN_ID } from "../components/Broadcast.tsx";
import { usePageTitle } from "../components/page-title.ts";

export default function NotFound() {
  usePageTitle("Page not found");
  return (
    <main id={MAIN_ID} tabIndex={-1}>
      <ErrorPanel
        level={1}
        title="404: we lost the signal"
        message="That page isn't on tonight's card."
      />
      <p>
        <Link to="/">Back to the studio</Link>
      </p>
    </main>
  );
}
