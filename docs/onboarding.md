# Onboarding: from nothing to your first PR

This guide is for teammates who don't write code every day. Follow it top to bottom once. It works on Windows and Mac; where they differ, both are shown. If you get stuck, ask Claude Code: *"I'm on step X of docs/onboarding.md and this happened: …"*

## 1. Accounts and access

- [ ] **GitHub account** with two-factor authentication on (GitHub → Settings → Password and authentication).
- [ ] **Repo invite accepted.** Send Mike your GitHub username and whether you're on Windows or Mac. Accept the invite from your email or https://github.com/notifications.
- [ ] **A Claude plan that includes Claude Code** (Pro or Max).
- [ ] **The course endpoint list** (host and API key). You'll type these into one command in step 3. Never paste the key into a chat, issue, PR, or file other than `.env`.

## 2. Installs

Install each one, then **open a new terminal** and run its check. Windows: use PowerShell or Windows Terminal. Mac: use Terminal.

| Tool | Windows | Mac | Check (expect a version) |
|---|---|---|---|
| Git | [Git for Windows](https://git-scm.com/download/win) (includes Git Bash, which Claude Code uses) | `xcode-select --install` | `git --version` |
| GitHub CLI | `winget install GitHub.cli` | `brew install gh` | `gh --version`, then run `gh auth login` |
| Claude Code | [Install guide](https://docs.claude.com/en/docs/claude-code/setup) (or use the Claude desktop app's Code tab) | same | `claude --version` |
| VS Code (or any editor) | [code.visualstudio.com](https://code.visualstudio.com) | same | opens |
| Node 26 | [nodejs.org](https://nodejs.org) LTS installer, or [nvm-windows](https://github.com/coreybutler/nvm-windows) / [fnm](https://github.com/Schniz/fnm) | nodejs.org installer, or `brew install fnm` then `fnm install 26` | `node --version` → `v26.x` |
| uv (installs Python 3.12 for you) | `winget install astral-sh.uv` | `brew install uv` | `uv --version` |
| gitleaks (optional secret scanner) | `winget install gitleaks` | `brew install gitleaks` | `gitleaks version` |

On the Node installer's "Tools for Native Modules" screen, leave the box **unchecked**; this project doesn't need those tools.

Once, on any computer:

```
git config --global user.name "Your Name"
git config --global user.email "the-email-on-your-github-account@example.com"
```

Windows only: `git config --global core.longpaths true`

## 3. First run

1. **Get the code:**
   ```
   git clone https://github.com/mlip3191/battleRoyale.git
   cd battleRoyale
   ```
2. **Install the project:** `npm run setup` (installs everything from the lockfiles and turns on the commit guard that blocks keys).
3. **Add your course key, in your own terminal, never in a chat:** `npm run env:setup`. It asks for the course host and API key (the key is hidden while you type or paste) and writes `.env`. In Claude Code, `/setup-env` walks you through it.
4. **Check the key file:** `npm run env:check`. Repeat step 3 until it says "All required values are filled in." It never shows your values.
5. **Check your whole setup:** `npm run doctor`. Every line should say `ok`. Lines marked `--` are optional. Each `!!` line has a **Fix:** under it; do it and run the doctor again.
6. **Run the app:** `npm run dev`, then open http://localhost:5173. (`npm start` runs the finished version at http://localhost:8000.)
7. **Meet the project:** run `claude` in the folder (or open the folder in the desktop app's Code tab) and say: *"Read CLAUDE.md and docs/PROJECT_GUIDE.md and explain the project to me in plain English."*

## 4. The practice loop

Every change follows the same loop. Claude Code does the typing; you make the decisions.

1. **Pick an issue** assigned to you on the project board.
2. **Start it:** *"Start work on issue #n."* Claude makes a branch named `issue-<n>-short-description`, explains its plan, and waits for your yes.
3. **Change and check:** Claude makes the change and runs `npm run check` (lint, types, tests, build). It won't commit if that fails.
4. **Open a PR** that says `Closes #n` and explains the change in plain English. CI, the Secret scan, and the advisory QA bot run on it.
5. **Get a review:** your default reviewer is in docs/plan/LANES.md ("Review pairing"). Fix what they ask, then merge once they approve and all checks pass.
6. **Review someone else:** *"What can I review?"* or `/review <n>`. Nothing is posted until you say send.

## 5. Cheat sheet: what to say to Claude Code

| You want to… | Say |
|---|---|
| Start your task | "Start work on issue #n." |
| Report a bug or idea | `/new-issue` |
| Review a teammate's PR | "What can I review?" or `/review <n>` |
| Check your own work before a PR | `/qa` |
| Get the latest code | "Pull the latest main." |
| Undo your last change | "Undo your last change and explain what you undid." |
| Understand something | "Explain this in plain English." |
| Set up or fix your key | `/setup-env` (then run `npm run env:setup` in your own terminal) |
| Check your machine | "Run npm run doctor and explain anything that isn't ok." |

**Never:** paste a key into a chat, work directly on `main`, or skip a failing check. If something looks like a real key in the code, stop and tell Mike.
