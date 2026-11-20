"""
Gráficos interativos (Plotly) do painel.

Regras de design seguidas:
  - um único eixo Y por gráfico (o Pareto usa % nos dois elementos, sem eixo duplo)
  - cores fixas por significado, nunca por posição; paleta validada para daltonismo
  - destaque com cor só no que importa (classe A do Pareto); o resto em cinza
  - grade discreta, barras finas com cantos arredondados, hover em todos os gráficos
"""

from __future__ import annotations

import textwrap

import pandas as pd
import plotly.graph_objects as go

from src.gargalo import TIPO_AV, TIPO_DESPERDICIO, TIPO_NAV
from src.indicadores import ResultadoOEE

# Paleta (slots 1–3 da paleta categórica de referência, validados para daltonismo)
AZUL = "#2a78d6"
LARANJA = "#eb6834"
VERDE_AGUA = "#1baf7a"
CINZA = "#c3c2b7"

SUPERFICIE = "#fcfcfb"
TINTA = "#0b0b0b"
TINTA_SECUNDARIA = "#52514e"
TINTA_FRACA = "#898781"
GRADE = "#e1e0d9"
EIXO = "#c3c2b7"

CORES_TIPO = {TIPO_AV: AZUL, TIPO_NAV: VERDE_AGUA, TIPO_DESPERDICIO: LARANJA}
CORES_TURNO = [AZUL, LARANJA, VERDE_AGUA]  # T1, T2, T3 — fixas pela ordem do turno, não pelo filtro

FONTE = 'system-ui, -apple-system, "Segoe UI", sans-serif'


def _layout_base(fig: go.Figure, titulo_y: str = "", altura: int = 380) -> go.Figure:
    fig.update_layout(
        height=altura,
        separators=",.",  # padrão brasileiro: vírgula decimal, ponto de milhar
        margin=dict(l=16, r=16, t=40, b=16),
        font=dict(family=FONTE, size=13, color=TINTA_SECUNDARIA),
        paper_bgcolor=SUPERFICIE,
        plot_bgcolor=SUPERFICIE,
        hoverlabel=dict(bgcolor="white", font=dict(family=FONTE, color=TINTA), bordercolor=GRADE),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, title_text=""),
        bargap=0.35,
        barcornerradius=4,
    )
    fig.update_xaxes(showgrid=False, linecolor=EIXO, tickfont=dict(color=TINTA_FRACA), ticks="", automargin=True)
    fig.update_yaxes(
        title_text=titulo_y, gridcolor=GRADE, gridwidth=1, zeroline=False, automargin=True,
        separatethousands=True,
        linecolor=EIXO, tickfont=dict(color=TINTA_FRACA), title_font=dict(color=TINTA_FRACA),
    )
    return fig


def _quebrar(texto: str, largura: int = 16) -> str:
    return "<br>".join(textwrap.wrap(str(texto), largura)) or str(texto)


def _formatar_min(valor: float) -> str:
    return f"{valor:,.0f}".replace(",", ".")


# ---------------------------------------------------------------------------
# OEE
# ---------------------------------------------------------------------------
def grafico_cascata(r: ResultadoOEE) -> go.Figure:
    """Cascata de tempo: do tempo planejado até o tempo efetivo (peças boas no ritmo ideal)."""
    perdas = r.perdas_min()
    nomes = ["Tempo<br>planejado", *[n.split(" (")[0].replace("/", "/<br>") for n in perdas], "Tempo<br>efetivo"]
    valores = [r.tempo_planejado_min, *[-v for v in perdas.values()], r.tempo_efetivo_min]
    medidas = ["absolute", "relative", "relative", "relative", "total"]
    textos = [_formatar_min(abs(v)) + " min" for v in valores]

    fig = go.Figure(
        go.Waterfall(
            x=nomes, y=valores, measure=medidas, text=textos, textposition="outside",
            textfont=dict(color=TINTA_SECUNDARIA),
            totals=dict(marker=dict(color=AZUL)),
            increasing=dict(marker=dict(color=AZUL)),
            decreasing=dict(marker=dict(color=LARANJA)),
            connector=dict(line=dict(color=EIXO, width=1)),
            hovertemplate="%{x}: %{text}<extra></extra>",
        )
    )
    _layout_base(fig, "minutos")
    fig.update_yaxes(range=[0, r.tempo_planejado_min * 1.12])
    return fig


