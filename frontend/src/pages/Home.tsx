// Home page, the intake desk (D03): type a matchup, answer one question if needed, start the battle.
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ApiError,
  answerIntake,
  createBattle,
  listShowcase,
  postIntake,
  type IntakeResult,
  type Matchup,
  type ShowcaseBattle,
} from "../api/client.ts";
import { ErrorPanel, MAIN_ID } from "../components/Broadcast.tsx";
import { usePageTitle } from "../components/page-title.ts";
import styles from "./home.module.css";

type Terrain = Matchup["terrain"];

// For now every example uses only fighters with a ready-made (seed) stat sheet in
// data/seed/fighters/, at their real size. Until research for other fighters and size swaps
// lands (later A05 work), any other matchup ends in "This fight was called off", which would
// make the suggestions look broken (#205). Bring the showcase-style examples back then.
// Gorilla vs grizzly bear is left out on purpose until calibration (#47) has looked at it.
// When the seed list changes, re-check all six chips from intake to a verdict, and update
// SEED_FIGHTERS in Home.test.tsx to match.
export const EXAMPLES = [
  "a grizzly bear vs 6 gray wolves in a forest",
  "a honey badger vs a saltwater crocodile",
  "an african elephant vs 12 gray wolves",
  "a horse vs a gorilla",
  "50 ducks vs a honey badger",
  "a saltwater crocodile vs a horse in the water",
];

export const TERRAINS = {
  arena: "Arena",
  open_field: "Open field",
  forest: "Forest",
  water: "Open water",
  shoreline: "Shoreline",
  urban: "City streets",
  mountain: "Mountain",
} satisfies Record<Terrain, string>;

const OFFLINE =
  "We couldn't reach the studio. Check your connection and try again.";

const LOST_QUESTION =
  "That question got lost on the way to the studio. Please send your matchup again.";

// Shown after about SLOW_MS of waiting, so a slow (but normal) reply doesn't look frozen (D-52).
const STILL_WORKING = "Still sizing them up…";
const SLOW_MS = 5_000;

// A busy matchup desk (503) speaks in the server's words; anything else blames the connection.
function failureMessage(error: unknown) {
  return error instanceof ApiError && error.status === 503 && error.detail
    ? error.detail
    : OFFLINE;
}

// A question the server no longer has (404: expired or already answered).
const isLostQuestion = (error: unknown): error is ApiError =>
  error instanceof ApiError && error.status === 404;

// The server's own lost-question words; a bare "Not Found" (a 404 from no route at all) isn't one.
const lostMessage = (error: ApiError) =>
  error.detail && error.detail !== "Not Found" ? error.detail : LOST_QUESTION;

// Where the desk is: waiting for input, talking to the backend, or showing intake's answer
// (while an answer to its question is on its way, or after that answer failed).
type Step =
  | { kind: "idle" }
  | { kind: "busy" }
  | {
      kind: "result";
      result: IntakeResult;
      answering?: boolean;
      error?: string;
    }
  | { kind: "error"; message: string };

