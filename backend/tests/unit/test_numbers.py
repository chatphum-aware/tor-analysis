from app.thai.numbers import thai_number_words_to_int


def test_brief_example():
    # the exact example from the project brief
    assert thai_number_words_to_int("หนึ่งล้านห้าแสนบาทถ้วน") == 1_500_000


def test_classic_full_reading():
    # 2,456,789 -- exercises every place value (ล้าน, แสน, หมื่น, พัน, ร้อย, สิบ)
    # plus a bare units digit with no trailing unit word
    text = "สองล้านสี่แสนห้าหมื่นหกพันเจ็ดร้อยแปดสิบเก้าบาทถ้วน"
    assert thai_number_words_to_int(text) == 2_456_789


def test_yisip_and_et_forms():
    # ยี่สิบเอ็ด = 21 (ยี่ not สอง before สิบ; เอ็ด not หนึ่ง in the units place)
    assert thai_number_words_to_int("ยี่สิบเอ็ดล้านสามแสนบาท") == 21_300_000


def test_simple_hundred():
    assert thai_number_words_to_int("ห้าร้อยบาท") == 500


def test_no_number_words_returns_none():
    assert thai_number_words_to_int("เอกสารประกวดราคาอิเล็กทรอนิกส์") is None


def test_ignores_surrounding_prose():
    text = "รวมเป็นเงินทั้งสิ้นหนึ่งล้านห้าแสนบาทถ้วน ซึ่งได้รวมภาษีมูลค่าเพิ่มแล้ว"
    assert thai_number_words_to_int(text) == 1_500_000
