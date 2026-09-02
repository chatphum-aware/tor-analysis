from app.thai.normalize import be_to_ce, find_glyph_order_anomalies, normalize_text


def test_be_to_ce():
    assert be_to_ce(2569) == 2026
    assert be_to_ce(2566) == 2023


def test_thai_digits_to_arabic():
    assert normalize_text("๐๑๒๓๔๕๖๗๘๙") == "0123456789"
    assert normalize_text("เลขที่ ๒๐/๒๕๖๙") == "เลขที่ 20/2569"


def test_nfc_normalization():
    # decomposed Thai sara + tone mark should normalize to a stable form
    decomposed = "กา่"  # ก + า + combining mai ek
    assert normalize_text(decomposed) == "กา่"  # already NFC-stable for this pair
    import unicodedata

    assert unicodedata.is_normalized("NFC", normalize_text(decomposed))


def test_no_false_positive_on_stacked_marks():
    # "กลุ่ม" = ก, ล, SARA U (ุ), MAI EK (่) -- a tone mark stacked on a
    # vowel is completely normal Thai orthography and must not be flagged.
    assert find_glyph_order_anomalies("กลุ่มงาน") == []


def test_flags_combining_mark_with_no_preceding_consonant():
    # a tone mark with nothing (or a space) before it is a real anomaly
    anomalies = find_glyph_order_anomalies("น ้าทิ้ง")
    assert len(anomalies) == 1
    assert "ั" not in anomalies[0].reason  # sanity: reason mentions the actual mark
    assert "0E49" in anomalies[0].reason  # MAI THO