def grafico_oee_diario(
    por_dia_turno: pd.DataFrame, todos_turnos: list[str] | None = None, meta: float = 0.85
) -> go.Figure:
    """
    Evolução do OEE por dia, uma linha por turno, com a meta de classe mundial como referência.
    `todos_turnos` garante que cada turno mantenha a mesma cor mesmo quando outro é filtrado.
    """
    fig = go.Figure()
    turnos = sorted(por_dia_turno["turno"].unique())
    todos_turnos = sorted(todos_turnos or turnos)
    for turno in turnos:
        dados = por_dia_turno[por_dia_turno["turno"] == turno].sort_values("data")
        cor = CORES_TURNO[todos_turnos.index(turno) % len(CORES_TURNO)]
        fig.add_trace(
            go.Scatter(
                x=dados["data"], y=dados["oee"], name=f"Turno {turno}", mode="lines+markers",
                line=dict(color=cor, width=2), marker=dict(size=8, line=dict(color=SUPERFICIE, width=2)),
                customdata=dados[["disponibilidade", "performance", "qualidade"]],
                hovertemplate=(
                    f"<b>Turno {turno}</b> · %{{x|%d/%m}}<br>OEE %{{y:.1%}}<br>"
                    "Disp. %{customdata[0]:.1%} · Perf. %{customdata[1]:.1%} · Qual. %{customdata[2]:.1%}"
                    "<extra></extra>"
                ),
            )
        )
        ultimo = dados.iloc[-1]
        fig.add_annotation(
            x=ultimo["data"], y=ultimo["oee"], text=f"{turno}", showarrow=False,
            xanchor="left", xshift=8, font=dict(color=TINTA_SECUNDARIA),
        )
    fig.add_hline(
        y=meta, line=dict(color=TINTA_FRACA, width=1),
        annotation_text=f"Classe mundial ({meta:.0%})", annotation_position="top left",
        annotation_font=dict(color=TINTA_FRACA, size=12),
    )
    _layout_base(fig, "OEE")
    fig.update_yaxes(tickformat=".0%", range=[0.4, 1.0])
    fig.update_xaxes(tickformat="%d/%m")
    fig.update_layout(hovermode="closest")
    return fig


def grafico_comparacao(atual: ResultadoOEE, simulado: ResultadoOEE) -> go.Figure:
    """Componentes do OEE hoje (cinza) vs. no cenário simulado (azul)."""
    nomes = ["Disponibilidade", "Performance", "Qualidade", "OEE"]
    atributos = ["disponibilidade", "performance", "qualidade", "oee"]
    fig = go.Figure()
    for resultado, nome, cor in [(atual, "Hoje", CINZA), (simulado, "Cenário simulado", AZUL)]:
        valores = [getattr(resultado, a) for a in atributos]
        fig.add_trace(
            go.Bar(
                x=nomes, y=valores, name=nome, marker_color=cor,
                # Rótulo só na barra do OEE, que é o número que importa
                # texttemplate (e não f-string) para respeitar o separador decimal brasileiro
                text=["", "", "", "oee"], texttemplate=["", "", "", "%{y:.1%}"], textposition="outside",
                textfont=dict(color=TINTA_SECUNDARIA),
                hovertemplate=f"<b>%{{x}}</b><br>{nome}: %{{y:.1%}}<extra></extra>",
            )
        )
    _layout_base(fig, "", altura=360)
    fig.update_layout(barmode="group", bargroupgap=0.08)
    fig.update_yaxes(tickformat=".0%", range=[0, 1.1])
    return fig


