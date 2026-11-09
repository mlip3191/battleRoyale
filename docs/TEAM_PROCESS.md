# Team Process — How We Build Battle Royale

> This is the team's setup and working standard (consolidated from the "Project Setup Guide – Claude Code Team Project"). [PRODUCT_SPEC.md](PRODUCT_SPEC.md) says **what** we build, [ARCHITECTURE.md](ARCHITECTURE.md) says **how it's structured**, and this file says **how we work**. The executable prompts for each step live in the lane files under [plan/](plan/LANES.md).

## How to Use This Guide

1. The assignment document (DECISIONS D-05) defines scope, deliverables, and deadlines. PRODUCT_SPEC.md is our reading of it.
2. This guide defines **how** the team builds: repo setup, rules, review, and workflow. Where any other document conflicts with it on process (branching, review, permissions, cross-platform, secrets), this guide wins.
3. Each step below is implemented by one or more tasks:

| Step | What | Task(s) |
|---|---|---|
| 0 | Repo settings | M01 (all Phase 0 tasks are in INIT.md) |
| 1 | CLAUDE.md | shipped in the repo; finalized in M02 |
| 2 | Branch protection, critical files, PR template | M07, M08 |
| 3 | Reviewer agent and the review-prs skill | shipped; verified in M07; guide in F01 |
| 4 | Issues scaffold | M08 (labels, issues, board), A01 (forms, /new-issue) |
| 5 | Onboarding | README quick start (shipped), D01 (guide + setup check) |
| 6 | CI and cross-platform | M04 |
| 7 | Claude Code settings and hooks | M03 |
| 8 | Secrets and .gitignore | shipped; verified in M02; Secret scan in M07 |
| 9 | QA bot | M07 |
| 10 | Other guardrails | M01, M04, M07, A04 |
| 11 | Team norms | everyone |

## Step 0: Before You Start

The PM sets up the repo and runs Phase 0 alone, in order (INIT.md). Teammates are invited early (task M02) so they can install and read, but start no task and merge nothing until M08 assigns their first issue.

### Order of operations

Phase 0 runs as tasks **M01 → M08** in [INIT.md](../INIT.md), in that order — the single document Mike gives Claude Code. A light ruleset goes on in M02 (pull request required, 0 approvals) so teammates can be invited early; full branch protection is turned on **last** (M08), and a required status check is only added after it has run at least once: GitHub can only select checks it has already seen, and a required check that never reports blocks every merge. While Mike builds the scaffold alone, M02 commits to main directly (M01 has no commit); M03–M08 go through PRs that Mike merges himself until the full rules start in M08.

### Create the repository

The repo exists: **github.com/mlip3191/battleRoyale**, owned by Mike's personal account, and is being made **private** with GitHub Pro (DECISIONS D-01). Task M01 applies these settings:

- [ ] Settings, General, Pull Requests: squash merging only; "Always suggest updating pull request branches" and "Automatically delete head branches" on.
- [ ] Settings, Code security: Dependabot alerts and security updates on. GitHub secret scanning and push protection are **not available** for private repos on personal accounts (they need GitHub Secret Protection on an organization), so the gitleaks **Secret scan** workflow (Step 8) and the local git hook are our secret checks.
- [ ] Settings, Actions, General: only GitHub-made actions plus anthropics/claude-code-action, oven-sh/setup-bun (used inside the Claude action), gitleaks/gitleaks-action, astral-sh/setup-uv; workflow permissions "Read repository contents"; "Allow GitHub Actions to create and approve pull requests" off.
- [ ] A pinned "Team board" issue for announcements and weekly check-ins; review requests go through GitHub's reviewer request (DECISIONS D-21).

Personal-account repos give every collaborator the same Write role, which matches this process. Branch protection on a private personal repo needs **GitHub Pro** (free with the GitHub Student Developer Pack) — turn Pro on before making the repo private, or protection silently stops being enforced. Private repos also use GitHub Actions minutes (Pro: 3,000 a month; Windows minutes count double and macOS ten times), so PR checks run on Linux and Windows, and macOS runs only on demand (before milestones).

### PM prerequisites

- [ ] Claude Code, Git, GitHub CLI, Node 26, and uv installed and logged in on Mike's machine.
- [ ] `.env` filled from `.env.example` with the course endpoint details (DECISIONS D-03).
- [ ] Team handles and OS are recorded in DECISIONS (team table).

## Step 1: CLAUDE.md

[CLAUDE.md](../CLAUDE.md) at the repo root is the rulebook every Claude Code session reads first. It is already written for this project and finalized in task M02. It covers: project overview and stack, commands, folder structure and protected files, coding conventions and approved/banned libraries, rules for working with non-coders, testing, definition of done, commits and PRs, environment and secrets, contracts, and permissions/hooks. Keep it under two pages; when Claude repeats a mistake, add a rule.

