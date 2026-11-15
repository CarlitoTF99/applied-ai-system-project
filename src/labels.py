"""The valid genre/mood labels (from the catalog) and the aliases the knowledge base defines for them."""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from src.recommender import MOOD_FAMILIES

# Alias words too common in ordinary phrases ("low energy", "heavy rain") to count as a label mention.
# They still work as alias *repairs* when a plan contains them.
AMBIGUOUS_MENTIONS = frozenset({
    "low", "down", "blue", "dark", "heavy", "bright", "mad", "house", "dub", "trap",
    "soul", "swing", "alternative", "piano", "indie", "cozy", "sunny", "lonely",
})


@dataclass
class LabelSpace:
    genres: List[str]
    moods: List[str]
    genre_aliases: Dict[str, str] = field(default_factory=dict)
    mood_aliases: Dict[str, str] = field(default_factory=dict)
    family_reps: Dict[str, str] = field(default_factory=dict)   # mood family name -> representative mood
    pairs: List[Tuple[str, str]] = field(default_factory=list)  # (genre, mood) of every catalog song

    def resolve(self, value: str, kind: str) -> str:
        """Return value if it is a catalog label, its alias/family target if it has one, else ""."""
        value = (value or "").strip().lower()
        catalog = self.genres if kind == "genre" else self.moods
        aliases = self.genre_aliases if kind == "genre" else {**self.mood_aliases, **self.family_reps}
        if value in catalog:
            return value
        return aliases.get(value, "")

    def default_label(self, kind: str, other: str = "") -> str:
        """Pick a label when retrieval gave no votes: the most common one among catalog songs that share
        the other label (e.g. the usual mood of hip-hop songs), else the catalog-wide most common; ties go
        alphabetically."""
        other_kind = "mood" if kind == "genre" else "genre"
        other = self.resolve(other, other_kind)
        index, other_index = (0, 1) if kind == "genre" else (1, 0)
        pool = [pair[index] for pair in self.pairs if other and pair[other_index] == other]
        if not pool:
            pool = [pair[index] for pair in self.pairs]
        if not pool:
            return (self.genres if kind == "genre" else self.moods)[0]
        counts: Dict[str, int] = {}
        for label in pool:
            counts[label] = counts.get(label, 0) + 1
        return min(counts, key=lambda label: (-counts[label], label))

    @classmethod
    def build(cls, songs: List[Dict], kb_docs: List) -> "LabelSpace":
        """Collect catalog labels from songs and aliases / family representatives from the knowledge docs."""
        genres = sorted({song["genre"].strip().lower() for song in songs})
        moods = sorted({song["mood"].strip().lower() for song in songs})
        genre_aliases, mood_aliases, family_reps = {}, {}, {}
        for doc in kb_docs:
            for source, target in doc.meta.get("aliases", {}).items():
                if target in genres:
                    genre_aliases[source] = target
                elif target in moods:
                    mood_aliases[source] = target
            family = doc.meta.get("family")
            doc_moods = [m for m in doc.meta.get("moods", []) if m in moods]
            if family and doc_moods:
                family_reps[family] = doc_moods[0]
        # Families with no knowledge doc fall back to a deterministic pick (sets have no order)
        for family, members in MOOD_FAMILIES.items():
            if family not in family_reps:
                in_catalog = sorted(m for m in members if m in moods)
                if in_catalog:
                    family_reps[family] = in_catalog[0]
        pairs = [(song["genre"].strip().lower(), song["mood"].strip().lower()) for song in songs]
        return cls(genres, moods, genre_aliases, mood_aliases, family_reps, pairs)

    def mentions(self, text: str, kind: str) -> List[Tuple[str, bool]]:
        """Return [(word, is_catalog_label)] for genre or mood words in text, in reading order.

        Catalog labels and unambiguous alias words both count; longer phrases win ("indie pop" over "pop").
        """
        if kind == "genre":
            catalog, aliases = self.genres, self.genre_aliases
        else:
            catalog = self.moods
            aliases = {**self.mood_aliases, **{f: r for f, r in self.family_reps.items()}}
        candidates = set(catalog) | {a for a in aliases if a not in AMBIGUOUS_MENTIONS}
        lowered = text.lower()
        found = []
        for word in sorted(candidates, key=len, reverse=True):
            pattern = r"(?<![a-z0-9&-])" + re.escape(word) + r"(?![a-z0-9&-])"
            for match in re.finditer(pattern, lowered):
                found.append((match.start(), word))
                # Blank the span so "pop" isn't found again inside "indie pop"
                lowered = lowered[: match.start()] + " " * len(word) + lowered[match.end():]
        found.sort()
        return [(word, word in catalog) for _, word in found]
