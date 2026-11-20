"""
Painel web do Analisador de OEE e Gargalos.

Rodar:
    .\\.venv\\Scripts\\python.exe -m streamlit run app.py
"""

from __future__ import annotations

import hashlib
import io
from pathlib import Path

import pandas as pd
import streamlit as st

from src.diagnostico import gerar_diagnostico
from src.gargalo import TIPO_DESPERDICIO, analisar_gargalo, yamazumi
from src.graficos import (
    grafico_cascata, grafico_comparacao, grafico_oee_diario, grafico_pareto, grafico_yamazumi,
)
from src.indicadores import calcular_oee, consolidar, oee_por, takt_time_s
from src.leitor import ErroPlanilha, carregar_excel, normalizar_texto, validar
from src.mapeamento import (
    ROTULOS_ABAS, ROTULOS_CAMPOS, TODAS_AS_ABAS, Mapeamento, ajustar_ao_arquivo,
    aplicar_mapeamento, campos_da_aba, sugerir_mapeamento,
)
from src.pareto import pareto
from src.relatorio import gerar_relatorio_excel
from src.simulador import Cenario, simular

EXEMPLO = Path(__file__).parent / "dados" / "exemplo_montagem.xlsx"
ICONE_CLASSE = {"Classe mundial": "🟢", "Bom": "🟢", "Regular": "🟡", "Crítico": "🔴"}
CAIXA_PRIORIDADE = {"alta": st.error, "media": st.warning, "info": st.info}
ICONE_PRIORIDADE = {"alta": "🚨", "media": "⚠️", "info": "ℹ️"}
NAO_USAR = "— não usar —"

st.set_page_config(page_title="Analisador de OEE · Montagem", page_icon="🏭", layout="wide")


def pct(valor: float) -> str:
    return f"{valor:.1%}".replace(".", ",")


def num(valor: float, casas: int = 0) -> str:
    return f"{valor:,.{casas}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def metrica(coluna, rotulo: str, valor: str, detalhe: str) -> None:
    coluna.metric(rotulo, valor, detalhe, delta_color="off", delta_arrow="off", border=True)


@st.cache_data(show_spinner="Lendo a planilha…")
def ler_abas(conteudo: bytes) -> dict[str, pd.DataFrame]:
    return carregar_excel(io.BytesIO(conteudo))


def tela_mapeamento(brutas: dict[str, pd.DataFrame], sugestao: Mapeamento, chave: str) -> Mapeamento:
    """Mostra o de-para de abas e colunas. Já vem preenchido com a sugestão automática."""
    escolhido = Mapeamento()
    with st.expander("🔗 Mapeamento de colunas", expanded=not sugestao.completo):
        st.caption(
            "Indique onde está cada informação na **sua** planilha. O sistema já sugere pelo nome "
            "das colunas; confira, corrija o que for preciso e salve o mapeamento para os próximos meses."
        )
        nomes_abas = list(brutas)
        for aba in TODAS_AS_ABAS:
            st.markdown(f"**{ROTULOS_ABAS[aba]}**")
            sugerida = sugestao.abas.get(aba)
            opcoes = [None, *nomes_abas]
            aba_usuario = st.selectbox(
                "Aba da planilha", opcoes, index=opcoes.index(sugerida) if sugerida in opcoes else 0,
                key=f"{chave}_aba_{aba}", format_func=lambda x: NAO_USAR if x is None else x,
            )
            escolhido.abas[aba] = aba_usuario
            escolhido.colunas[aba] = {}
            if aba_usuario is None:
                continue
            colunas = [None, *map(str, brutas[aba_usuario].columns)]
            grade = st.columns(3)
            for i, (campo, obrigatorio) in enumerate(campos_da_aba(aba).items()):
                sugerida_col = sugestao.colunas.get(aba, {}).get(campo) if sugerida == aba_usuario else None
                escolhido.colunas[aba][campo] = grade[i % 3].selectbox(
                    ROTULOS_CAMPOS[campo] + ("" if obrigatorio else " (opcional)"),
                    colunas, index=colunas.index(sugerida_col) if sugerida_col in colunas else 0,
                    key=f"{chave}_{aba}_{aba_usuario}_{campo}",
                    format_func=lambda x: NAO_USAR if x is None else x,
                )
        st.download_button(
            "💾 Salvar este mapeamento (.json)", escolhido.para_json(),
            file_name="mapeamento_colunas.json", mime="application/json",
        )
    return escolhido


