import pandas as pd
import pytest

from src.leitor import validar
from src.mapeamento import Mapeamento, ajustar_ao_arquivo, aplicar_mapeamento, sugerir_mapeamento


@pytest.fixture
def planilha_da_empresa(tabelas_validas) -> dict[str, pd.DataFrame]:
    """A mesma informação da planilha padrão, mas com os nomes que uma empresa real usaria."""
    producao = tabelas_validas["producao"].rename(columns={
        "data": "Data Produção",
        "linha": "Célula",
        "modelo": "Produto",
        "tempo_planejado_min": "Tempo Programado",
        "ciclo_ideal_s": "Tempo de Ciclo",
        "pecas_produzidas": "Qtd Produzida",
        "pecas_refugo": "Sucata",
        "pecas_retrabalho": "Rework",
    })
    paradas = tabelas_validas["paradas"].rename(columns={
        "linha": "Célula",
        "posto": "Estação",
        "motivo": "Causa",
        "categoria": "6M",
        "duracao_min": "Tempo de Parada",
    })
    postos = tabelas_validas["postos"].rename(columns={
        "posto": "Estação",
        "nome_posto": "Descrição Estação",
        "operacao": "Atividade",
        "tempo_s": "Tempo Cronometrado",
        "tipo": "Classificação",
        "modelo": "Produto",
    })
    return {"apontamentos": producao, "downtime": paradas, "cronoanalise": postos, "outra_aba": pd.DataFrame()}


def test_sugere_abas_pelos_sinonimos(planilha_da_empresa):
    m = sugerir_mapeamento(planilha_da_empresa)
    assert m.abas["producao"] == "apontamentos"
    assert m.abas["paradas"] == "downtime"
    assert m.abas["postos"] == "cronoanalise"
    assert m.abas["linhas"] is None  # aba opcional ausente


def test_sugere_colunas_pelos_sinonimos(planilha_da_empresa):
    m = sugerir_mapeamento(planilha_da_empresa)
    assert m.colunas["producao"]["pecas_produzidas"] == "Qtd Produzida"
    assert m.colunas["producao"]["pecas_retrabalho"] == "Rework"
    assert m.colunas["producao"]["linha"] == "Célula"
    assert m.colunas["paradas"]["duracao_min"] == "Tempo de Parada"
    assert m.colunas["postos"]["tempo_s"] == "Tempo Cronometrado"
    assert m.completo


def test_sugere_nome_parecido():
    tabelas = {"producao": pd.DataFrame(columns=["pecas_produzida"])}  # erro de digitação
    m = sugerir_mapeamento(tabelas)
    assert m.colunas["producao"]["pecas_produzidas"] == "pecas_produzida"


def test_planilha_da_empresa_passa_na_validacao(planilha_da_empresa):
    m = sugerir_mapeamento(planilha_da_empresa)
    dados = validar(aplicar_mapeamento(planilha_da_empresa, m))
    assert dados.producao.loc[0, "pecas_produzidas"] == 810
    assert len(dados.paradas) == 2


def test_aponta_pendencias(planilha_da_empresa):
    planilha_da_empresa["apontamentos"] = planilha_da_empresa["apontamentos"].rename(
        columns={"Rework": "Coluna sem nome conhecido"}
    )
    m = sugerir_mapeamento(planilha_da_empresa)
    assert not m.completo
    assert any("Peças retrabalhadas" in p for p in m.pendencias())

    # O usuário corrige na tela e o cálculo segue
    m.colunas["producao"]["pecas_retrabalho"] = "Coluna sem nome conhecido"
    assert m.completo


def test_json_ida_e_volta(planilha_da_empresa):
    m = sugerir_mapeamento(planilha_da_empresa)
    copia = Mapeamento.de_json(m.para_json())
    assert copia == m


def test_ajustar_ao_arquivo_descarta_o_que_nao_existe(planilha_da_empresa):
    m = sugerir_mapeamento(planilha_da_empresa)
    m.colunas["producao"]["turno"] = "Coluna de outro arquivo"
    ajustado = ajustar_ao_arquivo(m, planilha_da_empresa)
    assert ajustado.colunas["producao"]["turno"] is None
    assert ajustado.colunas["producao"]["pecas_produzidas"] == "Qtd Produzida"
