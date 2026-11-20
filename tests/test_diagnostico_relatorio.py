import io

import pandas as pd
import pytest

from dados.gerar_dados import gerar
from src.diagnostico import gerar_diagnostico
from src.gargalo import analisar_gargalo, yamazumi
from src.indicadores import calcular_oee, consolidar, oee_por, takt_time_s
from src.leitor import validar
from src.pareto import pareto
from src.relatorio import gerar_relatorio_excel


@pytest.fixture(scope="module")
def linha_a():
    dados = validar(gerar("2026-10-01", "2026-10-31", semente=42))
    producao = dados.producao[dados.producao["linha"] == "Linha A"]
    paradas = dados.paradas[dados.paradas["linha"] == "Linha A"]
    postos = dados.postos[dados.postos["linha"] == "Linha A"]
    consolidado = consolidar(producao, paradas)
    takt = takt_time_s(960, 1000)
    return {
        "resultado": calcular_oee(consolidado),
        "consolidado": consolidado,
        "paradas": paradas,
        "tabela_pareto": pareto(paradas),
        "por_turno": oee_por(consolidado, "turno"),
        "por_dia": oee_por(consolidado, "data"),
        "gargalos": [analisar_gargalo(postos, m, takt) for m in ("X100", "X200")],
        "yamazumi": yamazumi(postos, "X200"),
    }


@pytest.fixture(scope="module")
def achados(linha_a):
    chaves = ["resultado", "consolidado", "paradas", "tabela_pareto", "por_turno", "por_dia", "gargalos"]
    return gerar_diagnostico(**{k: linha_a[k] for k in chaves})


def test_gargalo_acima_do_takt_vem_primeiro(achados):
    assert achados[0].prioridade == "alta"
    assert "X200" in achados[0].titulo and "P04" in achados[0].titulo
    assert "desperdício" in achados[0].texto


def test_achados_ordenados_por_prioridade(achados):
    ordem = {"alta": 0, "media": 1, "info": 2}
    assert [ordem[a.prioridade] for a in achados] == sorted(ordem[a.prioridade] for a in achados)


def test_pareto_aponta_falta_de_peca_e_ganho(achados):
    pareto_achado = next(a for a in achados if "causas concentram" in a.titulo)
    assert "Falta de peça" in pareto_achado.texto
    assert "peças boas a mais" in pareto_achado.texto


def test_aponta_turno_pior(achados):
    assert any(a.titulo.startswith("Turno T2") for a in achados)


def test_aponta_queda_da_crise_de_fornecedor(achados):
    queda = next(a for a in achados if a.titulo.startswith("Queda forte"))
    dia = int(queda.titulo.split()[-1].split("/")[0])
    assert 13 <= dia <= 16  # período da crise de fornecedor no gerador


def test_relatorio_excel(linha_a, achados):
    conteudo = gerar_relatorio_excel(
        {"Linha": "Linha A", "Período": "01/10/2026 a 30/10/2026"},
        linha_a["resultado"], achados, linha_a["por_dia"], linha_a["por_turno"],
        linha_a["tabela_pareto"], linha_a["yamazumi"],
    )
    abas = pd.read_excel(io.BytesIO(conteudo), sheet_name=None)
    assert list(abas) == ["Resumo", "Achados", "OEE por dia", "OEE por turno", "Pareto", "Yamazumi"]
    resumo = abas["Resumo"].set_index("Indicador")["Valor"]
    assert resumo["Linha"] == "Linha A"
    assert float(resumo["OEE"]) == pytest.approx(linha_a["resultado"].oee)
    assert len(abas["Achados"]) == len(achados)
    assert "**" not in " ".join(abas["Achados"]["Detalhe"])  # markdown removido
