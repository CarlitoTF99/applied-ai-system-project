"""A deterministic 0-1 confidence for an agent result.

The LLM is never asked to rate itself. Confidence starts at 1.0 and loses points for:
  - a top score well below the profile's maximum      (up to -0.30)
  - a weak or missing knowledge-base retrieval match  (up to -0.25)
  - repairs the validator had to make to the plan     (-0.05 each, up to -0.15)
  - self-check retries                                (-0.10 each, up to -0.20)
  - the LLM falling back to offline mode              (-0.10; not applied when --offline was chosen)
"""

from dataclasses import dataclass, field
from typing import List

SCORE_WEIGHT = 0.6              # penalty = SCORE_WEIGHT * (1 - top_score / max_score), capped below
SCORE_PENALTY_CAP = 0.30
RETRIEVAL_FULL_SCORE = 4.0      # a top BM25 doc score at or above this counts as a strong match
RETRIEVAL_WEIGHT = 0.25
REPAIR_PENALTY = 0.05
REPAIR_PENALTY_CAP = 0.15
RETRY_PENALTY = 0.10
RETRY_PENALTY_CAP = 0.20
LLM_FALLBACK_PENALTY = 0.10
MIN_SHOWN_PENALTY = 0.005       # smaller penalties are not listed as reasons

HIGH = 0.75
MEDIUM = 0.50


@dataclass
class Confidence:
    score: float                                     # 0-1, rounded to 2 decimals
    label: str                                       # "high" | "medium" | "low"
    summary: str                                     # one line of the key facts
    lowered_by: List[str] = field(default_factory=list)


def compute_confidence(
    top_ratio: float,
    top_doc_score: float,
    repairs: int,
    retries: int,
    llm_fallback: bool,
) -> Confidence:
    """Combine the five signals into a confidence score with human-readable reasons."""
    penalties = []

    ratio = max(0.0, min(1.0, top_ratio))
    score_penalty = min(SCORE_PENALTY_CAP, SCORE_WEIGHT * (1 - ratio))
    penalties.append((score_penalty, f"top score only {ratio:.0%} of max"))

    if top_doc_score <= 0:
        penalties.append((RETRIEVAL_WEIGHT, "no knowledge doc matched the request"))
    elif top_doc_score < RETRIEVAL_FULL_SCORE:
        penalties.append((
            RETRIEVAL_WEIGHT * (1 - top_doc_score / RETRIEVAL_FULL_SCORE),
            f"weak retrieval match (top doc score {top_doc_score:.2f})",
        ))

    if repairs:
        penalties.append((min(REPAIR_PENALTY_CAP, REPAIR_PENALTY * repairs),
                          f"{repairs} repair{'s' if repairs != 1 else ''} to the plan"))
    if retries:
        penalties.append((min(RETRY_PENALTY_CAP, RETRY_PENALTY * retries),
                          f"{retries} self-check retr{'ies' if retries != 1 else 'y'}"))
    if llm_fallback:
        penalties.append((LLM_FALLBACK_PENALTY, "LLM fell back to offline mode"))

    total = sum(p for p, _ in penalties)
    score = round(max(0.0, min(1.0, 1.0 - total)), 2)
    label = "high" if score >= HIGH else "medium" if score >= MEDIUM else "low"

    facts = [f"top score {ratio:.0%} of max",
             "no repairs" if not repairs else f"{repairs} repair{'s' if repairs != 1 else ''}",
             "no retries" if not retries else f"{retries} retr{'ies' if retries != 1 else 'y'}"]
    if llm_fallback:
        facts.append("LLM fallback")
    lowered_by = [f"-{p:.2f} {reason}" for p, reason in sorted(penalties, key=lambda x: -x[0])
                  if p >= MIN_SHOWN_PENALTY]
    return Confidence(score, label, ", ".join(facts), lowered_by)
