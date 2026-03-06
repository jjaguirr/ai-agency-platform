"""
Finance specialist agent.

Second specialist in the delegation framework, proving the contract
holds without framework changes. Handles expense tracking, cash flow
summaries, and spending queries — all from conversation data passed
in through SpecialistTask. No external accounting integrations, no
direct memory-client access.

Routing overlap with social_media is the interesting bit: "$500 on
Facebook ads" is a finance action (track it) even though Facebook is
a social keyword. "How much does Instagram advertising cost?" is a
social question even though it has dollar semantics. The dollar-sign
and action-verb checks in assess_task are the tiebreakers.
"""
from __future__ import annotations

import logging
import re
from typing import Any, Dict, List, Optional, TYPE_CHECKING

from src.agents.base.specialist import (
    SpecialistAgent,
    SpecialistResult,
    SpecialistStatus,
    SpecialistTask,
    TaskAssessment,
)

if TYPE_CHECKING:
    from src.agents.executive_assistant import BusinessContext

logger = logging.getLogger(__name__)


# --- Assessment vocabulary --------------------------------------------------

# Strong signals: explicit finance actions or artefacts.
_STRONG_PHRASES = [
    "cash flow", "invoice", "expense", "spending", "spend", "spent",
    "revenue", "profit", "payroll", "budget",
]
# Verbs that mean "record a transaction" — these dominate platform keywords
# when both appear ("track $500 spent on Facebook ads" → finance, not social).
_TRACK_VERBS = ["track", "log", "record", "paid", "pay for"]
# Softer signals — these appear in strategic/advisory phrasing too ("prices",
# "loan") so they get the strategic check to fire.
_WEAK_PHRASES = [
    "cost", "money", "income", "receipt", "bill", "payment",
    "tax", "deduction", "balance", "prices", "loan", "accountant",
    "bookkeep", "roi", "lease", "equipment",
]

# Advisory / business-judgment — same pattern as social media, tuned for
# finance phrasing. Question-form only: "should I hire" is strategic,
# "paid my assistant" is not.
_STRATEGIC_PATTERNS = [
    r"\bshould i\b",
    r"\bis it worth\b",
    r"\bworth it\b",
    r"\bdoes .+ make sense\b",
    r"\bmake sense to\b",
    r"\bhow much (should|to) (i )?(budget|spend|invest|charge)\b",
    r"\bwhat should my\b",
    r"\braise (my )?prices\b",
    r"\blease vs buy\b",
    r"\blease or buy\b",
    r"\bhir(e|ing) an? (accountant|bookkeeper)\b",
    r"\bwhat('s| is) my roi\b",
]

# Finance tooling in customer's stack — confidence boost when present.
_FINANCE_TOOLS = {
    "QuickBooks", "Xero", "FreshBooks", "Wave", "Stripe", "Square",
}


# --- Categorization rules ---------------------------------------------------

# Ordered: first match wins. Patterns are substring checks on lowercased text.
_CATEGORY_RULES: List[tuple[str, List[str]]] = [
    ("rent", ["rent", "landlord", "lease payment"]),
    ("payroll", ["salary", "payroll", "wages", "assistant", "employee", "contractor"]),
    ("software", ["subscription", "saas", "shopify", "software", "app", "/mo", "per month"]),
    ("marketing", ["ads", "advertising", "marketing", "boost", "campaign", "promo"]),
    ("utilities", ["electric", "gas bill", "water bill", "utility", "internet", "phone bill"]),
    ("operations", ["supplies", "inventory", "materials", "equipment", "shipping"]),
]
_DEFAULT_CATEGORY = "operations"


# --- Parsing helpers --------------------------------------------------------

# $2,400 or $2400.50 or $49 — require a digit so bare commas don't match
_AMOUNT_RE = re.compile(r"\$\s*(\d[\d,]*(?:\.\d{1,2})?)")

