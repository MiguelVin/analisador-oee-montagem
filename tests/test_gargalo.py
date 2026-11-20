import pandas as pd
import pytest

from src.gargalo import analisar_gargalo, yamazumi


@pytest.fixture
def postos() -> pd.DataFrame:
    """
    P1 = 30 s (só AV)
    P2 = 50 s (30 AV + 10 NAV + 10 desperdício)  <- gargalo
    P3 = 40 s (25 AV + 15 NAV)
    """
    linhas = [
        ("M", "P1", "Base", "Op 1", 30, "Agrega valor"),
        ("M", "P2", "Motor", "Op 2", 30, "Agrega valor"),
        ("M", "P2", "Motor", "Op 3", 10, "Não agrega valor necessário"),
        ("M", "P2", "Motor", "Op 4", 10, "Desperdício"),
        ("M", "P3", "Tampa", "Op 5", 25, "Agrega valor"),
        ("M", "P3", "Tampa", "Op 6", 15, "Não agrega valor necessário"),
        ("N", "P1", "Base", "Op 1", 20, "Agrega valor"),
    ]
    return pd.DataFrame(linhas, columns=["modelo", "posto", "nome_posto", "operacao", "tempo_s", "tipo"])


def test_yamazumi_empilha_por_tipo(postos):
    y = yamazumi(postos, "M").set_index("posto")
    assert list(y.columns[1:4]) == ["Agrega valor", "Não agrega valor necessário", "Desperdício"]
    assert y.loc["P2", "Desperdício"] == 10
    assert y.loc["P1", "Desperdício"] == 0
    assert list(y["total_s"]) == [30, 50, 40]


def test_gargalo_acima_do_takt(postos):
    """
    Takt 45 s:
      gargalo = P2 (50 s), 5 s acima do takt -> não atende a demanda
      eficiência de balanceamento = 120 / (3 × 50) = 80%
      postos mínimos = arredondar para cima(120 / 45 = 2,67) = 3
      capacidade = 3600 / 50 = 72 peças/h
      sem o desperdício, o P2 cai para 40 s -> abaixo do takt
    """
    r = analisar_gargalo(postos, "M", takt_s=45)

    assert r.posto_gargalo == "P2"
    assert r.nome_posto_gargalo == "Motor"
    assert r.tempo_gargalo_s == 50
    assert not r.atende_demanda
    assert r.diferenca_takt_s == pytest.approx(5)
    assert r.postos_acima_takt == ("P2",)
    assert r.eficiencia_balanceamento == pytest.approx(0.80)
    assert r.postos_minimos == 3
    assert r.capacidade_pecas_hora == pytest.approx(72)
    assert r.gargalo_sem_desperdicio_s == 40


def test_gargalo_dentro_do_takt(postos):
    r = analisar_gargalo(postos, "M", takt_s=60)
    assert r.atende_demanda
    assert r.postos_acima_takt == ()
    assert r.postos_minimos == 2  # 120 / 60 = 2 exatos


def test_filtra_pelo_modelo(postos):
    r = analisar_gargalo(postos, "N", takt_s=60)
    assert r.numero_postos == 1
    assert r.tempo_gargalo_s == 20


def test_modelo_inexistente(postos):
    with pytest.raises(ValueError, match="não encontrado"):
        analisar_gargalo(postos, "Z", takt_s=60)
