def test_pdf_laedt_keine_externen_adressen():
    import pytest

    from app.services.pdf import nur_eingebettet

    abrufer = nur_eingebettet()
    for adresse in ("http://169.254.169.254/", "file:///etc/passwd", "https://example.org/a.png"):
        with pytest.raises(Exception):  # noqa: B017  jede Ablehnung ist recht
            abrufer.fetch(adresse)
    assert abrufer.fetch("data:text/plain;base64,aGFsbG8=").read() == b"hallo"
