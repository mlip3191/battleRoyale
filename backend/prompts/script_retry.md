<!-- What the announcer writer (narration/writer.py) sends after a rejected script, by section.
"retry" is the message: code fills {reason} (what the checks rejected) and {hint} (one of the
sections below, chosen by the reason, or nothing). Without its thinking step the model kept
counting moments or naming the winner itself after a bare "rejected" (#363). -->
## retry
That reply was rejected: {reason}
{hint}Write it again, following every rule. Reply with JSON only.
## placeholders
Write each one exactly like that, in curly braces; never write the winner's name or the deciding factor in your own words.
## numbers
Only numbers from the fact list are allowed, written the same way. Don't count or number the moments, and don't convert or round a number.