# "from Acme Corp" / "to the landlord" / "for Shopify" / "on Facebook"
_VENDOR_RE = re.compile(
    r"\b(?:from|to|for|on)\s+"
    r"((?:the\s+)?[A-Z][\w&'.-]*(?:\s+[A-Z][\w&'.-]*){0,3})"
)
# Fallback: lowercase targets like "the landlord", "my assistant"
_VENDOR_LOOSE_RE = re.compile(
    r"\b(?:from|to|for|paid|on)\s+"
    r"((?:the\s+|my\s+)?[a-z][\w'-]*(?:\s+[a-z][\w'-]*){0,2})",
    re.IGNORECASE,
)
# Known payee nouns — bare mentions in clarification answers ("the landlord")
_PAYEE_NOUNS = [
    "landlord", "contractor", "supplier", "vendor", "assistant",
    "employee", "accountant", "bookkeeper", "consultant", "freelancer",
]

# Month names + day, or m/d, or m-d
_DATE_RE = re.compile(
    r"\b((?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)\w*\s+\d{1,2}"
    r"|\d{1,2}[/-]\d{1,2}(?:[/-]\d{2,4})?)\b",
    re.IGNORECASE,
)

# Income signals in memory content — "invoice paid by client", "payment from", etc.
_INCOME_HINTS = ["paid by", "received from", "payment from", "revenue", "income", "deposit"]


