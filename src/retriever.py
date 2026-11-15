"""Knowledge-base and song-catalog loading plus a small pure-Python BM25 retriever."""

import math
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

BM25_K1 = 1.5
BM25_B = 0.75

# Words that carry no retrieval signal in requests like "some songs for the gym"
STOPWORDS = frozenset("""
a an the and or but for to of in on at by with from into over as is are was be been
it its this that these those i me my we our you your some something anything any
song songs music track tracks tune tunes playlist please want need like give play
find get can could would just really very too so not no also about what whats
""".split())

# Words joined by - & or ' stay together ("hip-hop", "r&b", "late-night")
_TOKEN_RE = re.compile(r"[a-z0-9]+(?:[-&'][a-z0-9]+)*")

FRONT_MATTER_LIST_KEYS = ("genres", "moods", "keywords")
FRONT_MATTER_RANGE_KEYS = ("energy", "valence")


def tokenize(text: str, drop_stopwords: bool = True) -> List[str]:
    """Lowercase text and split it into tokens; joined tokens also yield their parts (k-pop -> k-pop, pop)."""
    tokens = []
    for match in _TOKEN_RE.findall(text.lower()):
        pieces = [match]
        if re.search(r"[-&']", match):
            pieces += re.split(r"[-&']", match)
        for piece in pieces:
            if len(piece) < 2:
                continue
            if drop_stopwords and piece in STOPWORDS:
                continue
            tokens.append(piece)
    return tokens


@dataclass
class Doc:
    """One retrievable document: a knowledge-base markdown file or a song from the catalog."""
    doc_id: str                 # "studying.md" or "song:4"
    kind: str                   # "context" | "mood" | "genre" | "song"
    text: str                   # what BM25 indexes
    meta: Dict = field(default_factory=dict)
    body: str = ""              # prose shown to the LLM (knowledge docs only)

    def range(self, name: str) -> Optional[Tuple[float, float]]:
        """Return the (low, high) range for energy/valence, or None if the doc doesn't define one."""
        return self.meta.get(name)


def parse_front_matter(raw: str) -> Tuple[Dict, str]:
    """Split a markdown file into (front-matter dict, body); lists, ranges and aliases are parsed."""
    meta: Dict = {}
    body = raw
    if raw.startswith("---"):
        parts = raw.split("---", 2)
        if len(parts) == 3:
            _, header, body = parts
            for line in header.splitlines():
                line = line.split("#", 1)[0].strip()
                if not line or ":" not in line:
                    continue
                key, value = line.split(":", 1)
                meta[key.strip().lower()] = value.strip()

    for key in FRONT_MATTER_LIST_KEYS:
        if key in meta:
            meta[key] = [item.strip().lower() for item in meta[key].split(",") if item.strip()]
    for key in FRONT_MATTER_RANGE_KEYS:
        if key in meta:
            meta[key] = _parse_range(meta[key])
    if "aliases" in meta:
        aliases = {}
        for pair in meta["aliases"].split(","):
            if "=" in pair:
                source, target = pair.split("=", 1)
                aliases[source.strip().lower()] = target.strip().lower()
        meta["aliases"] = aliases
    if "acoustic" in meta:
        meta["acoustic"] = meta["acoustic"].lower()
    return meta, body.strip()


def _parse_range(value: str) -> Optional[Tuple[float, float]]:
    """Parse "0.20-0.45" into (0.2, 0.45); return None if it can't be read."""
    match = re.fullmatch(r"\s*([0-9.]+)\s*-\s*([0-9.]+)\s*", value)
    if not match:
        return None
    low, high = float(match.group(1)), float(match.group(2))
    return (min(low, high), max(low, high))


def load_knowledge(directory) -> List[Doc]:
    """Load every *.md file in directory as a Doc (sorted by name); a missing directory returns []."""
    directory = Path(directory)
    if not directory.is_dir():
        return []
    docs = []
    for path in sorted(directory.glob("*.md")):
        meta, body = parse_front_matter(path.read_text(encoding="utf-8"))
        kind = meta.get("type", "context")
        index_parts = [
            path.stem.replace("_", " "),
            body,
            " ".join(meta.get("keywords", [])),
            " ".join(meta.get("genres", [])),
            " ".join(meta.get("moods", [])),
            " ".join(meta.get("aliases", {}).keys()),
        ]
        docs.append(Doc(path.name, kind, "\n".join(index_parts), meta, body))
    return docs


def _bin(value: float, low_word: str, mid_word: str, high_word: str) -> str:
    """Turn a 0-1 feature into a word: below 0.4 low, 0.4-0.7 mid, above 0.7 high."""
    if value < 0.4:
        return low_word
    if value <= 0.7:
        return mid_word
    return high_word


def song_to_doc(song: Dict) -> Doc:
    """Describe a catalog song in words so BM25 can match it against a request."""
    words = [
        song["title"],
        song["artist"],
        song["genre"],
        song["mood"],
        " ".join(song.get("mood_tags", [])),
        _bin(song["energy"], "low-energy calm quiet slow", "mid-energy", "high-energy upbeat loud"),
        _bin(song["valence"], "low-valence dark", "mid-valence", "high-valence bright"),
        _bin(song["acousticness"], "electric", "semi-acoustic", "acoustic"),
    ]
    if song.get("instrumentalness", 0.0) > 0.7:
        words.append("instrumental")
    return Doc(f"song:{song['id']}", "song", " ".join(words), meta=song)


class BM25Index:
    """A BM25 index over a fixed list of Docs."""

    def __init__(self, docs: List[Doc], k1: float = BM25_K1, b: float = BM25_B):
        self.docs = list(docs)
        self.k1 = k1
        self.b = b
        self._term_freqs = [Counter(tokenize(doc.text)) for doc in self.docs]
        self._lengths = [sum(tf.values()) for tf in self._term_freqs]
        self._avg_length = (sum(self._lengths) / len(self._lengths)) if self.docs else 0.0
        doc_freq = Counter(term for tf in self._term_freqs for term in tf)
        n = len(self.docs)
        # The "+1" form of BM25 idf is always positive, even for very common terms
        self._idf = {
            term: math.log((n - df + 0.5) / (df + 0.5) + 1.0) for term, df in doc_freq.items()
        }

    def search(self, query: str, k: int = 3) -> List[Tuple[Doc, float]]:
        """Return up to k (doc, score) pairs with score > 0, best first; ties keep load order."""
        if k <= 0 or not self.docs:
            return []
        terms = tokenize(query)
        if not terms:
            return []
        scored = []
        for index, tf in enumerate(self._term_freqs):
            score = 0.0
            length_norm = self.k1 * (1 - self.b + self.b * self._lengths[index] / self._avg_length)
            for term in terms:
                freq = tf.get(term, 0)
                if freq:
                    score += self._idf[term] * freq * (self.k1 + 1) / (freq + length_norm)
            if score > 0:
                scored.append((index, round(score, 3)))
        scored.sort(key=lambda pair: (-pair[1], pair[0]))
        return [(self.docs[index], score) for index, score in scored[:k]]

    def vocabulary(self) -> set:
        """Return every indexed term."""
        return set(self._idf)