export default function Home() {
  const [text, setText] = useState("");
  const [step, setStep] = useState<Step>({ kind: "idle" });
  const [showcase, setShowcase] = useState<ShowcaseBattle[]>([]);
  const [slow, setSlow] = useState(false);
  const slowTimers = useRef(new Set<ReturnType<typeof setTimeout>>());
  const box = useRef<HTMLTextAreaElement>(null);
  usePageTitle();

  useEffect(() => {
    listShowcase()
      .then(setShowcase)
      .catch(() => setShowcase([]));
  }, []);

  // Leaving the page stops every still-working timer.
  useEffect(() => {
    const timers = slowTimers.current;
    return () => {
      timers.forEach(clearTimeout);
      timers.clear();
    };
  }, []);

  // Wait for one intake call; past SLOW_MS, show the still-working line. Each call has its own
  // timer, and the line goes only when no call is left waiting, so overlapping calls don't
  // hide it early.
  const wait = (request: Promise<IntakeResult>) => {
    const timers = slowTimers.current;
    const timer = setTimeout(() => setSlow(true), SLOW_MS);
    timers.add(timer);
    return request.finally(() => {
      clearTimeout(timer);
      if (timers.delete(timer) && timers.size === 0) setSlow(false);
    });
  };

  // Send intake's reply (or a failure) to the screen.
  const handle = (request: Promise<IntakeResult>) => {
    setStep({ kind: "busy" });
    wait(request)
      .then((result) => setStep({ kind: "result", result }))
      .catch((error: unknown) =>
        setStep({ kind: "error", message: failureMessage(error) }),
      );
  };

  // Answer the clarifying question. The card stays up (buttons off) while the answer is sent,
  // and stays up with an error if it fails, so the question is never lost. Only when the
  // server no longer has the question (404) does the card go, so the matchup is typed again.
  const answering = useRef(false);
  const answer = (result: IntakeResult, reply: string) => {
    if (answering.current) return;
    if (!result.pending_id) {
      setStep({ kind: "result", result, error: LOST_QUESTION });
      return;
    }
    answering.current = true;
    setStep({ kind: "result", result, answering: true });
    wait(answerIntake(result.pending_id, reply))
      .then((next) => setStep({ kind: "result", result: next }))
      .catch((error: unknown) =>
        setStep(
          isLostQuestion(error)
            ? { kind: "error", message: lostMessage(error) }
            : { kind: "result", result, error: failureMessage(error) },
        ),
      )
      .finally(() => (answering.current = false));
  };

  const submit = (e?: FormEvent) => {
    e?.preventDefault();
    if (text.trim() && step.kind !== "busy") handle(postIntake(text.trim()));
  };

  const pick = (example: string) => {
    setText(example);
    box.current?.focus();
  };

  const result = step.kind === "result" ? step.result : null;
  return (
    <main id={MAIN_ID} tabIndex={-1}>
      <form className={styles.intake} onSubmit={submit}>
        <h1 className={styles.prompt}>
          <label htmlFor="matchup">Who would win?</label>
        </h1>
        <textarea
          id="matchup"
          ref={box}
          className={styles.box}
          value={text}
          placeholder="a horse-sized duck vs a lion"
          aria-describedby="matchup-hint"
          onChange={(e) => setText(e.target.value)}
          onKeyDown={(e) => {
            // Enter fights; Shift+Enter adds a line; Enter that confirms an IME word does neither.
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing)
              submit(e);
          }}
        />
        <span id="matchup-hint" className={styles.muted}>
          Name two sides, with counts and a place if you like. Press Enter to
          fight.
        </span>
        <button
          className={styles.fight}
          type="submit"
          disabled={step.kind === "busy"}
        >
          {step.kind === "busy" ? "Checking the card…" : "FIGHT!"}
        </button>
        <p className={styles.muted} role="status" aria-live="polite">
          {slow ? STILL_WORKING : ""}
        </p>
        <ul className={styles.chips} aria-label="Examples">
          {EXAMPLES.map((example) => (
            <li key={example}>
              <button
                type="button"
                className={styles.chip}
                onClick={() => pick(example)}
              >
                {example}
              </button>
            </li>
          ))}
        </ul>
      </form>

      {step.kind === "error" && <ErrorPanel message={step.message} />}
      {result?.status === "blocked" && (
        <ErrorPanel
          title="We can't book that fight"
          message={
            result.message ??
            "That matchup isn't allowed on our show. Try different fighters."
          }
        />
      )}
      {result?.status === "clarify" && (
        <Clarify
          result={result}
          busy={step.kind === "result" && !!step.answering}
          error={step.kind === "result" ? step.error : undefined}
          onAnswer={(reply) => answer(result, reply)}
        />
      )}
      {result?.status === "ok" && result.matchup && (
        <Confirm
          key={result.matchup.raw_text}
          matchup={result.matchup}
          message={result.message}
        />
      )}

      {showcase.length > 0 && (
        <section className={styles.showcase} aria-labelledby="showcase-title">
          <h2 id="showcase-title">Showcase</h2>
          <ul>
            {showcase.map((s) => (
              <li key={s.battle_id}>
                <Link to={`/battle/${s.battle_id}`}>{s.title}</Link>
              </li>
            ))}
          </ul>
        </section>
      )}
    </main>
  );
}

