"""
Análise de gargalo e balanceamento de linha (base do gráfico Yamazumi).

Numa linha de montagem os postos trabalham em série: a peça só avança quando o posto
mais lento termina. Por isso:
  - o posto com maior tempo é o GARGALO e define a capacidade da linha
  - se o gargalo é mais lento que o takt, a linha NÃO atende a demanda
  - postos muito abaixo do gargalo ficam ociosos esperando (desbalanceamento)

Eficiência de balanceamento = soma dos tempos de todos os postos / (nº de postos × tempo do gargalo)
  100% = todos os postos com a mesma carga; quanto menor, mais ociosidade na linha.

Número mínimo teórico de postos = arredondar para cima(soma dos tempos / takt)
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from src.leitor import normalizar_texto

TIPO_AV = "Agrega valor"
TIPO_NAV = "Não agrega valor necessário"
TIPO_DESPERDICIO = "Desperdício"
ORDEM_TIPOS = [TIPO_AV, TIPO_NAV, TIPO_DESPERDICIO]


def _filtrar_modelo(postos: pd.DataFrame, modelo: str) -> pd.DataFrame:
    df = postos[postos["modelo"] == modelo]
    if df.empty:
        disponiveis = ", ".join(sorted(postos["modelo"].unique()))
        raise ValueError(f"Modelo '{modelo}' não encontrado. Disponíveis: {disponiveis}.")
    return df


def yamazumi(postos: pd.DataFrame, modelo: str) -> pd.DataFrame:
    """Tempo de cada posto quebrado por tipo de atividade (linhas = postos, colunas = tipos)."""
    df = _filtrar_modelo(postos, modelo)
    tabela = df.pivot_table(
        index=["posto", "nome_posto"], columns="tipo", values="tempo_s", aggfunc="sum", fill_value=0
    )
    # Tipos conhecidos primeiro, na ordem lógica de empilhamento; tipos extras no fim
    colunas = [t for t in ORDEM_TIPOS if t in tabela.columns]
    colunas += [t for t in tabela.columns if t not in colunas]
    tabela = tabela[colunas]
    tabela.columns.name = None
    tabela["total_s"] = tabela[colunas].sum(axis=1)
    return tabela.reset_index().sort_values("posto").reset_index(drop=True)


@dataclass(frozen=True)
class ResultadoGargalo:
    modelo: str
    takt_s: float
    posto_gargalo: str
    nome_posto_gargalo: str
    tempo_gargalo_s: float
    desperdicio_gargalo_s: float
    conteudo_trabalho_s: float  # soma dos tempos de todos os postos
    numero_postos: int
    postos_acima_takt: tuple[str, ...]

    @property
    def atende_demanda(self) -> bool:
        return self.tempo_gargalo_s <= self.takt_s

    @property
    def diferenca_takt_s(self) -> float:
        """Positivo = gargalo está ACIMA do takt (falta capacidade)."""
        return self.tempo_gargalo_s - self.takt_s

    @property
    def capacidade_pecas_hora(self) -> float:
        return 3600 / self.tempo_gargalo_s

    @property
    def eficiencia_balanceamento(self) -> float:
        return self.conteudo_trabalho_s / (self.numero_postos * self.tempo_gargalo_s)

    @property
    def postos_minimos(self) -> int:
        return math.ceil(round(self.conteudo_trabalho_s / self.takt_s, 9))

    @property
    def gargalo_sem_desperdicio_s(self) -> float:
        """Tempo do gargalo se o desperdício dele fosse eliminado (primeira ação de kaizen)."""
        return self.tempo_gargalo_s - self.desperdicio_gargalo_s


def analisar_gargalo(postos: pd.DataFrame, modelo: str, takt_s: float) -> ResultadoGargalo:
    if takt_s <= 0:
        raise ValueError("O takt time deve ser maior que zero.")

    tabela = yamazumi(postos, modelo)
    colunas_desperdicio = [
        c for c in tabela.columns if normalizar_texto(c) == normalizar_texto(TIPO_DESPERDICIO)
    ]
    tabela["desperdicio_s"] = tabela[colunas_desperdicio].sum(axis=1) if colunas_desperdicio else 0

    # Em caso de empate, o primeiro posto da linha é apontado como gargalo
    gargalo = tabela.loc[tabela["total_s"].idxmax()]
    acima = tabela.loc[tabela["total_s"] > takt_s, "posto"]

    return ResultadoGargalo(
        modelo=modelo,
        takt_s=float(takt_s),
        posto_gargalo=str(gargalo["posto"]),
        nome_posto_gargalo=str(gargalo["nome_posto"]),
        tempo_gargalo_s=float(gargalo["total_s"]),
        desperdicio_gargalo_s=float(gargalo["desperdicio_s"]),
        conteudo_trabalho_s=float(tabela["total_s"].sum()),
        numero_postos=len(tabela),
        postos_acima_takt=tuple(acima),
    )
