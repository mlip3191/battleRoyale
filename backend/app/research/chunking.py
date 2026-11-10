"""Cut plain text into overlapping passages, keeping each passage's section heading."""

import re
from dataclasses import dataclass

CHUNK_CHARS = 800
OVERLAP_CHARS = 100
HEADING_LINE = re.compile(r"^#{1,6}[ \t]+(.+?)(?:[ \t]+#+)?[ \t]*$")


@dataclass(frozen=True)
class Chunk:
    """One passage, its position in the document, and the section it came from."""

    ordinal: int
    heading: str | None
    text: str


# Split text into (heading, body) sections at markdown-style heading lines.
def _sections(text: str) -> list[tuple[str | None, str]]:
    sections: list[tuple[str | None, str]] = []
    heading: str | None = None
    lines: list[str] = []
    for line in text.splitlines():
        match = HEADING_LINE.match(line)
        if match:
            sections.append((heading, "\n".join(lines)))
            heading, lines = match.group(1), []
        else:
            lines.append(line)
    sections.append((heading, "\n".join(lines)))
    return sections


# Slide a window over one section, ending and starting on word breaks so no number is cut.
def _windows(body: str, size: int, overlap: int) -> list[str]:
    windows: list[str] = []
    start = 0
    while start < len(body):
        end = start + size
        if end >= len(body):
            windows.append(body[start:])
            break
        space = max(
            body.rfind(" ", start + overlap + 1, end), body.rfind("\n", start + overlap + 1, end)
        )
        end = space if space != -1 else end
        windows.append(body[start:end])
        start = _next_start(body, end, overlap)
    return windows


# Step back by the overlap, then forward to the start of a whole word.
def _next_start(body: str, end: int, overlap: int) -> int:
    start = end - overlap
    if body[start - 1].isspace():
        return start
    breaks = [
        found for found in (body.find(" ", start, end), body.find("\n", start, end)) if found != -1
    ]
    return min(breaks) + 1 if breaks else start


# Cut the text into numbered passages.
def chunk_text(text: str, size: int = CHUNK_CHARS, overlap: int = OVERLAP_CHARS) -> list[Chunk]:
    if not 0 <= overlap < size:
        raise ValueError("overlap must be at least 0 and smaller than size")
    chunks: list[Chunk] = []
    for heading, body in _sections(text):
        for window in _windows(body.strip(), size, overlap):
            if window.strip():
                chunks.append(Chunk(len(chunks), heading, window.strip()))
    return chunks
