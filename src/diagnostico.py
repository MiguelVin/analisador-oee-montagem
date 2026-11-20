"""
Diagnóstico automático: transforma os números em frases prontas para a reunião.

Cada achado tem uma prioridade:
  - "alta"  -> exige ação (gargalo acima do takt, OEE crítico...)
  - "media" -> oportunidade clara de melhoria
  - "info"  -> contexto (situação geral, pontos positivos)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import pandas as pd

from src.gargalo import ResultadoGargalo
from src.indicadores import ResultadoOEE
from src.simulador import Cenario, simular

Prioridade = Literal["alta", "media", "info"]
ORDEM_PRIORIDADE = {"alta": 0, "media": 1, "info": 2}
DIFERENCA_RELEVANTE_PP = 0.03  # 3 pontos percentuais
COMPONENTES = {"disponibilidade": "Disponibilidade", "performance": "Performance", "qualidade": "Qualidade"}


@dataclass(frozen=True)
class Achado:
    prioridade: Prioridade
    titulo: str
    texto: str


def _pct(valor: float) -> str:
    return f"{valor:.1%}".replace(".", ",")


def _pp(valor: float) -> str:
    return f"{valor * 100:.1f}".replace(".", ",") + " p.p."


def _num(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


def _segundos(valor: float) -> str:
    return f"{valor:.1f}".replace(".", ",") + " s"


def achado_oee_geral(r: ResultadoOEE) -> Achado:
    componentes = {nome: getattr(r, attr) for attr, nome in COMPONENTES.items()}
    pior = min(componentes, key=componentes.get)
    perdas = r.perdas_min()
    maior_perda = max(perdas, key=perdas.get)
    prioridade: Prioridade = "alta" if r.classificacao == "Crítico" else "info"
    return Achado(
        prioridade,
        f"OEE de {_pct(r.oee)} ({r.classificacao.lower()})",
        f"O componente mais baixo é a {pior} ({_pct(componentes[pior])}). A maior perda de tempo vem de "
        f"{maior_perda.split(' (')[0].lower()}: {_num(perdas[maior_perda])} min, "
        f"{_pct(perdas[maior_perda] / r.tempo_planejado_min)} do tempo planejado.",
    )


def achado_pareto(tabela_pareto: pd.DataFrame, consolidado: pd.DataFrame, paradas: pd.DataFrame) -> Achado | None:
    if tabela_pareto.empty:
        return None
    classe_a = tabela_pareto[tabela_pareto["classe"] == "A"]
    principal = tabela_pareto.iloc[0]
    sim = simular(consolidado, paradas, Cenario(reducao_paradas={principal["motivo"]: 0.5}))
    return Achado(
        "media",
        f"{len(classe_a)} causas concentram {_pct(classe_a['percentual'].sum() / 100)} do tempo parado",
        f"A principal é **{principal['motivo']}** ({_num(principal['valor'])} min, "
        f"{_pct(principal['percentual'] / 100)}). Reduzi-la pela metade elevaria o OEE em "
        f"{_pp(sim.ganho_oee_pp)}, cerca de {_num(sim.pecas_boas_extras)} peças boas a mais no período.",
    )


def achado_turnos(por_turno: pd.DataFrame) -> Achado | None:
    if len(por_turno) < 2:
        return None
    ordenado = por_turno.sort_values("oee")
    pior, melhor = ordenado.iloc[0], ordenado.iloc[-1]
    diferenca = melhor["oee"] - pior["oee"]
    if diferenca < DIFERENCA_RELEVANTE_PP:
        return Achado("info", "Turnos equilibrados", f"A diferença de OEE entre os turnos é de apenas {_pp(diferenca)}.")
    gaps = {nome: melhor[attr] - pior[attr] for attr, nome in COMPONENTES.items()}
    causa = max(gaps, key=gaps.get)
    return Achado(
        "media",
        f"Turno {pior['turno']} está {_pp(diferenca)} abaixo do turno {melhor['turno']}",
        f"OEE de {_pct(pior['oee'])} contra {_pct(melhor['oee'])}. A maior diferença está na "
        f"{causa} ({_pp(gaps[causa])}). Vale comparar a padronização do trabalho entre os turnos.",
    )


def achado_pior_dia(por_dia: pd.DataFrame, oee_medio: float) -> Achado | None:
    if por_dia.empty:
        return None
    pior = por_dia.loc[por_dia["oee"].idxmin()]
    if oee_medio - pior["oee"] < 0.10:
        return None
    return Achado(
        "media",
        f"Queda forte em {pior['data']:%d/%m}",
        f"O OEE caiu para {_pct(pior['oee'])} (disponibilidade de {_pct(pior['disponibilidade'])}), "
        f"{_pp(oee_medio - pior['oee'])} abaixo da média do período. Investigue as paradas desse dia.",
    )


def achado_gargalo(g: ResultadoGargalo) -> Achado:
    if g.atende_demanda:
        return Achado(
            "info",
            f"Modelo {g.modelo}: linha atende a demanda",
            f"O gargalo é o {g.posto_gargalo} ({g.nome_posto_gargalo}) com {_segundos(g.tempo_gargalo_s)}, "
            f"{_segundos(-g.diferenca_takt_s)} abaixo do takt de {_segundos(g.takt_s)}.",
        )
    if g.gargalo_sem_desperdicio_s <= g.takt_s:
        acao = (
            f"Eliminar o desperdício do posto ({_segundos(g.desperdicio_gargalo_s)}) resolve: "
            f"ele cairia para {_segundos(g.gargalo_sem_desperdicio_s)}."
        )
    else:
        acao = "Só eliminar desperdício não basta: é preciso redistribuir operações ou adicionar recurso."
    return Achado(
        "alta",
        f"Modelo {g.modelo}: {g.posto_gargalo} acima do takt",
        f"O {g.posto_gargalo} ({g.nome_posto_gargalo}) leva {_segundos(g.tempo_gargalo_s)} contra um takt de "
        f"{_segundos(g.takt_s)}: a linha não atende a demanda. {acao}",
    )


def gerar_diagnostico(
    resultado: ResultadoOEE,
    consolidado: pd.DataFrame,
    paradas: pd.DataFrame,
    tabela_pareto: pd.DataFrame,
    por_turno: pd.DataFrame,
    por_dia: pd.DataFrame,
    gargalos: list[ResultadoGargalo],
) -> list[Achado]:
    """Lista de achados ordenada por prioridade (alta primeiro)."""
    candidatos = [
        achado_oee_geral(resultado),
        *[achado_gargalo(g) for g in gargalos],
        achado_pareto(tabela_pareto, consolidado, paradas),
        achado_turnos(por_turno),
        achado_pior_dia(por_dia, resultado.oee),
    ]
    achados = [a for a in candidatos if a is not None]
    return sorted(achados, key=lambda a: ORDEM_PRIORIDADE[a.prioridade])