# ---------------------------------------------------------------------------
# Barra lateral: dados
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("1. Dados")
    arquivo = st.file_uploader("Planilha de apontamentos (.xlsx)", type=["xlsx"])
    arquivo_mapa = st.file_uploader(
        "Mapeamento salvo (.json, opcional)", type=["json"],
        help="Se a sua planilha usa nomes de colunas próprios, carregue aqui o mapeamento salvo antes.",
    )
    st.download_button(
        "Baixar planilha modelo", EXEMPLO.read_bytes(), file_name="modelo_apontamentos_montagem.xlsx",
        help="Formato padrão: abas producao, paradas, postos e linhas (opcional).", width="stretch",
    )

conteudo = arquivo.getvalue() if arquivo else EXEMPLO.read_bytes()
origem = arquivo.name if arquivo else "dados de exemplo (fictícios)"
texto_mapa = arquivo_mapa.getvalue().decode("utf-8") if arquivo_mapa else ""

st.title("Analisador de OEE e Gargalos")

try:
    brutas = ler_abas(conteudo)
except Exception as erro:  # arquivo corrompido, formato inesperado...
    st.error(f"Não foi possível ler o arquivo: {erro}")
    st.stop()

try:
    sugestao = ajustar_ao_arquivo(Mapeamento.de_json(texto_mapa), brutas) if texto_mapa else sugerir_mapeamento(brutas)
except ValueError:
    st.error("O arquivo de mapeamento (.json) é inválido.")
    st.stop()

chave = hashlib.md5(conteudo + texto_mapa.encode()).hexdigest()[:10]
mapeamento = tela_mapeamento(brutas, sugestao, chave)
if not mapeamento.completo:
    st.warning("**Complete o mapeamento de colunas para calcular:**\n\n" + "\n".join(f"- {p}" for p in mapeamento.pendencias()))
    st.stop()

try:
    dados = validar(aplicar_mapeamento(brutas, mapeamento))
except ErroPlanilha as erro:
    st.error("**A planilha tem problemas que impedem o cálculo:**\n\n" + "\n".join(f"- {e}" for e in erro.erros))
    st.stop()

# ---------------------------------------------------------------------------
# Barra lateral: linha, filtros e demanda
# ---------------------------------------------------------------------------
with st.sidebar:
    todas_linhas = sorted(dados.producao["linha"].unique())
    st.header("2. Linha e filtros")
    linha = st.selectbox("Linha de produção", todas_linhas, disabled=len(todas_linhas) == 1)

    producao_linha = dados.producao[dados.producao["linha"] == linha]
    data_min, data_max = producao_linha["data"].min().date(), producao_linha["data"].max().date()
    periodo = st.date_input("Período", (data_min, data_max), min_value=data_min, max_value=data_max,
                            format="DD/MM/YYYY", key=f"periodo_{linha}")
    todos_turnos = sorted(producao_linha["turno"].unique())
    turnos = st.multiselect("Turnos", todos_turnos, default=todos_turnos, key=f"turnos_{linha}")
    todos_modelos = sorted(producao_linha["modelo"].unique())
    modelos = st.multiselect("Modelos", todos_modelos, default=todos_modelos, key=f"modelos_{linha}")

    st.header("3. Demanda")
    parametros = (
        dados.linhas.set_index("linha").loc[linha]
        if dados.linhas is not None and linha in set(dados.linhas["linha"]) else None
    )
    padrao_tempo = (
        float(parametros["tempo_disponivel_min"]) if parametros is not None
        else float(producao_linha.groupby("data")["tempo_planejado_min"].sum().median())
    )
    padrao_demanda = int(parametros["demanda_diaria"]) if parametros is not None else 1000
    tempo_disponivel = st.number_input("Tempo disponível por dia (min)", min_value=1.0, value=padrao_tempo,
                                       step=10.0, key=f"tempo_{linha}")
    demanda = st.number_input("Demanda do cliente (peças/dia)", min_value=1, value=padrao_demanda,
                              step=50, key=f"demanda_{linha}")
    if parametros is not None:
        st.caption("Valores padrão vindos da aba 'linhas' da planilha.")

# date_input devolve só a data inicial enquanto o usuário escolhe o intervalo
inicio, fim = (periodo[0], periodo[-1]) if isinstance(periodo, tuple) and periodo else (data_min, data_max)
no_periodo = dados.producao["data"].dt.date.between(inicio, fim) & dados.producao["turno"].isin(turnos)

producao = dados.producao[no_periodo & (dados.producao["linha"] == linha) & dados.producao["modelo"].isin(modelos)]
chaves_turno = ["data", "turno", "linha"]
paradas = dados.paradas.merge(producao[chaves_turno], on=chaves_turno)  # só paradas dos turnos filtrados
takt = takt_time_s(tempo_disponivel, demanda)

