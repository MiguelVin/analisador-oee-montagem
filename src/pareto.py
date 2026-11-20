"""
Análise de Pareto das paradas, com classificação ABC.

Princípio de Pareto: poucas causas costumam responder pela maior parte do problema
(a famosa regra 80/20). Atacar as causas da classe A dá o maior retorno.

Classificação ABC (pelo percentual acumulado ANTES do item):
  A -> o item começa antes de 80%  (inclui o item que "cruza" os 80%)
  B -> começa entre 80% e 95%
  C -> o restante
"""

from __future__ import annotations

from typing import Literal

import pandas as pd

LIMITE_A = 80.0
LIMITE_B = 95.0


def pareto(
    paradas: pd.DataFrame,
    por: str = "motivo",
    medida: Literal["duracao", "ocorrencias"] = "duracao",
) -> pd.DataFrame:
    """
    Agrupa as paradas por `por` (motivo, categoria, posto...) e ordena do maior para o menor.

    medida='duracao'    -> soma os minutos parados (o que mais custa tempo)
    medida='ocorrencias' -> conta os eventos (o que mais interrompe a linha)
    """
    if medida == "duracao":
        valores = paradas.groupby(por)["duracao_min"].sum()
    elif medida == "ocorrencias":
        valores = paradas.groupby(por).size()
    else:
        raise ValueError("medida deve ser 'duracao' ou 'ocorrencias'.")

    df = valores.rename("valor").reset_index()
    # Desempate pelo nome deixa o resultado sempre na mesma ordem
    df = df.sort_values(["valor", por], ascending=[False, True]).reset_index(drop=True)

    total = df["valor"].sum()
    df["percentual"] = df["valor"] / total * 100 if total else 0.0
    df["percentual_acumulado"] = df["percentual"].cumsum()

    acumulado_antes = df["percentual_acumulado"] - df["percentual"]
    df["classe"] = "C"
    df.loc[acumulado_antes < LIMITE_B, "classe"] = "B"
    df.loc[acumulado_antes < LIMITE_A, "classe"] = "A"
    return df
