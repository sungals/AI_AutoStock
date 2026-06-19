"""대표 종목 워치리스트 검증."""

import watchlist


def test_representative_stock_lists_have_10_each():
    assert len(watchlist.REPRESENTATIVE_STOCKS['KOSPI']) == 10
    assert len(watchlist.REPRESENTATIVE_STOCKS['KOSDAQ']) == 10
    assert len(set(watchlist.REPRESENTATIVE_STOCKS['KOSPI'])) == 10
    assert len(set(watchlist.REPRESENTATIVE_STOCKS['KOSDAQ'])) == 10
