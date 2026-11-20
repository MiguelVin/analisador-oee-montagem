import pandas as pd
import pytest

from src.pareto import pareto


@pytest.fixture
def paradas() -> pd.DataFrame:
    # Falta de peça: 50 min (2 eventos) | Quebra: 30 min (3 eventos) | Setup: 15 min | Operador: 5 min
    eventos = [
        ("Falta de peça", "Material", 20), ("Falta de peça", "Material", 30),
        ("Quebra", "Máquina", 10), ("Quebra", "Máquina", 10), ("Quebra", "Máquina", 10),
        ("Setup", "Método", 15),
        ("Operador", "Mão de obra", 5),
    ]
    return pd.DataFrame(eventos, columns=["motivo", "categoria", "duracao_min"])


def test_pareto_por_duracao(paradas):
    """
    Total 100 min -> 50%, 30%, 15%, 5%; acumulado 50, 80, 95, 100.
    Classe pelo acumulado ANTES do item: 0 e 50 (<80) = A; 80 (<95) = B; 95 = C.
    """
    p = pareto(paradas, por="motivo")
    assert list(p["motivo"]) == ["Falta de peça", "Quebra", "Setup", "Operador"]
    assert list(p["valor"]) == [50, 30, 15, 5]
    assert list(p["percentual_acumulado"]) == pytest.approx([50, 80, 95, 100])
    assert list(p["classe"]) == ["A", "A", "B", "C"]


def test_pareto_por_ocorrencias(paradas):
    p = pareto(paradas, por="motivo", medida="ocorrencias")
    assert p.iloc[0]["motivo"] == "Quebra"  # interrompe mais vezes, mesmo parando menos tempo
    assert p.iloc[0]["valor"] == 3


def test_pareto_por_categoria(paradas):
    p = pareto(paradas, por="categoria")
    assert p.iloc[0]["categoria"] == "Material"


def test_pareto_sem_paradas(paradas):
    p = pareto(paradas.iloc[0:0])
    assert p.empty


def test_medida_invalida(paradas):
    with pytest.raises(ValueError):
        pareto(paradas, medida="custo")
