from lumen.text.normalize import fold, normalize


def test_normalize_case_and_space():
    assert normalize("  Học   Bổng ") == "học bổng"


def test_fold_removes_diacritics():
    assert fold("Học bổng Khuyến khích") == "hoc bong khuyen khich"
    assert fold("Điểm rèn luyện") == "diem ren luyen"


def test_fold_matches_unaccented_query():
    assert fold("an toàn thông tin") == fold("an toan thong tin")
