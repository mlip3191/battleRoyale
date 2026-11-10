# Filing and Tracking Issues

Every piece of work on Battle Royale starts as a GitHub issue that's small enough for one Claude Code session and one pull request. This guide shows you how to file a good issue without knowing how to code. The rules come from [TEAM_PROCESS Step 4](TEAM_PROCESS.md#step-4-github-issues-scaffold).

## The rules in one minute

- One issue = one branch = one pull request.
- An issue is about a day of work or less. Anything bigger is split into smaller issues.
- Every issue has acceptance criteria: checkable statements that say when it's done.
- Before work starts, every issue has one assignee, a type label, and a size label.
- If an issue has to wait for another one, it says so: "Blocked by #12".

## The easy way: `/new-issue`

In Claude Code, type `/new-issue`, followed by what you want in your own words. For example:

```text
/new-issue the results page should show which fighter was the underdog
```

Claude then:

1. **Asks a few short questions**: who it's for, what "done" looks like, and whether it depends on anything. It looks up what it can by itself and warns you if an open issue already covers it.
2. **Picks the right form** (feature, bug, or chore) and writes checkable acceptance criteria.
3. **Suggests labels**: type, size, lane, and wave.
4. **Splits it** into a few smaller issues if it's bigger than about a day, and asks you before drafting them.
5. **Shows you the whole draft**: title, labels, and body, exactly as it will appear on GitHub.
6. **Waits for you.** Answer **yes** to create it, **change something** to edit it, or **cancel** to stop. Nothing is created until you say yes.

Then it gives you the new issue's link. New issues land in **Backlog**.

## The other way: the GitHub website

On GitHub, go to **Issues → New issue** and choose **Feature**, **Bug**, or **Chore**. Blank issues are turned off, so every issue uses a form. Each form adds its type label for you. Acceptance criteria are required in all three forms. You don't need to add size, lane, wave, or an assignee yourself: the PM sets them at triage.

| Form | Use it when | It asks for |
|---|---|---|
| Feature | You want new behavior | User story ("As a ___, I want ___ so that ___"), acceptance criteria, likely files or areas, out of scope, depends on |
| Bug | Something is broken | What happened, what should happen, steps to reproduce, screenshots, acceptance criteria |
| Chore | Docs, process, setup, maintenance | What needs doing, why, acceptance criteria (done when) |

Never paste keys, passwords, or course endpoint hosts into an issue, even inside an error message.

## Writing good acceptance criteria

Good criteria are checks that someone else can answer with a yes or no. Each one names a concrete situation and the result you expect.

| Weak | Good |
|---|---|
| Login works | A user with a valid email and password reaches the dashboard |
| Handle errors | A wrong password shows "Incorrect email or password" and no data is lost |
| Make it fast | The page loads in under 2 seconds on the test data |

Here's a quick test: could a teammate who has never seen your idea tick each box without asking you anything? If not, make it more specific. For bugs, always include "a test reproduces the bug and now passes".

## What each label means

**Type** (exactly one; the forms add it for you)

| Label | Meaning |
|---|---|
| `type: feature` | New behavior or capability |
| `type: bug` | Something is broken |
| `type: chore` | Setup, cleanup, docs, dependencies, process |

**Size** (exactly one; the PM confirms it at triage)

| Label | Meaning |
|---|---|
| `size: S` | A few hours |
| `size: M` | About a day |
| `size: L` | Too big. Split it before anyone starts. `/new-issue` proposes the split for you. |

**Lane** (who owns the area; see [LANES.md](plan/LANES.md))

| Label | Area |
|---|---|
| `lane: mike` | Foundation, integration, evaluation |
| `lane: adam` | Intake, safety, orchestration, media |
| `lane: gunnar` | Research and knowledge base |
| `lane: felipe` | Simulation and analytics |
| `lane: dillon` | Front end and user experience |

**Wave** (when it's planned; see [LANES.md](plan/LANES.md))

| Label | Meaning |
|---|---|
| `wave: 1` | Onboard and setup |
| `wave: 2` | Skeleton |
| `wave: 3` | Core |
| `wave: 4` | Complete |

**Status and special handling**

| Label | Meaning |
|---|---|
| `status: blocked` | Waiting on another issue or a decision. Say which one in the issue. |
| `contract-change` | Changes a shared contract in `backend/app/models/`. Needs PM approval. |
| `needs-pm` | Needs a decision from the PM before work starts |
| `good first issue` | A safe starter task for a new teammate |
| `usability` | A finding from usability sessions (task D10) |
| `accessibility` | A barrier for people with disabilities |
| `re-review` | On a pull request: asks the QA bot to review it again after fixes |

GitHub's built-in labels (`bug`, `enhancement`, `documentation`, `question`, `duplicate`, `invalid`, `wontfix`, `help wanted`) are left over from setup. Use the `type:` labels instead.

## How issues move across the board

The GitHub Project board has five columns:

| Column | What it means | Who moves it |
|---|---|---|
| **Backlog** | Filed, not checked yet | Every new issue starts here |
| **Ready** | Scope, criteria, and size checked | The PM, at weekly triage |
| **In progress** | Someone is working on it | You: assign yourself and move the card when you start |
| **In review** | A pull request is open for it | Automatic, when a PR says `Closes #<n>` |
| **Done** | The PR is merged | Automatic, when the PR merges |

To start an issue, pick one from **Ready**, assign yourself, and move it to **In progress**. Then, in Claude Code, say "Start work on issue #<number>".
