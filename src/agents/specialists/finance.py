"""
Finance specialist agent.

Handles three kinds of work: logging individual expenses (parse → categorize),
spend summaries by category, and cash flow aggregation. All financial data
comes through domain_memories — no direct storage access.

Routing must coexist with social media: platform names are deliberately
absent from the keyword set, so "Instagram advertising cost" stays with
social media even though "cost" is a finance word.
"""
from __future__ import annotations

import logging
import re
from typing import Dict, List, Optional, Tuple, TYPE_CHECKING

from src.agents.base.specialist import (
    SpecialistAgent,
    SpecialistTask,
    SpecialistResult,
    SpecialistStatus,
    TaskAssessment,
)

if TYPE_CHECKING:
    from src.agents.executive_assistant import BusinessContext

logger = logging.getLogger(__name__)


# --- Scoring vocabulary -----------------------------------------------------

# "cash flow" is uniquely finance — no overlap with any other domain.
# Weighted high enough to clear the 0.6 threshold on its own.
_ANCHOR_PHRASES = ["cash flow"]  # +0.65

_STRONG_PHRASES = [
    "invoice", "expense", "revenue", "profit", "p&l",
    # "spent" is past-tense expense query — strong signal distinct from
    # advisory "should I spend" which the strategic patterns catch.
    "spent", "did i spend",
]  # +0.4

_WEAK_PHRASES = [
    "spend", "cost", "income", "budget", "payment", "receipt",
    "price", "invest", "accountant", "roi", "financial",
]  # +0.2

# Currency literals are a strong tell — nobody mentions "$2,400" in a
# social media question.
_CURRENCY_RE = re.compile(r"\$\s?[\d,]+(?:\.\d{1,2})?")

_FINANCE_TOOLS = {
    "QuickBooks", "Stripe", "Square", "Xero", "FreshBooks", "Wave", "PayPal",
}

_STRATEGIC_PATTERNS = [
    r"\bshould i\b",
    r"\bis it worth\b",
    r"\bworth it\b",
    r"\bdoes .+ make sense\b",
    r"\bhow much (should|to) (i )?(spend|invest|budget|charge)\b",
    r"\bwhat should\b",
    r"\braise (my )?prices?\b",
    r"\bhir(e|ing)\b",
]

# --- Expense categorization -------------------------------------------------

_CATEGORY_HINTS: Dict[str, List[str]] = {
    "marketing": ["marketing", "advertis", "ads", "promo", "campaign"],
    "rent": ["rent", "lease", "office space"],
    "software": ["software", "subscription", "saas", "license"],
    "payroll": ["payroll", "salary", "salaries", "wages", "contractor"],
    "utilities": ["utilities", "electric", "internet", "phone bill"],
    "travel": ["travel", "flight", "hotel", "mileage"],
}
_DEFAULT_CATEGORY = "operations"

# --- Parsing patterns -------------------------------------------------------

_AMOUNT_RE = re.compile(r"\$?\s?([\d,]+(?:\.\d{1,2})?)")
# Vendor: capitalized run after "from" or "to" — stops at punctuation,
# lowercase word, or line end. Matches "Acme Corp", "Google Ads", "Stripe".
_VENDOR_RE = re.compile(
    r"\b(?:from|to)\s+([A-Z][A-Za-z0-9&]*(?:\s+[A-Z][A-Za-z0-9&]*)*)"
)
_DUE_DATE_RE = re.compile(r"\bdue\s+([A-Za-z0-9 ,]+?)(?:$|[.,;]|\s+for\b)")


