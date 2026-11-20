"""
Testes de integração: os dados fictícios precisam contar a história que o app vai mostrar.
Se alguém mexer no gerador e quebrar essa história, estes testes avisam.
"""

import pytest

from dados.gerar_dados import gerar
from src.gargalo import analisar_gargalo
from src.indicadores import calcular_oee, consolidar, oee_por, takt_time_s
from src.leitor import validar
from src.pareto import pareto


@pytest.fixture(scope="module")
def dados():
    return validar(gerar("2026-10-01", "2026-10-31", semente=42))


def _da_linha(df, linha):
    return df[df["linha"] == linha]


def test_oee_realista(dados):
    r = calcular_oee(consolidar(dados.producao, dados.paradas))
    assert 0.60 < r.oee < 0.85


def test_linha_b_tem_oee_maior_que_linha_a(dados):
    por_linha = oee_por(consolidar(dados.producao, dados.paradas), "linha").set_index("linha")
    assert por_linha.loc["Linha B", "oee"] > por_linha.loc["Linha A", "oee"]


def test_segundo_turno_e_pior_na_linha_a(dados):
    c = consolidar(_da_linha(dados.producao, "Linha A"), _da_linha(dados.paradas, "Linha A"))
    por_turno = oee_por(c, "turno").set_index("turno")
    assert por_turno.loc["T2", "oee"] < por_turno.loc["T1", "oee"]


def test_falta_de_peca_lidera_o_pareto_da_linha_a(dados):
    p = pareto(_da_linha(dados.paradas, "Linha A"))
    assert p.iloc[0]["motivo"] == "Falta de peça"
    assert p.iloc[:3]["percentual"].sum() > 70  # poucas causas concentram o problema


def test_p04_e_gargalo_e_x200_estoura_o_takt(dados):
    postos_a = _da_linha(dados.postos, "Linha A")
    takt = takt_time_s(960, 1000)  # 57,6 s
    x100 = analisar_gargalo(postos_a, "X100", takt)
    x200 = analisar_gargalo(postos_a, "X200", takt)

    assert x100.posto_gargalo == x200.posto_gargalo == "P04"
    assert x100.atende_demanda
    assert not x200.atende_demanda
    assert x200.gargalo_sem_desperdicio_s < takt  # eliminar desperdício resolve


def test_linha_b_atende_a_demanda(dados):
    parametros = dados.linhas.set_index("linha").loc["Linha B"]
    takt = takt_time_s(parametros["tempo_disponivel_min"], parametros["demanda_diaria"])
    g = analisar_gargalo(_da_linha(dados.postos, "Linha B"), "C300", takt)
    assert g.atende_demanda
