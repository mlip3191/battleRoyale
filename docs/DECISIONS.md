# Decisions Log

Every decision that shapes the build, with its status. **OPEN** items need Mike's answer (the kickoff prompt asks about the ones that block Phase 0). **DEFAULT** items are decided unless Mike changes them. When a decision changes, edit its row and add the date — don't delete history.

## Open — need an answer

| ID | Question | Why it matters | Options | Recommendation | Blocks |
|---|---|---|---|---|---|
| D-03 | **Course endpoints — remaining details.** Decided 2026-11-07: they are reachable at **public URLs**. Still unknown: whether a key is required, the API format (OpenAI-compatible?), and the **ports** for Structured Decisions, Multimodal Reranking, Text-to-Speech/Voice Cloning, Music, and Speech-to-Text. | Every live adapter beyond chat, embeddings, parsing, and images. | — | Ask the instructor/TA for the missing ports and any key; then run `scripts/smoke_providers.py` (M06) | M06, G03, G04, A07 |
| D-05 | **Deadlines and deliverables.** The assignment document (rubric, due dates, demo format, report/video requirements) hasn't been shared. | Sets wave dates and what to cut if time is short. | — | Add the assignment document to `docs/assignment/`; Mike maps due dates onto the waves | wave dates |
| D-06 | **Team roster.** Dillon isn't on the proposal; the group letter and last names are placeholders. | The proposal and final report must list the right group. | — | Confirm Dillon's membership with the instructor; fill the group letter and names | report |
| D-08 | **Teammates' GitHub usernames and OS** (Windows, Mac, or both). | Invites, CODEOWNERS, cross-OS testing pairs. | — | Collect in the team channel | M08 |
| D-09 | **Announcer voice.** | Voice cloning needs consent. | (a) a stock TTS voice; (b) clone a teammate's voice with written consent | (a) for MVP; (b) as polish | A07 |
| D-16 | **Where does the demo run?** Endpoints are public, so any machine with internet works. | Pre-generated battles and Docker must work on the demo machine. | (a) presenter's laptop with Docker; (b) a course VM | (a), plus a recorded backup | G08, demo |
| D-20 | **Which Hugging Face datasets?** The proposal mentions them but doesn't name any. | Licensing and attribution. | — | Gunnar proposes in G01; Mike approves | G01, G02 |
| D-21 | **Team channel and password manager.** | Review requests; sharing `.env` values if any are secret. | Slack / Teams / Discord; Bitwarden / 1Password | Whatever the team already uses | M08 |

## Decided defaults — change only by PR

| ID | Decision | Reason |
|---|---|---|
| D-01 | **Private repo + GitHub Pro** (decided 2026-11-07). Mike claims GitHub Pro through the GitHub Student Developer Pack, then M01 makes the repo private and turns off forking. GitHub secret scanning/push protection aren't available for private personal repos, so the gitleaks Secret scan + local hook are our secret checks. CI runs the 3-OS matrix on PRs and Linux only on pushes to main to save Actions minutes. No license file needed while private. | Keeps code private from other teams while keeping enforced branch protection |
| D-02 | **Claude Code builds the app; Hermes Agent is used once** (decided 2026-11-07): task G06 is built with Hermes Agent (port 9000), Mike pairing, with screenshots for the final report. | Meets the proposal's Hermes commitment without splitting the process |
| D-04 | **QA bot uses Mike's Claude subscription token** (decided 2026-11-07): `claude setup-token` → repo secret `CLAUDE_CODE_OAUTH_TOKEN`. Runs count against Mike's plan limits; drafts are skipped and new pushes cancel old runs to save usage. If limits become a problem, switch to a spend-capped API key (one-line change). Regenerate the token if it stops working or might have leaked. | Chosen by Mike |
| D-07 | **Allowed fighters:** animals (living and extinct) and generic historical human archetypes. **Blocked:** named real people, minors, groups of people, sexual content, copyrighted fictional characters. Mythical creatures are a stretch goal and always all-estimate. | Safety, copyright, and the "real facts" promise |
| D-10 | **"Expert answers" for the benchmark** = obvious-by-biology cases + documented expert views with citations + rough fair-fight ranges (G07). Pass rules written before the first run. | The proposal didn't define it |
| D-11 | **Styling:** plain CSS modules with CSS variables; no CSS framework. | Fewer dependencies for non-coders |
| D-12 | **Versions:** Python 3.12, Node 24 LTS, uv for Python packages, npm for JS. Lockfiles committed. | Same results on Windows, Mac, CI |
| D-13 | **MVP is exactly two sides** (each side can have many fighters). | From the proposal |
| D-14 | **The number rule:** models copy numbers only with a verified quote; estimates come from code. | Makes "no language model sets a number" testable |
| D-15 | **Mock-first providers;** CI always runs in mock mode. | Course endpoints aren't reachable from GitHub |
| D-17 | **Monorepo** (`backend/`, `frontend/`) with root npm scripts as the cross-platform task runner. | One clone, one set of commands |
| D-19 | **No user accounts; battles stored locally** in SQLite; no personal data collected. | Privacy and scope |
| D-22 | **Five lanes,** 13–14 points each, owners as in `docs/plan/LANES.md`. | Balanced effort |
| D-23 | **PR review flow:** the review-prs skill drafts; nothing posts until the reviewer says send; approval is a separate, second confirmation. The QA bot never approves. | Humans stay accountable |
