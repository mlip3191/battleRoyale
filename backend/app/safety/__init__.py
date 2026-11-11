"""Moderation and blocklists for fighters and media prompts (A04).

Public surface: check_text_rules (code rules), classify_text (model classifier),
check_parsed_sides (intake's reading), check_matchup (a Matchup that skipped intake, for A05),
blocked_result (a verdict as an IntakeResult), and SafetyUnavailable (fail closed).
"""

from app.safety.classify import SafetyUnavailable, classify_text
from app.safety.gate import check_matchup, check_parsed_sides, check_side_rules
from app.safety.rules import check_text_rules
from app.safety.verdict import SafetyVerdict, blocked_result

__all__ = [
    "SafetyUnavailable",
    "SafetyVerdict",
    "blocked_result",
    "check_matchup",
    "check_parsed_sides",
    "check_side_rules",
    "check_text_rules",
    "classify_text",
]