## Step 2: Branch Protection and Pull Request Workflow

No one pushes directly to main. Every change goes through a feature branch and a pull request. Any teammate can review and approve; once approved, the author merges it into main.

### GitHub settings (PM does this once)

Task M02 turns on a light ruleset (pull request required, 0 approvals, no force push or deletion) so teammates can be invited early; task M08 tightens it to the rules below. In the repo, Settings, then Rules, then Rulesets:

- [ ] Require a pull request before merging

- [ ] Require at least 1 approval from any teammate other than the author (leave "Require review from Code Owners" off)

- [ ] Require status checks to pass: the four CI checks (backend and frontend on ubuntu-latest and windows-latest, Step 6), "Secret scan" (Step 8), and "Critical files approval" (below). For each, set the expected source to GitHub Actions. The QA bot (Step 9) is **advisory** and is not a required check.

- [ ] Leave **off**: "Dismiss stale approvals", "Require approval of the most recent push", "Require branches to be up to date", and "Require conversation resolution". Each adds re-runs or re-approvals a ten-day project can't afford, and "up to date" re-runs every open PR's CI after each merge, burning Actions minutes (DECISIONS D-26). The trade-off: an author could push after approval, so the norm is to request a fresh look if you push meaningful changes after an approval.

- [ ] Block force pushes and branch deletion

- [ ] Do not allow bypassing these rules, including admins

Also set up:

- [ ] Give every teammate Write access (Settings, Collaborators) so anyone can review and merge. Keep Admin for the PM only.

- [ ] Add a pull request template (.github/pull_request_template.md)

- [ ] Enable "Automatically delete head branches" after merge

- [ ] Use squash merging to keep main history clean

### Team workflow (every task)

1.  Pick an assigned GitHub Issue.

2.  Pull the latest main.

3.  Ask Claude Code to create a branch named issue-\<number\>-short-description.

4.  Work with Claude on that one issue only.

5.  Claude runs tests and lint, then commits.

6.  Claude pushes the branch and opens a pull request linked to the issue ("Closes \#\<number\>").

7.  Any teammate reviews and either requests changes or approves. Once approved, the author merges the pull request into main.

### Review and merge rules

- The author can never approve their own PR; GitHub enforces this.

- Request a reviewer on the PR when it is ready (GitHub notifies them); reviewers aim to respond within one working day.

- If changes are requested, the author fixes them on the same branch, pushes, and re-requests review from the same reviewer. To have the advisory QA bot look again, add the `re-review` label.

- Before merging, the author confirms: approved, all required checks green, and no meaningful pushes since the approval (if there were, ask the reviewer to look again). If GitHub reports a conflict with main, ask Claude to update the branch.

### Protect critical files

Critical files are exactly the root-anchored paths in .github/CODEOWNERS (M07): CLAUDE.md, INIT.md, .claude/, .github/, .githooks/, .gitignore, .gitattributes, .editorconfig, .nvmrc, .env.example, .mcp.json, .gitleaks.toml, .gitleaksignore (it can silence the secret scan), the root scripts/ folder (not backend/scripts/), all package.json/package-lock.json files, backend/pyproject.toml, backend/uv.lock, backend/app/config.py, backend/app/models/, and docs/ARCHITECTURE.md. Two matter most: one changed line in .gitignore or .githooks/ can let a .env file into the repo, and most workflows in .github/ run the PR's own copy, so a teammate's PR could weaken CI or Secret scan for itself. The approval rule depends on who made the change:

| Who changed a critical file | Who must approve                       |
|-----------------------------|----------------------------------------|
| A teammate                  | The PM                                 |
| The PM                      | Any one teammate                       |
| Normal code, anyone         | Any one teammate other than the author |

GitHub's built-in CODEOWNERS rule can't do this. If the PM were the only code owner, the PM's own changes would be blocked, because authors can never approve their own PRs. So the rule is enforced with a small GitHub Action instead:

- [ ] Add .github/CODEOWNERS listing the critical paths with the PM as owner. This only auto-requests the PM as a reviewer; leave "Require review from Code Owners" **off**.

- [ ] Add a workflow, .github/workflows/critical-files.yml, triggered by `pull_request_target` (opened, synchronize, reopened, ready_for_review). That trigger runs **main's** copy of the workflow, so a PR can't weaken the check that guards it; it never checks out the PR's code. If the PR touches a critical file and the author is not the PM, it passes only once the PM — or the backup approver, Gunnar, on a PR he didn't write (DECISIONS D-31) — has approved the latest commit. If the author is the PM, or no critical files changed, it passes right away; the normal one-approval rule covers the rest. Approvals don't re-trigger it, so after the PM approves, the check is re-run (the review-prs skill does this; or click "Re-run jobs").

- [ ] Make "Critical files approval" a required status check on main once it has run once.

