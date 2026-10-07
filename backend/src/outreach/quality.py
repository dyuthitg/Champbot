"""
Copy quality gate: the deterministic "is this spam?" check.

Every drafted message passes through here before a human ever sees it, and
again before it is sent. It is rules-based on purpose — a model asked "is this
spammy?" will happily approve its own output, and the failure modes we care
about (a leaked ``{{first_name}}``, a booking link in a connection note, a
message that could have been sent to literally anyone) are precisely the ones
plain string checks catch reliably.

Two severities:

- **Blockers** fail the copy outright. It cannot be shown for approval or sent
  until it is rewritten. These are things that are always wrong.
- **Warnings** deduct from a 0-100 quality score and are surfaced to the
  reviewer. These are things that are usually wrong.

The bar is intentionally high. Copy that scores badly here is copy that would
have made the recipient think "this is a bot", which is the one outcome that
costs more than sending nothing at all.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, List, Optional

# LinkedIn's hard limit on an invitation note.
CONNECT_NOTE_MAX = 300
# Our own limit on a first direct message. Longer than this doesn't get read.
MESSAGE_MAX = 900
MESSAGE_IDEAL_MAX = 600
COMMENT_MAX = 400
# The spec's own target for a comment (COMMENT_QUALITY_SPEC_V1.md, R2). It is
# deliberately *not* the enforced limit: COMMENT_MAX above is the blocking cap
# and the gap between the two is documented in COMMENT_RULES_ENFORCEMENT_GAP.md
# ("only by proxy, and the proxy is ~2x looser"). The editor's live counter
# turns amber at this number and red at COMMENT_MAX, so an operator can see
# both the target and the wall.
COMMENT_TARGET_CHARS = 280
# R1: a comment should be 1-3 sentences.
COMMENT_SENTENCE_MAX = 3

# Phrases that mark copy as template-generated outreach. Recipients have seen
# each of these a thousand times.
_TIRED_PHRASES = [
    "i hope this message finds you well",
    "i hope this email finds you well",
    "hope you're doing well",
    "hope you are doing well",
    "quick question",
    "just following up",
    "just checking in",
    "circle back",
    "touch base",
    "reach out to see if",
    "as per my last",
    "i wanted to reach out",
    "i came across your profile",
    "i stumbled upon your profile",
    "let me know if you'd be open",
    "does that sound like something",
    "pick your brain",
    "synergy",
    "synergies",
    "game-changer",
    "game changer",
    "revolutionary",
    "cutting-edge solution",
    "world-class",
    "best-in-class",
    "10x your",
    "guaranteed results",
    "limited time",
    "act now",
    "dear sir or madam",
    "to whom it may concern",
    # Added 2026-09-04. COMMENT_QUALITY_SPEC_V1.md's R4 list has carried these
    # since 2026-08-25, under "This week, no new logic: wire the extended R4
    # banned-phrase list into _TIRED_PHRASES" -- and it never got wired. The
    # first staging run of the full loop found out the hard way: three of the
    # five comments the model wrote that morning opened with "You make a solid
    # point" / "That's a solid insight", and R4 stayed silent on all three
    # because the enforced list had never caught up with the written one.
    #
    # Two phrases the spec deliberately leaves OFF stay off: "it's interesting
    # how" and "i've seen teams". The human audit never tagged either as a
    # violation on its own, and one of the six good-graded comments uses the
    # first outright. Frequency is not the bar; matching a named failure is.
    "thanks for sharing",
    "great insights",
    "spot on",
    "you make a solid point",
    "you make a great point",
    "you make a good point",
    "you raise a good point",
    "you raise a crucial point",
    "you nailed it",
    "you've nailed it",
    "absolutely agree",
    "that's a solid approach",
    "that is a solid",
    # Added 2026-09-08. The first staging run's "second opinion" check (the
    # independent audit taxonomy in scripts/score_audit.py) approved-and-flagged
    # "Interesting approach, Amaya." at 100/100 through this gate -- these two
    # specific validation openers from that taxonomy's VALIDATE_OPENERS list
    # were never wired in here, so the gate had nothing to catch them with.
    "interesting approach",
    "interesting results",
    "that's a pivotal",
    "that's a significant",
]

# Validation-opener phrases, checked separately from the scored list above:
# whether a comment *opens* on one of these (regardless of scoring) is the
# other half of the "3-beat bot template" the August audit named as its worst
# failure mode (validate -> restate the thesis -> generic strategy question).
# Mirrors scripts/score_audit.py's VALIDATE_OPENERS -- that script is the
# reference taxonomy this gate is now held to. Deliberately excludes "it's
# interesting" / "it is interesting" bare: the human audit never tagged either
# as a violation on its own (see the _TIRED_PHRASES note above).
_VALIDATION_OPENER_PHRASES = [
    "you raise a good point", "you make a good point", "you make a great point",
    "you make a solid point", "that's a solid", "that is a solid",
    "great point", "good point", "you nailed it", "you've nailed it",
    "spot on", "absolutely agree", "well said", "interesting approach",
    "interesting results", "that's a pivotal", "that's a significant",
]

# Asks that don't belong in a first touch, especially not a connection note.
_HARD_CTA = [
    "book a call",
    "book a time",
    "book a demo",
    "schedule a call",
    "schedule a demo",
    "hop on a call",
    "jump on a call",
    "15 minutes of your time",
    "15 mins of your time",
    "30 minutes of your time",
    "grab 15",
    "free trial",
    "sign up today",
    "buy now",
]

_LINK_PATTERN = re.compile(r"(https?://|www\.|\b[\w.-]+\.(?:com|io|co|ai|net|org)/)", re.I)
_CALENDAR_PATTERN = re.compile(r"(calendly|savvycal|hubspot\.com/meetings|cal\.com|zcal)", re.I)
# Unsubstituted template variables in every syntax we might plausibly emit.
_PLACEHOLDER_PATTERN = re.compile(
    r"(\{\{.*?\}\}|\{[a-z_]+\}|\[(?:first[_ ]?name|name|company|title|role)\]"
    r"|<[a-z_]+>|\bFIRST[_ ]NAME\b|\bXYZ\b|\bACME\b|\bLorem ipsum\b)",
    re.I,
)
_EMOJI_PATTERN = re.compile(
    "[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F900-\U0001F9FF]"
)
# Acronyms that are legitimately capitalized in professional copy.
_ALLOWED_CAPS = {
    "AI", "ML", "API", "SaaS", "B2B", "B2C", "CEO", "CTO", "COO", "CFO", "CMO",
    "VP", "HR", "IT", "SEO", "CRM", "ERP", "ROI", "KPI", "OKR", "SDR", "AE",
    "UK", "US", "USA", "EU", "NHS", "GTM", "PLG", "LLM", "SQL", "AWS", "GCP",
    "IPO", "PE", "VC", "NPS", "ARR", "MRR", "QA", "UX", "UI", "PM",
    # Added 2026-09-04 from the first staging run: the model wrote "NRR" --
    # the metric our own ICP posts about -- and the gate called it shouting,
    # while ARR and MRR two entries up were fine. Same vocabulary, same list.
    "NRR", "LTV", "CAC", "ICP", "SEM", "PPC", "CSAT", "DAU", "MAU", "WAU",
}

# Generic openers that prove nothing about the recipient was read.
_GENERIC_OPENERS = ["hi there", "hey there", "hello there", "dear friend", "hi friend"]

# Words common enough in professional headlines that echoing one back proves
# nothing. Without this, "growth" appearing in both a headline and a generic
# message would be scored as evidence the profile was read.
_GENERIC_HEADLINE_WORDS = {
    "growth", "manager", "director", "founder", "leader", "leading", "company",
    "business", "product", "customer", "customers", "marketing", "digital",
    "strategy", "strategic", "solutions", "services", "software", "technology",
    "platform", "consultant", "consulting", "specialist", "professional",
    "experience", "helping", "building", "passionate", "driving", "focused",
    "operations", "engineering", "development", "management", "partner",
    # Added 2026-09-02: the topic vocabulary of a whole vertical (SaaS growth
    # posts, here) is just as generic as a job title once a bot is writing at
    # scale — "activation" showing up in both a post and a reply proves the
    # post was about activation, not that the profile was actually read.
    # Found via the Aug 21 audit's worst-scoring comment, which shared only
    # "activation"/"product"/"marketing" with its source post and still
    # scored a false personalization signal without this.
    "activation", "retention", "onboarding", "strategies", "collaboration",
    "engagement", "conversion", "adoption", "alignment",
}


# ----------------------------------------------------------------------
# The rule vocabulary
# ----------------------------------------------------------------------
#
# One name per rule, defined once, here. Everything downstream -- the chips in
# the review queue, the failure-type filter, the PDF write-ups -- reads its
# wording from this table, so a rule is called the same thing in the spec, in
# the code, and on the operator's screen. Before this existed the gate emitted
# free-text sentences ("Uses worn-out outreach phrasing: 'quick question'") and
# the UI had no way to group two drafts that failed the same rule.
#
# ``spec_ref`` is the heading in COMMENT_QUALITY_SPEC_V1.md the rule comes
# from, or ``None`` for a check that exists in this file but was never written
# into the spec -- an honest gap, surfaced rather than quietly renamed.


@dataclass(frozen=True)
class Rule:
    """One named guardrail: its short operator-facing label and where it came from."""

    code: str
    label: str
    spec_ref: Optional[str] = None


RULES: dict = {
    r.code: r
    for r in [
        # --- Rules the comment spec numbers (COMMENT_QUALITY_SPEC_V1.md) ---
        Rule("R1", "Too many sentences", "R1 - Length: 1 to 3 sentences"),
        Rule("R2", "Too long", "R2 - Length: 280 characters"),
        Rule("R3", "No specific reference", "R3 - Specificity"),
        Rule("R4", "Generic phrase", "R4 - Banned phrases"),
        Rule("R5", "Formula question", "R5 - The formulaic closing question"),
        Rule("R6", "Emoji", "R6 - Emoji: zero"),
        Rule("R7", "Too many exclamations", "R7 - Exclamation marks: at most one"),
        # Spec item 8 lumps three different failures under one number. Split
        # here because an operator filtering the queue needs them apart: a
        # leaked merge field and a booking link are not the same mistake.
        Rule("R8.1", "Placeholder left in", "Automatic reject 8 - placeholder"),
        Rule("R8.2", "Link", "Automatic reject 8 - link"),
        # --- Checks that live in this file but not (yet) in the spec ---
        # Flagged as gaps on purpose: v2 of the spec should name these, and
        # until it does, the chip says so rather than implying spec coverage.
        Rule("LEN_SOFT", "Longer than ideal"),
        Rule("THIN", "Too thin"),
        Rule("CTA", "Asks for time up front"),
        Rule("OPENER", "Generic opener"),
        Rule("CAPS", "Shouting in caps"),
        Rule("SELF", "All about us"),
        Rule("EMPTY", "No draft"),
        # Added 2026-09-08, closing the gap the first staging run's second
        # opinion check found: a validation opener plus the formulaic closing
        # question, together, is the "3-beat bot template" the August audit
        # named as its worst failure mode and grades as a hard fail. R4 and R5
        # alone only warn/advise; this is what actually stops that exact shape.
        Rule("TEMPLATE3", "Formulaic 3-beat template"),
        # Cross-queue, not per-draft: computed in src/outreach/similarity.py
        # once the whole pending batch is loaded. It lives in this table
        # anyway so the queue has one vocabulary, not two.
        Rule("DUP", "Near-identical to others"),
    ]
}

# Severity decides colour and whether the item can be approved at all.
#   blocker  - cannot be approved or sent until rewritten
#   warning  - deducts from the 0-100 score, shown to the reviewer
#   advisory - shown only. Never touches the score or the pass/fail verdict.
SEVERITIES = ("blocker", "warning", "advisory")


@dataclass
class QualityFlag:
    """One rule, failed, on one piece of copy."""

    code: str
    label: str
    severity: str
    detail: str
    spec_ref: Optional[str] = None

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "label": self.label,
            "severity": self.severity,
            "detail": self.detail,
            "spec_ref": self.spec_ref,
        }


def flag(code: str, detail: str, severity: str = "warning") -> QualityFlag:
    """Build a flag from the rule table, so wording is never retyped."""
    rule = RULES[code]
    return QualityFlag(
        code=rule.code,
        label=rule.label,
        severity=severity,
        detail=detail,
        spec_ref=rule.spec_ref,
    )


def _normalize_quotes(text: str) -> str:
    """
    Typographic apostrophes/quotes -> straight ASCII ones.

    An LLM writes "That's" with a curly '’', not a straight "'" -- every
    phrase list in this file (_TIRED_PHRASES, _VALIDATION_OPENER_PHRASES,
    _R5_STRATEGY_PHRASES, _R5_PRONOUNS) is written with straight ones, so
    without this, any phrase containing an apostrophe silently never matches
    real model output. Found via the first demo run against a live OpenRouter
    draft: "That’s a solid insight..." followed by the exact formulaic
    question shape scored 100/100 and passed clean, because '’' != "'".
    """
    return (text or "").replace("’", "'").replace("‘", "'")


def count_sentences(text: str) -> int:
    """
    R1's test, exactly as the spec writes it: split on ``.``/``!``/``?``
    boundaries and count the non-empty segments.
    """
    return len([part for part in re.split(r"[.!?]+", text or "") if part.strip()])


# R5's test: a question containing a pronoun near one of these verbs *and* a
# topic noun is the formulaic closing question -- the shape 43 of 58 audited
# comments shared. Banning the shape holds where banning the wording does not.
_R5_PRONOUNS = re.compile(r"\b(you|you've|you'd|your)\b", re.I)
# The spec names five verbs: found, find, noticed, seen, tried. It named them
# in one tense each, which is a wording slip rather than a decision -- "did you
# notice any specific trends" is the same rule being broken as "have you noticed
# any specific trends", and the first staging run produced exactly that sentence
# and sailed through. Completing the inflections of the verbs the spec already
# chose is finishing the rule as written. Adding *new* verbs, or new topic
# nouns, would be chasing a dataset -- that stays a v2 item with real data
# behind it, per R5's logged gap.
_R5_VERBS = re.compile(
    r"\b(found|find|finds|finding|notice|notices|noticed|noticing"
    r"|see|sees|seen|seeing|try|tries|tried|trying)\b",
    re.I,
)
_R5_TOPIC_NOUNS = re.compile(
    r"\b(strateg\w*|approach\w*|tactic\w*|framework\w*|trend\w*|metric\w*)\b", re.I
)

# A second, literal detector for the same rule, mirroring
# scripts/score_audit.py's STRATEGY_QUESTION list. The shape-based regex above
# requires a topic noun near the verb, which the August audit's list does not
# -- and that gap is exactly how "...have you found any particular user
# feedback that led to other changes in the onboarding process?" passed this
# gate at 100/100 in the first staging run while the audit taxonomy graded the
# same comment "weak" ("feedback"/"changes" aren't in _R5_TOPIC_NOUNS). Both
# detectors stay: the shape-based one catches paraphrases the audit's fixed
# phrases don't, and the phrase list catches the literal wording the audit
# taxonomy was built from.
_R5_STRATEGY_PHRASES = [
    "have you found", "what strategies have you", "any specific strategies",
    "what specific strategies", "have you seen any specific",
    "have you noticed any", "did you notice any", "what strategies",
]


def has_formulaic_question(text: str) -> bool:
    """True if any question in ``text`` matches R5's pronoun+verb+topic shape,
    or contains one of the audit's literal formulaic-question phrases."""
    normalized = _normalize_quotes(text)
    low = normalized.lower()
    if any(p in low for p in _R5_STRATEGY_PHRASES):
        return True
    for sentence in re.split(r"(?<=[.!?])\s+", normalized):
        if not sentence.strip().endswith("?"):
            continue
        if (
            _R5_PRONOUNS.search(sentence)
            and _R5_VERBS.search(sentence)
            and _R5_TOPIC_NOUNS.search(sentence)
        ):
            return True
    return False


