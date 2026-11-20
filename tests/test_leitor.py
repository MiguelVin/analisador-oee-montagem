from pathlib import Path

import pandas as pd
import pytest

from src.leitor import ErroPlanilha, carregar_e_validar, normalizar_texto, validar

EXEMPLO = Path(__file__).parents[1] / "dados" / "exemplo_montagem.xlsx"


def test_normalizar_texto():
    assert normalizar_texto("Peças Produzidas ") == "pecas_produzidas"
    assert normalizar_texto("Duração (min)") == "duracao_min"
    assert normalizar_texto("Produção") == "producao"


def test_planilha_valida(tabelas_validas):
    dados = validar(tabelas_validas)
    assert len(dados.producao) == 1
    assert len(dados.paradas) == 2
    assert dados.avisos == []
    assert pd.api.types.is_datetime64_any_dtype(dados.producao["data"])


def test_aceita_cabecalhos_com_acento_e_maiusculas(tabelas_validas):
    tabelas_validas["producao"] = tabelas_validas["producao"].rename(
        columns={"pecas_produzidas": "Peças Produzidas", "tempo_planejado_min": "Tempo Planejado (min)"}
    )
    dados = validar(tabelas_validas)
    assert dados.producao.loc[0, "pecas_produzidas"] == 810


def test_aceita_decimal_com_virgula_e_data_brasileira(tabelas_validas):
    tabelas_validas["paradas"]["duracao_min"] = ["12,5", "20"]
    tabelas_validas["paradas"]["data"] = ["01/10/2026", "01/10/2026"]
    tabelas_validas["producao"]["data"] = ["01/10/2026"]
    dados = validar(tabelas_validas)
    assert dados.paradas.loc[0, "duracao_min"] == 12.5
    assert dados.producao.loc[0, "data"] == pd.Timestamp("2026-10-01")  # 1º de outubro, não 10 de janeiro


def test_aba_faltando(tabelas_validas):
    del tabelas_validas["postos"]
    with pytest.raises(ErroPlanilha, match="'postos'"):
        validar(tabelas_validas)


def test_coluna_faltando(tabelas_validas):
    tabelas_validas["producao"] = tabelas_validas["producao"].drop(columns="ciclo_ideal_s")
    with pytest.raises(ErroPlanilha, match="ciclo_ideal_s"):
        validar(tabelas_validas)


def test_numero_invalido_aponta_linha_do_excel(tabelas_validas):
    tabelas_validas["paradas"]["duracao_min"] = [30, "abc"]
    with pytest.raises(ErroPlanilha, match="linhas 3") as erro:  # 2º registro = linha 3 do Excel
        validar(tabelas_validas)
    assert "duracao_min" in str(erro.value)


def test_refugo_maior_que_producao(tabelas_validas):
    tabelas_validas["producao"]["pecas_refugo"] = [900]
    with pytest.raises(ErroPlanilha, match="refugo"):
        validar(tabelas_validas)


def test_valor_negativo(tabelas_validas):
    tabelas_validas["producao"]["pecas_retrabalho"] = [-1]
    with pytest.raises(ErroPlanilha, match="negativo"):
        validar(tabelas_validas)


def test_paradas_maiores_que_turno(tabelas_validas):
    tabelas_validas["paradas"]["duracao_min"] = [400, 200]
    with pytest.raises(ErroPlanilha, match="mais que o tempo planejado"):
        validar(tabelas_validas)


def test_registro_duplicado(tabelas_validas):
    tabelas_validas["producao"] = pd.concat([tabelas_validas["producao"]] * 2, ignore_index=True)
    with pytest.raises(ErroPlanilha, match="mais de um registro"):
        validar(tabelas_validas)


def test_parada_sem_producao_vira_aviso(tabelas_validas):
    tabelas_validas["paradas"].loc[1, "turno"] = "T3"
    dados = validar(tabelas_validas)
    assert len(dados.paradas) == 1
    assert any("sem registro de produção" in a for a in dados.avisos)


def test_performance_acima_de_100_vira_aviso(tabelas_validas):
    tabelas_validas["producao"]["pecas_produzidas"] = [1000]  # 1000 × 30 s = 500 min > 450 operando
    dados = validar(tabelas_validas)
    assert any("Performance acima de 100%" in a for a in dados.avisos)


def test_planilha_de_exemplo_e_valida():
    dados = carregar_e_validar(EXEMPLO)
    assert dados.avisos == []
    assert sorted(dados.producao["linha"].unique()) == ["Linha A", "Linha B"]
    assert dados.linhas is not None and len(dados.linhas) == 2


def test_postos_sem_coluna_linha_com_uma_linha_so(tabelas_validas):
    """Com uma única linha de produção, a coluna 'linha' dos postos é opcional."""
    dados = validar(tabelas_validas)
    assert set(dados.postos["linha"]) == {"Linha A"}


def test_postos_sem_coluna_linha_com_varias_linhas(tabelas_validas):
    extra = tabelas_validas["producao"].assign(linha="Linha B")
    tabelas_validas["producao"] = pd.concat([tabelas_validas["producao"], extra], ignore_index=True)
    with pytest.raises(ErroPlanilha, match="precisam da coluna 'linha'"):
        validar(tabelas_validas)


def test_linha_sem_estudo_de_tempos_vira_aviso(tabelas_validas):
    extra = tabelas_validas["producao"].assign(linha="Linha B")
    tabelas_validas["producao"] = pd.concat([tabelas_validas["producao"], extra], ignore_index=True)
    tabelas_validas["postos"]["linha"] = "Linha A"
    dados = validar(tabelas_validas)
    assert any("Linha B" in a and "gargalo" in a for a in dados.avisos)


def test_aba_linhas_opcional_validada(tabelas_validas):
    tabelas_validas["linhas"] = pd.DataFrame(
        {"linha": ["Linha A"], "demanda_diaria": [0], "tempo_disponivel_min": [960]}
    )
    with pytest.raises(ErroPlanilha, match="demanda_diaria"):
        validar(tabelas_validas)
