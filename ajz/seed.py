"""Starting universe (spec §12, Phase 6).

Both come from Jeff's own Copilot chats, so his first open is a dashboard he recognises
rather than a blank grid — which is exactly what v5.1 handed him.

Seeds apply ONLY on a true first run. Once the workbook exists it is the system of
record and his edits are absolute, including scores he has deliberately cleared.
"""

from __future__ import annotations

from .store import UniverseEntry

# (ticker, company, sector) — his AI/quality universe plus the names he scored.
# Jeff's own 24, exactly as his Copilot chats had them, then a second block widening the
# screen to 50.
#
# **This is a candidate list, not a recommendation.** A screen is not a portfolio: putting
# a ticker here says "rank this", not "buy this", and a name Jeff dislikes gets ranked and
# then ignored at no cost. The second block is chosen for breadth rather than conviction —
# large, liquid, covered by analysts so Forward P/E resolves, and spread across sectors so
# the screen is not 90% software. He deletes what he does not want, or sets Active to NO.
#
# It only applies to a first install. Once the workbook exists his Universe sheet is the
# system of record and this list is never consulted again.
#
# 50 tickers x 8 endpoints = ~400 API calls per refresh. That is the real cost of growing
# this list, and the reason it is not larger.
_UNIVERSE: list[tuple[str, str, str]] = [
    # --- Jeff's original 24
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

    # --- Widening the screen. Sectors here are placeholders; the refresh overwrites each
    #     one with what the vendor reports, so a wrong guess costs nothing.
    ("AAPL", "Apple Inc.", "Technology"),
    ("ORCL", "Oracle Corporation", "Technology"),
    ("ASML", "ASML Holding N.V.", "Technology"),
    ("AMAT", "Applied Materials Inc.", "Technology"),
    ("LRCX", "Lam Research Corporation", "Technology"),
    ("QCOM", "QUALCOMM Incorporated", "Technology"),
    ("TXN", "Texas Instruments Incorporated", "Technology"),
    ("INTU", "Intuit Inc.", "Technology"),
    ("ADBE", "Adobe Inc.", "Technology"),
    ("PANW", "Palo Alto Networks Inc.", "Technology"),
    ("SNOW", "Snowflake Inc.", "Technology"),
    ("TEAM", "Atlassian Corporation", "Technology"),
    ("TTD", "The Trade Desk Inc.", "Communication Services"),
    ("COST", "Costco Wholesale Corporation", "Consumer Staples"),
    ("CMG", "Chipotle Mexican Grill Inc.", "Consumer Discretionary"),
    ("BKNG", "Booking Holdings Inc.", "Consumer Discretionary"),
    ("ABNB", "Airbnb Inc.", "Consumer Discretionary"),
    ("UNH", "UnitedHealth Group Incorporated", "Healthcare"),
    ("ISRG", "Intuitive Surgical Inc.", "Healthcare"),
    ("REGN", "Regeneron Pharmaceuticals Inc.", "Healthcare"),
    ("NVO", "Novo Nordisk A/S", "Healthcare"),
    ("SPGI", "S&P Global Inc.", "Financials"),
    ("AXP", "American Express Company", "Financials"),
    ("PGR", "Progressive Corporation", "Financials"),
    ("GE", "GE Aerospace", "Industrials"),
    ("ETN", "Eaton Corporation plc", "Industrials"),
]

SEED_UNIVERSE: list[UniverseEntry] = [
    UniverseEntry(ticker=t, company=c, sector=s) for t, c, s in _UNIVERSE
]
