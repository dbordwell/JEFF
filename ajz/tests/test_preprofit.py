"""The pre-profit bucket (Jeff, 2026-08-31).

He asked for companies with no forward P/E to be ranked and to appear in the matrix,
and proposed defaulting the P/E to zero. Mathematically that is a divide by zero, and
read as a P/E it means "infinitely cheap" -- so the least profitable companies on the
sheet would have taken rank 1 permanently. He agreed once it was put that way:

    "Mathematically, it doesn't work and can blow up a spreadsheet pretty quickly...
     tracking them isn't a bad idea but they shouldn't pollute the others."

So: their own bucket, ordered by AJZ Score (which needs no earnings), and out of every
average. No number is invented anywhere.
"""

from __future__ import annotations

from ajz.calc import average_ajz_value, rank_pre_profit, rank_stocks, score_stock
from ajz.fixtures import sample_stocks
from ajz.models import PEAbsence, PEBasis, StockData


def _stock(ticker, *, pe=None, roic=12.0, absence=None):
    return score_stock(StockData(
        ticker=ticker, revenue_growth=30.0, gross_margin=70.0, fcf_margin=20.0,
        roic=roic, pe_ratio=pe, pe_basis=PEBasis.FORWARD if pe else None,
        pe_absence=absence,
    ))


class TestClassification:
    def test_a_scored_stock_with_no_pe_is_pre_profit(self):
        assert _stock("SPCX").is_pre_profit

    def test_a_stock_with_a_pe_is_not(self):
        assert not _stock("MSFT", pe=25.0).is_pre_profit

    def test_a_stock_with_no_ajz_score_is_not_pre_profit(self):
        """No score means no data, which is a different problem and a different fix.

        Calling it pre-profit would rank it on a number we do not have.
        """
        assert not _stock("SNOW", roic=None).is_pre_profit

    def test_pre_profit_and_rankable_are_mutually_exclusive(self):
        for stock in sample_stocks():
            assert not (stock.is_rankable and stock.is_pre_profit)


class TestRanking:
    def test_pre_profit_stocks_are_ordered_by_ajz_score(self):
        stocks = [_stock("LOW", roic=4.0), _stock("HIGH", roic=40.0),
                  _stock("MID", roic=20.0)]
        assert [s.ticker for s in rank_pre_profit(stocks)] == ["HIGH", "MID", "LOW"]

    def test_the_main_ranking_never_contains_them(self):
        assert all(not s.is_pre_profit for s in rank_stocks(sample_stocks()))

    def test_stocks_with_no_score_appear_in_neither_ranking(self):
        stocks = sample_stocks() + [_stock("NODATA", roic=None)]
        listed = {s.ticker for s in rank_stocks(stocks)} | {
            s.ticker for s in rank_pre_profit(stocks)}
        assert "NODATA" not in listed

    def test_rivn_is_the_fixture_case(self):
        """The fixture universe already contains one, so this is not a synthetic path."""
        assert "RIVN" in {s.ticker for s in rank_pre_profit(sample_stocks())}


class TestTheyDoNotPolluteTheAverages:
    def test_adding_pre_profit_stocks_does_not_move_the_average(self):
        """His words: they "shouldn't pollute the others".

        This is v5.1's worst bug restated -- unrankable rows contributing 0 to every
        AVERAGE, pinning every headline number near zero.
        """
        base = sample_stocks()
        before = average_ajz_value(base)
        after = average_ajz_value(base + [_stock("A"), _stock("B"), _stock("C")])
        assert after == before


class TestWhyThePeIsMissing:
    def test_a_loss_making_company_is_reported_as_such(self):
        """Worded to cover both routes here: an estimate projecting a loss, and no
        estimate at all next to negative trailing earnings. SPCX and CBRS are the
        second kind, so a note claiming analysts forecast a loss would overclaim."""
        note = " ".join(_stock("RIVN", absence=PEAbsence.NOT_PROFITABLE).notes)
        assert "not profitable" in note.lower()
        assert "no forecast of profit" in note.lower()

    def test_no_coverage_is_reported_differently(self):
        """A fact about our data, not about the company -- and the likeliest sign of a
        ticker that does not exist, which is worth him seeing separately."""
        note = " ".join(_stock("SPCX", absence=PEAbsence.NO_ESTIMATE).notes)
        assert "no analyst" in note.lower()


# --- The sheets he actually reads -----------------------------------------------------


class TestTheSheets:
    def _wb(self):
        from ajz.workbook import build_workbook
        return build_workbook(sample_stocks())

    def test_top_rankings_has_a_labelled_pre_profit_section(self):
        """Listed but unranked was the complaint. A heading is what makes it a bucket."""
        ws = self._wb()["Top Rankings"]
        text = [ws.cell(row=r, column=1).value for r in range(1, ws.max_row + 1)]
        assert any(v and "AJZ Score" in str(v) for v in text), \
            "no section heading explaining what these are ranked on"

    def test_pre_profit_rows_are_numbered_within_their_own_section(self):
        """Ordered, not just present -- and numbered separately so a P3 is never
        mistaken for a 3 in the main ranking."""
        ws = self._wb()["Top Rankings"]
        ranks = [str(ws.cell(row=r, column=1).value or "")
                 for r in range(2, ws.max_row + 1)]
        assert any(v.startswith("P") for v in ranks), "pre-profit rows are not numbered"

    def test_the_matrix_gives_them_a_column(self):
        ws = self._wb()["Opportunity Matrix"]
        heads = [ws.cell(row=5, column=c).value for c in range(2, ws.max_column + 1)]
        assert "Pre-Profit" in heads

    def test_the_matrix_column_holds_the_stocks(self):
        ws = self._wb()["Opportunity Matrix"]
        col = next(c for c in range(2, ws.max_column + 1)
                   if ws.cell(row=5, column=c).value == "Pre-Profit")
        body = [str(ws.cell(row=r, column=col).value or "")
                for r in range(7, ws.max_row + 1)]
        assert any("RIVN" in v for v in body)

    def test_he_can_rename_the_bucket(self):
        """Same rule as the band names: he reads it, so he names it."""
        from ajz.settings import DEFAULT_THRESHOLDS
        from ajz.workbook import build_workbook
        from dataclasses import replace

        thresholds = replace(DEFAULT_THRESHOLDS, pre_profit_label="Not Yet Earning")
        ws = build_workbook(sample_stocks(), thresholds=thresholds)["Opportunity Matrix"]
        heads = [ws.cell(row=5, column=c).value for c in range(2, ws.max_column + 1)]
        assert "Not Yet Earning" in heads

    def test_the_label_cell_is_not_validated_as_a_number(self):
        """It is a word. The Settings sheet validates every other value cell as numeric,
        and Excel would refuse the word if that validator caught this row too."""
        ws = self._wb()["Settings"]
        row = next(r for r in range(2, ws.max_row + 1)
                   if ws.cell(row=r, column=4).value == "pre_profit_label")
        target = f"B{row}"
        for validation in ws.data_validations.dataValidation:
            if validation.type == "decimal":
                assert target not in str(validation.sqref), \
                    "the name cell is validated as a number"
