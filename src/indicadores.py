"""
Indicadores de eficiência: OEE (e seus 3 componentes) e Takt Time.

OEE = Disponibilidade × Performance × Qualidade

A forma mais fácil de entender o OEE é como uma "cascata de tempo":

  Tempo planejado                       (turno menos pausas programadas)
   └─ − paradas           = Tempo operando        -> Disponibilidade = operando / planejado
       └─ − perdas de ritmo = Tempo ideal produzido -> Performance     = ideal / operando
           └─ − refugo/retrabalho = Tempo efetivo  -> Qualidade       = efetivo / ideal

  Tempo ideal produzido = peças produzidas × ciclo ideal
  Tempo efetivo         = peças boas       × ciclo ideal

Multiplicando tudo: OEE = tempo efetivo / tempo planejado.
Ou seja: "de todo o tempo que a linha deveria produzir, quanto virou peça boa no ritmo ideal".

Por que somar tempos em vez de tirar a média dos OEEs de cada turno?
Porque a média simples dá o mesmo peso a um turno curto e a um turno cheio. Somar os tempos
primeiro e dividir depois é a única forma de o OEE do mês bater com a produção real do mês.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from src.leitor import CHAVE_TURNO

FAIXAS_OEE = [
    (0.85, "Classe mundial"),
    (0.75, "Bom"),
    (0.65, "Regular"),
    (0.00, "Crítico"),
]


def _razao(numerador: float, denominador: float) -> float:
    return float(numerador / denominador) if denominador else 0.0


@dataclass(frozen=True)
class ResultadoOEE:
    tempo_planejado_min: float
    tempo_parada_min: float
    tempo_operando_min: float
    tempo_ideal_min: float
    tempo_efetivo_min: float
    pecas_produzidas: int
    pecas_boas: int

    @property
    def disponibilidade(self) -> float:
        return _razao(self.tempo_operando_min, self.tempo_planejado_min)

    @property
    def performance(self) -> float:
        return _razao(self.tempo_ideal_min, self.tempo_operando_min)

    @property
    def qualidade(self) -> float:
        return _razao(self.tempo_efetivo_min, self.tempo_ideal_min)

    @property
    def oee(self) -> float:
        return self.disponibilidade * self.performance * self.qualidade

    @property
    def classificacao(self) -> str:
        return classificar_oee(self.oee)

    def perdas_min(self) -> dict[str, float]:
        """Minutos perdidos em cada etapa da cascata (base do gráfico de cascata)."""
        return {
            "Paradas (disponibilidade)": self.tempo_planejado_min - self.tempo_operando_min,
            "Ritmo (performance)": self.tempo_operando_min - self.tempo_ideal_min,
            "Refugo/retrabalho (qualidade)": self.tempo_ideal_min - self.tempo_efetivo_min,
        }


def classificar_oee(oee: float) -> str:
    for limite, nome in FAIXAS_OEE:
        if oee >= limite:
            return nome
    return FAIXAS_OEE[-1][1]


def consolidar(producao: pd.DataFrame, paradas: pd.DataFrame) -> pd.DataFrame:
    """Junta produção e paradas: uma linha por turno com todos os tempos da cascata."""
    if paradas.empty:
        df = producao.assign(tempo_parada_min=0.0)
    else:
        tempo_parada = paradas.groupby(CHAVE_TURNO)["duracao_min"].sum().rename("tempo_parada_min")
        df = producao.join(tempo_parada, on=CHAVE_TURNO)
        df["tempo_parada_min"] = df["tempo_parada_min"].fillna(0.0)
    df["tempo_operando_min"] = df["tempo_planejado_min"] - df["tempo_parada_min"]
    df["pecas_boas"] = df["pecas_produzidas"] - df["pecas_refugo"] - df["pecas_retrabalho"]
    df["tempo_ideal_min"] = df["pecas_produzidas"] * df["ciclo_ideal_s"] / 60
    df["tempo_efetivo_min"] = df["pecas_boas"] * df["ciclo_ideal_s"] / 60
    return df


_COLUNAS_SOMA = [
    "tempo_planejado_min", "tempo_parada_min", "tempo_operando_min",
    "tempo_ideal_min", "tempo_efetivo_min", "pecas_produzidas", "pecas_boas",
]


def calcular_oee(consolidado: pd.DataFrame) -> ResultadoOEE:
    """OEE agregado de todos os turnos do DataFrame (soma os tempos, depois divide)."""
    somas = consolidado[_COLUNAS_SOMA].sum()
    return ResultadoOEE(
        tempo_planejado_min=float(somas["tempo_planejado_min"]),
        tempo_parada_min=float(somas["tempo_parada_min"]),
        tempo_operando_min=float(somas["tempo_operando_min"]),
        tempo_ideal_min=float(somas["tempo_ideal_min"]),
        tempo_efetivo_min=float(somas["tempo_efetivo_min"]),
        pecas_produzidas=int(somas["pecas_produzidas"]),
        pecas_boas=int(somas["pecas_boas"]),
    )


def oee_por(consolidado: pd.DataFrame, por: str | list[str]) -> pd.DataFrame:
    """OEE quebrado por uma ou mais colunas, ex.: oee_por(df, 'turno') ou ['data', 'turno']."""
    grupos = consolidado.groupby(por, sort=True)[_COLUNAS_SOMA].sum()
    planejado, operando = grupos["tempo_planejado_min"], grupos["tempo_operando_min"]
    ideal, efetivo = grupos["tempo_ideal_min"], grupos["tempo_efetivo_min"]

    def dividir(a: pd.Series, b: pd.Series) -> pd.Series:
        return (a / b.where(b != 0)).fillna(0.0)

    grupos["disponibilidade"] = dividir(operando, planejado)
    grupos["performance"] = dividir(ideal, operando)
    grupos["qualidade"] = dividir(efetivo, ideal)
    grupos["oee"] = grupos["disponibilidade"] * grupos["performance"] * grupos["qualidade"]
    return grupos.reset_index()


def takt_time_s(tempo_disponivel_min: float, demanda_pecas: float) -> float:
    """Takt = tempo disponível / demanda. É o ritmo que a linha PRECISA ter para atender o cliente."""
    if demanda_pecas <= 0:
        raise ValueError("A demanda deve ser maior que zero.")
    if tempo_disponivel_min <= 0:
        raise ValueError("O tempo disponível deve ser maior que zero.")
    return tempo_disponivel_min * 60 / demanda_pecas
