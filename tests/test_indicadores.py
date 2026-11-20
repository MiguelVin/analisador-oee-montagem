import pandas as pd
import pytest

from src.indicadores import calcular_oee, classificar_oee, consolidar, oee_por, takt_time_s
from src.leitor import validar


def test_caso_classico_90_90_90(tabelas_validas):
    """
    Cálculo à mão:
      planejado 500 min, paradas 50 min  -> operando 450 min -> Disponibilidade = 450/500 = 90%
      810 peças × 30 s = 405 min ideais  -> Performance = 405/450 = 90%
      boas = 810 − 41 − 40 = 729          -> Qualidade  = 729/810 = 90%
      OEE = 0,9 × 0,9 × 0,9 = 72,9%
    """
    dados = validar(tabelas_validas)
    r = calcular_oee(consolidar(dados.producao, dados.paradas))

    assert r.disponibilidade == pytest.approx(0.90)
    assert r.performance == pytest.approx(0.90)
    assert r.qualidade == pytest.approx(0.90)
    assert r.oee == pytest.approx(0.729)
    assert r.pecas_boas == 729
    assert r.classificacao == "Regular"


def test_perdas_da_cascata_somam_tempo_perdido(tabelas_validas):
    dados = validar(tabelas_validas)
    r = calcular_oee(consolidar(dados.producao, dados.paradas))
    perdas = r.perdas_min()

    assert perdas["Paradas (disponibilidade)"] == pytest.approx(50)
    assert perdas["Ritmo (performance)"] == pytest.approx(45)  # 450 − 405
    assert perdas["Refugo/retrabalho (qualidade)"] == pytest.approx(40.5)  # 81 peças × 30 s
    # planejado − perdas = tempo efetivo, e OEE = efetivo / planejado
    assert r.tempo_planejado_min - sum(perdas.values()) == pytest.approx(r.tempo_efetivo_min)
    assert r.oee == pytest.approx(r.tempo_efetivo_min / r.tempo_planejado_min)


def _dois_turnos_desiguais() -> pd.DataFrame:
    """T1: turno cheio e perfeito (OEE 100%). T2: turno curto com metade parado (OEE 50%)."""
    producao = pd.DataFrame(
        {
            "data": pd.to_datetime(["2026-10-01", "2026-10-01"]),
            "turno": ["T1", "T2"],
            "linha": ["Linha A", "Linha A"],
            "modelo": ["X100", "X100"],
            "tempo_planejado_min": [480, 120],
            "ciclo_ideal_s": [60, 60],
            "pecas_produzidas": [480, 60],
            "pecas_refugo": [0, 0],
            "pecas_retrabalho": [0, 0],
        }
    )
    paradas = pd.DataFrame(
        {
            "data": pd.to_datetime(["2026-10-01"]),
            "turno": ["T2"],
            "linha": ["Linha A"],
            "duracao_min": [60],
        }
    )
    return consolidar(producao, paradas)


def test_oee_agregado_pondera_pelo_tempo_e_nao_pela_media():
    """
    Média simples dos turnos daria (100% + 50%) / 2 = 75%, o que está ERRADO.
    Correto: 540 min efetivos / 600 min planejados = 90%.
    """
    r = calcular_oee(_dois_turnos_desiguais())
    assert r.oee == pytest.approx(0.90)


def test_oee_por_turno():
    tabela = oee_por(_dois_turnos_desiguais(), "turno").set_index("turno")
    assert tabela.loc["T1", "oee"] == pytest.approx(1.0)
    assert tabela.loc["T2", "oee"] == pytest.approx(0.5)
    assert tabela.loc["T2", "disponibilidade"] == pytest.approx(0.5)


def test_sem_paradas_disponibilidade_100(tabelas_validas):
    tabelas_validas["paradas"] = tabelas_validas["paradas"].iloc[0:0]
    dados = validar(tabelas_validas)
    r = calcular_oee(consolidar(dados.producao, dados.paradas))
    assert r.disponibilidade == pytest.approx(1.0)


def test_takt_time():
    # 2 turnos de 480 min = 960 min; demanda 1000 peças -> 960 × 60 / 1000 = 57,6 s
    assert takt_time_s(960, 1000) == pytest.approx(57.6)


@pytest.mark.parametrize("tempo, demanda", [(960, 0), (0, 1000), (960, -5)])
def test_takt_rejeita_valores_invalidos(tempo, demanda):
    with pytest.raises(ValueError):
        takt_time_s(tempo, demanda)


@pytest.mark.parametrize(
    "oee, esperado",
    [(0.90, "Classe mundial"), (0.85, "Classe mundial"), (0.80, "Bom"), (0.70, "Regular"), (0.40, "Crítico")],
)
def test_classificacao_oee(oee, esperado):
    assert classificar_oee(oee) == esperado
