# Usability findings (D10)

Sessions run with the [plan](plan.md). Testers are T1 to T5; no names or personal data. Session notes are on #50.

## Sessions

| Tester | Date | Mode | In person or call | Tasks finished (of 5) |
|---|---|---|---|---|
| T1 | Fri Nov 20 | live | in person | 5 |
| T2 | Fri Nov 20 | live | in person | 5 |
| T3 | Mon Nov 23 (main `0b22a87`) | live | in person | 4 (task 4, finding a source, is noted only as "struggled"; task 5 done with difficulty) |

Three sessions, the minimum. T3 ran a day after the planned Nov 22 deadline, on the code as it stood after the freeze. One planned session's notes were never posted; T3 was run in its place. Practice runs by two teammates before the sessions (T0) aren't counted, but where they saw the same problem it's noted below.

## Findings

Ordered by severity, then by how many testers hit it, then by whether the fix is size S or M. Severity is defined in the [plan](plan.md#severity-for-the-findings-table). N = 3.

| # | Task # | Problem | Testers affected (x of N) | Severity | Suggested fix | Issue |
|---|---|---|---|---|---|---|
| 1 | 2 | A misspelled fighter ("Kimono dragon") was silently read as a different fighter (the mythical dragon), with no note or "did you mean". | 1 of 3 | High (misled) | Say on the card when a typed word was dropped or replaced, or ask, as for "which bear?" | #500 (fixed, #526) |
| 2 | Broadcast | The announcer said "28 geese" when the matchup was 128 geese. | 1 of 3 | High (misled: a number heard wrong) | Send counts to the speech service as words; captions keep the digits. | #502 (fixed, #525) |
| 3 | 4 | Finding a source was hard, and the stats felt technical; T3 wanted plain fun facts on why one side would win. The notes don't say the task was finished. | 1 of 3 | High (task not finished) | Short plain-language reasons next to the verdict, from the stat sheets. | #582 (open) |
| 4 | 1, 2, broadcast | Sound is easy to miss, and out of step with the fight. T1 and T2 didn't know "Play sound" had to be clicked, and T1 found the timing off. T3, after #512, still had to press it, and the voice didn't line up with the picture. (Also T0.) | 3 of 3 | Medium | Turn sound on when the viewer clicks "Start the fight" (#512); make sure it really starts (#579); play each announcer line when the fight reaches it, and pause and speed up with the fight (#576). | #499 (#512); still seen by T3: #579 (open); sync #576 (PR #585), follow-up #584 |
| 5 | Broadcast, 5 | The floating damage numbers have no context. T1 and T2 asked for a health bar; after #514 added one, T3 saw it move only at the end, and was unsure what the minus numbers meant. (Also T0.) | 3 of 3 | Medium | A health bar per side that drops with every hit, from the simulation's own hit points. | #503 (#514); per hit: #575 (PR #578) |
| 6 | Results | The fair fight suggested the matchup just fought: after 1 field mouse vs 1 gray wolf (T2, who read it as a bug), and after a tiger vs 128 geese, where it "needs 128 geese" while the geese won 46% (T1). | 2 of 3 | Medium | Say "already about even" or "as close as it gets" when the fair count is the one just fought, in the box and in the outro. | #501 (fixed, #510); #549 (fixed, #554); outro #527 (fixed, #530) |
| 7 | 1, 5 | The next step isn't obvious: the tonight's-card confirm step was confusing, and "Fair fight" blends in, with nothing saying "click me next". | 1 of 3 | Medium | Make the next step stand out on the card and on the results page. | #581 (open); earlier #462 (fixed, #467), #504 (fixed, #507) |
| 8 | 2, 3 | Fights last too long: a 100-guinea-pig crowd is knocked out one at a time and "Guinea pig goes down! That is a knockout!" repeats about 100 times. T3: "a fight should last about 15 seconds." T3 finished both tasks; rated Medium because it was one of T3's top themes and it repeats in every crowd fight. | 1 of 3 | Medium | Shorter replays at 1×, and summarize a crowd's knock-outs instead of one line each. 5× and 10× speeds help in the meantime. | #580 (open); speeds #577 (PR #583) |
| 9 | 2 | The announcer took far too long to load, and the wait felt like a stall. T3 finished the task; rated Medium because it was one of T3's top themes and every first fight waits on it. | 1 of 3 | Medium | Load the voice sooner; say the announcer is loading, and if practical play a short crowd bed while it waits. | #579 (open) |
| 10 | 1 | T3 found the instruction line under the box poorly placed and suggested friendlier wording, with the line right under "Who would win?" and "Stumped? Try one of the sample battles below" over the examples. (Earlier, #511 and #513 added a heading over the examples and renamed the showcase.) | 1 of 3 | Low | Move the instruction line up under "Who would win?" with friendlier wording. | not filed |
| 11 | 5 | "Fight them!" (next challenger) sat at the very bottom of the results, among the sources. | 1 of 3 | Low | Move the fair fight and next challenger right under the verdict. | #504 (fixed, #507) |
| 12 | Broadcast | "Whiff" isn't clear to a first-time viewer ("sounds like smelling"). | 1 of 3 | Low | Plain wording ("miss"). | #505 (fixed, #545) |
| 13 | Results | "Tiger wins 55%" next to "on average 0.6 tigers vs 67.4 geese left standing" reads as contradictory, even after #463 (#473) reworded "left standing". | 1 of 3 | Low | Explain that survivors are averaged over every fight, wins included. | not filed |

**Known limits seen, not filed:**
- Off-list animals fight on generic estimates. That hurt trust for T2 (a gray wolf only 60% over a field mouse). T1 noticed a tiger weighed like a 50 kg mammal but still trusted the verdict (#441, #453). Size classes (#517) and on-demand research (#518) address this after D-69 (#523). Recorded in the [evaluation](../evaluation.md).
- Exact-looking numbers for absurd matchups feel funny or dubious (T3: "I suppose").
- Wikipedia is the main source; T2 trusted the verdict less for it. Every sourced stat shows its quote and link.

## Answers to the five questions

A short summary of what testers said, with no names.

1. **What confused you?** That sound needed a click, with the timing off (T1, T2; T3 hit the same in the tasks). Where the floating numbers come from, with no health bar for context, and "whiff" (T2). "Fair fight" blending in, with nothing saying what to click next (T3).
2. **What made you laugh?** The dramatic announcer voice and 128 geese against a tiger (T1); the field mouse vs hedgehog commentary and the sprites hovering in the air (T2); the throwback visuals (T3).
3. **Would you trust the verdict?** Yes (T1); mostly yes (T2), who liked the fair-fight suggestion but trusted Wikipedia sources and all-estimate fights less; "I suppose" (T3), since exact stats for absurd matchups feel dubious.
4. **Would you share it?** Not as it is (T1); no (T3). T2 would like the app to ask when it doesn't understand a word, as it does for "bear".
5. **What's missing?** A damage or health bar (T1, T2; T3 saw it not move). Plain fun facts on why one side wins, a "waiting room" while the announcer loads, and shorter fights (T3).

## Top 3 to fix

**Before the freeze (picked from T1 and T2's notes):** all three are fixed.

1. **#500**, a misspelled fighter read silently as another (High, misled). Fixed in #526.
2. **#502**, the spoken count "28" for 128 (High, misled). Fixed in #525.
3. **#499**, sound easy to miss (Medium, 2 of 2 then). Fixed in #512, but T3 still hit it (finding 4).

**After T3 (for code complete, Wed Nov 25), proposed:**

1. **Sound that starts and stays with the fight** (finding 4, 3 of 3): #576 in PR #585, then #579 and #584.
2. **A health bar that drops with every hit** (finding 5, 3 of 3): #575 in PR #578.
3. **Shorter fights without a hundred repeated knock-out lines** (finding 8): #580, with 5× and 10× speeds (#577, PR #583) in the meantime.
