# Usability sessions: plan and script (D10)

We're testing the app with 3–5 people from outside the team (friends, family, classmates not in our group). The goal is to find out where a first-time user gets stuck, confused, or bored, and to turn each problem into an issue before the feature freeze (end of Sun Nov 22).

- **Who can test:** adults only (18+), or a parent's written consent for anyone younger.
- **Length:** about 15 minutes per session. Each task gets about 3 minutes; after that, mark it "gave up" and move on.
- **When:** by the afternoon of Sat Nov 21. Each facilitator posts their filled-in notes as a comment on issue #50 by 3 pm, and Mike picks the top 3 that evening. #50 is public: T-numbers only, no names or personal details.
- **Who runs it:** one teammate as the facilitator. The facilitator reads the script, watches, and takes notes. They don't help unless the tester is stuck for more than a minute.
- **Where:** in person at the facilitator's computer if you can. On a video call, give the tester remote control of your screen; if you drive the mouse for them, they can't discover hovering for a quote, Mute, or Skip, and the sound depends on the call. Run at least some sessions in person. Don't record video calls.
- **Mode:** live mode (`npm run env:setup` done, `npm start`). Task 3 needs live mode, because mock mode never asks a clarifying question. If live mode is down, run in mock mode, skip task 3, and note it; for tasks 4 and 5, use one of the five showcase battles on the home page. A facilitator setting up live mode for the first time can follow [docs/onboarding.md](../onboarding.md).
- **No personal data:** don't record names, ages, emails, faces, or voices. Testers are "T1" to "T5" in the notes. Don't take screen recordings with the tester's face or voice.

## Before each session (2 minutes)

1. Run `npm run doctor`, then start the app and open http://localhost:8000 in a fresh browser window.
2. Make sure the knowledge base is there. Since #442 the app loads a prebuilt one the first time it starts in live mode: the terminal says "Loaded the prebuilt knowledge base (3299 passages from 30 articles)". If it says instead that your embedding model differs, or that the knowledge base is empty, run `npm run ingest` (about 30 minutes; do it the day before, not just before a session). Without a knowledge base, research falls back and listed fighters lose their looked-up stats, which a tester would log as a product finding.
3. Play one example battle through to the verdict. This catches a live-mode outage or a called-off fighter before the tester arrives. Also play "a hippopotamus vs a saltwater crocodile in the water": the hippo is on the fighter list but has no hand-checked sheet, so its stats come from the knowledge base. On its results page the hippo should have a few sourced stats (mass, length) with a link and quote. If they're all estimates, or the broadcast says "Some effects unavailable: research" for this matchup, stop and fix setup (step 2) before the tester arrives. That note is normal for an animal that isn't on the list (a tiger, a kangaroo), so don't use one of those for this check.
4. Open a fresh browser window for the tester, and have a notes sheet ready (below), one per tester.

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

**Known in live mode** (refreshed Nov 20 from Mike's practice run on main; re-run your example battle on the day, since fixes may land before Nov 21):

- **Animals off the fighter list fight back, on generic stats.** Since #441 and #453, a tiger, moose or penguin is no longer called off and fights as a living animal, but on generic mammal estimates, and every one of its stats is labeled an estimate. The broadcast also says "Some effects unavailable: research" for these fights; that's expected, so note only whether the tester was confused by it. So an off-list matchup can look odd (a polar bear about as strong as one wolf, or "a lion vs a tiger" going to the lion 100% because only the lion has a real sheet); that's a known limit, so log the tester's reaction (question 3, trust), not a new bug. In task 4, watch whether the tester notices the estimate tags and what they make of them.
- **Getting around.** There's a Home button in the top bar (#464). Tonight's card and the quick question scroll into view, and the card's button is "Start the fight!" (#467). The home page has five showcase battles.
- **Two verdict bugs are fixed on main (Nov 20).** A verdict that contradicted itself ("WINNER: HONEY BADGER!" over "Duck came out ahead in spite of its size", #474) and a 50% coin flip shown as a winner (#476, now "Too close to call") are both merged. If a tester still sees either, check that your copy is up to date before logging it. Still open, log as known: "We assumed" can show internal model text (#475), and on a coin flip the spoken outro still says "Your winner: X!" while the banner says "Too close to call" (#482). "Too close to call" now shows on the card, the reveal and the arena banner (#478): note how the tester reacts to it.
- **The quick question's buttons all lead to a fight.** In task 3, "Grizzly" uses the hand-checked stat sheet; the others fight on estimates ("Polar" loses to the 6 wolves 99.7% of the time). Note which button they press, and suggest Grizzly only if they ask.
- **Announcer voice: check it on the day. No music.** The live voice landed on Nov 19 (#443); music is cut. If your example battle says "Captions only this time, no announcer voice", check that `ANNOUNCER_VOICE_ID` in your `.env` is `default` as in `.env.example` (an older placeholder value makes the voice service refuse every line; #454 makes the app skip a placeholder). If the voice still isn't working, tell the tester up front that it's captions only, so "no sound" isn't logged as a new finding, and don't spend task time on Mute.
- **Some fighters fail closed (#444, post-MVP).** "a god", "a priest" or "a sword" can end with "We don't have a stat sheet for ...". That's known: log the tester's reaction, not a new bug.
- **Blank-circle sprites (#461).** After any mock-mode run on your computer, some fighters (gorilla, grizzly, lion) can show as blank circles in live mode. Check `data/media/sprites/` before the session, and log it as known if it shows up.
- **Sound starts only on Play sound.** Nothing plays until the tester presses **Play sound** in the audio bar. Watch whether they find it on their own; don't point at it.
- **Expect pauses.** Reading the matchup takes 7–15 seconds after pressing go (longer with a question), and a whole battle 20–50 seconds.

**Fighter list** (show this only if a tester's own fight in task 2 is called off, or they're stuck for ideas). These are on the fighter list (12 have hand-checked stat sheets; the rest are built by research), and everyday names for them work too ("hippo", "dog"). Since #441, an animal that isn't on the list (tiger, moose, polar bear) fights on estimated stats instead of being called off. These notes go stale fast: re-run "a tiger vs a goose" on the day to confirm.

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
3. Post your notes on #50 by 3 pm on Sat Nov 21 (T-numbers only, no personal details); Mike picks the top 3 that should be fixed before the freeze that evening. Rank by severity, then by testers affected, then by whether the fix is size S or M and can land by Nov 22.