class FinanceSpecialist(SpecialistAgent):

    @property
    def domain(self) -> str:
        return "finance"

    # --- Assessment ---------------------------------------------------------

    def assess_task(self, task_description: str, context: "BusinessContext") -> TaskAssessment:
        text = task_description.lower()

        confidence = 0.0

        # Strong finance signals
        for phrase in _STRONG_PHRASES:
            if phrase in text:
                confidence += 0.35

        # Tracking verb + dollar amount is the clearest signal — this is what
        # beats social-media's platform keyword when both appear.
        has_dollar = "$" in task_description
        has_track_verb = any(v in text for v in _TRACK_VERBS)
        if has_track_verb and has_dollar:
            confidence += 0.5
        elif has_track_verb:
            confidence += 0.2
        elif has_dollar:
            confidence += 0.15

        # Weak signals — capped so "how much does Instagram advertising cost?"
        # doesn't pile up (cost + advertising) into false-positive territory.
        # These fire even with a strong signal present, but the cap keeps the
        # contribution modest.
        weak_hits = sum(1 for p in _WEAK_PHRASES if p in text)
        confidence += min(0.25, weak_hits * 0.15)

        # Context boost — but only if there's some lexical signal already.
        if confidence > 0:
            tools = set(context.current_tools or [])
            if tools & _FINANCE_TOOLS:
                confidence += 0.15
            pain_points = [p.lower() for p in (context.pain_points or [])]
            if any(any(k in pp for k in ["cash flow", "expense", "financ", "invoic"])
                   for pp in pain_points):
                confidence += 0.15

        confidence = min(0.9, confidence)

        # Strategic gate — same pattern as social media.
        is_strategic = False
        if confidence >= 0.4:
            is_strategic = any(re.search(p, text) for p in _STRATEGIC_PATTERNS)

        return TaskAssessment(confidence=confidence, is_strategic=is_strategic)

    # --- Execution ----------------------------------------------------------

    async def execute_task(self, task: SpecialistTask) -> SpecialistResult:
        text = task.description.lower()

        # Route to the right handler based on intent.
        if self._is_summary_query(text):
            return self._handle_summary(task)
        return self._handle_expense_entry(task)

    # --- Intent routing (internal) ------------------------------------------

    def _is_summary_query(self, text: str) -> bool:
        """Distinguish 'track $X for Y' from 'how much did I spend on Y?'."""
        summary_cues = [
            "how much did", "how much have", "what did i spend",
            "what's my cash flow", "whats my cash flow",
            "cash flow looking", "top expense", "expense categories",
            "spending looking",
        ]
        return any(cue in text for cue in summary_cues)

    # --- Expense entry ------------------------------------------------------

    def _handle_expense_entry(self, task: SpecialistTask) -> SpecialistResult:
        # Pool the current message with prior customer turns so multi-turn
        # clarification works: the amount might be in task.description and
        # the vendor in a prior turn, or vice versa.
        corpus = self._customer_corpus(task)
        corpus_lower = corpus.lower()

        amount = self._extract_amount(corpus)
        vendor = self._extract_vendor(corpus)
        due_date = self._extract_date(corpus)
        category = self._categorize(corpus_lower)

        if amount is None:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={},
                confidence=0.3,
                clarification_question="How much was the amount?",
            )

        # Vendor is required UNLESS the description already gives us a
        # recognizable expense category. "$80 for office supplies" doesn't
        # need a vendor name — the category is the useful info.
        if not vendor:
            if category != _DEFAULT_CATEGORY or self._has_expense_description(corpus_lower):
                # We can proceed with a descriptive placeholder.
                vendor = self._derive_vendor_label(corpus_lower, category)
            else:
                return SpecialistResult(
                    status=SpecialistStatus.NEEDS_CLARIFICATION,
                    domain=self.domain,
                    payload={"amount": amount},
                    confidence=0.3,
                    clarification_question="Who was that paid to — vendor or payee name?",
                )

        payload: Dict[str, Any] = {
            "amount": amount,
            "vendor": vendor,
            "category": category,
            "due_date": due_date or "",
            "memories_consulted": len(task.domain_memories),
        }

        summary = (
            f"Tracked ${amount:,.2f} → {vendor} "
            f"(category: {category}"
            + (f", due {due_date}" if due_date else "")
            + ")."
        )

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload=payload,
            confidence=0.85,
            summary_for_ea=summary,
        )

    # --- Summary / cash flow ------------------------------------------------

    def _handle_summary(self, task: SpecialistTask) -> SpecialistResult:
        text = task.description.lower()
        memories = task.domain_memories or []

        # Parse each memory into (amount, category, is_income).
        entries = []
        for mem in memories:
            content = mem.get("content", "")
            amt = self._extract_amount(content)
            if amt is None:
                continue
            is_income = any(h in content.lower() for h in _INCOME_HINTS)
            cat = self._categorize(content.lower()) if not is_income else "income"
            entries.append({"amount": amt, "category": cat, "is_income": is_income,
                            "raw": content})

        # Cash flow query → income/expense split
        if "cash flow" in text:
            return self._build_cashflow_result(entries, len(memories))

        # Category-specific spend query → filter + total
        requested_cat = self._requested_category(text)
        if requested_cat:
            cat_entries = [e for e in entries if e["category"] == requested_cat]
            total = sum(e["amount"] for e in cat_entries)
            payload = {
                "category": requested_cat,
                "total": total,
                "entry_count": len(cat_entries),
                "category_totals": {requested_cat: total},
                "memories_consulted": len(memories),
            }
            summary = (
                f"Your {requested_cat} spending: ${total:,.2f} across "
                f"{len(cat_entries)} entr{'y' if len(cat_entries) == 1 else 'ies'}."
                if cat_entries else
                f"I don't see any {requested_cat} expenses in what I have on file yet."
            )
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED,
                domain=self.domain,
                payload=payload,
                confidence=0.75,
                summary_for_ea=summary,
            )

        # Generic spending summary → all-category breakdown
        return self._build_cashflow_result(entries, len(memories))

    def _build_cashflow_result(self, entries: List[Dict], mem_count: int) -> SpecialistResult:
        income = sum(e["amount"] for e in entries if e["is_income"])
        expenses = sum(e["amount"] for e in entries if not e["is_income"])
        net = income - expenses

        category_totals: Dict[str, float] = {}
        for e in entries:
            if not e["is_income"]:
                category_totals[e["category"]] = category_totals.get(e["category"], 0.0) + e["amount"]

        payload = {
            "income": income,
            "expenses": expenses,
            "net": net,
            "category_totals": category_totals,
            "memories_consulted": mem_count,
        }

        if mem_count == 0:
            summary = (
                "I don't have any financial records on file yet — "
                "once you log some expenses and income I can give you a breakdown."
            )
        else:
            summary = (
                f"Cash flow: ${income:,.2f} in, ${expenses:,.2f} out "
                f"(net {'+'if net >= 0 else ''}${net:,.2f})."
            )
            if category_totals:
                top = max(category_totals.items(), key=lambda kv: kv[1])
                summary += f" Biggest outlay: {top[0]} at ${top[1]:,.2f}."

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload=payload,
            confidence=0.7,
            summary_for_ea=summary,
        )

    # --- Extraction helpers -------------------------------------------------

    def _customer_corpus(self, task: SpecialistTask) -> str:
        """Concatenate current message + prior customer turns for multi-turn
        extraction. Specialist turns are excluded (they're our questions)."""
        parts = [task.description]
        for turn in task.prior_turns:
            if turn.get("role") == "customer":
                parts.append(turn["content"])
        return "  ".join(parts)

    def _extract_amount(self, text: str) -> Optional[float]:
        m = _AMOUNT_RE.search(text)
        if not m:
            return None
        raw = m.group(1).replace(",", "")
        try:
            return float(raw)
        except ValueError:
            return None

    _MONTHS = {"jan", "feb", "mar", "apr", "may", "jun",
               "jul", "aug", "sep", "oct", "nov", "dec"}
    _STOPWORDS = {"this", "that", "an", "a", "it", "last", "week", "month"}

    def _extract_vendor(self, text: str) -> Optional[str]:
        # Try capitalized-name pattern first ("from Acme Corp", "on Facebook")
        for m in _VENDOR_RE.finditer(text):
            v = m.group(1).strip()
            first = v.split()[0].lower()
            if first[:3] not in self._MONTHS and first not in self._STOPWORDS:
                return v
        # Loose fallback ("to the landlord", "paid my assistant", "for office supplies")
        for m in _VENDOR_LOOSE_RE.finditer(text):
            v = m.group(1).strip()
            first = v.split()[0].lower()
            if first[:3] in self._MONTHS or first in self._STOPWORDS:
                continue
            if v.lstrip().startswith("$"):
                continue
            return v
        # Bare payee nouns — e.g. clarification answer "the landlord, it's for rent"
        lower = text.lower()
        for noun in _PAYEE_NOUNS:
            if noun in lower:
                return noun
        return None

    def _has_expense_description(self, text_lower: str) -> bool:
        """True if the message has a 'for X' / 'on X' description that serves
        as a meaningful expense label even without a formal vendor name."""
        return bool(re.search(r"\bfor\s+\w+\s+\w+", text_lower))

    def _derive_vendor_label(self, text_lower: str, category: str) -> str:
        """When we have no vendor but a clear category, synthesize a label."""
        # Pull the "for X" phrase as a readable label.
        m = re.search(r"\bfor\s+((?:\w+\s+){0,2}\w+)", text_lower)
        if m:
            return m.group(1).strip()
        return f"({category})"

    def _extract_date(self, text: str) -> Optional[str]:
        m = _DATE_RE.search(text)
        return m.group(1) if m else None

    def _categorize(self, text_lower: str) -> str:
        for category, keywords in _CATEGORY_RULES:
            if any(kw in text_lower for kw in keywords):
                return category
        return _DEFAULT_CATEGORY

    def _requested_category(self, text_lower: str) -> Optional[str]:
        """Figure out which category a spending query is asking about."""
        for category, keywords in _CATEGORY_RULES:
            if any(kw in text_lower for kw in keywords):
                return category
        return None
