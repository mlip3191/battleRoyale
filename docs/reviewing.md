# How to Review a Pull Request (for non-coders)

A **pull request (PR)** is a teammate's proposed change, waiting for someone else to look at it before it joins the project. Reviewing is how we catch mistakes early. You don't need to read code: Claude does the reading, and you make the decisions.

## One-screen checklist

- [ ] Open Claude Code in the repo and type `/review` (or ask: "What can I review?").
- [ ] Pick a PR from **Needs your review**. Not your own: you can never approve your own PR.
- [ ] Wait for the agent's report. It runs the tests on your machine and posts nothing.
- [ ] Read **Acceptance criteria**, **Must fix**, and **Merge recommendation** first.
- [ ] Optional but good: run the app (`npm run dev`) and click through the change.
- [ ] Edit the draft comments if you want, then say **"send"** to post them.
- [ ] Approval is a **separate** question. Approve only if the report says **Ready to merge** and you agree.
- [ ] Anything unclear? Choose **Request changes** or just comment. Never approve to be polite.

## 1. Asking "what can I review?"

Type `/review` or ask Claude "What can I review?". It lists every open PR in groups:

| Group | Meaning |
|---|---|
| **Needs your review** | Not yours, not a draft, and still needs an approval. Start here. |
| **Needs the PM** | Touches critical files (settings, hooks, contracts). Only Mike's approval (or Gunnar's if Mike is away) counts, but you can still comment. |
| **Blocked** | A required check is failing or there are merge conflicts. Reviewing helps; approving waits. |
| **Approved, ready to merge** | The author should merge it. |
| **Your PRs** | Yours. You can't review them; the list shows what you need to fix. |
| **Drafts** | Not ready. Review only if the author asks. |

Each row shows the linked issue, size (+added/−removed lines), check results, the QA bot's verdict, approvals so far, and **what it needs** in a few words. `/review 42` skips the list and reviews PR #42.

## 2. How an agent review works

1. Claude reads the **issue** (the task and its acceptance criteria) and the **change**.
2. It runs the tests and checks on your machine, then returns to your own branch.
3. It drafts comments with **suggested fixes** you can accept with one click on GitHub.
4. **Nothing is posted until you say "send".** You can edit, drop, or add comments first.

If a PR comes from outside the team (a fork), the agent reads it but does not run its code.

## 3. Reading the report

- **What this code does**: a plain-English summary. If it doesn't match the issue, say so.
- **Acceptance criteria**: the issue's checklist, each marked met / not met, with evidence.
- **Must fix**: blocking problems. Any one of them means the PR is not ready.
- **Nits**: small, optional polish.
- **Proposed additional fixes**: extras, marked *in this PR* or *follow-up issue*.
- **Merge recommendation**: Ready to merge, Merge after fixes, or Do not merge, with one reason.

## 4. Checking it yourself in the running app

For anything visible, run `npm run dev`, open http://localhost:5173, and try the feature the PR describes: type a matchup, click the new button, check the page on a narrow window. Backend-only changes show up through the tests; ask Claude "how can I see this working?" and it will suggest a command.

## 5. Approve, request changes, or comment

- **Approve** when the report says Ready to merge, required checks pass, and you agree.
- **Request changes** when there is a must-fix item, or an acceptance criterion isn't met.
- **Comment** when you have questions but no verdict yet.
- **Why you can't approve your own PR:** GitHub ignores self-approval. A second pair of eyes is the whole point. Authors self-check with `/qa` instead.

## 6. QA bot vs. your review

The **QA bot** on GitHub runs automatically when a PR opens, using the same rulebook (`.claude/qa/checklist.md`) and model as `/review`. It is **advisory: it never blocks a merge.** **Your approval** is what lets a PR merge, along with the required checks (CI, Secret scan, Critical files approval).

To ask the bot to look again after new commits, add the **`re-review`** label (anyone can).

**Authors:** run `/qa` on your own branch before opening a PR. It uses the same rulebook, so fixing its must-fix items first means fewer review rounds.

## 7. Re-reviewing

If you reviewed before and the author pushed changes, `/review` treats it as a re-review: it looks only at new commits and tells you whether each earlier comment was addressed.
