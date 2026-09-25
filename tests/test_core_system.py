from max_cli.core.engines.system_engine import SystemEngine


def test_generate_qr_returns_text_without_printing(capsys):
    qr_text = SystemEngine().generate_qr("https://example.com")

    assert qr_text.strip()
    assert len(qr_text.splitlines()) > 5
    assert capsys.readouterr().out == ""
