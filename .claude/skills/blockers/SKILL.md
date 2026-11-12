---
name: blockers
description: The team's view of Battle Royale's blockers and essential items, ordered by priority (blockers first), then by who's responsible, with your own items first. Use when someone types /blockers or asks "what's blocking us?", "what's left on my list?", "what's on my plate?", or "who needs to do what?". Read-only; posts nothing.
---

# /blockers: essential items and blockers, by priority and owner

Read-only. Nothing gets posted, commented on, or changed unless the user says yes to a specific action afterwards.

## 1. Run the script

From the repo root:

```
python3 -I .claude/skills/blockers/blockers.py
```

On Windows, if `python3` opens the Microsoft Store or isn't found, use `py -3 -I .claude/skills/blockers/blockers.py` (or `python -I …`).

If you're not inside the repo, or `gh` isn't logged in, say so in plain English and stop. Add `--json` to get raw data if you need to reason about it. Add `--as <github-login>` to preview what a teammate sees (the PM uses this to check someone's list). It's a preview only: it doesn't change who `gh` is logged in as, and it still only reads.

The script sorts items like this:
- **🔴 P0, blocking other people's work:** something is waiting on the item. Either open PRs are stacked on it (another PR targets its branch), or issues have "Blocked by #n" pointing at it or at the issue its PR closes. It also catches stacked PRs merged into a branch other than `main` without an approval.
- **🟠 P1, blocking a merge or a decision:** failing required checks, merge conflicts, changes requested, reviews owed, critical files that need the PM, contract changes nobody has approved, needs-pm decisions, and overdue wave issues.
- **🟡 P2, ready to act on / housekeeping:** approved PRs to merge (stacked ones wait for the PR below them), unassigned issues due soon, `status: blocked` issues whose blockers have all closed, and decisions still waiting on something else.
- Within each tier, items are grouped by **who's responsible**: **you** first (marked "(you)"), then the PM (marked "(PM)"), then teammates by name. Within each person, the item blocking the most comes first.

How it decides who's responsible:
- Failing checks, conflicts, or unaddressed feedback: the author.
- A changes request answered with new commits: the reviewer, who needs to re-review.
- Reviews still requested: each reviewer on the list.
- Critical files, contract changes, and needs-pm items: the PM (from the Team table in `docs/DECISIONS.md`).
- An approved PR: its author, to merge it. The PM or the backup may also merge it after an @mention (D-49).

Commits that only merge a base branch in don't count as answering a review.

## 2. Show it

Show the script's output as it is. Then add:

1. **Your top 3 right now:** the three items most worth doing first for the person running it. Pick from their P0 items first, then the ones that unblock the most, then their P1 items. Give one short line each. If they have nothing, say so, and suggest a review someone is waiting on.
2. **Nudges worth sending:** any P0 item owned by someone else that has sat untouched for more than about a day. Name who and which PR or issue.
3. **Anything the script can't see:** if something from earlier in the conversation matters (for example, a reviewer asked for small changes before merging), mention it in one line.

Keep it short. Don't repeat the table in prose.

## 3. Offer next steps (one question; AskUserQuestion if available)

- **Review one:** start `/review <n>` for the top item that's a review for them.
- **Send reminders:** draft one PR or issue comment per person, @mentioning them, with the specific action. Show every draft, and post only after a yes. Write each body to `.claude/tmp/` and use `--body-file` (CLAUDE.md §5).
- **Done for now.**

## Rules
- Never post, label, assign, merge, approve, or close anything from this skill without a separate, explicit yes.
- Merging someone else's PR is for its author, or for the PM or backup after an @mention (D-49). Don't offer it to anyone else.
- Never send the instructor invite. If the person running this is the PM, then on or after Nov 23 remind them to send it themselves at code complete (Nov 25). It must be accepted within 7 days.
- If the schedule changes (DELIVERABLES.md or PROJECT_GUIDE.md §3), update `WAVE_DUE` and `MILESTONES` at the top of `blockers.py` in a PR.
