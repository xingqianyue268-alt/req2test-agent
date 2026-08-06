from req2test.document_loader import load_document_bytes


def test_load_utf8_text():
    text = load_document_bytes("需求一\n需求二".encode("utf-8"), ".txt")
    assert "需求一" in text
    assert "需求二" in text
