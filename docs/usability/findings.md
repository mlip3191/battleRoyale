# Usability findings (D10)

Sessions run with the [plan](plan.md). Testers are T1 to T5; no names or personal data. Session notes are on #50.

## Sessions

| Tester | Date | Mode | In person or call | Tasks finished (of 5) |
|---|---|---|---|---|
| T1 | Fri Nov 20 | live | in person | 5 |
| T2 | Fri Nov 20 | live | in person | 5 |
| T3 | Mon Nov 23 (main `0b22a87`) | live | in person | 4 (struggled to find a source in task 4; finished task 5 with difficulty) |

Three sessions, the minimum. T3 ran a day after the planned Nov 22 deadline, on the code as it stood after the freeze. A fourth planned session's notes were never posted. Practice runs by two teammates before the sessions (T0) aren't counted, but where they saw the same problem it's noted below.

## Findings

Ordered by severity, then by how many testers hit it, then by whether the fix is size S or M. Severity is defined in the [plan](plan.md#severity-for-the-findings-table). N = 3.

| # | Task # | Problem | Testers affected (x of N) | Severity | Suggested fix | Issue |
|---|---|---|---|---|---|---|
| 1 | 2 | A misspelled fighter ("Kimono dragon") was silently read as a different fighter (the mythical dragon), with no note or "did you mean". | 1 of 3 | High (misled) | Say on the card when a typed word was dropped or replaced, or ask, as for "which bear?" | #500 (fixed, #526) |
| 2 | Broadcast | The announcer said "28 geese" when the matchup was 128 geese. | 1 of 3 | High (misled: a number heard wrong) | Send counts to the speech service as words; captions keep the digits. | #502 (fixed, #525) |
| 3 | 1, 2, broadcast | Sound is easy to miss, and out of step with the fight. T1 and T2 didn't know "Play sound" had to be clicked. T3, after #512, still had to press it, and the voice didn't line up with the picture. (Also T0.) | 3 of 3 | Medium | Turn sound on when the viewer clicks "Start the fight" (#512); make sure it really starts (#579); play each announcer line when the fight reaches it, and pause and speed up with the fight (#576). | #499 (#512); still seen by T3: #579 (open); sync #576 (PR #585) |
| 4 | Broadcast, 5 | The floating damage numbers have no context. T1 and T2 asked for a health bar; after #514 added one, T3 saw it move only at the end, and was unsure what the minus numbers meant. (Also T0.) | 3 of 3 | Medium | A health bar per side that drops with every hit, from the simulation's own hit points. | #503 (#514); per hit: #575 (PR #578) |
| 5 | 2, 3 | Fights last too long: a 100-guinea-pig crowd is knocked out one at a time and "Guinea pig goes down!" repeats about 100 times. T3: "a fight should last about 15 seconds." | 1 of 3 | Medium | Shorter replays at 1×, and summarize a crowd's knock-outs instead of one line each. 5× and 10× speeds help in the meantime. | #580 (open); speeds #577 (PR #583) |
| 6 | 2 | The announcer took far too long to load, and the wait felt like a stall. | 1 of 3 | Medium | Load the voice sooner; say the announcer is loading, and if practical play a short crowd bed while it waits. | #579 (open) |
| 7 | 1, 5 | The next step isn't obvious: the tonight's-card confirm step was confusing, and "Fair fight" blends in, with nothing saying "click me next". | 1 of 3 | Medium | Make the next step stand out on the card and on the results page. | #581 (open) |
| 8 | 4 | Finding a source was hard, and the stats felt technical; T3 wanted plain fun facts on why one side would win. | 1 of 3 | Medium | Short plain-language reasons next to the verdict, from the stat sheets. | #582 (open) |
| 9 | Results | After 1 field mouse vs 1 gray wolf, the fair fight suggested the same 1 vs 1 matchup just fought; it read as a bug. | 1 of 3 | Medium | Say "already about even" in the fair-fight box and in the outro. | #501 (fixed, #510); outro #527 (fixed, #530) |
| 10 | 1 | The example matchups weren't obviously clickable at first, or different from the showcase. T3 found the instructions under the box easy to miss and suggested friendlier wording ("Stumped? Try one of the sample battles below"). | 2 of 3 | Low | A "Try one of these" heading over the examples, and "Showcase (Ready Made)" (#511, #513). Move the instruction line up under "Who would win?" with friendlier wording. | #511, #513 (fixed, #532); T3's wording: not filed |
| 11 | 5 | "Fight them!" (next challenger) sat at the very bottom of the results, among the sources. | 1 of 3 | Low | Move the fair fight and next challenger right under the verdict. | #504 (fixed, #507) |
| 12 | Broadcast | "Whiff" isn't clear to a first-time viewer ("sounds like smelling"). | 1 of 3 | Low | Plain wording ("miss"). | #505 (fixed, #545) |
| 13 | Results | "Tiger wins 55%" next to "on average 0.6 tigers vs 67.4 geese left standing" reads as contradictory. | 1 of 3 | Low | Explain that survivors are averaged over every fight, wins included. | not filed |
| 14 | Results | The fair fight said it "needs 128 geese" while its own test gave the geese 46%. | 1 of 3 | Low | Word the fair count as "about even" when its win share is near 50%. | not filed |

**Known limits seen, not filed** (recorded in the [evaluation](../evaluation.md)):
- Off-list animals fight on generic estimates, which hurt trust for T1 and T2: a tiger weighed like a 50 kg mammal (T1), and a gray wolf only 60% over a field mouse (T2) (#441, #453). Size classes (#517) and on-demand research (#518) address this after D-69 (#523).
- Exact-looking numbers for absurd matchups feel funny or dubious (T3: "I suppose").
- Wikipedia is the main source; T2 trusted the verdict less for it. Every sourced stat shows its quote and link.

## Answers to the five questions

A short summary of what testers said, with no names.

1. **What confused you?** That sound needed a click (all three), and the voice not lining up with the fight (T3). Where the floating numbers come from, with no health bar moving for context (all three). "Whiff" (T2). "Fair fight" blending in, with nothing saying what to click next (T3).
2. **What made you laugh?** The dramatic announcer voice and 128 geese against a tiger (T1); the field mouse vs hedgehog commentary and the sprites hovering in the air (T2); the throwback visuals (T3).
3. **Would you trust the verdict?** Yes (T1); mostly yes (T2), who liked the fair-fight suggestion but trusted Wikipedia sources and all-estimate fights less; "I suppose" (T3), since exact stats for absurd matchups feel dubious.
4. **Would you share it?** Not as it is (T1); no (T3). T2 would like the app to ask when it doesn't understand a word, as it does for "bear".
5. **What's missing?** A health bar that moves (all three). Plain fun facts on why one side wins, a "waiting room" while the announcer loads, and shorter fights (T3).

## Top 3 to fix

**Before the freeze (picked Sat Nov 21 from T1 and T2):** all three are fixed.

1. **#500**, a misspelled fighter read silently as another (High, misled). Fixed in #526.
2. **#502**, the spoken count "28" for 128 (High, misled). Fixed in #525.
3. **#499**, sound easy to miss (Medium, 2 of 2 then). Fixed in #512, but T3 still hit it (finding 3).

**After T3 (for code complete, Wed Nov 25), proposed:**

1. **Sound that starts and stays with the fight** (finding 3, 3 of 3): #576 in PR #585, then #579 and #584.
2. **A health bar that drops with every hit** (finding 4, 3 of 3): #575 in PR #578.
3. **Shorter fights without a hundred repeated knock-out lines** (finding 5): #580, with 5× and 10× speeds (#577, PR #583) in the meantime.