// One clarifying question: tap an option or type an answer.
function Clarify({
  result,
  busy,
  error,
  onAnswer,
}: {
  result: IntakeResult;
  busy: boolean;
  error?: string;
  onAnswer: (answer: string) => void;
}) {
  const [own, setOwn] = useState("");
  return (
    <section className={styles.card} aria-labelledby="clarify-title">
      <h2 id="clarify-title">Quick question</h2>
      <p>{result.question}</p>
      {error && <ErrorPanel message={error} />}
      <div className={styles.row}>
        {result.options.map((option) => (
          <button
            key={option}
            type="button"
            className={styles.option}
            disabled={busy}
            onClick={() => onAnswer(option)}
          >
            {option}
          </button>
        ))}
      </div>
      <form
        className={styles.row}
        onSubmit={(e) => {
          e.preventDefault();
          if (own.trim()) onAnswer(own.trim());
        }}
      >
        <label htmlFor="own-answer">Or type your answer</label>
        <input
          id="own-answer"
          className={styles.answer}
          value={own}
          onChange={(e) => setOwn(e.target.value)}
        />
        <button type="submit" className={styles.option} disabled={busy}>
          {busy ? "Sending…" : "Answer"}
        </button>
      </form>
    </section>
  );
}

// The tale of the tape before the bell: who's fighting, where, and what we assumed.
function Confirm({
  matchup,
  message,
}: {
  matchup: Matchup;
  message?: string | null;
}) {
  const [terrain, setTerrain] = useState<Terrain>(matchup.terrain);
  const [starting, setStarting] = useState(false);
  const [failed, setFailed] = useState(false);
  const navigate = useNavigate();

  const fight = () => {
    setStarting(true);
    setFailed(false);
    createBattle({ ...matchup, terrain })
      .then(({ battle_id }) => navigate(`/battle/${battle_id}`))
      .catch(() => {
        setStarting(false);
        setFailed(true);
      });
  };

  return (
    <section className={styles.card} aria-labelledby="confirm-title">
      <h2 id="confirm-title">Tonight's card</h2>
      {message && <p>{message}</p>}
      <ul className={styles.sides}>
        {matchup.fighters.map((f, i) => (
          <li key={i} className={styles.side}>
            <strong>
              {f.count > 1 ? `${f.count.toLocaleString()} × ` : ""}
              {f.entity}
            </strong>
            {f.variant && <div className={styles.muted}>{f.variant}</div>}
            {f.size_reference && (
              <div className={styles.muted}>
                sized like a {f.size_reference}
              </div>
            )}
          </li>
        ))}
      </ul>
      <div className={styles.row}>
        <label htmlFor="terrain">Battlefield</label>
        <select
          id="terrain"
          className={styles.select}
          value={terrain}
          onChange={(e) => setTerrain(e.target.value as Terrain)}
        >
          {Object.entries(TERRAINS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
      {matchup.assumptions.length > 0 && (
        <div>
          <span className={styles.muted}>We assumed:</span>
          <ul>
            {matchup.assumptions.map((a) => (
              <li key={a}>{a}</li>
            ))}
          </ul>
        </div>
      )}
      {failed && <ErrorPanel message={OFFLINE} />}
      <button
        type="button"
        className={styles.fight}
        onClick={fight}
        disabled={starting}
      >
        {starting ? "Ringing the bell…" : "FIGHT!"}
      </button>
    </section>
  );
}
