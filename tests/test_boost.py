import datetime as dt

from lumen.retrieve.boost import apply_metadata_boost, parse_query_meta


def test_boost_series_and_year_and_recency():
    docs = {"d1": {"date": "2025-01-01", "meta": {"notice_seq": 1, "academic_year": "2024-2025", "semester": "HK1"}},
            "d2": {"date": "2025-02-01", "meta": {"notice_seq": 2, "academic_year": "2024-2025", "semester": "HK1"}},
            "d3": {"date": "2020-02-01", "meta": {"notice_seq": 2, "academic_year": "2019-2020", "semester": "HK1"}}}
    assert parse_query_meta("thong bao so 2 hoc bong nam hoc 2024-2025") == {"notice_seq": 2, "academic_year": "2024-2025", "semester": None}
    ranked = [("d1", 10.0), ("d3", 9.9), ("d2", 9.8)]
    # min-max normalised base scores span 0..1, so the weights decide whether metadata can flip the order
    out = apply_metadata_boost(ranked, docs, "Thông báo số 2 học bổng năm học 2024-2025", dt.date(2025, 6, 1),
                               w_seq=1.0, w_year=1.0)
    assert [d for d, _ in out] == ["d2", "d1", "d3"]
    plain = apply_metadata_boost(ranked, docs, "học bổng", dt.date(2025, 6, 1), w_recency=0.0)
    assert [d for d, _ in plain] == ["d1", "d3", "d2"]  # no metadata in query -> order unchanged
