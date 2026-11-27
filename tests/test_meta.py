from lumen.meta.extract import extract_meta, series_key
from lumen.text.dates import parse_date
from lumen.text.pii import has_mssv, mask_mssv


def test_extract_meta_notice_and_year():
    m = extract_meta("Thông báo số 2 về học bổng khuyến khích học tập HK1 năm học 2024-2025")
    assert (m["doc_type"], m["notice_seq"], m["academic_year"], m["semester"]) == ("thong_bao", 2, "2024-2025", "HK1")


def test_extract_meta_decision_number_not_notice_seq():
    m = extract_meta("Quyết định khen thưởng", "ĐẠI HỌC CNTT\nSố: 123/QĐ-ĐHCNTT\nTP.HCM, ngày 5 tháng 11 năm 2025")
    assert m["doc_type"] == "quyet_dinh" and m["doc_number"] == "123/QĐ-ĐHCNTT" and m["notice_seq"] is None
    assert m["doc_date"] == "2025-11-05"
    m2 = extract_meta("Thông báo", "Số 45/2024/TB-CTSV")
    assert m2["doc_number"] == "45/2024/TB-CTSV" and m2["doc_year"] == 2024 and m2["notice_seq"] is None


def test_extract_meta_semester_forms_and_no_diacritics():
    assert extract_meta("Học phí học kỳ 2")["semester"] == "HK2"
    assert extract_meta("hoc phi hoc ky II nam hoc 2023 - 2024")["academic_year"] == "2023-2024"
    assert extract_meta("Lịch thi HK1/HK2")["semesters"] == ["HK1", "HK2"]
    assert extract_meta("Điểm rèn luyện năm 2020-2024")["academic_year"] is None  # not consecutive years


def test_series_key_ignores_numbers_and_years():
    a = series_key("Thông báo số 1 về học bổng HK1 năm học 2023-2024", "thong_bao")
    b = series_key("Thông báo số 2 về học bổng HK2 năm học 2024-2025", "thong_bao")
    c = series_key("Thông báo về học phí", "thong_bao")
    assert a == b != c


def test_dates_and_pii():
    assert parse_date("hạn 05/11/2025") == "2025-11-05" and parse_date("31/02/2025") is None
    assert has_mssv("SV Nguyen A 21520001") and not has_mssv("so 2152000123")
    assert mask_mssv("21520001 va 21520002") == "******** va ********"
