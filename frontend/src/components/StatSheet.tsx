// Stat sheet pieces for the results page (D04): every number shows where it came from.
import { useId } from "react";
import type {
  LoreProfile,
  Source,
  StatSheet,
  StatValue,
} from "../api/client.ts";
import { srOnly } from "./Broadcast.tsx";
import styles from "./stat-sheet.module.css";

// More estimates or assumptions than this on one sheet earns a warning banner.
export const MAX_GUESSES = 3;

const STAT_LABELS: Record<string, string> = {
  mass_kg: "Mass",
  size_m: "Size",
  top_speed_mps: "Top speed",
  attack_force_n: "Attack force",
  attacks_per_s: "Attack rate",
  reach_m: "Reach",
  armor_0_1: "Armor",
  endurance_s: "Endurance",
  aggression_0_1: "Aggression",
  group_tactics_0_1: "Group tactics",
};

const ABILITIES: Record<LoreProfile["abilities"][number], [string, string]> = {
  flight: ["🪽", "Flight"],
  breath_weapon: ["🔥", "Breath weapon"],
  regeneration: ["♻️", "Regeneration"],
  extra_heads: ["🐲", "Extra heads"],
};

// A source link that opens in a new tab and shows its exact quote on hover or focus.
function SourceLink({
  source,
  describedBy,
}: {
  source: Source;
  describedBy?: string;
}) {
  return (
    <a
      href={source.url}
      target="_blank"
      rel="noopener noreferrer"
      aria-describedby={describedBy}
    >
      {source.title}
      <span className={srOnly}> (opens in a new tab)</span>
    </a>
  );
}

// The badge behind a sourced stat: confidence dot, source link, and the quote it came from.
export function SourceBadge({
  source,
  confidence,
}: {
  source: Source;
  confidence: StatValue["confidence"];
}) {
  const quoteId = useId();
  return (
    <span className={styles.badge}>
      <span
        className={`${styles.dot} ${styles[confidence]}`}
        aria-hidden="true"
      />
      <SourceLink source={source} describedBy={quoteId} />
      <span className={styles.muted}> {confidence} confidence</span>
      <span id={quoteId} role="tooltip" className={styles.quote}>
        “{source.quote}”
      </span>
    </span>
  );
}

// The honesty tag for a stat, from how it was produced; null when the source badge says it all.
export function statTag(stat: StatValue) {
  if (stat.method === "assumption") return "assumption";
  if (stat.is_estimate) return "estimate";
  if (stat.source) return null;
  return stat.method.replace("_", " ");
}

// Show every digit the sheet has (the number rule): no rounding, only thousands separators.
export const formatStatValue = (value: number) =>
  value.toLocaleString("en-US", { maximumFractionDigits: 20 });

// Whether a stat counts toward the "lots of guesses" banner.
const isGuess = (stat: StatValue) =>
  stat.is_estimate || stat.method === "assumption";

// One table row: stat name, value with unit, and where the number came from.
function StatRow({ name, stat }: { name: string; stat: StatValue }) {
  const tag = statTag(stat);
  return (
    <tr>
      <th scope="row">{STAT_LABELS[name] ?? name}</th>
      <td className={styles.value}>
        {formatStatValue(stat.value)} {stat.unit}
      </td>
      <td>
        {stat.source && (
          <SourceBadge source={stat.source} confidence={stat.confidence} />
        )}
        {tag && <span className={styles.tag}>{tag}</span>}
        {stat.note && <small className={styles.note}>{stat.note}</small>}
      </td>
    </tr>
  );
}

// What the legend compares a mythical fighter to, its powers, and the quote that says so.
export function LoreCard({ lore }: { lore: LoreProfile }) {
  const titleId = useId();
  return (
    <section aria-labelledby={titleId}>
      <h4 id={titleId}>According to legend</h4>
      <p>
        Modeled on {lore.body_analog}
        {lore.size_analog && `, scaled to ${lore.size_analog}`}.
      </p>
      <ul className={styles.abilities} aria-label="Abilities">
        {lore.abilities.map((a) => (
          <li key={a}>
            <span aria-hidden="true">{ABILITIES[a][0]}</span> {ABILITIES[a][1]}
            {a === "extra_heads" && lore.heads && ` (${lore.heads})`}
          </li>
        ))}
      </ul>
      <figure className={styles.figure}>
        <blockquote cite={lore.source.url}>“{lore.source.quote}”</blockquote>
        <figcaption>
          <SourceLink source={lore.source} />
        </figcaption>
      </figure>
    </section>
  );
}

// One fighter's tale of the tape, with a warning when most of it is guesswork.
export function StatSheetCard({ sheet }: { sheet: StatSheet }) {
  const stats = Object.entries(sheet.stats);
  const guesses = stats.filter(([, s]) => isGuess(s)).length;
  return (
    <article className={styles.card}>
      <h3>{sheet.display_name}</h3>
      {sheet.lore ? (
        <p className={styles.banner}>
          Legendary fighter: every stat is an assumption
        </p>
      ) : (
        guesses > MAX_GUESSES && (
          <p className={styles.banner}>
            Heads up: {guesses} of {stats.length} stats are estimates or
            assumptions, so treat this sheet as a best guess.
          </p>
        )
      )}
      {sheet.lore && <LoreCard lore={sheet.lore} />}
      <table className={styles.table}>
        <caption className={srOnly}>Stats for {sheet.display_name}</caption>
        <thead>
          <tr>
            <th scope="col">Stat</th>
            <th scope="col">Value</th>
            <th scope="col">Where it comes from</th>
          </tr>
        </thead>
        <tbody>
          {stats.map(([name, stat]) => (
            <StatRow key={name} name={name} stat={stat} />
          ))}
        </tbody>
      </table>
    </article>
  );
}

// Every source behind the stat sheets and legends, each listed once (by URL).
export function uniqueSources(sheets: StatSheet[]) {
  const all = sheets.flatMap((sheet) => [
    ...Object.values(sheet.stats).map((s) => s.source),
    sheet.lore?.source,
  ]);
  const byUrl = new Map<string, Source>();
  for (const s of all) if (s && !byUrl.has(s.url)) byUrl.set(s.url, s);
  return [...byUrl.values()];
}

// The bibliography: title, URL, and license for every unique source.
export function SourceList({ sheets }: { sheets: StatSheet[] }) {
  const sources = uniqueSources(sheets);
  return (
    <section aria-labelledby="sources-title">
      <h2 id="sources-title">Sources</h2>
      {sources.length === 0 ? (
        <p>No outside sources: every stat here is an estimate.</p>
      ) : (
        <ul>
          {sources.map((s) => (
            <li key={s.url}>
              <SourceLink source={s} />{" "}
              <span className={styles.url}>{s.url}</span> · {s.license}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}
