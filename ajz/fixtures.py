"""Sample data for developing and demoing the workbook without an API (spec §12, Phase 2).

The tickers and rough AJZ Value Scores come from Jeff's own Copilot
chats, so the generated file is immediately recognisable to him. The underlying
fundamentals are PLAUSIBLE, NOT REAL — they are back-solved to land near the AJZ Value
Scores he was shown, so the dashboard reads correctly in a demo.

Do not let these reach production. Phase 4 replaces this module entirely.
"""

from __future__ import annotations

from datetime import date

from .calc import score_stock
from .models import PEBasis, ScoredStock, StockData

AS_OF = date(2026, 8, 19)

# ticker, company, sector, rev growth %, gross margin %, fcf margin %, roic %, fwd P/E,
# The trailing tuple is a legacy conviction score, retained only so the seed rows
# still read as they did in his chats; nothing consumes it since v2.1 removed
# conviction. It is left in place rather than stripped so the numbers stay
# traceable to the source they came from.
_SEED: list[tuple] = [
    ("NVDA", "NVIDIA Corporation", "Technology", 114.0, 75.0, 45.0, 90.0, 22.6, (4, 5, 5, 5, 5)),
    ("TSM", "Taiwan Semiconductor", "Technology", 36.0, 56.0, 28.0, 32.0, 18.5, (5, 5, 5, 5, 5)),
    ("AVGO", "Broadcom Inc.", "Technology", 44.0, 77.0, 46.0, 24.0, 31.0, (5, 5, 5, 4, 4)),
    ("LLY", "Eli Lilly and Company", "Healthcare", 32.0, 81.0, 22.0, 42.0, 34.0, (5, 5, 5, 4, 4)),
    ("ANET", "Arista Networks", "Technology", 24.0, 64.0, 38.0, 33.0, 38.0, (4, 4, 5, 5, 4)),
    ("BE", "Bloom Energy", "Industrials", 38.0, 27.0, 6.0, 9.0, 42.0, (2, 4, 4, 3, 5)),
    ("HOOD", "Robinhood Markets", "Financials", 46.0, 88.0, 34.0, 18.0, 41.0, (3, 3, 4, 4, 4)),
    ("MELI", "MercadoLibre", "Consumer Discretionary", 37.0, 47.0, 14.0, 38.0, 36.0, (4, 4, 5, 3, 4)),
    ("AMZN", "Amazon.com Inc.", "Consumer Discretionary", 11.0, 49.0, 9.0, 14.0, 33.0, (5, 5, 5, 5, 4)),
    ("MSFT", "Microsoft Corporation", "Technology", 15.0, 69.0, 30.0, 29.0, 31.0, (5, 5, 5, 5, 4)),
    ("PLTR", "Palantir Technologies", "Technology", 30.0, 80.0, 38.0, 12.0, 210.0, (4, 4, 4, 5, 5)),
    ("CRWD", "CrowdStrike Holdings", "Technology", 29.0, 75.0, 31.0, 11.0, 88.0, (5, 4, 4, 4, 5)),
    ("DDOG", "Datadog Inc.", "Technology", 26.0, 81.0, 28.0, 13.0, 72.0, (4, 4, 4, 4, 4)),
    ("VRTX", "Vertex Pharmaceuticals", "Healthcare", 12.0, 86.0, 33.0, 21.0, 26.0, (5, 5, 4, 5, 3)),
    ("V", "Visa Inc.", "Financials", 10.0, 80.0, 52.0, 45.0, 27.0, (5, 5, 5, 5, 3)),
    # Deliberate edge cases — these exercise the paths v5.1 got wrong.
    ("RIVN", "Rivian Automotive", "Consumer Discretionary", 22.0, -18.0, -55.0, -28.0, None, None),
    ("SNOW", "Snowflake Inc.", "Technology", 28.0, 68.0, 25.0, None, 130.0, (4, 4, 4, 4, 4)),
    ("NET", "Cloudflare Inc.", "Technology", 28.0, 77.0, 12.0, 4.0, 180.0, None),
]


def sample_stocks() -> list[ScoredStock]:
    """A realistic 18-stock universe including the awkward cases.

    Edge cases included on purpose:
      * RIVN  — loss-making, no forward P/E -> Not Rated, excluded from every average.
      * SNOW  — missing ROIC -> no AJZ Score at all, with a note explaining which field.
      * NET   — very high P/E, so it ranks last and lands in the bottom value band
                rather than being dropped.
    """
    out: list[ScoredStock] = []
    for ticker, company, sector, growth, gm, fcf, roic, pe, _legacy in _SEED:
        data = StockData(
            ticker=ticker,
            company=company,
            sector=sector,
            revenue_growth=growth,
            gross_margin=gm,
            fcf_margin=fcf,
            roic=roic,
            pe_ratio=pe,
            pe_basis=PEBasis.FORWARD if pe is not None else None,
            as_of=AS_OF,
            source="fixtures",
        )
        out.append(score_stock(data))
    return out