# ---------------------------------------------------------------------------
# Pareto
# ---------------------------------------------------------------------------
def grafico_pareto(tabela: pd.DataFrame, coluna: str, unidade: str) -> go.Figure:
    """
    Barras = % de cada causa; linha = % acumulado. Os dois em %, num ÚNICO eixo.
    Classe A em azul (onde agir primeiro), classes B e C em cinza.
    """
    tabela = tabela.assign(**{coluna: tabela[coluna].map(_quebrar)})  # rótulos longos em 2 linhas
    eh_a = tabela["classe"] == "A"
    fig = go.Figure()
    for mascara, nome, cor in [(eh_a, "Classe A (prioridade)", AZUL), (~eh_a, "Classes B e C", CINZA)]:
        dados = tabela[mascara]
        if dados.empty:
            continue
        fig.add_trace(
            go.Bar(
                x=dados[coluna], y=dados["percentual"], name=nome, marker_color=cor,
                customdata=dados[["valor", "classe"]],
                hovertemplate=(
                    "<b>%{x}</b><br>%{customdata[0]:,.0f} " + unidade
                    + " · %{y:.1f}% do total<br>Classe %{customdata[1]}<extra></extra>"
                ),
            )
        )
    fig.add_trace(
        go.Scatter(
            x=tabela[coluna], y=tabela["percentual_acumulado"], name="% acumulado",
            mode="lines+markers", line=dict(color=LARANJA, width=2),
            marker=dict(size=8, line=dict(color=SUPERFICIE, width=2)),
            hovertemplate="<b>%{x}</b><br>Acumulado: %{y:.1f}%<extra></extra>",
        )
    )
    fig.add_hline(
        y=80, line=dict(color=TINTA_FRACA, width=1),
        annotation_text="80%", annotation_position="right", annotation_font=dict(color=TINTA_FRACA),
    )
    _layout_base(fig, "% do total", altura=420)
    fig.update_yaxes(range=[0, 105], ticksuffix="%")
    fig.update_xaxes(categoryorder="array", categoryarray=list(tabela[coluna]))
    fig.update_layout(barmode="overlay")
    return fig


# ---------------------------------------------------------------------------
# Yamazumi
# ---------------------------------------------------------------------------
def grafico_yamazumi(tabela: pd.DataFrame, takt_s: float, posto_gargalo: str) -> go.Figure:
    """Tempo de cada posto empilhado por tipo de atividade, com a linha do takt."""
    tipos = [c for c in tabela.columns if c not in ("posto", "nome_posto", "total_s")]
    rotulos = tabela["posto"] + "<br>" + tabela["nome_posto"].str.replace(" ", "<br>", n=1)
    fig = go.Figure()
    for i, tipo in enumerate(tipos):
        cor = CORES_TIPO.get(tipo, [AZUL, VERDE_AGUA, LARANJA][i % 3])
        fig.add_trace(
            go.Bar(
                x=rotulos, y=tabela[tipo], name=tipo, marker=dict(color=cor, line=dict(color=SUPERFICIE, width=2)),
                hovertemplate=f"<b>%{{x}}</b><br>{tipo}: %{{y:.0f}} s<extra></extra>",
            )
        )
    # Total acima de cada barra; o gargalo ganha destaque no texto (não só na cor)
    for rotulo, posto, total in zip(rotulos, tabela["posto"], tabela["total_s"]):
        eh_gargalo = posto == posto_gargalo
        fig.add_annotation(
            x=rotulo, y=total, text=f"<b>{total:.0f} s · gargalo</b>" if eh_gargalo else f"{total:.0f} s",
            showarrow=False, yshift=12, font=dict(color=TINTA if eh_gargalo else TINTA_SECUNDARIA, size=12),
        )
    fig.add_hline(
        y=takt_s, line=dict(color=TINTA, width=2),
        annotation_text=f"Takt {takt_s:.1f} s".replace(".", ","), annotation_position="top right",
        annotation_font=dict(color=TINTA, size=12),
    )
    _layout_base(fig, "segundos por peça", altura=460)
    fig.update_layout(barmode="stack", legend_traceorder="normal")
    fig.update_yaxes(range=[0, max(tabela["total_s"].max(), takt_s) * 1.18])
    return fig
