# QA checklist — the one rulebook for every review

Every QA review uses this file, whoever runs it:

- the **QA bot** on GitHub (`.github/workflows/ai-qa-review.yml`);
- a reviewer's **/review** (review-prs skill → code-reviewer agent);
- an author's **/qa** self-check on their own branch or PR.

All three use the same checks, severities, and verdict rules, and run on the same model (`sonnet`), so they should reach the same conclusions. They differ only in *where* they run and *what they may do* (see the table at the end). Change this file only through a PM-approved PR. It is a critical file, and the bot always uses `main`'s copy.

## What to check

1. **Issue and acceptance criteria.** Find the linked issue (`Closes #n` in the PR, or the number in a branch named `issue-<n>-…`), run `gh issue view <n>`, and list every acceptance criterion. If the issue names a task ID (e.g. A02), also read that task in `docs/plan/lane-*.md`. Mark each criterion **met** / **not met** / **can't tell**, with evidence (file:line, test name, or pasted output).
2. **The change in context.** Read the whole diff and every touched file in full, plus the contracts in `backend/app/models/` and the relevant sections of `docs/ARCHITECTURE.md`.
3. **Project rules (CLAUDE.md).**
   - No silent contract changes: changes to `backend/app/models/` need the `contract-change` label.
   - Critical files.
   - Cross-platform: path libraries, no bash- or PowerShell-only scripts, lowercase-with-dashes file names.
   - Prompts live in `backend/prompts/`.
   - Only `config.py` reads environment variables.
   - Only `providers/` calls course endpoints.
4. **Battle Royale rules.**
   - **Number rule:** no model-produced number is used without a verified quote. Estimates and assumptions come from code and are labeled. A mythical creature's stats are all `assumption`, built from its analogs. Scripts contain only numbers present in the inputs.
   - **Simulation:** randomness only from the seeded generator; `ENGINE_VERSION` bumped if results change; every new constant is in `constants.py` and `docs/simulation-model.md`.
   - **Providers:** timeouts, retries, and a fallback; a mock exists; tests run in mock mode.
   - **Prompts:** user text delimited as data; media prompts use the allowlisted, brand-free `media_name`; tone is PG.
   - **Safety (DECISIONS D-07, D-38):** nothing lets through real people, minors, groups of people, named fictional characters, deities, firearms, explosives, or weapons of mass destruction. Objects, machines, plants, and mythical creature *types* are allowed.
   - **Front end:** generated API types only; every stat shows a source or an estimate/assumption tag; captions present; reduced motion respected.
5. **Bugs and robustness:** wrong logic, missing error handling or fallbacks, unhandled edge cases from ARCHITECTURE §14, race conditions, performance against the stage budgets.
6. **Security:**
   - Secrets, keys, `.env` files, or course endpoint hosts anywhere (treat the repo as public).
   - Any new `gitleaks:allow` marker or `.gitleaksignore` entry.
   - Unsafe workflows (`pull_request_target` with a checkout, broad permissions).
   - New dependencies: real, popular, correctly spelled?
7. **Tests:** new behavior has tests; no test deleted, skipped, or weakened; a bug fix starts with a failing test.
8. **Size and scope:** over ~300 changed lines, or changes unrelated to the issue → recommend splitting. Merge conflicts with `main`; overlap with other open PRs.

## Severity

**Must fix (blocking):**
- any key, token, password, or `.env` file;
- any new `gitleaks:allow` / `.gitleaksignore` entry without a note that the PM approved it;
- a deleted, skipped, or weakened test;
- a weakened guardrail in `.gitignore`, `.githooks/`, `.github/`, `.claude/`, `CLAUDE.md`, or `.env.example`;
- course endpoint URLs or keys in code;
- a number-rule violation;
- a safety rule that lets a blocked fighter through;
- a bug that breaks an acceptance criterion;
- missing tests for new behavior.

**Needs PM (a note, not must-fix):** new or upgraded dependencies, contract changes, any critical-file change, PRs over ~300 lines.

**Nit:** style, naming, small clarity improvements.

Every must-fix cites file and line, explains why in plain English, and gives the fix: a GitHub ```` ```suggestion ```` block when it fits in the changed lines, otherwise a precise description. Never quote a secret's value; say where it is and that the PM must replace the key.

## Verdict (the same words everywhere)

- **Ready to merge:** zero must-fix items and every acceptance criterion met. Needs PM notes and *pending* checks don't block this.
- **Merge after fixes:** must-fix items or unmet criteria that the author can fix in this PR.
- **Do not merge:** wrong approach, a secret, or scope that needs a new issue.

A *failed* required check (CI, Secret scan, Critical files approval) means a human reviewer can't approve yet. The bot judges the code only and leaves checks to GitHub.

## Where the three differ

| | QA bot (GitHub) | /review (a teammate's PR) | /qa (your own work) |
|---|---|---|---|
| Who | GitHub, automatically | the reviewer | anyone, including the author |
| Runs tests | no (CI does) | yes, locally | yes, locally |
| Posts | advisory comments + verdict | a review, only after "send" | nothing; it's for you |
| Can approve | never | separate confirmation, never your own PR | never |
