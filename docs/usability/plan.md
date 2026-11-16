# Usability sessions: plan and script (D10)

We're testing the app with 3–5 people from outside the team (friends, family, classmates not in our group). The goal is to find out where a first-time user gets stuck, confused, or bored, and to turn each problem into an issue before the feature freeze (end of Sun Nov 22).

- **Length:** about 15 minutes per session.
- **Who runs it:** one teammate as the facilitator. The facilitator reads the script, watches, and takes notes. They don't help unless the tester is stuck for more than a minute.
- **Where:** in person at the facilitator's computer, or over a video call. On a call, the facilitator shares their screen and clicks where the tester tells them to.
- **Mode:** live mode (`npm run env:setup` done, `npm start`). Task 3 needs live mode, because mock mode never asks a clarifying question. If live mode is down, run in mock mode, skip task 3, and note it.
- **No personal data:** don't record names, ages, emails, faces, or voices. Testers are "T1" to "T5" in the notes. Don't take screen recordings with the tester's face or voice.

## Before each session (2 minutes)

1. Start the app and open http://localhost:8000 in a fresh browser window.
2. Check that the home page loads and the studio status is OK.
3. Have a notes sheet ready (below), one per tester.

## Script (read this out)

> Thanks for helping. This is a web app our class team built. You name two fighters, and it works out who would win using real animal facts, then shows the fight as a cheesy sports broadcast.
>
> We're testing the app, not you. There are no wrong answers. If something is confusing, that's exactly what we want to find.
>
> Please think out loud as you go: say what you're looking for, what you expect to happen, and what surprises you. I'll mostly stay quiet. I won't record your name or anything personal.

## The five tasks

Read each task out, then watch. Don't point at the screen or name the button.

| # | Say this | It's done when | Watch for |
|---|---|---|---|
| 1 | "Start a battle using one of the examples on the page." | A battle starts from an example chip. | Do they see the examples? Do they know they have to confirm on tonight's card? |
| 2 | "Now type a matchup of your own: any two animals you like." | Their own battle starts, or they get a clear message about why not. | Do refusals or "no stat sheet" messages make sense to them? Do they know what to type? |
| 3 | "Type: *a bear vs 6 gray wolves in a forest*, and follow what it asks." | They answer the quick question and the battle starts. | Do they understand why it's asking? Do they use a button or type? |
| 4 | "After the fight, find out where one of the numbers came from." | They find a stat's source or tag (source, estimate, derived, assumption). | Do they find the results page and sources? Do the tags mean anything to them? |
| 5 | "Start the next challenger battle." | The next challenger fight starts. | Do they find the next challenger section? Is "Fight them!" clear? |

While they watch the broadcast, note whether they skip, mute, or wait it out, and anything that makes them laugh.

## The five questions (after the tasks)

1. What confused you?
2. What made you laugh?
3. Would you trust the verdict? Why or why not?
4. Would you share a result with a friend?
5. What's missing?

## Notes sheet (copy once per tester)

```text
Tester: T_     Date: ___     Mode: live / mock     In person / call

Task 1 (example):      done / done with help / gave up    time: ___
  notes:
Task 2 (own matchup):  done / done with help / gave up    time: ___
  what they typed (no personal details):
  notes:
Task 3 (question):     done / done with help / gave up / skipped (mock)
  notes:
Task 4 (a source):     done / done with help / gave up
  notes:
Task 5 (challenger):   done / done with help / gave up
  notes:
Broadcast: watched / skipped / muted     laughed at:

Q1 confused:
Q2 laughed:
Q3 trust verdict:
Q4 would share:
Q5 missing:
```

## Severity, for the findings table

| Severity | Meaning |
|---|---|
| High | The tester couldn't finish a task, or was misled (for example, read a number wrong). |
| Medium | They finished, but only after real confusion or a long hunt. |
| Low | Small friction, a wording issue, or a nice-to-have idea. |

## After the sessions

1. Write each problem in [findings.md](findings.md): what happened, how many testers hit it, severity, and a suggested fix. No names or personal data.
2. File one issue per finding with `/new-issue` (`type: bug` or `type: feature`, label `usability`).
3. Send Mike the top 3 that should be fixed before the freeze.
