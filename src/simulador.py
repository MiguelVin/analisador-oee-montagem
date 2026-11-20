"""
Simulador "e se": quanto o OEE melhora se eu atacar uma causa específica?

Exemplo de pergunta que ele responde:
  "Se reduzirmos em 50% as paradas por falta de peça e ganharmos 2 pontos de performance,
   quantas peças boas a mais teríamos no mês?"

Premissas (simples e explícitas, como num estudo de engenharia):
  - o tempo de parada eliminado vira tempo operando
  - esse tempo recuperado roda com a MESMA performance de hoje (mais o ganho informado)
  - a perda de qualidade cai proporcionalmente à redução informada
  - o ciclo ideal médio (ponderado pelo mix de modelos) não muda
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from src.indicadores import ResultadoOEE, calcular_oee


@dataclass(frozen=True)
class Cenario:
    reducao_paradas: dict[str, float] = field(default_factory=dict)  # motivo -> fração (0 a 1)
    ganho_performance_pp: float = 0.0  # em fração: 0.02 = +2 pontos percentuais
    reducao_perdas_qualidade: float = 0.0  # fração do refugo+retrabalho eliminada (0 a 1)


@dataclass(frozen=True)
class ResultadoSimulacao:
    atual: ResultadoOEE
    simulado: ResultadoOEE

    @property
    def ganho_oee_pp(self) -> float:
        return self.simulado.oee - self.atual.oee

    @property
    def minutos_recuperados(self) -> float:
        return self.atual.tempo_parada_min - self.simulado.tempo_parada_min

    @property
    def pecas_boas_extras(self) -> int:
        return self.simulado.pecas_boas - self.atual.pecas_boas


def _limitar(valor: float) -> float:
    return min(max(valor, 0.0), 1.0)


def simular(consolidado: pd.DataFrame, paradas: pd.DataFrame, cenario: Cenario) -> ResultadoSimulacao:
    atual = calcular_oee(consolidado)

    por_motivo = paradas.groupby("motivo")["duracao_min"].sum() if not paradas.empty else pd.Series(dtype=float)
    recuperado = sum(
        por_motivo.get(motivo, 0.0) * _limitar(fracao) for motivo, fracao in cenario.reducao_paradas.items()
    )

    operando = atual.tempo_operando_min + recuperado
    performance = _limitar(atual.performance + cenario.ganho_performance_pp)
    qualidade = 1 - (1 - atual.qualidade) * (1 - _limitar(cenario.reducao_perdas_qualidade))
    ideal = operando * performance
    efetivo = ideal * qualidade

    # Só o tempo GANHO é convertido em peças, pelo ciclo médio do período (respeita o mix de modelos).
    # Converter o tempo total geraria erro de arredondamento quando há modelos com ciclos diferentes.
    ciclo_medio_min = atual.tempo_ideal_min / atual.pecas_produzidas if atual.pecas_produzidas else 0.0
    ciclo_medio_bom_min = atual.tempo_efetivo_min / atual.pecas_boas if atual.pecas_boas else 0.0
    pecas = atual.pecas_produzidas + (round((ideal - atual.tempo_ideal_min) / ciclo_medio_min) if ciclo_medio_min else 0)
    boas = atual.pecas_boas + (round((efetivo - atual.tempo_efetivo_min) / ciclo_medio_bom_min) if ciclo_medio_bom_min else 0)

    simulado = ResultadoOEE(
        tempo_planejado_min=atual.tempo_planejado_min,
        tempo_parada_min=atual.tempo_parada_min - recuperado,
        tempo_operando_min=operando,
        tempo_ideal_min=ideal,
        tempo_efetivo_min=efetivo,
        pecas_produzidas=pecas,
        pecas_boas=boas,
    )
    return ResultadoSimulacao(atual=atual, simulado=simulado)