class FinanceSpecialist(SpecialistAgent):

    @property
    def domain(self) -> str:
        return "finance"

    # --- Assessment ---------------------------------------------------------

    def assess_task(self, task_description: str, context: "BusinessContext") -> TaskAssessment:
        text = task_description.lower()

        confidence = 0.0
        for phrase in _ANCHOR_PHRASES:
            if phrase in text:
                confidence += 0.65
        for phrase in _STRONG_PHRASES:
            if phrase in text:
                confidence += 0.4
        for phrase in _WEAK_PHRASES:
            if phrase in text:
                confidence += 0.2
        if _CURRENCY_RE.search(task_description):
            confidence += 0.3

        # Context boosts — gated so "check my Instagram" from a
        # QuickBooks-using customer stays at 0.
        if confidence > 0:
            if self._has_finance_pain_point(context):
                confidence += 0.15
            if self._uses_finance_tools(context):
                confidence += 0.1

        confidence = min(0.9, confidence)

        is_strategic = False
        if confidence >= 0.4:
            is_strategic = any(re.search(p, text) for p in _STRATEGIC_PATTERNS)

        return TaskAssessment(confidence=confidence, is_strategic=is_strategic)

    # --- Execution ----------------------------------------------------------

    async def execute_task(self, task: SpecialistTask) -> SpecialistResult:
        # Stitch current turn + customer prior_turns so multi-turn parsing
        # sees the whole exchange.
        full_text = self._assemble_text(task)
        low = full_text.lower()

        if "cash flow" in low:
            return self._cash_flow_summary(task)

        if self._is_spend_query(low):
            return self._spend_summary(task, low)

        return self._track_expense(task, full_text)

    # --- Mode: expense tracking ---------------------------------------------

    def _track_expense(self, task: SpecialistTask, full_text: str) -> SpecialistResult:
        amount = self._parse_amount(full_text)
        vendor = self._parse_vendor(full_text)
        due_date = self._parse_due_date(full_text)
        category = self._categorize(full_text.lower())

        if amount is None:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={},
                confidence=0.3,
                clarification_question="How much was the expense?",
            )

        # Vendor is required unless the category is specific — recurring
        # categorized expenses (rent, payroll) often have an implicit vendor.
        if vendor is None and category == _DEFAULT_CATEGORY:
            return SpecialistResult(
                status=SpecialistStatus.NEEDS_CLARIFICATION,
                domain=self.domain,
                payload={"amount": amount},
                confidence=0.3,
                clarification_question="Who was the vendor?",
            )

        payload = {
            "entry_type": "expense",
            "amount": amount,
            "vendor": vendor,
            "category": category,
            "due_date": due_date,
        }
        summary = self._build_expense_summary(payload)

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload=payload,
            confidence=0.8,
            summary_for_ea=summary,
        )

    # --- Mode: spend summary by category ------------------------------------

    def _spend_summary(self, task: SpecialistTask, low_text: str) -> SpecialistResult:
        target_category = self._extract_query_category(low_text)
        expenses = self._parse_memory_entries(task.domain_memories, kind="expense")

        if target_category:
            matching = [e for e in expenses if target_category in e["raw"].lower()]
        else:
            matching = expenses

        total = sum(e["amount"] for e in matching)

        payload = {
            "query_type": "spend_summary",
            "category": target_category,
            "total": total,
            "entry_count": len(matching),
            "memories_consulted": len(task.domain_memories),
        }

        if target_category:
            summary = f"Total {target_category} spend: ${total:,.2f} across {len(matching)} entries."
        else:
            summary = f"Total expenses: ${total:,.2f} across {len(matching)} entries."

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload=payload,
            confidence=0.75,
            summary_for_ea=summary,
        )

    # --- Mode: cash flow ----------------------------------------------------

    def _cash_flow_summary(self, task: SpecialistTask) -> SpecialistResult:
        income = self._parse_memory_entries(task.domain_memories, kind="income")
        expenses = self._parse_memory_entries(task.domain_memories, kind="expense")

        income_total = sum(e["amount"] for e in income)
        expense_total = sum(e["amount"] for e in expenses)
        net = income_total - expense_total

        payload = {
            "query_type": "cash_flow",
            "income_total": income_total,
            "expense_total": expense_total,
            "net": net,
            "income_entries": len(income),
            "expense_entries": len(expenses),
            "memories_consulted": len(task.domain_memories),
        }

        direction = "positive" if net >= 0 else "negative"
        summary = (
            f"Cash flow is {direction}: ${income_total:,.2f} in, "
            f"${expense_total:,.2f} out, net ${net:,.2f}."
        )

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload=payload,
            confidence=0.75,
            summary_for_ea=summary,
        )

    # --- Parsing helpers ----------------------------------------------------

    def _assemble_text(self, task: SpecialistTask) -> str:
        """Current description + customer-side prior turns, newest last."""
        parts = []
        for turn in task.prior_turns:
            if turn.get("role") == "customer":
                parts.append(turn["content"])
        parts.append(task.description)
        return " ".join(parts)

    def _parse_amount(self, text: str) -> Optional[float]:
        # Prefer currency-marked amounts; fall back to bare numbers only if
        # they're large enough to plausibly be money (avoids "March 15" → 15).
        m = _CURRENCY_RE.search(text)
        if m:
            digits = re.sub(r"[^\d.]", "", m.group(0))
            return float(digits) if digits else None
        # Bare number after an expense verb: "expense of 1500"
        m = re.search(r"\b(?:of|for)\s+([\d,]+(?:\.\d{1,2})?)\b", text)
        if m:
            return float(m.group(1).replace(",", ""))
        return None

    def _parse_vendor(self, text: str) -> Optional[str]:
        m = _VENDOR_RE.search(text)
        return m.group(1).strip() if m else None

    def _parse_due_date(self, text: str) -> Optional[str]:
        m = _DUE_DATE_RE.search(text)
        return m.group(1).strip() if m else None

    def _categorize(self, low_text: str) -> str:
        for category, hints in _CATEGORY_HINTS.items():
            if any(h in low_text for h in hints):
                return category
        return _DEFAULT_CATEGORY

    def _extract_query_category(self, low_text: str) -> Optional[str]:
        """Pull the category out of 'how much did I spend on marketing'."""
        for category, hints in _CATEGORY_HINTS.items():
            if any(h in low_text for h in hints):
                return category
        return None

    def _is_spend_query(self, low_text: str) -> bool:
        if re.search(r"how much.*\bspen[dt]\b", low_text):
            return True
        if re.search(r"\bspen[dt]\b.*\b(last|this)\b", low_text):
            return True
        if re.search(r"show me .*(expense|spend)", low_text):
            return True
        if re.search(r"expenses? by category", low_text):
            return True
        return False

    def _parse_memory_entries(
        self, memories: List[Dict], kind: str
    ) -> List[Dict]:
        """Extract amounts from memories tagged as Income: or Expense:.

        Memory format is loose — we look for the kind as a prefix/word and
        the first currency-looking number in the content.
        """
        prefix = kind.lower()
        out = []
        for mem in memories:
            content = mem.get("content", "")
            low = content.lower()
            if not low.startswith(prefix) and f"{prefix}:" not in low:
                continue
            m = _AMOUNT_RE.search(content)
            if not m:
                continue
            amount = float(m.group(1).replace(",", ""))
            out.append({"amount": amount, "raw": content})
        return out

    # --- Context helpers ----------------------------------------------------

    def _has_finance_pain_point(self, context: "BusinessContext") -> bool:
        markers = ("invoic", "expense", "financ", "bookkeep", "cash", "budget")
        return any(
            any(m in p.lower() for m in markers)
            for p in (context.pain_points or [])
        )

    def _uses_finance_tools(self, context: "BusinessContext") -> bool:
        tools = set(context.current_tools or [])
        return bool(tools & _FINANCE_TOOLS)

    # --- Summary formatting -------------------------------------------------

    def _build_expense_summary(self, payload: Dict) -> str:
        amount = payload["amount"]
        vendor = payload["vendor"]
        category = payload["category"]
        due = payload["due_date"]

        parts = [f"Logged ${amount:,.2f}"]
        if vendor:
            parts.append(f"from {vendor}")
        parts.append(f"under {category}")
        if due:
            parts.append(f"(due {due})")

        return " ".join(parts) + "."
