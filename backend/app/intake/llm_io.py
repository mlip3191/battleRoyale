"""Shared by every prompt that reads the user's text: the data markers and outage errors.

Intake (parser.py) and safety (app/safety/classify.py) both wrap user text the same way, so a
request can never close the data block early in either prompt.
"""

import httpx

from app.providers.live.http import ProviderError

INPUT_START = "<<<USER_INPUT>>>"
INPUT_END = "<<<END_USER_INPUT>>>"
# Errors a chat call may raise when the provider is unavailable (timeout, connection, server
# error). Anything else, such as a missing mock fixture (LookupError), is a developer error and
# must surface instead of looking like "please rephrase".
CALL_ERRORS = (ProviderError, httpx.HTTPError, TimeoutError)


# Break up marker-like text so user input can never close the data block early.
def as_data(text: str) -> str:
    return text.replace("<<<", "< < <").replace(">>>", "> > >")


# The user's text as one data block: the markers on their own lines around it.
def data_block(text: str) -> str:
    return f"{INPUT_START}\n{as_data(text)}\n{INPUT_END}"
