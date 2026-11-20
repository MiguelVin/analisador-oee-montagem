"""
Mapeamento de colunas ("de-para"): adapta a planilha de QUALQUER empresa ao formato padrão.

Cada empresa exporta os dados do seu jeito: "Qtd Retrab.", "Rework", "Tempo de parada (min)"...
Em vez de exigir que a planilha seja refeita, o sistema:
  1. sugere automaticamente qual aba/coluna corresponde a cada campo padrão
     (nome exato -> sinônimos conhecidos -> nome parecido)
  2. deixa o usuário confirmar ou corrigir na tela
  3. permite salvar o mapeamento em JSON para reutilizar no mês seguinte
"""

from __future__ import annotations

import difflib
import json
from dataclasses import dataclass, field

import pandas as pd

from src.leitor import ABAS_OPCIONAIS, COLUNAS_OPCIONAIS, ESQUEMA, normalizar_texto

SIMILARIDADE_MINIMA = 0.75

ROTULOS_ABAS = {
    "producao": "Produção (um registro por turno)",
    "paradas": "Paradas (um registro por evento)",
    "postos": "Estudo de tempos dos postos",
    "linhas": "Parâmetros das linhas (opcional)",
}

ROTULOS_CAMPOS = {
    "data": "Data",
    "turno": "Turno",
    "linha": "Linha de produção",
    "modelo": "Modelo / produto",
    "tempo_planejado_min": "Tempo planejado (min)",
    "ciclo_ideal_s": "Ciclo ideal (s/peça)",
    "pecas_produzidas": "Peças produzidas",
    "pecas_refugo": "Peças refugadas",
    "pecas_retrabalho": "Peças retrabalhadas",
    "posto": "Posto / estação",
    "motivo": "Motivo da parada",
    "categoria": "Categoria (6M)",
    "duracao_min": "Duração da parada (min)",
    "nome_posto": "Nome do posto",
    "operacao": "Operação",
    "tempo_s": "Tempo da operação (s)",
    "tipo": "Tipo de atividade (AV/NAV/desperdício)",
    "demanda_diaria": "Demanda diária (peças)",
    "tempo_disponivel_min": "Tempo disponível por dia (min)",
}

# Nomes alternativos comuns no chão de fábrica (já normalizados: minúsculo, sem acento, com _)
SINONIMOS_CAMPOS = {
    "data": ["dia", "date", "data_producao", "data_apontamento", "data_da_parada"],
    "turno": ["shift", "periodo", "turma"],
    "linha": ["line", "linha_de_producao", "linha_producao", "celula", "cell", "area"],
    "modelo": ["produto", "item", "sku", "part_number", "codigo_produto", "model", "referencia"],
    "tempo_planejado_min": [
        "tempo_planejado", "tempo_programado", "tempo_programado_min", "planned_time",
        "minutos_planejados", "tempo_disponivel_turno",
    ],
    "ciclo_ideal_s": [
        "ciclo_ideal", "tempo_de_ciclo", "tempo_ciclo", "ciclo_padrao", "tempo_padrao",
        "cycle_time", "ideal_cycle_time", "ciclo_s",
    ],
    "pecas_produzidas": [
        "qtd_produzida", "quantidade_produzida", "producao", "total_produzido", "pecas",
        "qtd_total", "produzido", "output", "pecas_totais",
    ],
    "pecas_refugo": ["refugo", "sucata", "scrap", "qtd_refugo", "rejeitadas", "pecas_rejeitadas"],
    "pecas_retrabalho": ["retrabalho", "rework", "qtd_retrabalho", "qtd_retrab", "retrab"],
    "posto": ["estacao", "station", "workstation", "maquina", "equipamento", "posto_de_trabalho"],
    "motivo": ["causa", "motivo_parada", "motivo_da_parada", "reason", "descricao_parada"],
    "categoria": ["grupo", "categoria_6m", "6m", "tipo_parada", "classe_parada"],
    "duracao_min": [
        "duracao", "tempo_parada", "tempo_de_parada", "tempo_parado", "minutos", "downtime",
        "duracao_minutos", "tempo_parada_min",
    ],
    "nome_posto": ["descricao_posto", "nome_estacao", "nome_da_estacao", "descricao_estacao"],
    "operacao": ["atividade", "elemento", "tarefa", "descricao_operacao", "elemento_de_trabalho"],
    "tempo_s": ["tempo", "tempo_segundos", "tempo_operacao", "tempo_cronometrado", "duracao_s"],
    "tipo": ["classificacao", "tipo_atividade", "tipo_de_atividade", "valor_agregado"],
    "demanda_diaria": ["demanda", "demanda_dia", "pedido_diario", "demanda_cliente"],
    "tempo_disponivel_min": ["tempo_disponivel", "tempo_disponivel_dia", "minutos_disponiveis"],
}

SINONIMOS_ABAS = {
    "producao": ["apontamentos", "apontamento", "producao_diaria", "production", "dados_producao"],
    "paradas": ["paradas_de_linha", "paradas_linha", "downtime", "eventos", "ocorrencias"],
    "postos": ["estudo_de_tempos", "cronoanalise", "balanceamento", "tempos", "operacoes"],
    "linhas": ["parametros", "configuracao", "demanda", "demandas"],
}


