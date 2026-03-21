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
from typing import Any, Dict, List, Optional, Protocol, TYPE_CHECKING

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


# --- External seam ----------------------------------------------------------

class StockPriceClient(Protocol):
    """Contract for live-quote providers. The specialist depends on this,
    never on a transport library. Concrete clients (FinnhubClient, etc.)
    live outside this module and conform by structure — no inheritance.

    Contract: never raise. Transport/auth failures return {}, unknown
    tickers are simply absent from the result. The specialist treats
    missing prices as degradation, not error."""

    async def fetch(self, tickers: List[str]) -> Dict[str, float]:
        ...


# --- Assessment vocabulary --------------------------------------------------

# Unambiguous signals — phrases with a single meaning. One of these alone
# is enough to route regardless of context.
_UNAMBIGUOUS_PHRASES = ["cash flow", "invoice", "payroll", "portfolio", "stock holdings"]
# Strong signals: explicit finance actions or artefacts. These need at
# least one additional signal (or context boost) to clear the threshold.
_STRONG_PHRASES = [
    "expense", "spending", "spend", "spent",
    "revenue", "profit", "budget",
    "shares", "valuation",
]
# Verbs that mean "record a transaction" — these dominate platform keywords
# when both appear ("track $500 spent on Facebook ads" → finance, not social).
_TRACK_VERBS = ["track", "log", "record", "paid", "pay for"]
# Softer signals — these appear in strategic/advisory phrasing too ("prices",
# "loan") so they get the strategic check to fire.
_WEAK_PHRASES = [
    "cost", "money", "income", "receipt", "bill", "payment",
    "tax", "deduction", "balance", "prices", "loan", "accountant",
    "bookkeep", "roi", "lease", "equipment", "stock",
    "holdings", "ticker",
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
    r"\bshould i sell\b",
    r"\bshould i buy\b",
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

# Income signals in memory content. Regex, not substrings — because
# misclassification here is a SIGN error: a $500 expense mis-tagged as
# income swings the reported net by $1,000. Small-business ledgers are
# expense-dominated, so the default is expense and these patterns are
# the burden of proof for income.
#
# The key guard: "paid by <party>" is inflow, but "paid by <instrument>"
# (credit card, check, wire) is expense metadata. Negative lookahead on
# payment-method nouns distinguishes the two. Similarly "deposit" alone
# is ambiguous (security deposit = outflow), so we require direction.
_PAYMENT_METHODS_RE = r"(?:credit|debit|card|check|cash|wire|ach|bank\s+transfer|venmo|paypal|zelle)\b"
_INCOME_PATTERNS = [
    re.compile(rf"\bpaid by\s+(?!{_PAYMENT_METHODS_RE})\w", re.IGNORECASE),
    re.compile(r"\breceived from\b", re.IGNORECASE),
    re.compile(r"\bpayment from\b", re.IGNORECASE),
    re.compile(r"\bgot paid\b", re.IGNORECASE),
    re.compile(r"\brevenue\b", re.IGNORECASE),
    re.compile(r"\bincome\b", re.IGNORECASE),
    re.compile(r"\bdeposit\s+(?:from|received)\b", re.IGNORECASE),
]


class FinanceSpecialist(SpecialistAgent):

    def __init__(
        self,
        stock_client: Optional[StockPriceClient] = None,
        state_store=None,
        anomaly_threshold: float = 2.0,
    ):
        self._stock_client = stock_client
        self._state_store = state_store
        self._anomaly_threshold = anomaly_threshold

    @property
    def domain(self) -> str:
        return "finance"

    # --- Assessment ---------------------------------------------------------

    def assess_task(self, task_description: str, context: "BusinessContext") -> TaskAssessment:
        text = task_description.lower()

        confidence = 0.0

        # Unambiguous phrases — one hit is enough to route.
        for phrase in _UNAMBIGUOUS_PHRASES:
            if phrase in text:
                confidence += 0.6
                break  # one is sufficient; don't stack

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
        if self._is_portfolio_query(text):
            return await self._handle_portfolio_valuation(task)
        if self._is_summary_query(text):
            return self._handle_summary(task)
        return self._handle_expense_entry(task)

    # --- Proactive anomaly detection ----------------------------------------

    async def proactive_check(
        self, customer_id: str, context: "BusinessContext",
    ) -> Optional["ProactiveTrigger"]:
        if self._state_store is None:
            return None

        from src.proactive.triggers import Priority, ProactiveTrigger

        stats = await self._state_store.get_transaction_stats(customer_id)
        if stats["count"] < 2:
            return None

        latest = await self._state_store.get_latest_transaction(customer_id)
        if latest is None:
            return None

        avg = stats["average"]
        amount = latest["amount"]
        if avg <= 0:
            return None

        ratio = amount / avg
        if ratio < self._anomaly_threshold:
            return None

        return ProactiveTrigger(
            domain="finance",
            trigger_type="finance_anomaly",
            priority=Priority.HIGH,
            title=f"Unusual spending: ${amount:,.2f}",
            payload={
                "amount": amount,
                "average": avg,
                "ratio": round(ratio, 2),
                "category": latest.get("category", "unknown"),
            },
            suggested_message=(
                f"Heads up — a recent expense of ${amount:,.2f} is "
                f"{ratio:.1f}x your average of ${avg:,.2f}. "
                f"Want me to look into it?"
            ),
            cooldown_key=f"finance:anomaly:{customer_id}",
        )

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

    def _is_portfolio_query(self, text: str) -> bool:
        portfolio_cues = [
            "portfolio", "my holdings", "stock holdings",
            "my shares", "my stocks", "valuation on",
        ]
        return any(cue in text for cue in portfolio_cues)

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
            is_income = any(p.search(content) for p in _INCOME_PATTERNS)
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

    # --- Portfolio valuation ------------------------------------------------

    # "100 shares of AAPL", "50 MSFT", "bought 200 GOOGL" — 2-5 caps for
    # the ticker to avoid matching "I", "A", etc. Single-char tickers (F, T)
    # won't match; acceptable tradeoff for precision.
    _HOLDING_RE = re.compile(
        r"(?:bought|own|hold|have|picked up)?\s*"
        r"(\d[\d,]*)\s+"
        r"(?:shares?\s+of\s+)?"
        r"([A-Z]{2,5})\b"
    )

    async def _handle_portfolio_valuation(self, task: SpecialistTask) -> SpecialistResult:
        memories = task.domain_memories or []
        holdings = self._parse_holdings(memories)

        # No holdings on record → empty portfolio, not an error.
        if not holdings:
            return SpecialistResult(
                status=SpecialistStatus.COMPLETED,
                domain=self.domain,
                payload={
                    "positions": [],
                    "total_value": 0.0,
                    "quotes_unavailable": False,
                    "unpriced_tickers": [],
                    "memories_consulted": len(memories),
                },
                confidence=0.7,
                summary_for_ea=(
                    "I don't have any stock holdings on record — let me know what "
                    "positions you hold and I'll track them going forward."
                ),
            )

        tickers = [h["ticker"] for h in holdings]

        # Fetch via the seam. No client or empty response → degrade.
        quotes: Dict[str, float] = {}
        if self._stock_client is not None:
            quotes = await self._stock_client.fetch(tickers)

        # Build positions — price is None when quote is missing.
        positions: List[Dict[str, Any]] = []
        unpriced: List[str] = []
        total_value = 0.0
        for h in holdings:
            price = quotes.get(h["ticker"])
            value = price * h["shares"] if price is not None else None
            positions.append({
                "ticker": h["ticker"],
                "shares": h["shares"],
                "price": price,
                "value": value,
            })
            if price is None:
                unpriced.append(h["ticker"])
            else:
                total_value += value

        # Classify the quote situation for payload schema + summary wording.
        all_unpriced = len(unpriced) == len(holdings)
        any_unpriced = len(unpriced) > 0

        if all_unpriced:
            payload_total: Optional[float] = None
            holdings_str = ", ".join(f"{p['shares']} {p['ticker']}" for p in positions)
            summary = (
                f"I can see your holdings ({holdings_str}) "
                "but I don't have live prices right now — can't give you a valuation."
            )
        elif any_unpriced:
            payload_total = total_value
            priced_count = len(holdings) - len(unpriced)
            summary = (
                f"Partial valuation: ${total_value:,.2f} across {priced_count} "
                f"priced position{'s' if priced_count != 1 else ''} "
                f"(no quote for {', '.join(unpriced)})."
            )
        else:
            payload_total = total_value
            summary = (
                f"Portfolio worth ${total_value:,.2f} across "
                f"{len(positions)} position{'s' if len(positions) != 1 else ''}."
            )

        return SpecialistResult(
            status=SpecialistStatus.COMPLETED,
            domain=self.domain,
            payload={
                "positions": positions,
                "total_value": payload_total,
                "quotes_unavailable": all_unpriced,
                "unpriced_tickers": unpriced,
                "memories_consulted": len(memories),
            },
            confidence=0.8 if not any_unpriced else 0.6,
            summary_for_ea=summary,
        )

    def _parse_holdings(self, memories: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Extract (ticker, shares) pairs from memory content. Non-holding
        memories (rent, expenses) won't match the regex and are ignored."""
        holdings: List[Dict[str, Any]] = []
        for mem in memories:
            content = mem.get("content", "")
            m = self._HOLDING_RE.search(content)
            if not m:
                continue
            shares_raw, ticker = m.group(1), m.group(2)
            try:
                shares = int(shares_raw.replace(",", ""))
            except ValueError:
                continue
            holdings.append({"ticker": ticker, "shares": shares})
        return holdings

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