- No admin bypass: the PM's own changes still need a teammate's approval.

### When things go wrong

| Situation                                             | What to do                                                                                                                                                                                                                                           |
|-------------------------------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Merge conflict                                        | Ask Claude: "Update my branch from main and resolve the conflicts. Explain each one before you change it." Ask the PM if unsure.                                                                                                                     |
| Branch is behind main                                 | Click "Update branch" on the PR, or ask Claude to pull main into the branch.                                                                                                                                                                         |
| CI check failed                                       | Ask Claude: "Read the failed CI check on PR \#\<number\> and explain what broke."                                                                                                                                                                    |
| Something bad was merged                              | On the merged PR, click "Revert". This opens a new PR that undoes it; review and merge it like any other.                                                                                                                                            |
| Lost work or a confusing git state                    | Stop. Do not run more commands. Comment on your issue and @mention the PM (`@mlip3191`).                                                                                                                                                                              |
| A key, password, or .env file was committed or pushed | Tell the PM right away by direct message, and say where it is without pasting it. The PM revokes and replaces the key first: deleting the file is not enough, because it stays in git history and in the PR. Then follow "If a key leaks" in Step 8. |
| The pre-commit hook or Secret scan blocked you        | Ask Claude: "Explain what the secret check found and move the value into .env." Never use --no-verify. If it is a false alarm, ask the PM to allow-list it.                                                                                          |
| The QA bot flagged problems                           | It's advisory. Read its comment, fix what makes sense on the same branch, push, and add the `re-review` label if you want it to look again. Your reviewer decides; the bot doesn't block merging. If it didn't comment at all, add the `re-review` label or ask the PM.                                              |

## Step 3: Reviewer Agent and the review-prs Skill

Every human review runs through the **review-prs skill** (`.claude/skills/review-prs/SKILL.md`) and the **code-reviewer agent** (`.claude/agents/code-reviewer.md`). A teammate asks Claude Code *"What can I review?"* (or types `/review`, or `/review 42`). No PR can be merged until a teammate has approved after reviewing and the required checks (CI, Secret scan, Critical files approval) pass. The QA bot (Step 9) adds advisory comments.

### How it works

