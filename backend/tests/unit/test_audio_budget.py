"""The audio limit leaves room for the cloned announcer voice (#485).

Kept in its own file because test_pipeline_stages shrinks the stage budgets.
"""

from app.media import audio
from app.pipeline import stages

# Live timing of one 23-line show with the reference clip (#485): 66.0 s and 53.1 s; the slower
# run is the one to clear. (The #480 review measured about 46 s for a 20-line show.)
MEASURED_WITH_CLIP_S = 66.0
WANTED_MARGIN_S = 20.0


# The per-file limit the audio stage hands the provider must clear the measured time easily.
def test_the_audio_limit_leaves_margin_over_the_cloned_voice() -> None:
    per_file = stages.STAGE_BUDGETS_S["audio"] * stages.MEDIA_PROVIDER_SHARE
    assert per_file - MEASURED_WITH_CLIP_S >= WANTED_MARGIN_S


# Only the audio budget changes: the other media and script limits stay as decided.
def test_the_other_stage_budgets_are_unchanged() -> None:
    assert stages.STAGE_BUDGETS_S["music"] == 60.0
    assert stages.STAGE_BUDGETS_S["images"] == 60.0
    assert stages.STAGE_BUDGETS_S["script"] == 10.0


# The default per-file limit matches what the stage passes, so direct callers see the same.
def test_the_default_file_limit_matches_the_stage_share() -> None:
    assert audio.ITEM_TIMEOUT_S == stages.STAGE_BUDGETS_S["audio"] * stages.MEDIA_PROVIDER_SHARE