@dataclass
class QualityReport:
    """Verdict on one piece of drafted copy."""

    score: int
    passed: bool
    blockers: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)
    # The same findings as ``blockers``/``warnings``, plus advisory-only ones,
    # each carrying the rule it broke. This is what the review queue renders
    # as chips and filters by; the two string lists above stay exactly as they
    # were so every existing caller keeps working.
    flags: List[QualityFlag] = field(default_factory=list)

    def __bool__(self) -> bool:
        return self.passed

    @property
    def all_issues(self) -> List[str]:
        return self.blockers + self.warnings

    @property
    def flag_codes(self) -> List[str]:
        return [f.code for f in self.flags]


def _limit_for(action: str) -> int:
    if action == "connect":
        return CONNECT_NOTE_MAX
    if action == "comment":
        return COMMENT_MAX
    return MESSAGE_MAX


def check_copy(
    text: Optional[str],
    action: str,
    target: Any = None,
    *,
    min_score: int = 70,
    allow_scheduler_link: bool = False,
) -> QualityReport:
    """
    Evaluate drafted copy for ``action`` aimed at ``target``.

    ``target`` is duck-typed (``first_name``, ``full_name``, ``company``,
    ``title``, ``headline``) and used to verify the copy is actually about this
    person rather than about nobody in particular.

    ``allow_scheduler_link`` is set only by the booking step of a sequence,
    after the prospect has replied and been qualified. A calendar link in a
    first touch is spam; the same link once someone has asked to talk is what
    they wanted. The rule is about *when*, not about the link.
    """
    blockers: List[str] = []
    warnings: List[str] = []
    flags: List[QualityFlag] = []
    score = 100

    def fail(code: str, message: str, severity: str = "warning") -> None:
        """Record one finding once, in both shapes: the sentence humans read
        and the named rule the queue groups and filters by."""
        if severity == "blocker":
            blockers.append(message)
        elif severity == "warning":
            warnings.append(message)
        flags.append(flag(code, message, severity))

    body = (text or "").strip()
    if not body:
        return QualityReport(
            score=0,
            passed=False,
            blockers=["Message is empty"],
            stats={"length": 0},
            flags=[flag("EMPTY", "Message is empty", "blocker")],
        )

    lowered = _normalize_quotes(body).lower()
    limit = _limit_for(action)
    words = body.split()

    # --- Length ---
    if len(body) > limit:
        fail(
            "R2",
            f"Too long for a {action}: {len(body)} characters (limit {limit})",
            "blocker",
        )
    elif action == "message" and len(body) > MESSAGE_IDEAL_MAX:
        fail("LEN_SOFT", f"Long for a first message ({len(body)} chars); shorter reads better")
        score -= 10
    elif action == "comment" and len(body) > COMMENT_TARGET_CHARS:
        # Over the spec's own R2 target but under the enforced cap. Advisory:
        # the number that blocks is COMMENT_MAX, and pretending otherwise
        # would reject copy the gate actually lets through.
        fail(
            "R2",
            f"Over the {COMMENT_TARGET_CHARS}-character target for a comment ({len(body)} chars)",
            "advisory",
        )

    if len(words) < 8:
        fail("THIN", "Very short — likely too thin to be worth sending")
        score -= 15

    # R1, comments only, advisory: sentence counting is new logic the
    # enforcement audit assigned to whoever owns the shared gate, so it is
    # shown and never enforced here. See COMMENT_RULES_ENFORCEMENT_GAP.md.
    if action == "comment":
        sentences = count_sentences(body)
        if sentences > COMMENT_SENTENCE_MAX:
            fail("R1", f"{sentences} sentences — the rule is 1 to 3", "advisory")

    # --- Unsubstituted placeholders: always a blocker ---
    placeholder = _PLACEHOLDER_PATTERN.search(body)
    if placeholder:
        fail(
            "R8.1",
            f"Contains an unfilled placeholder: '{placeholder.group(0)}'",
            "blocker",
        )

    # --- Links ---
    has_calendar = bool(_CALENDAR_PATTERN.search(body))
    if has_calendar and not allow_scheduler_link:
        fail("R8.2", "Contains a booking link — never in a first touch", "blocker")
    elif _LINK_PATTERN.search(body) and not (has_calendar and allow_scheduler_link):
        if action == "connect":
            fail(
                "R8.2",
                "Contains a link — connection notes with links get reported",
                "blocker",
            )
        elif not allow_scheduler_link:
            fail("R8.2", "Contains a link in a first message")
            score -= 20

    # --- Hard CTAs ---
    # Asking for time is the entire point of the booking step, so the CTA rules
    # relax exactly where a scheduler link is permitted.
    if not allow_scheduler_link:
        for phrase in _HARD_CTA:
            if phrase in lowered:
                if action == "connect":
                    fail("CTA", f"Pitches in a connection request: '{phrase}'", "blocker")
                else:
                    fail("CTA", f"Asks for time up front: '{phrase}'")
                    score -= 15
                break

    # --- Tired template phrases ---
    tired = [p for p in _TIRED_PHRASES if p in lowered]
    if tired:
        fail("R4", f"Uses worn-out outreach phrasing: '{tired[0]}'")
        score -= 20 * min(len(tired), 3)

    # Validation-opener check (combo detection only -- see TEMPLATE3 below).
    # Not separately scored: most of these phrases are already in
    # _TIRED_PHRASES and would double-count against the same R4 deduction
    # above if scored again here.
    opener_hit = any(p in lowered for p in _VALIDATION_OPENER_PHRASES)

    # --- Generic opener ---
    for opener in _GENERIC_OPENERS:
        if lowered.startswith(opener):
            fail("OPENER", f"Generic opener '{opener}' — no sign the profile was read")
            score -= 30
            break

    # --- Personalization: is this message about *this* person? ---
    if target is not None:
        signals = _personalization_signals(lowered, target)
        if not signals:
            fail("R3", "No personal detail — this could have been sent to anyone")
            score -= 25
    else:
        signals = []

    # --- Shouting and punctuation ---
    # Strip punctuation *before* both tests, not just the allow-list check.
    # Found in the first staging run: "NRR?" was flagged as shouting while a
    # bare "NRR" was not, because the length test ran on the unstripped token
    # and a trailing question mark pushed a three-letter acronym over the
    # limit. Whether an acronym is shouting cannot depend on where it lands in
    # the sentence.
    shouty = []
    for word in words:
        bare = word.strip(".,!?;:'\"")
        if len(bare) > 3 and bare.isupper() and bare not in _ALLOWED_CAPS:
            shouty.append(word)
    if shouty:
        fail("CAPS", f"Shouting in caps: '{shouty[0]}'")
        score -= 15

    exclamations = body.count("!")
    if exclamations > 2:
        fail("R7", f"{exclamations} exclamation marks reads as hype")
        score -= 15
    elif exclamations > 1:
        # The spec's R7 is "at most one"; the enforced threshold is two. The
        # gap is shown rather than closed here — closing it changes what gets
        # rejected across connect and message too.
        fail("R7", f"{exclamations} exclamation marks — the rule is at most one", "advisory")
    if "!!" in body:
        fail("R7", "Repeated exclamation marks")
        score -= 10

    emoji_count = len(_EMOJI_PATTERN.findall(body))
    if emoji_count > 2:
        fail("R6", f"{emoji_count} emoji is a lot for professional outreach")
        score -= 10
    elif emoji_count:
        # Same story as R7: the written rule is zero, the enforced number is
        # two. Advisory until the shared threshold is signed off.
        fail("R6", f"{emoji_count} emoji — the rule is none", "advisory")

    # --- "I/we" heavy copy: talking about yourself, not them ---
    self_refs = len(re.findall(r"\b(i|we|our|my|us)\b", lowered))
    you_refs = len(re.findall(r"\b(you|your|you're)\b", lowered))
    if self_refs > 0 and you_refs == 0:
        fail("SELF", "Entirely about the sender — never mentions the recipient")
        score -= 30
    elif self_refs >= 3 * max(you_refs, 1):
        fail("SELF", "Heavily sender-focused ('I/we' far outweighs 'you')")
        score -= 15

    # R5, comments only, advisory. This is the audit's headline failure --
    # 43 of 58 comments ended in a version of "have you found any specific
    # strategies" -- and the one rule the operator most needs to see. It is
    # not enforced here for the same reason R1 is not: the gate is shared with
    # connect and message, and tightening it is not a solo call.
    if action == "comment" and has_formulaic_question(body):
        if opener_hit:
            # The full 3-beat template: validate, restate, then this exact
            # question shape. The August audit calls this combination its
            # damning case, and the first staging run proved why it has to be
            # a blocker rather than advisory: R4 and R5 alone still summed to
            # 100/100 on a comment the audit graded "weak".
            fail(
                "TEMPLATE3",
                "Validates first, then closes on the formulaic 'have you found "
                "any strategies' question — the 3-beat bot template",
                "blocker",
            )
        else:
            fail(
                "R5",
                "Ends on the formulaic 'have you found any strategies' question shape",
                "advisory",
            )

    score = max(0, min(100, score))
    passed = not blockers and score >= min_score

    return QualityReport(
        score=score,
        passed=passed,
        blockers=blockers,
        warnings=warnings,
        flags=flags,
        stats={
            "length": len(body),
            "words": len(words),
            "sentences": count_sentences(body),
            "personalization_signals": signals,
            "emoji": emoji_count,
        },
    )