st.caption(
    f"Fonte: **{origem}** · **{linha}** · {inicio:%d/%m/%Y} a {fim:%d/%m/%Y} · "
    f"{len(producao)} turnos · takt {num(takt, 1)} s"
)
for aviso in dados.avisos:
    st.warning(aviso, icon="⚠️")
if producao.empty:
    st.info("Nenhum turno corresponde aos filtros selecionados.")
    st.stop()

# ---------------------------------------------------------------------------
# Cálculos
# ---------------------------------------------------------------------------
consolidado = consolidar(producao, paradas)
resultado = calcular_oee(consolidado)
por_dia_turno = oee_por(consolidado, ["data", "turno"])
por_dia = oee_por(consolidado, "data")
por_turno = oee_por(consolidado, "turno")
pareto_motivos = pareto(paradas) if not paradas.empty else pd.DataFrame()

postos_linha = dados.postos[dados.postos["linha"] == linha]
modelos_com_tempos = [m for m in sorted(postos_linha["modelo"].unique()) if m in modelos]
gargalos = [analisar_gargalo(postos_linha, m, takt) for m in modelos_com_tempos]
achados = gerar_diagnostico(resultado, consolidado, paradas, pareto_motivos, por_turno, por_dia, gargalos)

aba_diag, aba_oee, aba_pareto, aba_gargalo, aba_sim = st.tabs(
    ["🧭 Diagnóstico", "📈 OEE", "📊 Pareto de paradas", "⚙️ Gargalo e balanceamento", "🔮 Simulador"]
)

# ---------------------------------------------------------------------------
# Aba: Diagnóstico
# ---------------------------------------------------------------------------
with aba_diag:
    c1, c2, c3, c4 = st.columns(4)
    metrica(c1, "OEE", pct(resultado.oee), f"{ICONE_CLASSE[resultado.classificacao]} {resultado.classificacao}")
    metrica(c2, "Peças boas", num(resultado.pecas_boas), f"de {num(resultado.pecas_produzidas)} produzidas")
    metrica(c3, "Tempo parado", f"{num(resultado.tempo_parada_min)} min", f"{pct(resultado.tempo_parada_min / resultado.tempo_planejado_min)} do planejado")
    if gargalos:
        criticos = [g for g in gargalos if not g.atende_demanda]
        metrica(c4, "Atende a demanda?", "Não" if criticos else "Sim",
                f"{', '.join(g.modelo for g in criticos)} acima do takt" if criticos else f"takt {num(takt, 1)} s")

    st.subheader("Principais achados")
    for achado in achados:
        CAIXA_PRIORIDADE[achado.prioridade](f"**{achado.titulo}**\n\n{achado.texto}", icon=ICONE_PRIORIDADE[achado.prioridade])

    if len(todas_linhas) > 1:
        st.subheader("Comparativo entre linhas")
        st.caption("Mesmo período e turnos selecionados, todos os modelos.")
        producao_todas = dados.producao[no_periodo]
        comparativo = oee_por(
            consolidar(producao_todas, dados.paradas.merge(producao_todas[chaves_turno], on=chaves_turno)), "linha"
        )
        nomes = {"linha": "Linha", "disponibilidade": "Disponibilidade", "performance": "Performance", "qualidade": "Qualidade", "oee": "OEE"}
        st.dataframe(
            comparativo[list(nomes)].rename(columns=nomes), hide_index=True, width="stretch",
            column_config={n: st.column_config.ProgressColumn(n, format="percent", min_value=0, max_value=1) for n in list(nomes.values())[1:]},
        )

