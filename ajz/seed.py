"""Starting universe and conviction seeds (spec §12, Phase 6).

Both come from Jeff's own Copilot chats, so his first open is a dashboard he recognises
rather than a blank grid — which is exactly what v5.1 handed him.

Seeds apply ONLY on a true first run. Once the workbook exists it is the system of
record and his edits are absolute, including scores he has deliberately cleared.
"""

from __future__ import annotations

from .models import Conviction
from .store import UniverseEntry

# (ticker, company, sector) — his AI/quality universe plus the names he scored.
_UNIVERSE: list[tuple[str, str, str]] = [
    ("NVDA", "NVIDIA Corporation", "Technology"),
    ("AVGO", "Broadcom Inc.", "Technology"),
    ("TSM", "Taiwan Semiconductor Manufacturing", "Technology"),
    ("LLY", "Eli Lilly and Company", "Healthcare"),
    ("ANET", "Arista Networks", "Technology"),
    ("META", "Meta Platforms", "Technology"),
    ("MSFT", "Microsoft Corporation", "Technology"),
    ("AMZN", "Amazon.com Inc.", "Consumer Discretionary"),
    ("GOOGL", "Alphabet Inc.", "Technology"),
    ("CRM", "Salesforce Inc.", "Technology"),
    ("NOW", "ServiceNow Inc.", "Technology"),
    ("CRWD", "CrowdStrike Holdings", "Technology"),
    ("DDOG", "Datadog Inc.", "Technology"),
    ("SHOP", "Shopify Inc.", "Technology"),
    ("MELI", "MercadoLibre Inc.", "Consumer Discretionary"),
    ("BE", "Bloom Energy Corporation", "Industrials"),
    ("HOOD", "Robinhood Markets", "Financials"),
    ("VRTX", "Vertex Pharmaceuticals", "Healthcare"),
    ("AMD", "Advanced Micro Devices", "Technology"),
    ("NFLX", "Netflix Inc.", "Communication Services"),
    ("PLTR", "Palantir Technologies", "Technology"),
    ("V", "Visa Inc.", "Financials"),
    ("MA", "Mastercard Incorporated", "Financials"),
    ("NET", "Cloudflare Inc.", "Technology"),
]

SEED_UNIVERSE: list[UniverseEntry] = [
    UniverseEntry(ticker=t, company=c, sector=s) for t, c, s in _UNIVERSE
]

# Conviction scores Jeff and Copilot worked out together, in his order:
# Predictability, Moat, Management, Balance Sheet, Tailwind.
#
# Only the five he actually scored are here. The rest arrive as "Needs Conviction",
# which is honest — inventing scores for him would corrupt the one input that is
# genuinely his judgement.
SEED_CONVICTION: dict[str, Conviction] = {
    "NVDA": Conviction(4, 5, 5, 5, 5),  # 24/25 Very High
    "TSM": Conviction(5, 5, 5, 5, 5),   # 25/25 Very High
    "AVGO": Conviction(5, 5, 5, 4, 4),  # 23/25 Very High
    "BE": Conviction(2, 4, 4, 3, 5),    # 18/25 High
    "HOOD": Conviction(3, 3, 4, 4, 4),  # 18/25 High
}