def _personalization_signals(lowered: str, target: Any) -> List[str]:
    """Which concrete facts about the target actually appear in the copy."""
    signals = []

    def value(name: str):
        if isinstance(target, dict):
            return target.get(name)
        return getattr(target, name, None)

    first_name = value("first_name")
    if not first_name and value("full_name"):
        first_name = str(value("full_name")).split()[0]
    if first_name and str(first_name).lower() in lowered:
        signals.append("first_name")

    for field_name in ("company", "title", "industry"):
        raw = value(field_name)
        if raw and str(raw).lower() in lowered:
            signals.append(field_name)

    # A *distinctive* word from the headline counts as evidence the profile was
    # read. Generic business vocabulary does not — echoing "growth" back at a
    # growth lead says nothing.
    headline = str(value("headline") or "")
    for word in re.findall(r"\b[a-z]{6,}\b", headline.lower()):
        if word in lowered and word not in _GENERIC_HEADLINE_WORDS:
            signals.append("headline")
            break

    # A reference to something they actually posted is the strongest signal —
    # but only if the shared word is actually distinctive. Without this
    # stoplist (matching the headline check above), any 6+ letter word the
    # comment happens to share with the post text counts as personalization,
    # even a generic one like "activation" or "strategy" that would show up
    # in a templated comment on almost any post in the same topic. That gap
    # is exactly why 58/58 templated audit comments scored 100/100 on
    # 2026-08-21: every one was "about" the post's own generic vocabulary.
    context = value("context") or {}
    if isinstance(context, dict):
        snippet = str(context.get("post_text") or "")
        for word in re.findall(r"\b[a-z]{6,}\b", snippet.lower())[:40]:
            if word in lowered and word not in _GENERIC_HEADLINE_WORDS:
                signals.append("their_post")
                break

    return sorted(set(signals))
