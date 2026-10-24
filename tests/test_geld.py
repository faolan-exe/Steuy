import pytest

from app.domain.geld import GeldFormatFehler, cent_zu_dezimal, cent_zu_euro, euro_zu_cent


@pytest.mark.parametrize(
    ("eingabe", "cent"),
    [
        ("12,50", 1250),
        ("12,5", 1250),
        ("12", 1200),
        ("0,01", 1),
        ("0", 0),
        ("12.50", 1250),
        ("12.5", 1250),
        ("1.234,56", 123456),
        ("1.234.567,89", 123456789),
        ("1.234", 123400),
        ("1,234.56", 123456),
        ("  12,50 €  ", 1250),
        ("€ 12,50", 1250),
        ("12,50 EUR", 1250),
        ("-3,00", -300),
        ("−3,00", -300),
        ("+3,00", 300),
        ("-0,99", -99),
        (",50", 50),
    ],
)
def test_euro_zu_cent_gueltig(eingabe, cent):
    assert euro_zu_cent(eingabe) == cent


@pytest.mark.parametrize(
    "eingabe",
    [
        "",
        "   ",
        "€",
        "abc",
        "12,345",
        "12.345.6",
        "1.23,45",
        "12,50,00",
        "1,234,56",
        "12..50",
        "--3",
        "3-",
        "1 234,56",
        "12,5x",
        "1e3",
    ],
)
def test_euro_zu_cent_ungueltig(eingabe):
    with pytest.raises(GeldFormatFehler):
        euro_zu_cent(eingabe)


@pytest.mark.parametrize("eingabe", [12.5, 12, None, True])
def test_euro_zu_cent_nur_text(eingabe):
    with pytest.raises(TypeError):
        euro_zu_cent(eingabe)


@pytest.mark.parametrize(
    ("cent", "text"),
    [
        (0, "0,00 €"),
        (1, "0,01 €"),
        (1250, "12,50 €"),
        (123456, "1.234,56 €"),
        (123456789, "1.234.567,89 €"),
        (-99, "-0,99 €"),
        (-123456, "-1.234,56 €"),
    ],
)
def test_cent_zu_euro(cent, text):
    assert cent_zu_euro(cent) == text


@pytest.mark.parametrize(
    ("cent", "text"),
    [(0, "0.00"), (5, "0.05"), (1250, "12.50"), (123456, "1234.56"), (-99, "-0.99")],
)
def test_cent_zu_dezimal(cent, text):
    assert cent_zu_dezimal(cent) == text


@pytest.mark.parametrize("cent", [12.5, "1250", None, True])
def test_ausgabe_nur_int(cent):
    with pytest.raises(TypeError):
        cent_zu_euro(cent)
    with pytest.raises(TypeError):
        cent_zu_dezimal(cent)


@pytest.mark.parametrize("cent", [0, 1, 99, 1250, 123456, -99, -123456789])
def test_hin_und_zurueck(cent):
    assert euro_zu_cent(cent_zu_euro(cent)) == cent
    assert euro_zu_cent(cent_zu_dezimal(cent)) == cent
