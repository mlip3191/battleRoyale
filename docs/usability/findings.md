# Usability findings (D10)

Sessions run with the [plan](plan.md). Testers are T1 to T5; no names or personal data. Session notes are on #50.

## Sessions

| Tester | Date | Mode | In person or call | Tasks finished (of 5) |
|---|---|---|---|---|
| T1 | Fri Nov 20 | live | in person | 5 |
| T2 | Fri Nov 20 | live | in person | 5 |
| T3 | (notes pending on #50) | | | |

A practice run by a teammate before the sessions (T0) isn't counted, but where it saw the same problem it's noted below.

## Findings

Ordered by severity, then by how many testers hit it, then by whether the fix is size S or M and can land by Nov 22. Severity is defined in the [plan](plan.md#severity-for-the-findings-table). N = 2 until T3's notes are in.

| # | Task # | Problem | Testers affected (x of N) | Severity | Suggested fix | Issue |
|---|---|---|---|---|---|---|
| 1 | 2 | A misspelled fighter ("Kimono dragon") was silently read as a different fighter (the mythical dragon), with no note or "did you mean". | 1 of 2 | High (misled) | Say on the card when a typed word was dropped or replaced, or ask, as for "which bear?" | #500 (PR #526 in review) |
| 2 | Broadcast | The announcer said "28 geese" when the matchup was 128 geese. | 1 of 2 | High (misled: a number heard wrong) | Send counts to the speech service as words; captions keep the digits. | #502 (fixed, #525) |
| 3 | 1, broadcast | Sound is easy to miss: neither tester knew "Play sound" had to be clicked, and a late click started the voice out of sync. (Also T0.) | 2 of 2 | Medium | Turn sound on when the viewer clicks "Start the fight", with a clear Sound on/off button. | #499 (fixed, #512) |
| 4 | Results | After 1 field mouse vs 1 gray wolf, the fair fight suggested the same 1 vs 1 matchup just fought; it read as a bug. | 1 of 2 | Medium | Say "already about even" in the fair-fight box and in the outro. | #501 (box fixed, #510); outro #527 (PR #530) |
| 5 | Broadcast | The floating damage numbers have no context; both testers asked for a health bar or total health. (Also T0.) | 2 of 2 | Low | A remaining-health bar per side, from the simulation log. | #503 (fixed, #514); Skip fix #528 (PR #531) |
| 6 | 1 | The example matchups weren't obviously clickable at first, or different from the showcase. | 1 of 2 | Low | A "Try one of these" heading over the examples; "Showcase (Ready Made)". | #511, #513 (PR #532) |
| 7 | 5 | "Fight them!" (next challenger) sat at the very bottom of the results, among the sources. | 1 of 2 | Low | Move the fair fight and next challenger right under the verdict. | #504 (fixed, #507) |
| 8 | Broadcast | "Whiff" isn't clear to a first-time viewer ("sounds like smelling"). | 1 of 2 | Low | Plain wording ("miss"). | #505 |
| 9 | Results | "Tiger wins 55%" next to "on average 0.6 tigers vs 67.4 geese left standing" reads as contradictory. | 1 of 2 | Low | Explain that survivors are averaged over every fight, wins included. | not filed |
| 10 | Results | The fair fight said it "needs 128 geese" while its own test gave the geese 46%. | 1 of 2 | Low | Word the fair count as "about even" when its win share is near 50%. | not filed |

**Known limits seen, not filed** (recorded in the [evaluation](../evaluation.md)):
- Off-list animals fight on generic estimates, which hurt trust for both testers: a tiger weighed like a 50 kg mammal (T1), and a gray wolf only 60% over a field mouse (T2) (#441, #453). Size classes (#517) and on-demand research (#518) address this after D-69 (#523).
- Wikipedia is the main source; T2 trusted the verdict less for it. Every sourced stat shows its quote and link.

## Answers to the five questions

A short summary of what testers said, with no names.

1. **What confused you?** That sound needed a click (both). Where the floating numbers come from, with no health bar for context (both). "Whiff" (T2).
2. **What made you laugh?** The dramatic announcer voice and 128 geese against a tiger (T1); the field mouse vs hedgehog commentary and the sprites hovering in the air (T2).
3. **Would you trust the verdict?** Yes (T1); mostly yes (T2), who liked the fair-fight suggestion but trusted Wikipedia sources and all-estimate fights less.
4. **Would you share it?** Not as it is (T1). T2 would like the app to ask when it doesn't understand a word, as it does for "bear".
5. **What's missing?** A damage or health bar (both).

## Top 3 to fix before the freeze

Notes posted on #50 by 3 pm Sat Nov 21 (T-numbers only, no personal details); Mike picks the top 3 that evening. Proposed, pending T3's notes:

1. **#500**, a misspelled fighter read silently as another (High, misled). PR #526 is in review.
2. **#502**, the spoken count "28" for 128 (High, misled). Fixed in #525.
3. **#499**, sound easy to miss (Medium, 2 of 2). Fixed in #512.
