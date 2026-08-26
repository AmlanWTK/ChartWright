"""Document classification (CP14): page image -> DocType via the CP11 model gateway.

First model-calling checkpoint in the pipeline (CP12's OCR and CP13's preprocessing are
both deterministic). Runs at the ``CLASSIFIED`` stage, *before* OCR
(``STATUS_ORDER``: ``NORMALIZED -> CLASSIFIED -> OCR_DONE``), so classification works
from the page image alone — no OCR text is available yet.

Two scope decisions fixed by the owner before implementation (CP14 spec):
  1. Only the packet's first page is classified, not the whole packet.
  2. Confidence is uncalibrated. CP17 builds the real signal; this checkpoint exists to
     give CP17 something to calibrate against, not to be trustworthy on its own.

Design: describe-then-map, not constrained choice
-------------------------------------------------
The first implementation asked the Tier-0 model to pick one of the nine ``DocType``
codes directly, using Ollama's structured-output mode to constrain decoding to a
nine-value enum. Measured against synthetic documents it scored **28.3%**, and the
diagnosis was instructive:

  * Asked simply to "Describe this image.", the model reads a PA form correctly —
    "a page of text that appears to be a request for prior authorization". Vision,
    resolution and legibility are all fine.
  * Asked the same question as a nine-way constrained selection, it collapses. The
    grammar guarantees *well-formed* output, which masks the fact that the content is
    wrong; every miss came back as ``clinical_note`` with a confidence wedged in a dead
    0.66-0.71 band. Shortening the prompt, reordering the enum, and cropping the page
    all failed to fix it (measured: 33-53% across those variants).

So the model does perception in the register it is actually good at — free-text
description — and the taxonomy mapping happens here, in deterministic code, where it is
auditable, testable, and structurally incapable of inventing a tenth type. Measured
66.7% overall on the same eval that scored 28.3% before, with prior-auth forms going
from 0/4 to 4/4.

Two known fragilities, documented rather than hidden:
  * **The prompt is load-bearing.** "Describe this image." works; "What kind of document
    is this?" scored 0% on every type. Small VLMs are extremely sensitive to phrasing,
    so ``_DESCRIBE_PROMPT`` is not a free parameter — changing it requires re-running
    ``scripts/eval_classify.py``.
  * **The keyword table is tuned against the synthetic generators.** It encodes what
    these nine coarse, verbally-distinct types are *called*, which is stable, but it has
    not been measured against real faxes and would not survive a fine-grained taxonomy.

Confidence here is derived from evidence, not self-reported: the winning type's keyword
score over the total matched score, so an unambiguous description scores 1.0, a mixed one
scores lower, and an unmatched one is ``OTHER`` at 0.0. Unlike the model's self-report,
this actually varies with the input — which is the point, since CP17 cannot calibrate a
constant.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from chartwright_gateway import ModelGateway, ModelRequest, ModelResponse
from chartwright_schemas.taxonomy import DocType
from PIL import Image

# Load-bearing (see module docstring). Do not tune without re-running the eval.
_DESCRIBE_PROMPT = "Describe this image."

# Descriptions run 30-70 tokens; the cap is generous enough not to truncate mid-phrase
# and small enough to keep CPU inference quick.
_MAX_TOKENS = 96

# Revision note (CP14 verification, second pass): the first table was written from the
# taxonomy's formal type names and under-covered ordinary phrasing. Reading the eval's
# actual failures showed the model saying "lab result" (not "laboratory result") and
# "health plan card" (not "insurance card"), so those were added, along with a
# low-weight "health insurance". Each is a term a clinician would list without seeing
# the eval -- but they WERE added after observing failures, so the resulting accuracy
# is fitted to the synthetic set and should be read as optimistic. CP26's versioned
# gold set is where this table's generalization actually gets tested.
#
# Phrase -> weight, per type. Multi-word phrases score higher because they are far less
# likely to appear incidentally: "insurance" shows up in a PA form's description, while
# "insurance card" does not. Deliberately conservative — no match at all must mean
# OTHER (which always routes to human review), never a guess.
_KEYWORDS: dict[DocType, tuple[tuple[str, float], ...]] = {
    DocType.PRIOR_AUTH_REQUEST: (
        ("prior authorization", 5.0),
        ("pre-authorization", 4.0),
        ("preauthorization", 4.0),
        ("prior auth", 4.0),
        ("authorization request", 4.0),
        ("authorization", 1.5),
    ),
    DocType.REFERRAL: (
        ("referral", 5.0),
        ("referred to", 3.0),
        ("consultation request", 3.0),
    ),
    DocType.EOB: (
        ("explanation of benefits", 5.0),
        ("eob", 4.0),
        ("claim line", 3.0),
        ("amount billed", 3.0),
        ("patient responsibility", 3.0),
        ("claim", 1.5),
    ),
    DocType.LAB_REPORT: (
        ("laboratory result", 5.0),
        ("laboratory report", 5.0),
        ("lab report", 5.0),
        ("lab result", 4.5),
        ("test result", 4.0),
        ("reference range", 3.0),
        ("laboratory", 2.5),
    ),
    DocType.DISCHARGE_SUMMARY: (
        ("discharge summary", 5.0),
        ("discharge instructions", 4.0),
        ("discharge", 2.5),
    ),
    DocType.CLINICAL_NOTE: (
        ("progress note", 5.0),
        ("clinical note", 5.0),
        ("office visit", 4.0),
        ("visit note", 4.0),
        ("physician note", 4.0),
        ("chief complaint", 3.0),
    ),
    DocType.INSURANCE_CARD: (
        ("insurance card", 5.0),
        ("member id card", 5.0),
        ("health insurance member", 5.0),
        ("health plan card", 4.5),
        ("id card", 4.0),
        ("member card", 4.0),
        ("member id", 3.0),
        ("group number", 2.5),
        ("rxbin", 3.0),
        ("health insurance", 2.0),
    ),
    DocType.ID_DOCUMENT: (
        ("driver's license", 5.0),
        ("drivers license", 5.0),
        ("identification card", 4.0),
        ("passport", 4.0),
    ),
}


@dataclass(frozen=True)
class ClassificationResult:
    """The classifier's verdict for one page, plus the model's raw description.

    ``raw_text`` is the full description the model produced. It is strictly richer for
    audit than the bare enum value the previous implementation stored: a reviewer can
    see *why* a page was typed the way it was, and a wrong call is legible rather than
    opaque.
    """

    doc_type: DocType
    confidence: float  # derived from evidence, [0, 1] — UNCALIBRATED, see module docstring
    raw_text: str


def map_description(text: str) -> tuple[DocType, float]:
    """Map a free-text page description onto exactly one ``DocType``.

    Pure and deterministic — the whole point of doing this step in code rather than in
    the model. Returns ``(OTHER, 0.0)`` when nothing matches, which is precisely the
    case ``OTHER`` + mandatory review exists for (``docs/domain/taxonomy.md``, "safety
    rails in the taxonomy itself").
    """
    lowered = text.lower()
    scores: dict[DocType, float] = {}
    for doc_type, phrases in _KEYWORDS.items():
        score = sum(weight for phrase, weight in phrases if phrase in lowered)
        if score > 0.0:
            scores[doc_type] = score
    if not scores:
        return DocType.OTHER, 0.0

    # Deterministic tie-break on the type's own code, so an exact score tie never
    # depends on dict iteration order.
    best = max(scores, key=lambda k: (scores[k], k.value))
    total = sum(scores.values())
    return best, scores[best] / total


def classify_packet(
    page_image: Image.Image, *, gateway: ModelGateway, tenant_id: str
) -> ClassificationResult:
    """Classify a packet from its first page image.

    Never raises on any model output — an empty, truncated, or nonsensical description
    simply matches no keyword and lands in ``OTHER`` at 0.0 confidence. Provider-level
    failures (``AllProvidersFailedError``) do propagate, so the pipeline's retry and
    DLQ machinery can see them; a dead engine is not the same thing as an unrecognized
    document.
    """
    buf = io.BytesIO()
    page_image.convert("RGB").save(buf, format="PNG")
    request = ModelRequest(
        prompt=_DESCRIBE_PROMPT,
        images=(buf.getvalue(),),
        tier=0,
        purpose="classify",
        tenant_id=tenant_id,
        temperature=0.0,
        max_tokens=_MAX_TOKENS,
    )
    return _from_response(gateway.generate(request))


def _from_response(response: ModelResponse) -> ClassificationResult:
    doc_type, confidence = map_description(response.text)
    return ClassificationResult(doc_type=doc_type, confidence=confidence, raw_text=response.text)