def campos_da_aba(aba: str) -> dict[str, bool]:
    """{campo: obrigatório?} na ordem de exibição."""
    if aba in ESQUEMA:
        campos = {c: True for c in ESQUEMA[aba]}
        campos.update({c: False for c in COLUNAS_OPCIONAIS.get(aba, {})})
        return campos
    return {c: True for c in ABAS_OPCIONAIS[aba]}


TODAS_AS_ABAS = [*ESQUEMA, *ABAS_OPCIONAIS]


@dataclass
class Mapeamento:
    # aba padrão -> nome da aba no arquivo do usuário (None = não usar)
    abas: dict[str, str | None] = field(default_factory=dict)
    # aba padrão -> {campo padrão -> coluna do usuário (None = não mapeado)}
    colunas: dict[str, dict[str, str | None]] = field(default_factory=dict)

    def pendencias(self) -> list[str]:
        """O que falta mapear para o cálculo poder rodar."""
        faltas = []
        for aba in TODAS_AS_ABAS:
            obrigatoria = aba in ESQUEMA
            if not self.abas.get(aba):
                if obrigatoria:
                    faltas.append(f"Escolha a aba de {ROTULOS_ABAS[aba].split(' (')[0].lower()}.")
                continue
            for campo, campo_obrigatorio in campos_da_aba(aba).items():
                if campo_obrigatorio and not self.colunas.get(aba, {}).get(campo):
                    faltas.append(f"{ROTULOS_ABAS[aba].split(' (')[0]}: falta a coluna '{ROTULOS_CAMPOS[campo]}'.")
        return faltas

    @property
    def completo(self) -> bool:
        return not self.pendencias()

    def para_json(self) -> str:
        return json.dumps({"abas": self.abas, "colunas": self.colunas}, ensure_ascii=False, indent=2)

    @classmethod
    def de_json(cls, texto: str) -> Mapeamento:
        dados = json.loads(texto)
        return cls(abas=dict(dados.get("abas", {})), colunas={k: dict(v) for k, v in dados.get("colunas", {}).items()})


def _melhor_correspondencia(alvo: str, sinonimos: list[str], candidatos: list[str]) -> str | None:
    """Procura `alvo` entre os candidatos: nome exato, depois sinônimos, depois nome parecido."""
    por_normalizado = {normalizar_texto(c): c for c in candidatos}
    for nome in [alvo, *sinonimos]:
        if nome in por_normalizado:
            return por_normalizado[nome]
    parecidos = difflib.get_close_matches(alvo, list(por_normalizado), n=1, cutoff=SIMILARIDADE_MINIMA)
    return por_normalizado[parecidos[0]] if parecidos else None


def sugerir_mapeamento(tabelas: dict[str, pd.DataFrame]) -> Mapeamento:
    mapeamento = Mapeamento()
    abas_livres = list(tabelas)
    for aba in TODAS_AS_ABAS:
        escolhida = _melhor_correspondencia(aba, SINONIMOS_ABAS.get(aba, []), abas_livres)
        mapeamento.abas[aba] = escolhida
        mapeamento.colunas[aba] = {}
        if escolhida is None:
            continue
        abas_livres.remove(escolhida)
        colunas_livres = [str(c) for c in tabelas[escolhida].columns]
        for campo in campos_da_aba(aba):
            coluna = _melhor_correspondencia(campo, SINONIMOS_CAMPOS.get(campo, []), colunas_livres)
            mapeamento.colunas[aba][campo] = coluna
            if coluna is not None:
                colunas_livres.remove(coluna)  # cada coluna só pode ser usada uma vez
    return mapeamento


def ajustar_ao_arquivo(mapeamento: Mapeamento, tabelas: dict[str, pd.DataFrame]) -> Mapeamento:
    """Descarta do mapeamento (ex.: carregado de JSON) as abas/colunas que não existem no arquivo atual."""
    ajustado = Mapeamento()
    for aba in TODAS_AS_ABAS:
        nome = mapeamento.abas.get(aba)
        ajustado.abas[aba] = nome if nome in tabelas else None
        colunas = [str(c) for c in tabelas[nome].columns] if ajustado.abas[aba] else []
        ajustado.colunas[aba] = {
            campo: (col if col in colunas else None)
            for campo, col in mapeamento.colunas.get(aba, {}).items()
        }
    return ajustado


def aplicar_mapeamento(tabelas: dict[str, pd.DataFrame], mapeamento: Mapeamento) -> dict[str, pd.DataFrame]:
    """Devolve as abas com os nomes padrão, prontas para `leitor.validar`."""
    resultado = {}
    for aba, nome in mapeamento.abas.items():
        if not nome:
            continue
        df = tabelas[nome]
        df = df.set_axis([str(c) for c in df.columns], axis=1)
        pares = {col: campo for campo, col in mapeamento.colunas.get(aba, {}).items() if col}
        resultado[aba] = df[list(pares)].rename(columns=pares)
    return resultado
