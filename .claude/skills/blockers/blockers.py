#!/usr/bin/env python3
"""List the project's essential items and blockers, ordered by priority, then by who's responsible.

Run from the repo root: python3 -I .claude/skills/blockers/blockers.py [--json] [--as LOGIN]
The person running it is listed first; --as LOGIN previews what a teammate would see.
Read-only: it only calls `gh` to read PRs and issues. It never posts or changes anything.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

# Battle Royale schedule (docs/plan/DELIVERABLES.md, PROJECT_GUIDE.md §3). Update in a PR if it
# changes.
WAVE_DUE = {1: "2026-11-11", 2: "2026-11-14", 3: "2026-11-17", 4: "2026-11-20"}
MILESTONES = [
    ("2026-11-14", "MS-1 walking skeleton + first scope check"),
    ("2026-11-17", "MS-2 real brain + second scope check"),
    ("2026-11-20", "MS-3 the show works (wave 4 ends)"),
    ("2026-11-21", "Bug bash; usability sessions start; M09 evaluation written"),
    ("2026-11-22", "MS-4 demo-ready; FEATURE FREEZE end of day"),
    (
        "2026-11-25",
        "CODE COMPLETE: tag v1.0, export ZIP; the PM sends the instructor invite "
        "(expires in 7 days)",
    ),
]
ADVISORY_CHECKS = {"AI QA Review (advisory)"}
CRITICAL_CHECK = "Critical files approval"
TIERS = {
    0: "🔴 P0: blocking other people's work",
    1: "🟠 P1: blocking a merge or a decision",
    2: "🟡 P2: ready to act on / housekeeping",
}


def gh(*args: str):
    """Run a read-only gh command and parse its JSON output."""
    res = subprocess.run(["gh", *args], capture_output=True, text=True)
    if res.returncode != 0:
        sys.exit(f"gh {' '.join(args[:3])} failed: {res.stderr.strip()}")
    return json.loads(res.stdout) if res.stdout.strip() else None


def load_team() -> tuple[dict[str, str], str | None]:
    """Read login -> first name (and the PM's login) from the Team table in docs/DECISIONS.md."""
    names, pm = {}, None
    path = Path("docs/DECISIONS.md")
    if path.exists():
        for name, login in re.findall(
            r"^\|\s*([^|`]+?)\s*\|\s*`([\w-]+)`\s*\|", path.read_text(), re.M
        ):
            names[login] = name.split()[0]
            if "(PM)" in name:
                pm = login
    return names, pm


def blocked_by(body: str) -> set[int]:
    """Issue numbers named on 'Blocked by' lines (ignores lines like 'blocked by safety')."""
    refs: set[int] = set()
    for rest in re.findall(r"(?i)blocked by\W*(#\d+[^\n]*)", body or ""):
        refs |= {int(n) for n in re.findall(r"#(\d+)", rest)}
    return refs


def closes(body: str) -> set[int]:
    """Issue numbers a PR closes ('Closes #n' / 'Fixes #n')."""
    return {int(n) for n in re.findall(r"(?i)(?:closes|fixes|resolves)\s+#(\d+)", body or "")}


def label_value(labels: list[str], prefix: str) -> str | None:
    """Value of a 'prefix: value' label, e.g. wave: 4 -> '4'."""
    for lab in labels:
        if lab.startswith(prefix + ":"):
            return lab.split(":", 1)[1].strip()
    return None


def main() -> None:
    as_json = "--json" in sys.argv
    today = dt.date.today()
    names, pm = load_team()
    who_runs = None
    if "--as" in sys.argv:
        idx = sys.argv.index("--as") + 1
        if idx >= len(sys.argv) or sys.argv[idx].startswith("--"):
            sys.exit("--as needs a GitHub login, e.g. --as dilloncsmart")
        who_runs = sys.argv[idx]
        if who_runs not in names:
            print(f"Note: {who_runs} isn't in the Team table; no '(you)' group.", file=sys.stderr)
    me = who_runs or gh("api", "user")["login"]
    pm = pm or me
    pm_name = names.get(pm, pm)

    prs = (
        gh(
            "pr",
            "list",
            "--state",
            "open",
            "--limit",
            "40",
            "--json",
            "number,title,author,isDraft,baseRefName,headRefName,reviewDecision,reviews,"
            "reviewRequests,statusCheckRollup,mergeable,commits,body,updatedAt",
        )
        or []
    )
    issues = (
        gh(
            "issue",
            "list",
            "--state",
            "open",
            "--limit",
            "300",
            "--json",
            "number,title,author,assignees,labels,body",
        )
        or []
    )
    merged = (
        gh(
            "pr",
            "list",
            "--state",
            "merged",
            "--limit",
            "60",
            "--json",
            "number,title,baseRefName,author,reviews",
        )
        or []
    )

    open_issue_nums = {i["number"] for i in issues}
    by_head = {p["headRefName"]: p for p in prs}

    # Stacks: a PR whose base is another open PR's branch sits on top of it.
    children = defaultdict(list)
    for p in prs:
        if p["baseRefName"] in by_head:
            children[by_head[p["baseRefName"]]["number"]].append(p["number"])

    def descendants(n: int) -> list[int]:
        out = []
        for c in children.get(n, []):
            out += [c, *descendants(c)]
        return out

    # Issue dependencies: who is waiting on each issue.
    waiting_on = defaultdict(set)
    for i in issues:
        for ref in blocked_by(i["body"]):
            waiting_on[ref].add(i["number"])
    pr_for_issue = {n: p["number"] for p in prs for n in closes(p["body"])}

    items = []

    def add(
        tier: int, who: str, ref: str, action: str, title: str, blocks: list | None = None
    ) -> None:
        items.append(
            {
                "tier": tier,
                "who": who,
                "name": names.get(who, who),
                "ref": ref,
                "action": action,
                "title": title[:70],
                "blocks": sorted(set(blocks or [])),
            }
        )

    # Pull requests
    for p in prs:
        if p["isDraft"]:
            continue
        n, author, title = p["number"], p["author"]["login"], p["title"]
        downstream = descendants(n) + sorted(
            {w for c in closes(p["body"]) for w in waiting_on.get(c, set())}
        )
        tier_if = lambda base, blocks=downstream: 0 if blocks else base  # noqa: E731
        checks = p.get("statusCheckRollup") or []
        failing = [
            c["name"]
            for c in checks
            if c.get("conclusion") in ("FAILURE", "TIMED_OUT", "CANCELLED")
            and c["name"] not in ADVISORY_CHECKS
        ]
        real_fail = [c for c in failing if c != CRITICAL_CHECK]
        parent = by_head.get(p["baseRefName"])

        if real_fail:
            add(
                tier_if(1),
                author,
                f"PR #{n}",
                f"fix failing checks ({', '.join(sorted(set(real_fail)))})",
                title,
                downstream,
            )
        if p.get("mergeable") == "CONFLICTING":
            add(tier_if(1), author, f"PR #{n}", "resolve merge conflicts", title, downstream)
        if CRITICAL_CHECK in failing and author != pm:
            mine = [
                r
                for r in p["reviews"]
                if r["author"]["login"] == pm and r["state"] in ("APPROVED", "CHANGES_REQUESTED")
            ]
            act = (
                "re-approve on the latest commit, then re-run the critical-files check"
                if mine and mine[-1]["state"] == "APPROVED"
                else "review + approve (touches critical files)"
            )
            add(tier_if(1), pm, f"PR #{n}", act, title, downstream)

        # Changes requested: whoever holds the ball.
        latest = {}
        for r in p["reviews"]:
            if r["state"] in ("APPROVED", "CHANGES_REQUESTED", "DISMISSED"):
                latest[r["author"]["login"]] = r
        real_commits = [c for c in p["commits"] if not c["messageHeadline"].startswith("Merge ")]
        last_push = max((c["committedDate"] for c in real_commits), default="")
        for reviewer, r in latest.items():
            if r["state"] != "CHANGES_REQUESTED":
                continue
            if last_push > r["submittedAt"]:
                add(
                    tier_if(1),
                    reviewer,
                    f"PR #{n}",
                    "re-review (fixes pushed after your changes request; "
                    f"author {names.get(author, author)})",
                    title,
                    downstream,
                )
            else:
                add(
                    tier_if(1),
                    author,
                    f"PR #{n}",
                    f"address {names.get(reviewer, reviewer)}'s changes request",
                    title,
                    downstream,
                )

        approved = p["reviewDecision"] == "APPROVED" or any(
            r["state"] == "APPROVED" for r in latest.values()
        )
        has_cr = any(r["state"] == "CHANGES_REQUESTED" for r in latest.values())
        if not approved and not has_cr:
            requested = [rr.get("login") for rr in p["reviewRequests"] if rr.get("login")]
            # GitHub drops you from the request list when you review, so anyone still on it owes
            # a review.
            reviewed = {r["author"]["login"] for r in p["reviews"]}
            if requested:
                for r in requested:
                    kind = "review again (re-requested)" if r in reviewed else "first review"
                    add(
                        tier_if(1),
                        r,
                        f"PR #{n}",
                        f"{kind} (by {names.get(author, author)})",
                        title,
                        downstream,
                    )
            elif not requested:
                add(
                    tier_if(1),
                    author,
                    f"PR #{n}",
                    "request a reviewer (no review yet)",
                    title,
                    downstream,
                )
        if approved and not has_cr and not failing and p.get("mergeable") != "CONFLICTING":
            if parent:
                add(
                    2,
                    author,
                    f"PR #{n}",
                    f"approved: merge only after PR #{parent['number']} lands (stacked)",
                    title,
                    downstream,
                )
            else:
                add(
                    tier_if(2),
                    author,
                    f"PR #{n}",
                    "approved and green: merge it"
                    + (
                        ""
                        if author == pm
                        else f" (or {pm_name} or the backup can, after a ping: D-49)"
                    ),
                    title,
                    downstream,
                )

    # Issues
    for i in issues:
        n, title = i["number"], i["title"]
        labels = [lab["name"] for lab in i["labels"]]
        assignees = [a["login"] for a in i["assignees"]]
        downstream = sorted(waiting_on.get(n, set()))
        refs = blocked_by(i["body"])
        open_blockers = refs & open_issue_nums
        waits = (
            f" (waits on {', '.join('#' + str(r) for r in sorted(open_blockers))})"
            if open_blockers
            else ""
        )
        if "needs-pm" in labels:
            tier = 2 if open_blockers else (0 if downstream else 1)
            add(tier, pm, f"#{n}", "PM decision needed" + waits, title, downstream)
        pm_ok = i["author"]["login"] == pm or re.search(
            rf"(?i)approved (?:in principle )?by {re.escape(pm_name)}|pm approv|decision \(pm",
            i["body"] or "",
        )
        if "contract-change" in labels and not pm_ok:
            add(
                0 if downstream else 1,
                pm,
                f"#{n}",
                "approve or reject the contract change",
                title,
                downstream,
            )
        if "status: blocked" in labels and refs and not open_blockers:
            for who in assignees or [pm]:
                add(
                    2,
                    who,
                    f"#{n}",
                    "unblock: all blockers "
                    f"({', '.join('#' + str(r) for r in sorted(refs))}) are closed",
                    title,
                    downstream,
                )
        wave = label_value(labels, "wave")
        if wave and wave.isdigit() and int(wave) in WAVE_DUE and "needs-pm" not in labels:
            due = dt.date.fromisoformat(WAVE_DUE[int(wave)])
            has_pr = n in pr_for_issue
            if not assignees:
                if due <= today + dt.timedelta(days=3):
                    late = "OVERDUE, " if due < today else ""
                    add(
                        1 if due < today else 2,
                        pm,
                        f"#{n}",
                        f"assign someone ({late}wave {wave} due {due:%b %d}){waits}",
                        title,
                        downstream,
                    )
                continue
            if due < today and not open_blockers:
                for who in assignees:
                    add(
                        0 if downstream else 1,
                        who,
                        f"#{n}",
                        f"OVERDUE: wave {wave} ended {due:%b %d}"
                        + (f" (PR #{pr_for_issue[n]} open)" if has_pr else " (no PR yet)"),
                        title,
                        downstream,
                    )
            elif 0 <= (due - today).days <= 2 and not has_pr and not open_blockers:
                for who in assignees:
                    add(
                        2,
                        who,
                        f"#{n}",
                        f"due {due:%b %d} (wave {wave}), no PR yet",
                        title,
                        downstream,
                    )

    # Stacked PRs merged into a non-main branch without an approval.
    for m in merged:
        if m["baseRefName"] != "main" and not any(r["state"] == "APPROVED" for r in m["reviews"]):
            add(
                0,
                pm,
                f"PR #{m['number']}",
                f"merged into {m['baseRefName']} WITHOUT approval: check it",
                m["title"],
            )

    dates = MILESTONES + [(d, f"wave {w} ends") for w, d in WAVE_DUE.items()]
    upcoming = sorted((d, t) for d, t in dates if 0 <= (dt.date.fromisoformat(d) - today).days <= 3)

    # Order: tier, then responsible (you first, then the PM, then by name), then most-blocking.
    items.sort(
        key=lambda x: (
            x["tier"],
            x["who"] != me,
            x["who"] != pm,
            x["name"].lower(),
            -len(x["blocks"]),
            x["ref"],
        )
    )

    if as_json:
        print(
            json.dumps(
                {"today": str(today), "me": me, "pm": pm, "items": items, "upcoming": upcoming},
                indent=2,
            )
        )
        return

    print(f"# Blockers and essentials ({today:%a %b %d})\n")
    if not items:
        print("Nothing blocking. 🎉\n")
    for tier, label in TIERS.items():
        tier_items = [x for x in items if x["tier"] == tier]
        if not tier_items:
            continue
        print(f"## {label}\n")
        current = None
        for x in tier_items:
            if x["name"] != current:
                current = x["name"]
                tags = [t for t, on in (("you", x["who"] == me), ("PM", x["who"] == pm)) if on]
                print(f"**{current}**{' (' + ', '.join(tags) + ')' if tags else ''}")
            blocks = (
                f" ⛓ blocks {', '.join('#' + str(b) for b in x['blocks'])}" if x["blocks"] else ""
            )
            print(f"- {x['ref']}: {x['action']}. *{x['title']}*{blocks}")
        print()
    if upcoming:
        print("## 📅 Next 3 days\n")
        for d, t in upcoming:
            print(f"- {dt.date.fromisoformat(d):%a %b %d}: {t}")
        print()
    counts = defaultdict(int)
    for x in items:
        counts[x["name"]] += 1
    print(
        "**Per person:** "
        + " · ".join(f"{k} {v}" for k, v in sorted(counts.items(), key=lambda kv: -kv[1]))
    )


if __name__ == "__main__":
    main()
