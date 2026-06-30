"""Testes unitários do módulo ML (sem banco, sem container externo)."""
import pytest
from app.jurimetria.ml_predicao import _encode_features, TRIBUNAIS_MAP, GRAU_MAP


def test_encode_features_valores_conhecidos():
    arr = _encode_features(1116, 7619, "TJMG", 365, "G1")
    assert arr.shape == (1, 5)
    assert arr[0][0] == 1116
    assert arr[0][2] == TRIBUNAIS_MAP["TJMG"]
    assert arr[0][3] == 365
    assert arr[0][4] == GRAU_MAP["G1"]


def test_encode_features_tribunal_desconhecido():
    arr = _encode_features(None, None, "TRIBUNAL_XYZ", 0, None)
    assert arr[0][2] == -1  # tribunal não mapeado → -1


def test_encode_features_dias_capped():
    """Dias > 3650 (10 anos) devem ser limitados."""
    arr = _encode_features(1116, None, "STJ", 99999, "G2")
    assert arr[0][3] == 3650


def test_prever_sem_modelo_treinado(tmp_path, monkeypatch):
    """prever_provimento sem modelo retorna disponivel=False."""
    import app.jurimetria.ml_predicao as ml
    # Aponta MODEL_PATH para local inexistente
    original = ml.MODEL_PATH
    ml.MODEL_PATH = tmp_path / "nao_existe.pkl"
    try:
        result = ml.prever_provimento(1116, None, "TJMG", 365, "G1")
        assert result["disponivel"] is False
        assert "mensagem" in result
    finally:
        ml.MODEL_PATH = original
