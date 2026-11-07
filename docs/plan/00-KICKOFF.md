# Kickoff — paste this into Claude Code

This is the single prompt Mike pastes into Claude Code, at the root of a fresh clone of this repo, to start building. It runs Phase 0 (tasks M01–M08) one task at a time, stopping for your confirmation, and ends by telling you exactly what happens next.

## Before you paste it (10 minutes, by hand)

1. Install: Git, GitHub CLI, Claude Code, Node 24, uv. Log in: `gh auth login` (as `mlip3191`) and `claude`.
2. Clone: `git clone https://github.com/mlip3191/battleRoyale.git` and `cd battleRoyale`.
3. Copy `.env.example` to `.env` and fill in the course endpoint URLs (DECISIONS D-03). Never paste them anywhere else.
4. Skim [DECISIONS.md](../DECISIONS.md) — the items marked **OPEN** need your answer; Claude will ask about them when a task depends on one.
5. Have ready: GitHub Pro active through the Student Developer Pack (D-01), teammates' GitHub usernames, and run `claude setup-token` for the QA bot secret when M07 asks (D-04).

## The prompt

```text
You are the build assistant for the Battle Royale team project. I am Mike, the project manager and the only team member with coding experience. Four non-coder teammates (Adam, Gunnar, Felipe, Dillon) will join after this phase and build through Claude Code.

Read these files fully before doing anything else, in this order:
CLAUDE.md, docs/PROJECT_GUIDE.md, docs/PRODUCT_SPEC.md, docs/ARCHITECTURE.md, docs/TEAM_PROCESS.md, docs/DECISIONS.md, docs/plan/LANES.md, docs/plan/lane-1-mike.md.

Then:
1. Give me a 10-line summary of what we are building and how Phase 0 works, and list any contradiction or gap you found between those documents, with your recommended fix. Wait for my answers.
2. Check docs/DECISIONS.md for OPEN items that block Phase 0 (D-03 missing ports, D-08 usernames) and confirm GitHub Pro is active (D-01) and ask me about each one I haven't answered. Record my answers in DECISIONS.md.
3. Execute docs/plan/lane-1-mike.md tasks M01 through M08, strictly in order, one at a time. For each task:
   a. Say which task you are starting and show its acceptance criteria.
   b. Follow the task's "Prompt for Claude Code" exactly, including its confirmation points.
   c. When the task needs me to do something by hand (a GitHub setting, a secret, a username), stop and give me a numbered checklist, then wait.
   d. Verify every acceptance criterion and show me the evidence.
   e. Commit with the message the task specifies. During Phase 0 you may commit to main; from M08 on, never commit to main.
   f. Ask "Ready for the next task?" and wait.
4. If anything fails, stop, explain it in plain English, and propose a fix. Never skip a guardrail, never use --no-verify, never force push.
5. After M08, give me the "What happens next" briefing from docs/plan/00-KICKOFF.md, filled in with the real issue numbers and the dry-run PR link.
```

## What happens next (after Phase 0)

1. **Kickoff call (30 min).** Share your screen: the board, one lane file, the dry-run PR. Everyone runs `npm run doctor` (or the README quick start until D01 lands).
2. **Wave 1 (days 4–5).** Each teammate does their setup task: A01, G01, F01, D01. Felipe's F01 includes reviewing the dry-run PR with the review-prs skill — the first real review.
3. **Wave 2 → 4.** Teammates pick up their next issue from **Ready** on the board. Every task's prompt is in their lane file. Mike moves issues to Ready as dependencies merge.
4. **Weekly rhythm.** Monday: Mike triages, updates the board. Mid-week: async check-in in the channel (done / doing / blocked). Friday: run the benchmark (after F07) and review `docs/benchmark-results.md` together.
5. **Milestones.** MS-1 walking skeleton (end of Wave 2), MS-2 real brain (Wave 3), MS-3 the show (Wave 4), MS-4 demo-ready. See LANES.md.
6. **Each teammate's prompt to start any task:**
   ```text
   Start work on issue #<number>. Read the task in docs/plan/<my lane file> under its ID, follow its prompt, and check off its acceptance criteria before opening the PR.
   ```
7. **Each teammate's prompt to review:**
   ```text
   What can I review?
   ```
