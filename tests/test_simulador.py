import pytest

from src.indicadores import consolidar
from src.leitor import validar
from src.simulador import Cenario, simular


@pytest.fixture
def base(tabelas_validas):
    """Caso clássico: D 90% × P 90% × Q 90%. Paradas: falta de peça 30 min + quebra 20 min."""
    dados = validar(tabelas_validas)
    return consolidar(dados.producao, dados.paradas), dados.paradas


def test_cenario_vazio_nao_muda_nada(base):
    r = simular(*base, Cenario())
    assert r.simulado.oee == pytest.approx(r.atual.oee)
    assert r.pecas_boas_extras == 0


def test_eliminar_falta_de_peca(base):
    """
    Recupera 30 min: operando 450 -> 480 de 500 -> D = 96%
    OEE = 0,96 × 0,9 × 0,9 = 77,76% (ganho de 4,86 p.p.)
    Peças boas: 480 min × 0,9 × 0,9 = 388,8 min efetivos / 0,5 min por peça = 778 (eram 729)
    """
    r = simular(*base, Cenario(reducao_paradas={"Falta de peça": 1.0}))
    assert r.simulado.disponibilidade == pytest.approx(0.96)
    assert r.simulado.oee == pytest.approx(0.7776)
    assert r.ganho_oee_pp == pytest.approx(0.0486)
    assert r.minutos_recuperados == pytest.approx(30)
    assert r.pecas_boas_extras == 778 - 729


def test_reducao_parcial(base):
    r = simular(*base, Cenario(reducao_paradas={"Quebra de parafusadeira": 0.5}))
    assert r.minutos_recuperados == pytest.approx(10)


def test_performance_limitada_a_100(base):
    r = simular(*base, Cenario(ganho_performance_pp=0.5))
    assert r.simulado.performance == pytest.approx(1.0)


def test_reducao_de_perdas_de_qualidade(base):
    # Perda de qualidade de 10% cai pela metade -> qualidade 95%
    r = simular(*base, Cenario(reducao_perdas_qualidade=0.5))
    assert r.simulado.qualidade == pytest.approx(0.95)


def test_cenario_vazio_com_mix_de_modelos():
    """Bug encontrado no painel: com X100 e X200 (ciclos diferentes) o cenário vazio dava -3 peças."""
    from dados.gerar_dados import gerar

    dados = validar(gerar("2026-10-01", "2026-10-31", semente=42))
    producao = dados.producao[dados.producao["linha"] == "Linha A"]
    paradas = dados.paradas[dados.paradas["linha"] == "Linha A"]
    r = simular(consolidar(producao, paradas), paradas, Cenario())
    assert r.pecas_boas_extras == 0
    assert r.simulado.pecas_produzidas == r.atual.pecas_produzidas


def test_motivo_inexistente_e_ignorado(base):
    r = simular(*base, Cenario(reducao_paradas={"Motivo que não existe": 1.0}))
    assert r.minutos_recuperados == 0
