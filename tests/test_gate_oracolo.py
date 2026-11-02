import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import gate_oracolo


def test_sonda_mancante_e_un_errore(monkeypatch, capsys):
    monkeypatch.setattr(gate_oracolo, "Sonda_disponibile", lambda: False)
    monkeypatch.setattr(sys, "argv", ["gate_oracolo.py"])

    assert gate_oracolo.main() == 1
    captured = capsys.readouterr()
    assert "ERRORE: sonda non trovata" in captured.err
    assert "SALTATO" not in captured.out + captured.err
