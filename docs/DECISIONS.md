# Decisions Log

Every decision that shapes the build, with its status. **OPEN** items need Mike's answer (the kickoff prompt asks about the ones that block Phase 0). **DEFAULT** items are decided unless Mike changes them. When a decision changes, edit its row and add the date — don't delete history.

## Open — need an answer

| ID | Question | Why it matters | Options | Recommendation | Blocks |
|---|---|---|---|---|---|
| D-01 | **Public or private repo?** The repo is currently **public**, under Mike's personal account. | Public: branch protection, secret scanning, and push protection are free, but anyone (including other teams) can read the code and any leaked key is exposed instantly. Private on GitHub Free: **no enforced branch protection** and no secret scanning. | (a) stay public; (b) private + GitHub Pro (free through the GitHub Student Developer Pack); (c) move to a free organization (private repos still lack protection on Free) | (a) if the instructor allows public code; otherwise (b) | M01, M08 |
| D-02 | **Which coding agent?** The proposal names "Hermes Primary Model (port 9000) with Hermes Agent" as the AI coding agent; the team's process is built on Claude Code. | The proposal is graded; the process docs assume Claude Code. | (a) Claude Code only — update the proposal/report wording; (b) Claude Code for building + show Hermes in one task for the course; (c) Hermes only | (b) if the course expects Hermes use, else (a) — check the assignment | report wording |
| D-03 | **Course endpoints:** host name, how to reach them (campus network, VPN, public URL), whether a key is needed, API format (OpenAI-compatible?), and the **missing ports** for Structured Decisions, Multimodal Reranking, Text-to-Speech/Voice Cloning, Music, Speech-to-Text. | Every live adapter, CI, Docker networking, and the demo depend on this. | — | Ask the instructor/TA; then run `scripts/smoke_providers.py` (M06) | M06, G02–G04, A07, D06 |
| D-04 | **How does the QA bot pay for Claude?** | The bot runs on every push to every PR. | (a) Anthropic API key with a monthly spend limit; (b) token from `claude setup-token` on Mike's subscription; (c) skip the bot, rely on local review only | (a), with a low monthly cap | M07 |
| D-05 | **Deadlines and deliverables.** The assignment document (rubric, due dates, demo format, report/video requirements) hasn't been shared. | Sets wave dates and what to cut if time is short. | — | Add the assignment document to `docs/assignment/`; Mike maps due dates onto the waves | wave dates |
| D-06 | **Team roster.** Dillon isn't on the proposal; the group letter and last names are placeholders. | The proposal and final report must list the right group. | — | Confirm Dillon's membership with the instructor; fill the group letter and names | report |
| D-08 | **Teammates' GitHub usernames and OS** (Windows, Mac, or both). | Invites, CODEOWNERS, cross-OS testing pairs. | — | Collect in the team channel | M08 |
| D-09 | **Announcer voice.** | Voice cloning needs consent. | (a) a stock TTS voice; (b) clone a teammate's voice with written consent | (a) for MVP; (b) as polish | A07 |
| D-16 | **Where does the demo run?** | The course endpoints must be reachable from that machine and network. | (a) presenter's laptop with Docker; (b) a course VM | (a), plus a recorded backup | G08, demo |
| D-18 | **License for a public repo.** | Without a license, the code is "all rights reserved." | (a) MIT; (b) none | (a) if public, unless the course says otherwise | — |
| D-20 | **Which Hugging Face datasets?** The proposal mentions them but doesn't name any. | Licensing and attribution. | — | Gunnar proposes in G01; Mike approves | G01, G02 |
| D-21 | **Team channel and password manager.** | Review requests; sharing `.env` values if any are secret. | Slack / Teams / Discord; Bitwarden / 1Password | Whatever the team already uses | M08 |

## Decided defaults — change only by PR

| ID | Decision | Reason |
|---|---|---|
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
