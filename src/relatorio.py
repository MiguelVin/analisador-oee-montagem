"""
Relatório em Excel para levar à reunião: resumo, achados e as tabelas por trás de cada gráfico.
"""

from __future__ import annotations

import io
import re

import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

from src.diagnostico import Achado
from src.indicadores import ResultadoOEE

COR_CABECALHO = "2A78D6"


def _sem_markdown(texto: str) -> str:
    return re.sub(r"\*\*(.+?)\*\*", r"\1", texto)


def _formatar_planilha(planilha, formatos_pct: list[str]) -> None:
    for celula in planilha[1]:
        celula.font = Font(bold=True, color="FFFFFF")
        celula.fill = PatternFill("solid", fgColor=COR_CABECALHO)
    cabecalhos = [c.value for c in planilha[1]]
    for indice, nome in enumerate(cabecalhos, start=1):
        letra = planilha.cell(1, indice).column_letter
        largura = max(len(str(nome)), *(len(str(c.value or "")) for c in planilha[letra][1:200]), 8)
        planilha.column_dimensions[letra].width = min(largura + 2, 90)
        if nome in formatos_pct:
            for celula in planilha[letra][1:]:
                celula.number_format = "0.0%"
    planilha.freeze_panes = "A2"


def gerar_relatorio_excel(
    filtros: dict[str, str],
    resultado: ResultadoOEE,
    achados: list[Achado],
    por_dia: pd.DataFrame,
    por_turno: pd.DataFrame,
    tabela_pareto: pd.DataFrame,
    tabela_yamazumi: pd.DataFrame | None,
) -> bytes:
    resumo = pd.DataFrame(
        [
            *filtros.items(),
            ("OEE", resultado.oee),
            ("Classificação", resultado.classificacao),
            ("Disponibilidade", resultado.disponibilidade),
            ("Performance", resultado.performance),
            ("Qualidade", resultado.qualidade),
            ("Tempo planejado (min)", round(resultado.tempo_planejado_min)),
            ("Tempo parado (min)", round(resultado.tempo_parada_min)),
            ("Peças produzidas", resultado.pecas_produzidas),
            ("Peças boas", resultado.pecas_boas),
        ],
        columns=["Indicador", "Valor"],
    )
    tabela_achados = pd.DataFrame(
        [(a.prioridade.capitalize(), _sem_markdown(a.titulo), _sem_markdown(a.texto)) for a in achados],
        columns=["Prioridade", "Achado", "Detalhe"],
    )
    colunas_pct = ["disponibilidade", "performance", "qualidade", "oee"]
    abas = {
        "Resumo": (resumo, []),
        "Achados": (tabela_achados, []),
        "OEE por dia": (por_dia.assign(data=por_dia["data"].dt.date), colunas_pct),
        "OEE por turno": (por_turno, colunas_pct),
        "Pareto": (tabela_pareto.round(2), []),
    }
    if tabela_yamazumi is not None:
        abas["Yamazumi"] = (tabela_yamazumi, [])

    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for nome, (df, formatos) in abas.items():
            df.to_excel(writer, sheet_name=nome, index=False)
            _formatar_planilha(writer.sheets[nome], formatos)

        planilha_resumo = writer.sheets["Resumo"]
        for linha in planilha_resumo.iter_rows(min_row=2):
            if linha[0].value in ("OEE", "Disponibilidade", "Performance", "Qualidade"):
                linha[1].number_format = "0.0%"
            linha[1].alignment = Alignment(horizontal="left")
        for linha in writer.sheets["Achados"].iter_rows(min_row=2):
            linha[2].alignment = Alignment(wrap_text=True, vertical="top")
    return buffer.getvalue()