# ---------------------------------------------------------------------------
# Aba: OEE
# ---------------------------------------------------------------------------
with aba_oee:
    c1, c2, c3, c4 = st.columns(4)
    metrica(c1, "OEE", pct(resultado.oee), f"{ICONE_CLASSE[resultado.classificacao]} {resultado.classificacao}")
    metrica(c2, "Disponibilidade", pct(resultado.disponibilidade), f"{num(resultado.tempo_parada_min)} min parados")
    metrica(c3, "Performance", pct(resultado.performance), "ritmo vs. ciclo ideal")
    metrica(c4, "Qualidade", pct(resultado.qualidade), f"{num(resultado.pecas_boas)} de {num(resultado.pecas_produzidas)} peças boas")

    esquerda, direita = st.columns([2, 3])
    with esquerda:
        st.subheader("Para onde foi o tempo")
        st.plotly_chart(grafico_cascata(resultado), width="stretch", theme=None)
    with direita:
        st.subheader("OEE por dia e turno")
        st.plotly_chart(grafico_oee_diario(por_dia_turno, todos_turnos), width="stretch", theme=None)

    st.subheader("Comparativos")
    col_turno, col_modelo = st.columns(2)
    nomes = {"disponibilidade": "Disponibilidade", "performance": "Performance", "qualidade": "Qualidade", "oee": "OEE"}
    formato = {n: st.column_config.ProgressColumn(n, format="percent", min_value=0, max_value=1) for n in nomes.values()}
    for coluna_st, grupo, titulo in [(col_turno, "turno", "Turno"), (col_modelo, "modelo", "Modelo")]:
        tabela = oee_por(consolidado, grupo)[[grupo, *nomes]].rename(columns={grupo: titulo, **nomes})
        coluna_st.dataframe(tabela, hide_index=True, width="stretch", column_config=formato)

    with st.expander("Ver dados por turno"):
        st.dataframe(por_dia_turno.assign(data=por_dia_turno["data"].dt.strftime("%d/%m/%Y")).round(4),
                     hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Aba: Pareto
# ---------------------------------------------------------------------------
with aba_pareto:
    if paradas.empty:
        st.info("Nenhuma parada registrada nos turnos filtrados.")
    else:
        o1, o2 = st.columns(2)
        agrupar = o1.radio("Agrupar por", ["motivo", "categoria", "posto"], horizontal=True,
                           format_func={"motivo": "Motivo", "categoria": "Categoria (6M)", "posto": "Posto"}.get)
        medida = o2.radio("Medir por", ["duracao", "ocorrencias"], horizontal=True,
                          format_func={"duracao": "Tempo parado", "ocorrencias": "Nº de ocorrências"}.get)
        unidade = "min" if medida == "duracao" else "ocorrências"

        tabela = pareto(paradas, por=agrupar, medida=medida)
        classe_a = tabela[tabela["classe"] == "A"]
        st.markdown(
            f"**{len(classe_a)} de {len(tabela)}** itens (classe A) concentram "
            f"**{pct(classe_a['percentual'].sum() / 100)}** do {'tempo parado' if medida == 'duracao' else 'número de paradas'}: "
            + ", ".join(f"*{n}*" for n in classe_a[agrupar]) + "."
        )
        st.plotly_chart(grafico_pareto(tabela, agrupar, unidade), width="stretch", theme=None)
        with st.expander("Ver tabela do Pareto"):
            st.dataframe(
                tabela.rename(columns={agrupar: agrupar.capitalize(), "valor": unidade.capitalize(), "percentual": "%",
                                       "percentual_acumulado": "% acumulado", "classe": "Classe"}).round(1),
                hide_index=True, width="stretch",
            )

# ---------------------------------------------------------------------------
# Aba: Gargalo e balanceamento
# ---------------------------------------------------------------------------
tabela_y = None
with aba_gargalo:
    if postos_linha.empty:
        st.info(f"A planilha não tem estudo de tempos (aba 'postos') para a {linha}.")
    else:
        e1, e2 = st.columns([1, 2])
        modelo = e1.selectbox("Modelo", sorted(postos_linha["modelo"].unique()), key=f"modelo_gargalo_{linha}")
        sem_desperdicio = e2.toggle(
            "Simular eliminação do desperdício",
            help="Remove as operações classificadas como desperdício e recalcula o balanceamento.",
        )
        postos_analise = postos_linha
        if sem_desperdicio:
            postos_analise = postos_linha[postos_linha["tipo"].map(normalizar_texto) != normalizar_texto(TIPO_DESPERDICIO)]

        g = analisar_gargalo(postos_analise, modelo, takt)
        c1, c2, c3, c4 = st.columns(4)
        metrica(c1, "Takt time", f"{num(takt, 1)} s", f"{num(demanda)} peças/dia")
        metrica(c2, "Gargalo", f"{g.posto_gargalo} · {num(g.tempo_gargalo_s)} s", g.nome_posto_gargalo)
        metrica(c3, "Capacidade", f"{num(g.capacidade_pecas_hora)} peças/h", f"{num(g.capacidade_pecas_hora * tempo_disponivel / 60)} peças/dia")
        metrica(c4, "Balanceamento", pct(g.eficiencia_balanceamento), f"{g.numero_postos} postos (mín. teórico {g.postos_minimos})")

        if g.atende_demanda:
            st.success(f"A linha atende a demanda: o gargalo ({g.posto_gargalo}) está {num(-g.diferenca_takt_s, 1)} s abaixo do takt.", icon="✅")
        else:
            if sem_desperdicio:
                acao = "Mesmo sem desperdício, é preciso redistribuir operações ou adicionar recurso."
            elif g.gargalo_sem_desperdicio_s <= takt:
                acao = (f"Eliminar o desperdício do {g.posto_gargalo} ({num(g.desperdicio_gargalo_s)} s) o levaria a "
                        f"{num(g.gargalo_sem_desperdicio_s)} s, **abaixo do takt**.")
            else:
                acao = (f"Mesmo sem desperdício o {g.posto_gargalo} ficaria em {num(g.gargalo_sem_desperdicio_s)} s: "
                        "é preciso redistribuir operações ou adicionar recurso.")
            outros = [p for p in g.postos_acima_takt if p != g.posto_gargalo]
            st.error(
                f"**A linha não atende a demanda.** O gargalo {g.posto_gargalo} está {num(g.diferenca_takt_s, 1)} s acima do takt"
                + (f" (também acima: {', '.join(outros)})" if outros else "") + f". {acao}",
                icon="🚨",
            )

        st.subheader(f"Yamazumi · {linha} · modelo {modelo}" + (" · sem desperdício" if sem_desperdicio else ""))
        tabela_y = yamazumi(postos_analise, modelo)
        st.plotly_chart(grafico_yamazumi(tabela_y, takt, g.posto_gargalo), width="stretch", theme=None)
        with st.expander("Ver estudo de tempos"):
            st.dataframe(tabela_y, hide_index=True, width="stretch")
            st.dataframe(postos_analise[postos_analise["modelo"] == modelo], hide_index=True, width="stretch")

# ---------------------------------------------------------------------------
# Aba: Simulador
# ---------------------------------------------------------------------------
with aba_sim:
    st.markdown(
        "Quanto o OEE melhora se a equipe atacar causas específicas? Ajuste as metas e veja o resultado. "
        "Premissa: o tempo recuperado roda com a performance e a qualidade atuais (mais os ganhos informados)."
    )
    controles, saida = st.columns([2, 3], gap="large")
    reducoes: dict[str, float] = {}
    with controles:
        st.markdown("**Reduzir paradas** (maiores causas)")
        for _, item in pareto_motivos.head(6).iterrows():
            reducoes[item["motivo"]] = st.slider(
                f"{item['motivo']} · {num(item['valor'])} min", 0, 100, 0, step=10, format="%d%%",
                key=f"sim_{linha}_{item['motivo']}",
            ) / 100
        st.markdown("**Outras melhorias**")
        ganho_performance = st.slider("Ganho de performance (pontos percentuais)", 0, 10, 0, 1,
                                      format="%d p.p.", key=f"sim_perf_{linha}") / 100
        reducao_qualidade = st.slider("Redução de refugo e retrabalho", 0, 100, 0, step=10, format="%d%%",
                                      key=f"sim_qual_{linha}") / 100

    sim = simular(consolidado, paradas, Cenario(reducoes, ganho_performance, reducao_qualidade))
    with saida:
        dias = max(producao["data"].nunique(), 1)
        boas_por_dia = resultado.pecas_boas / dias
        c1, c2, c3 = st.columns(3)
        metrica(c1, "OEE simulado", pct(sim.simulado.oee), f"+{num(sim.ganho_oee_pp * 100, 1)} p.p. · {sim.simulado.classificacao}")
        metrica(c2, "Peças boas a mais", num(sim.pecas_boas_extras),
                f"≈ {num(sim.pecas_boas_extras / boas_por_dia, 1)} dias" if boas_por_dia else "")
        metrica(c3, "Paradas eliminadas", f"{num(sim.minutos_recuperados)} min", f"{num(sim.minutos_recuperados / 60, 1)} h no período")
        st.plotly_chart(grafico_comparacao(sim.atual, sim.simulado), width="stretch", theme=None)

# ---------------------------------------------------------------------------
# Barra lateral: relatório
# ---------------------------------------------------------------------------
with st.sidebar:
    st.header("4. Relatório")
    filtros = {
        "Fonte": origem,
        "Linha": linha,
        "Período": f"{inicio:%d/%m/%Y} a {fim:%d/%m/%Y}",
        "Turnos": ", ".join(turnos),
        "Modelos": ", ".join(modelos),
        "Demanda (peças/dia)": str(demanda),
        "Takt (s)": num(takt, 1),
    }
    st.download_button(
        "📥 Baixar relatório (.xlsx)",
        gerar_relatorio_excel(filtros, resultado, achados, por_dia, por_turno, pareto_motivos, tabela_y),
        file_name=f"relatorio_oee_{normalizar_texto(linha)}_{inicio:%Y%m%d}_{fim:%Y%m%d}.xlsx",
        type="primary", width="stretch",
    )
