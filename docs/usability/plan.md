# Usability sessions: plan and script (D10)

We're testing the app with 3–5 people from outside the team (friends, family, classmates not in our group). The goal is to find out where a first-time user gets stuck, confused, or bored, and to turn each problem into an issue before the feature freeze (end of Sun Nov 22).

- **Who can test:** adults only (18+), or a parent's written consent for anyone younger.
- **Length:** about 15 minutes per session. Each task gets about 3 minutes; after that, mark it "gave up" and move on.
- **When:** by the afternoon of Sat Nov 21. Each facilitator sends their filled-in notes sheet to Dillon by 3 pm, and the top 3 go to Mike that evening.
- **Who runs it:** one teammate as the facilitator. The facilitator reads the script, watches, and takes notes. They don't help unless the tester is stuck for more than a minute.
- **Where:** in person at the facilitator's computer if you can. On a video call, give the tester remote control of your screen; if you drive the mouse for them, they can't discover hovering for a quote, Mute, or Skip, and the sound depends on the call. Run at least some sessions in person. Don't record video calls.
- **Mode:** live mode (`npm run env:setup` done, `npm start`). Task 3 needs live mode, because mock mode never asks a clarifying question. If live mode is down, run in mock mode, skip task 3, and note it; for tasks 4 and 5, use one of the five showcase battles on the home page. A facilitator setting up live mode for the first time can follow [docs/onboarding.md](../onboarding.md).
- **No personal data:** don't record names, ages, emails, faces, or voices. Testers are "T1" to "T5" in the notes. Don't take screen recordings with the tester's face or voice.

## Before each session (2 minutes)

1. Run `npm run doctor`, then start the app and open http://localhost:8000 in a fresh browser window.
2. Play one example battle through to the verdict. This catches a live-mode outage or a called-off fighter before the tester arrives.
3. Open a fresh browser window for the tester, and have a notes sheet ready (below), one per tester.

## Script (read this out)

> Thanks for helping. Is it OK if I take notes and use what you say, without your name? You can stop any time.
>
> This is a web app our class team built. You name two fighters, and it works out who would win using real animal facts, then shows the fight as a cheesy sports broadcast.
>
> We're testing the app, not you. There are no wrong answers. If something is confusing, that's exactly what we want to find.
>
> Please think out loud as you go: say what you're looking for, what you expect to happen, and what surprises you. I'll mostly stay quiet. I won't record your name or anything personal.

## The five tasks

Read each task out, then watch. Don't point at the screen or name the button. Give each task about 3 minutes, then mark it "gave up" and go on. You may press "Skip to verdict" for them only from the second battle on, once they've seen one broadcast.

- **Called off:** if a battle ends with "This fight was called off" (rare since #441; for example, when a service is down), that's a **product** finding, not the tester's fault. Mark the task "called off", note what they typed, and move on.
- **Off-limits fighters:** don't suggest real people or other off-limits fighters. If a tester tries one, the safety check refuses it: note how the refusal landed, and don't coach.

**Known in live mode** (re-checked live on Nov 19 after #441 and #443; re-run your example battle on the day, since fixes may land before Nov 21):

- **Animals off the fighter list fight on estimates.** Since #441 (Nov 19), a tiger, moose or penguin is no longer called off: the battle runs, and every one of its stats is labeled an estimate (checked live: tiger vs goose, moose vs hippo, penguin vs house cat). In task 4, watch whether the tester notices the estimate tags and what they make of them.
- **The quick question's buttons all lead to a fight.** In task 3, "Grizzly" uses the hand-checked stat sheet; the others ("Polar" was checked live) fight on estimates. Note which button they press.
- **Announcer voice: check it on the day. No music.** The live voice landed on Nov 19 (#443); music is cut. If your example battle says "Captions only this time, no announcer voice", check that `ANNOUNCER_VOICE_ID` in your `.env` is `default` as in `.env.example` (an older placeholder value makes the voice service refuse every line; #454 makes the app skip a placeholder). If the voice still isn't working, tell the tester up front that it's captions only, so "no sound" isn't logged as a new finding, and don't spend task time on Mute.
- **Expect pauses.** Reading the matchup takes 7–15 seconds after pressing go (longer with a question), and a whole battle 20–50 seconds.

**Fighter list** (show this only if a tester's own fight in task 2 is called off, or they're stuck for ideas). These have hand-checked stat sheets, and everyday names for them work too ("hippo", "t-rex", "dog"). Since #441, an animal that isn't on the list (tiger, moose, polar bear) fights on estimated stats instead of being called off. These notes go stale fast: re-run "a tiger vs a goose" on the day to confirm.

> Grizzly bear · Gray wolf · African lion · House cat · Golden retriever · African elephant · Horse · Hippopotamus · Chimpanzee · Gorilla · Honey badger · House mouse · Bald eagle · Duck · Goose · Saltwater crocodile · King cobra · Great white shark · Army ant · Honey bee · Triceratops

| # | Say this | It's done when | Watch for |
|---|---|---|---|
| 1 | "Get a fight going without making up your own." | A battle starts from an example chip. | Do they see the examples? Do they know they have to confirm on tonight's card? |
| 2 | "Now type a matchup of your own: any two animals you like." | Their own battle starts, or they get a clear message about why not. A "called off" battle counts as done; log it as a product finding, then show the fighter list above and say "Try one more from this list" (this second try doesn't change the task's mark). | Do refusals or "no stat sheet" messages make sense to them? Do they know what to type? |
| 3 | "Type this in, then carry on until a fight starts: *a bear vs 6 gray wolves in a forest*." | They answer the quick question and the battle starts (or it's called off: log that as a product finding). | Do they understand why it's asking? Do they use a button or type? |
| 4 | "After the fight, find out where one of the numbers came from." | They find a sourced stat's link and quote, or a stat's tag (estimate, derived, assumption). | Do they find the results page and sources? Do the tags mean anything to them? |
| 5 | "Keep the show going: set up another fight from where you are." | The next challenger fight starts. No challenger card (a draw or no contest)? Note it and skip task 5. | Do they find the next challenger section? Is "Fight them!" clear? |

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

Task 1 (example):      done / done with help / gave up / called off    time: ___
  notes:
Task 2 (own matchup):  done / done with help / gave up / called off    time: ___
  what they typed (no personal details):
  if called off, second try from the list: ___   ran / called off
  notes:
Task 3 (question):     done / done with help / gave up / called off / skipped (mock)
  notes:
Task 4 (a source):     done / done with help / gave up
  notes:
Task 5 (challenger):   done / done with help / gave up / skipped (no card)
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
| High | The tester gave up on a task, or was misled (for example, read a number wrong). |
| Medium | They finished only with help, or after real confusion or a long hunt. |
| Low | Small friction, a wording issue, or a nice-to-have idea. |

## After the sessions

1. Write each problem in [findings.md](findings.md): which task, what happened, how many testers hit it ("x of N"), severity, and a suggested fix. No names or personal data.
2. File one issue per finding with `/new-issue` (`type: bug` or `type: feature`, label `usability`).
3. Send Mike the top 3 that should be fixed before the freeze, by the evening of Sat Nov 21. Rank by severity, then by testers affected, then by whether the fix is size S or M and can land by Nov 22.
