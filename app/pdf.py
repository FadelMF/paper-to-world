import io
import os
import re
import urllib.error
import urllib.request
from collections import Counter

from pypdf import PdfReader
from pypdf.errors import PdfReadError

from app.errors import NoTextLayer, PublicError

ARXIV_ID = re.compile(r"(?:[0-9]{4}\.[0-9]{4,5}|[a-zA-Z.-]+/[0-9]{7})(?:v[0-9]+)?")

LIGATURES = str.maketrans({"ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "ﬅ": "st", "ﬆ": "st"})
CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
PAGE_NUMBER = re.compile(r"^\W*(?:page\s*)?\d{1,4}(?:\s*(?:of|/)\s*\d{1,4})?\W*$", re.I)
REFERENCES = re.compile(r"^(?:\d+\.?\s*)?(?:references|bibliography|literature cited)\s*$", re.I)
CAPTION = re.compile(r"^(extended data\s+)?(?:figure|fig\.?)\s*(S?\d+)\s*[.:|]", re.I)
CAPTION_CHARS = 400
SENTENCE_END = re.compile(r"(?<=[.!?])(?<![Ff]ig\.)(?<!Eq\.)(?<!al\.)(?<!e\.g\.)(?<!i\.e\.)\s+")
APPENDIX = re.compile(r"^(?:appendix|appendices|supplementary)\b|^[A-Z](?:\.\d+)?\s+[A-Z][a-z]+[^.]*$")

NOT_PDF = "This file couldn't be opened as a PDF. Try downloading it again or use the arXiv ID."
LOCKED = "This PDF is password-protected. Upload an unlocked copy."
NO_TEXT = "This PDF has no selectable text, so it may be a scanned image. Try a text-based copy, such as the arXiv version."


COMPOUND = re.compile(r"\b[A-Za-z]+(?:-[A-Za-z]+)+\b")


def clean_page(text, compounds=frozenset()):
    """Repair extracted text. `compounds` are hyphenated words seen unbroken in the paper; they keep their hyphen."""
    text = CONTROL.sub("", text.translate(LIGATURES))

    def rejoin(match):
        # A lowercase word split across a line break is rejoined; the break moves after the word.
        head, tail = match.group(1), match.group(2)
        joined = f"{head}-{tail}" if f"{head}-{tail}".lower() in compounds else head + tail
        return joined + "\n"

    text = re.sub(r"([A-Za-z-]*[a-z])-\n([a-z]+)[^\S\n]*", rejoin, text)
    text = re.sub(r"[^\S\n]+", " ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def strip_running_lines(pages):
    if len(pages) < 3:
        return pages
    edge = lambda lines: {line for line in lines[:2] + lines[-2:] if line}
    split = [page.split("\n") for page in pages]
    counts = Counter(line for lines in split for line in edge(lines))
    running = {line for line, n in counts.items() if n >= 0.6 * len(pages)}
    cleaned = []
    for lines in split:
        edges = set(range(2)) | set(range(len(lines) - 2, len(lines)))
        kept = [line for i, line in enumerate(lines) if not (i in edges and (line in running or (PAGE_NUMBER.match(line) and i in (0, len(lines) - 1))))]
        cleaned.append("\n".join(kept).strip())
    return cleaned


def read_pdf(data):
    if not data.lstrip()[:5] == b"%PDF-":
        raise PublicError(NOT_PDF)
    try:
        reader = PdfReader(io.BytesIO(data))
        if reader.is_encrypted and not reader.decrypt(""):
            raise PublicError(LOCKED)
        raw = [page.extract_text() or "" for page in reader.pages]
    except PublicError:
        raise
    except Exception as error:
        if isinstance(error, PdfReadError) and "decrypt" in str(error).lower():
            raise PublicError(LOCKED) from error
        raise PublicError(NOT_PDF) from error
    compounds = frozenset(word.lower() for page in raw for word in COMPOUND.findall(page))
    pages = [clean_page(page, compounds) for page in raw]
    if not any(len(page) > 20 for page in pages):
        raise NoTextLayer(NO_TEXT)
    return strip_running_lines(pages)


def download_arxiv(arxiv_id):
    if not ARXIV_ID.fullmatch(arxiv_id):
        raise PublicError("Enter an arXiv ID such as 1706.03762.")
    limit = int(os.getenv("PAPER_MAX_UPLOAD_MB", "50")) * 1024 * 1024
    url = f"https://arxiv.org/pdf/{arxiv_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "paper-to-world"})
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            data = r.read(limit + 1)
            if len(data) > limit:
                raise PublicError(f"This paper exceeds the {limit // (1024 * 1024)} MB limit.")
            return data
    except urllib.error.HTTPError as error:
        error.close()
        if error.code == 404:
            raise PublicError(f"arXiv has no paper {arxiv_id}. Check the arXiv ID, or upload the PDF instead.") from error
        raise PublicError("arXiv could not serve the paper just now. Try again later, or upload the PDF instead.") from error
    except OSError as error:
        raise PublicError("We couldn't reach arXiv just now. Try again, or upload the PDF instead.") from error


def without_references(pages):
    """Drop the reference list, from its heading to an appendix heading. Page 1 is skipped: it may hold a contents list."""
    result, skipping = [], False
    for number, page in enumerate(pages):
        kept = []
        for line in page.split("\n"):
            if not skipping and number > 0 and REFERENCES.match(line):
                skipping = True
            elif skipping and APPENDIX.match(line):
                skipping = False
            if not skipping:
                kept.append(line)
        result.append("\n".join(kept).strip())
    return result


def paper_chunks(pages, max_chars):
    """The paper's text for the model in parts of at most max_chars, split at page boundaries (references dropped).
    When there is more than one part, each starts with "[part i of n: pages a-b]"."""
    parts, text, first, last = [], "", None, None
    for number, page in enumerate(without_references(pages), 1):
        if not page:
            continue
        block = f"[page {number}]\n{page}"[:max_chars]
        if text and len(text) + 1 + len(block) > max_chars:
            parts.append((first, last, text))
            text, first = "", None
        text, first, last = (text + "\n" + block if text else block), first or number, number
    if text:
        parts.append((first, last, text))
    if len(parts) == 1:
        return [parts[0][2]]
    return [f"[part {i} of {len(parts)}: pages {a}-{b}]\n{text}" for i, (a, b, text) in enumerate(parts, 1)]


def figure_captions(pages):
    """Figure captions with their page: a line starting "Figure N:" (or "Fig. N.", "Fig N", "FIGURE N |", "Figure S1.",
    "Extended Data Fig. 2 |") up to a blank line. Ids: fig1, figS1, figED2."""
    captions, seen = [], set()
    for number, page in enumerate(pages, 1):
        lines = page.split("\n")
        for i, line in enumerate(lines):
            match = CAPTION.match(line)
            figure_id = match and "fig" + ("ED" if match.group(1) else "") + match.group(2).upper()
            if not match or figure_id in seen:
                continue
            seen.add(figure_id)
            text = line
            for following in lines[i + 1 :]:
                if not following or CAPTION.match(following) or len(text) >= CAPTION_CHARS:
                    break
                text += " " + following
            captions.append({"id": figure_id, "page": number, "caption": text[:CAPTION_CHARS]})
    return captions


def figure_mentions(pages, figure_id, limit=3):
    """Sentences in the body text that refer to a figure, e.g. "As Fig. 2 shows, ..."; captions excluded."""
    if figure_id.startswith("figP"):
        return []  # an unnumbered figure cannot be referred to by number
    number = figure_id.removeprefix("fig")
    extended = number.startswith("ED")
    mention = re.compile(rf"\b{'extended data ' if extended else '(?<!data )'}(?:figure|fig\.?)\s*{number.removeprefix('ED')}\b", re.I)
    found = []
    for page in pages:
        for sentence in SENTENCE_END.split(page.replace("\n", " ")):
            if mention.search(sentence) and not CAPTION.match(sentence) and sentence not in found:
                found.append(sentence.strip()[:300])
                if len(found) == limit:
                    return found
    return found


def select_figures(pages, captions, limit):
    """At most `limit` figures, keeping the ones the text refers to most, in paper order (unnumbered ones have no mentions)."""
    if len(captions) <= limit:
        return captions
    counts = {c["id"]: len(figure_mentions(pages, c["id"], limit=50)) for c in captions}
    chosen = set(sorted(counts, key=lambda i: -counts[i])[:limit])
    return [c for c in captions if c["id"] in chosen]
