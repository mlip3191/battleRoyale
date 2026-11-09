---
description: Run the same QA review the GitHub bot runs, on your own branch or any PR — including your own. Shows the report only; posts nothing.
argument-hint: "[PR number]"
---

Run a **self-check QA review** using the code-reviewer agent (`.claude/agents/code-reviewer.md`) in **MODE: self-check**. It follows `.claude/qa/checklist.md`, the same rulebook the GitHub QA bot uses.

PR number given: "$ARGUMENTS"

1. **What to review:**
   - If a PR number was given, review that PR (yours or anyone's).
   - Otherwise, review the current branch against `origin/main` (run `git fetch origin main` first).
   - If the current branch is `main`, stop and say there's nothing to check.
2. **Before running anything:** if `git status --porcelain` isn't empty, say so. Review the committed work only, and mention the uncommitted files. Don't stash or commit without a yes.
3. **Run the agent** with: MODE self-check, the PR number or branch name, `REPO` (`gh repo view --json nameWithOwner -q .nameWithOwner`), `ME` (`gh api user -q .login`), `START_BRANCH`, and running code allowed (unless the PR is from a fork). If subagents aren't available, follow the agent file yourself.
4. **Show the report** in full, with its must-fix items, nits, and verdict. Say plainly: "This is the same check the QA bot will run on GitHub. Nothing was posted."
5. **Then offer, as one question (AskUserQuestion if available):**
   - **Fix the must-fix items on my branch.** Only on your own branch, never someone else's PR. Follow CLAUDE.md §5: explain the plan, wait for a yes, make the fixes, run `npm run check`, commit. Then offer to run /qa again.
   - **Open or update the PR.** Only when the verdict is "Ready to merge", or the user says to go ahead anyway.
   - **Done for now.**
   - If the PR isn't yours, offer `/review <n>` instead of fixing. That's how feedback gets posted to its author.

Rules: never post comments or reviews, never approve, never push to someone else's branch, and never quote a secret's value. /qa doesn't replace a teammate's review; a teammate's approval is still what lets a PR merge.