1. **List.** The skill lists open PRs grouped as: *Needs your review*, *Your PRs* (you can't review these), *Needs PM* (touches critical files), *Blocked* (checks failing or conflicts), *Drafts*, and *Approved, ready to merge*. Each row shows title, author, linked issue, size, check status, QA bot verdict, approvals, and age.
2. **Pick.** The reviewer picks a PR. The skill refuses if the reviewer is the author, and asks first if they have uncommitted work.
3. **Agent review.** The code-reviewer agent reads the linked issue, the diff, and every touched file; checks out the branch to run install, lint, and tests; then returns to the reviewer's original branch.
4. **Draft.** It drafts the full review: the report, inline comments on exact lines, a GitHub suggestion block with a fix for every must-fix item, and a list of **proposed additional fixes** (missing tests, edge cases, follow-ups).
5. **Confirm before sending.** The reviewer sees the complete draft and chooses: *Send*, *Edit*, or *Cancel*. Nothing is posted until they say send. Comments are sent as "Comment" or "Request changes".
6. **Confirm before approving.** Only after the comments are posted, and only if the recommendation is *Ready to merge*, the skill asks a second, separate question: *Approve this PR now?* Approval is never automatic.
7. **Follow-ups.** Proposed additional fixes that are out of scope can be turned into new issues (again only after confirmation).

### QA process the agent follows

1.  Read the linked issue and confirm the PR does what it asks, and nothing more.

2.  Read the full diff and the files it touches.

3.  Run install, tests, and lint; record pass or fail.

4.  Check against CLAUDE.md conventions and protected files.

5.  Look for bugs, missing error handling, security issues, and committed secrets.

6.  Check for new dependencies and whether they were approved.

7.  Check whether it conflicts with main or other open PRs.

### Report format

- **What this code does:** plain-English summary for non-coders

- **Must fix (blocking):** bugs, failing tests, security issues, scope creep

- **Nits (optional):** style, naming, small cleanups

- **Other considerations:** risks, missing tests, docs to update

- **Proposed additional fixes:** improvements beyond the must-fix list, each with a suggested change or a proposed follow-up issue

- **Dependencies:** does this block or depend on other issues or PRs?

- **Merge recommendation:** Ready to merge / Merge after fixes / Do not merge, with one-line reason

### Reviewer agent rules

- If the person running /review is the PR's author, the agent stops and says a different teammate must review. Authors use /qa instead (below).

- The agent checks out the PR branch with gh pr checkout to run tests, and switches back to the reviewer's original branch afterwards. If the reviewer has uncommitted work, it stops and asks first.

- If CI checks are still running or failing, the report says so, and the recommendation cannot be "Ready to merge".

- If the PR is over about 300 changed lines or touches unrelated areas, it recommends splitting.

- Every "must fix" item cites the file and line, explains why in plain English, and includes a suggested fix.

- The agent never approves a PR with a failing test, a committed secret, or an unmet acceptance criterion, and never approves without the reviewer's explicit second confirmation.

- If the reviewer edits the draft, the agent submits the edited version.

### /qa — check your own work first

Anyone can run `/qa` on their own branch (before a PR exists) or on any PR number, including their own. It runs the same code-reviewer agent in self-check mode, against the same rulebook (`.claude/qa/checklist.md`) and on the same model as the QA bot, so what it finds is what the bot and your reviewer will find. It runs the tests locally, shows the report, and posts nothing. Then it offers to fix the must-fix items on your branch (with the usual explain-then-yes). Habit: **run /qa before you open a PR, and again before asking for a re-review.**

Three layers, one rulebook: /qa is the author's self-check; /review is the human reviewer's tool and the gate; the QA bot in Step 9 runs the same checklist on GitHub when a PR opens (or on the `re-review` label, which anyone can add) and posts advisory findings.

## Step 4: GitHub Issues Scaffold

Every piece of work starts as a GitHub Issue small enough for one Claude Code session and one pull request.

### Issue rules

- One issue = one branch = one PR.

- An issue should take roughly a day or less; anything bigger is split into smaller issues.

- Every issue has acceptance criteria written as checkable statements.

- Every issue has one assignee, a type label, and a size label before work starts.

- Blocked or dependent issues name the issue they depend on ("Blocked by \#12").

### Who does what

- Anyone can create issues with /new-issue; they land in Backlog.

- The PM triages weekly: checks scope and criteria, sets size, and moves ready issues to Ready.

- Teammates pick from Ready, assign themselves, and move the card to In progress.

### Good vs. weak acceptance criteria

| Weak          | Good                                                                     |
|---------------|--------------------------------------------------------------------------|
| Login works   | A user with a valid email and password reaches the dashboard             |
| Handle errors | A wrong password shows "Incorrect email or password" and no data is lost |
| Make it fast  | The page loads in under 2 seconds on the test data                       |

### Labels

| Label            | Meaning                             |
|------------------|-------------------------------------|
| type: feature    | New functionality                   |
| type: bug        | Something is broken                 |
| type: chore      | Setup, cleanup, docs, dependencies  |
| size: S          | A few hours                         |
| size: M          | About a day                         |
| size: L          | Too big; split before starting      |
| status: blocked  | Waiting on another issue            |
| good first issue | Safe starter task for new teammates |

### Issue templates

- **Feature:** user story ("As a \_\_\_, I want \_\_\_ so that \_\_\_"), acceptance criteria checklist, files or areas likely affected, out of scope, depends on.

- **Bug:** what happened, what should happen, steps to reproduce, screenshots, acceptance criteria.

- **Chore:** what needs doing, why, done-when checklist.

### Board

A GitHub Project board with columns: Backlog, Ready, In progress, In review, Done. Issues move to In review automatically when a PR is linked, and to Done when it merges.

## Step 5: Teammate Onboarding

Each teammate goes from zero to a first merged pull request on day one.

### 1. Accounts and access

- [ ] GitHub account created, with two-factor authentication on

- [ ] Invited to the repo with Write access

- [ ] Claude plan that includes Claude Code

- [ ] The course endpoint URLs, ports, and keys (everyone has them) for your `.env`

### 2. Installs

- [ ] Git

- [ ] GitHub CLI, then run gh auth login

- [ ] Claude Code

- [ ] VS Code (or another editor)

- [ ] Optional: gitleaks (the secret checker): Homebrew on Mac, winget on Windows. Without it the hook uses its built-in checker (DECISIONS D-08). The setup check script prints the exact command.

- [ ] Project runtime: Node 26 (via fnm or nvm-windows) and uv (it installs Python 3.12 for you)

OS-specific setup:

| Item                    | Windows                                                                | Mac                                                           |
|-------------------------|------------------------------------------------------------------------|---------------------------------------------------------------|
| Git                     | Git for Windows (includes Git Bash, which Claude Code uses on Windows) | Xcode Command Line Tools (xcode-select --install) or Homebrew |
| Package installer       | winget                                                                 | Homebrew                                                      |
| Runtime version manager | fnm or nvm-windows (Node); uv (Python)                                | fnm or nvm (Node); uv (Python)                                   |
| Terminal                | PowerShell or Windows Terminal                                         | Terminal                                                      |
| Extra setting           | git config --global core.longpaths true                                | none                                                          |

Everyone, once: set your name and email with git config --global user.name and user.email, using the same email as your GitHub account.

People on two computers repeat the installs on both, log in to GitHub and Claude Code on both, and follow the switching rules in Step 6.

### 3. First run

1.  Clone the repo.

2.  Run the setup check script. It also switches on the team's shared git hook (git config core.hooksPath .githooks), which blocks commits that contain keys.

3.  Copy .env.example to a new file named .env and fill in every [required] line with the course endpoint values; check with node scripts/check-env.mjs.

4.  Open Claude Code in the repo folder and ask it to read CLAUDE.md and explain the project in plain English.

5.  Ask Claude to install dependencies, start the app, and run the tests.

6.  Confirm the app runs and tests pass; if not, comment on your issue and @mention the PM.

### 4. Practice loop

1.  Pick a "good first issue" and assign it to yourself.

2.  Ask Claude to create the branch and make the change.

3.  Ask Claude to open the pull request.

4.  Run /review on a teammate's PR to practice reviewing.

5.  Once your PR is approved, merge it.

### 5. Cheat sheet

| You want to...     | Type in Claude Code                                |
|--------------------|----------------------------------------------------|
| Start a task       | "Start work on issue \#\<number\>"                 |
| Create a new issue | /new-issue                                         |
| Review a PR        | "What can I review?" or /review \<PR number\>|
| Check my own work  | /qa (current branch) or /qa \<PR number\>     |
| Get latest code    | "Pull the latest main"                             |
| Undo something     | "Undo your last change and explain what you undid" |
| Ask for help       | "Explain what this does in plain English"          |

## Step 6: CI and Cross-Platform Consistency

Every PR is tested automatically on Windows and Linux (macOS runs only on demand — Mike triggers it before each milestone — to save Actions minutes; Mike also tests Mac by hand), and the repo is set up so the same code and commands work on any machine, including one person switching between a Windows PC and a Mac.

### CI with GitHub Actions

- A workflow runs on every PR and every push to main (Linux + Windows), plus macOS on demand.

- On PRs it runs install, lint, typecheck, tests, and the production build on windows-latest and ubuntu-latest (4 required checks). On pushes to main it runs the same on Linux and Windows; macOS runs only when triggered by hand (`gh workflow run ci.yml --ref main -f os=macos-latest`), before each milestone. It also fails if generated API types or synced fixtures are stale.

- Linux and Windows are required status checks, so a PR that breaks on either cannot merge. No `paths:` filters on required workflows: a skipped required check waits forever and blocks the merge.

- Runtime version comes from the repo's version file, so CI matches local machines.

### Cross-platform rules

| Problem                                       | Fix                                                                                                              |
|-----------------------------------------------|------------------------------------------------------------------------------------------------------------------|
| Windows and Mac save line endings differently | .gitattributes with \* text=auto eol=lf, plus exceptions for .bat/.cmd (CRLF)                                    |
| Editors format differently                    | .editorconfig for indentation, line endings, final newline, UTF-8                                                |
| Different runtime versions                    | Pin the version in a file (.nvmrc, .python-version, or engines) and use a version manager                        |
| Different dependency versions                 | Commit the lockfile; install with the lockfile-respecting command (e.g. npm ci)                                  |
| Shell scripts only work on Mac                | All project commands are cross-platform scripts in the package manager or Python, never bash- or PowerShell-only |
| File paths break                              | Build paths with the language's path library; never hard-code / or \\                                            |
| Case-sensitive filenames                      | Never have two files differing only by case; keep names lowercase-with-dashes                                    |
| Secrets and local settings                    | .env.example committed; real .env ignored; same variable names on every OS. Full setup in Step 8.                |
| OS junk files                                 | .gitignore covers .DS_Store, Thumbs.db, desktop.ini, and editor folders (Step 8)                                 |


### Switching between machines

1.  Before leaving a machine: ask Claude to commit and push your branch.

2.  On the other machine: ask Claude to pull your branch and run the install command.

3.  Never copy project files between computers by hand; always go through GitHub.

## Step 7: Shared Claude Code Settings, Permissions, and Hooks

CLAUDE.md tells Claude the rules; settings and hooks enforce them, so a non-coder cannot accidentally approve something dangerous.

### What gets committed vs. kept local

| File                        | Committed?      | Purpose                                    |
|-----------------------------|-----------------|--------------------------------------------|
| CLAUDE.md                   | Yes             | Project rules for every session            |
| .claude/settings.json       | Yes             | Team-wide permissions and hooks            |
| .claude/agents/             | Yes             | Shared agents, e.g. code-reviewer          |
| .claude/commands/           | Yes             | Shared slash commands: /review, /qa, /new-issue |
| .claude/settings.local.json | No (gitignored) | Personal overrides on one machine          |
| CLAUDE.local.md             | No (gitignored) | Personal notes for Claude                  |

### Permissions

- **Allow without asking:** reading files, running the project's install, test, lint, and run scripts, git status, diff, log, branch, checkout, add, commit, pull, push of the current branch, and read-only gh commands.

- **Always ask:** installing new packages, editing config files, any gh command that writes (creating PRs, issues, reviews).

- **Deny:** reading .env and secret files, git push --force, git reset --hard, deleting branches, pushing to main, recursive deletes, commands that use sudo or admin rights, git add -f or --force, git commit --no-verify, changing core.hooksPath, and printing environment variables (printenv, env). Also set "disableBypassPermissionsMode": "disable" so no one can switch Claude into skip-all-permissions mode.

- **Watch out:** a Read deny rule only blocks Claude's file-reading tool. It does not stop a shell command like cat .env, or a script that prints the file. So also deny the shell forms (cat, type, more, head, tail, grep, Get-Content on .env files) and add the secret-file hook below. Where Claude Code's sandbox is supported, turning it on adds OS-level blocking.

- **List .env files by exact name** (.env, .env.local, .env.\*.local, .env.development, .env.production, .env.test), not .env.\*: deny always beats allow, so a .env.\* rule would also block .env.example, which Claude needs to read.

### Hooks

- **Block commits on main:** before any git commit, if the current branch is main, stop and tell the user to create a feature branch.

- **Auto-format:** after Claude edits a file, run the formatter on it.

- **Secret guard:** before git commit, confirm core.hooksPath is set to .githooks (and set it if not), so the shared secret check from Step 8 always runs.

- **Secret-file guard:** before any shell command, block it if it mentions a .env file other than .env.example, or a key file such as \*.pem, and tell the user Claude isn't allowed to read secrets.

- Hooks must be written as cross-platform scripts (same language as the project scripts), not bash-only.

## Step 8: Secrets, Keys, and .gitignore

A leaked key can't be un-leaked. Once it is pushed, assume someone has it, even in a private repo, and replace it. The team uses four layers so one mistake is caught by the next.

| Layer                                    | What it catches                                                                                               | Can it be skipped?                                           |
|------------------------------------------|---------------------------------------------------------------------------------------------------------------|--------------------------------------------------------------|
| 1\. .gitignore                           | Stops .env and key files from being added at all                                                              | Yes, with git add -f (Claude is blocked from this in Step 7) |
| 2\. Claude Code rules and hooks (Step 7) | Stops Claude from reading, printing, or force-adding secrets                                                  | Only by changing .claude/, a critical file                   |
| 3\. Shared pre-commit hook               | Blocks any commit, from any tool, that contains a .env file, a key file, key-shaped text, or a file over 5 MB | Yes, with --no-verify (banned) or if never switched on       |
| 4\. Secret scan on GitHub                | Scans every commit in every PR on GitHub's servers                                                            | No: a PR can't merge until it passes                         |

### How the .env files work

- **.env** holds the real values on each person's machine. It is never committed.

- **.env.example** is committed. It has the same variable names, placeholder values, and a comment for each.

- Everyone already has the course endpoint values (DECISIONS D-03) and keeps them only in their own `.env`. Never in issues, PRs, commits, email, or Claude chats.

- Where the provider allows it, each person gets their own key, so a leak means one key to replace and usage is traceable.

- Every key has a spend or usage limit set at the provider.

- Deployment secrets live in GitHub Actions secrets or the host's settings, never in a file.

### The .gitignore, section by section

The full annotated file is the repo's root .gitignore. Commit it first, before anyone creates a .env.

| Section                        | What it covers                                                                                                                                 | Why                                                                                                     |
|--------------------------------|------------------------------------------------------------------------------------------------------------------------------------------------|---------------------------------------------------------------------------------------------------------|
| 1\. Secrets and environment    | .env, .env.\*, \*.env, private keys (\*.pem, \*.key, \*.p12, id_rsa), cloud credential JSON files, secrets folders, infrastructure state files | The core of this step. A pattern with no slash matches in every folder, so backend/.env is covered too. |
| Exceptions                     | !.env.example, !.env.sample, !.env.template                                                                                                    | Templates stay committed. The "!" lines must come after .env.\*; order matters.                         |
| 2\. Claude Code personal files | .claude/settings.local.json, CLAUDE.local.md                                                                                                   | Personal overrides stay local; the shared .claude/ folder stays committed.                              |
| 3\. Local data and logs        | \*.log, \*.db, \*.sqlite, dumps, tmp/                                                                                                          | Logs and local databases often contain tokens or real user data.                                        |
| 4\. OS junk                    | .DS_Store, Thumbs.db, desktop.ini                                                                                                              | Mac and Windows add these silently.                                                                     |
| 5\. Editors                    | .vscode/\* except extensions.json, .idea/, swap files                                                                                          | Personal settings stay local; recommended extensions are shared.                                        |
| 6-7. Node and Python           | node_modules/, build output, virtual environments, caches, coverage                                                                            | Generated files. Keeping both sections is harmless.                                                     |
| Never ignored                  | Lockfiles, CLAUDE.md, .claude/settings.json, .env.example, .mcp.json                                                                           | Lockfiles keep everyone on identical versions (Step 6).                                                 |

### Rules that trip people up

- .gitignore does not untrack a file that was already committed. If one slips in, run git rm --cached \<file\>, commit, and treat any key in it as leaked.

- Deleting a file in a later commit doesn't remove it from history or from the PR's commits, and squash merging doesn't either. Replace the key first.

- Never ignore the whole .claude/ folder, and never ignore lockfiles.

- .mcp.json is committed, so reference keys as ${VARIABLE_NAME}. Never paste the key into it.

- Don't rely on anyone's personal global gitignore; the repo file must cover everything.

- To check: git check-ignore -v .env shows which rule ignores .env. git ls-files --cached --ignored --exclude-standard must print nothing; anything it lists was committed before it was ignored.

### The shared pre-commit hook

A git hook runs on every commit however it is made: Claude Code, VS Code, GitHub Desktop, or the terminal. The hook lives in the repo at .githooks/pre-commit so everyone runs the same one, and the setup check script switches it on for each clone with git config core.hooksPath .githooks. Git for Windows runs hooks with its own built-in shell, so the same file works on Windows and Mac.

- Blocks .env and key files by name, even if someone force-added them.

- Blocks added lines that look like keys. It uses gitleaks if installed, otherwise a built-in list of common formats (Anthropic, OpenAI, AWS, GitHub, Google, Slack, Stripe, private keys, and long quoted passwords).

- Blocks files over 5 MB.

- Names the file but never prints the key, so the key doesn't end up in a terminal log or a Claude chat.

- For a false alarm, the PM adds "gitleaks:allow" in a comment at the end of that line, or adds it to .gitleaksignore. Only the PM may add these: `.gitleaksignore` is a critical file, and the QA bot and reviewers flag any new `gitleaks:allow` marker as must-fix unless the PR says the PM approved it.

- Mark the hook as executable in git (git update-index --chmod=+x .githooks/pre-commit) so it runs on a Mac even when it was committed from Windows.

### Secret scan on GitHub

Local hooks can be skipped or never switched on, so a workflow (.github/workflows/secret-scan.yml, installed from setup/templates/ in task M07) checks every PR on GitHub. It blocks .env and key files by name, then runs gitleaks over every commit in the PR. Make "Secret scan" a required check (Step 2).

- This repo belongs to a personal account, so gitleaks needs no license key. (An organization-owned repo would need a free key saved as GITLEAKS_LICENSE.)

- GitHub push protection isn't available for this private personal repo, so a key is only caught after it is pushed (by Secret scan) unless the local hook stops it first. That makes the hook (`npm run doctor` checks it is on) essential, and any leak means replacing the key.

### If a key leaks

1.  Tell the PM right away by direct message. Say where the key is; don't paste it.

2.  The PM revokes the key at the provider and creates a new one before doing anything else. Assume it is compromised, even in a private repo.

3.  The PM checks the provider's usage page for anything unexpected.

4.  Remove the file or line in a new commit and add any missing .gitignore rule.

5.  Only if the key can't be revoked: the PM rewrites history (git filter-repo) and asks GitHub Support to clear cached PR views. Otherwise, replacing the key is enough.

6.  Add a rule to CLAUDE.md or the hook so the same mistake is caught next time.

## Step 9: QA Bot (Advisory Automated Review)

The QA bot runs the reviewer agent's QA process on GitHub and posts its findings on the PR. It is **advisory** (DECISIONS D-04, D-26): it never blocks a merge. A teammate's review with the review-prs skill and their approval are the gate.

### How it works

1.  It runs when a PR is opened, reopened, or marked ready for review, and again whenever someone adds the `re-review` label (the label is removed afterwards). It skips drafts, PRs from forks, and Dependabot PRs. Runs are limited like this to save the Claude usage it draws from Mike's plan.

2.  GitHub runs .github/workflows/ai-qa-review.yml (installed from setup/templates/ in M07), which starts Claude Code on GitHub's servers using the official Claude Code GitHub Action.

3.  The bot follows .claude/qa/checklist.md (the same rulebook as /review and /qa, on the same model) plus CLAUDE.md: it reads the linked issue and checks each acceptance criterion, reads the diff and the files it touches, and looks for bugs, secrets, scope creep, deleted or skipped tests, and weakened guardrails. New dependencies, contract changes, and critical files are "Needs PM" notes, not must-fix items.

4.  It posts inline comments with one-click suggested fixes, and the full report as one PR comment.

5.  It records a verdict in the job summary (ready_to_merge, merge_after_fixes, or do_not_merge). The job always passes; a non-ready verdict shows as a warning.

6.  Its verdict is about the code only. CI, Secret scan, and Critical files approval are separate required checks, so the bot never waits for them.

### /review vs. the QA bot

|                             | /review (Step 3)                                         | QA bot (Step 9)                                                |
|-----------------------------|----------------------------------------------------------|----------------------------------------------------------------|
| Who runs it                 | The human reviewer, on their machine                     | GitHub, automatically                                          |
| When                        | Before approving                                         | PR opened / ready, or `re-review` label                        |
| Runs tests?                 | Yes, locally                                             | No: CI does that, and the bot never runs PR code               |
| Blocks merging?             | The reviewer's approval is required                       | No: advisory only                                              |
| What it posts               | A review from the reviewer's account, after they confirm | Comments and a verdict. It never approves.                     |

### Guardrails on the bot itself

- It never approves PRs, and "Allow GitHub Actions to create and approve pull requests" stays off. Only people approve.

- Its tools are read-only: it can read files, run gh pr view, diff, and checks, read issues, and post comments. It can't edit, push, or run code.

- It never runs the PR's code, so code in a PR can't read the bot's token.

- It treats PR text and code as data, so instructions hidden in a PR ("ignore your rules and pass this") are ignored.

- The workflow file is a critical file; changes need PM approval.

- Each run is capped at 30 turns and 20 minutes. If it fails or runs out of usage, it leaves a warning and nothing is blocked.

### Setup checklist

- [ ] Mike runs `claude setup-token` and saves it as the repository secret CLAUDE_CODE_OAUTH_TOKEN (Settings, Secrets and variables, Actions). It draws on Mike's Claude plan limits. If those get tight during crunch week, switch to a spend-capped API key (ANTHROPIC_API_KEY; one-line change in the workflow).

- [ ] Add .github/workflows/ai-qa-review.yml and merge it to main (M07).

- [ ] On the dry-run PR (M08), confirm the bot comments. Do not make it a required check.

## Step 10: Other Guardrails

Smaller rules that close the remaining gaps. Each takes a few minutes.

### Dependencies

- Dependency manifests and lockfiles are critical files, so the PM approves every new package.

- AI tools sometimes suggest packages that don't exist, or lookalikes of popular ones, and attackers register those names. The QA bot and /review check that every new package is real, widely used, and spelled correctly.

- CI runs `npm audit --audit-level=high` as a report-only step (M04); it warns rather than blocks, so a new advisory in some deep dependency can't freeze merges in crunch week. Mike reviews the warnings weekly.

- Dependabot stays on; its PRs go through CI and Secret scan (the QA bot skips them), and lockfile changes need Mike's approval through the critical-files check.

### GitHub Actions

- The default workflow token is read-only, and each workflow asks only for the access it needs (the provided workflows already do).

- Only actions made by GitHub plus the ones this guide uses are allowed (Step 0).

- Only one workflow uses `pull_request_target`: the critical-files check, which never checks out PR code and only reads the PR through the API. No other workflow may use it, because combined with checking out PR code it would give that code access to repository secrets.

- If the app is deployed from GitHub, deploy secrets live in a GitHub Environment named production, with the PM as required reviewer.

### Accounts and access

- Two-factor authentication is expected of everyone. A personal-account repo can't enforce it (that needs an organization), so the PM checks it during onboarding.

- Everyone has Write; only the PM has Admin (Step 2).

- When someone leaves, their access is removed the same day and the PM replaces every key they had.

### Tests and data

- The QA bot flags any deleted, skipped, or weakened test as must fix. CLAUDE.md already forbids it; now it is checked.

- Optional: a coverage floor in CI, so total test coverage can't drop below today's level.

- No real personal data in test fixtures, sample data, screenshots, or Claude chats; use made-up data.

## Step 11: Team Norms and Maintenance

The scaffold stays healthy only if the team keeps the habits and the PM keeps the rules current.

### Team norms

- One short check-in a week (as a comment on the pinned Team board issue): what I finished, what I am on, what is blocking me.

- Request a reviewer on every PR when it is ready for review.

- Ask early: if stuck for more than 30 minutes, comment on your issue and @mention the PM.

- Never share API keys or passwords in chat, issues, or PRs; everyone keeps the course values only in their own `.env`.

- Each person uses their own Claude account; watch usage limits and tell the PM if you run out.

### Keeping the scaffold up to date

- Changes to CLAUDE.md, .claude/, .github/, .githooks/, or .gitignore go through a normal PR like any other change.

- When Claude repeatedly makes the same mistake, add a rule to CLAUDE.md to prevent it.

- Review CLAUDE.md monthly and keep it under two pages; remove rules nobody needs.

- Merge Dependabot PRs after CI and Secret scan pass (Mike approves; lockfiles are critical files).

- When someone leaves the team, remove their access the same day, and the PM replaces every key they had.

- Replace shared keys at the end of the project, and review the collaborator list monthly.

### Open decisions

All open decisions are tracked in [DECISIONS.md](DECISIONS.md).
