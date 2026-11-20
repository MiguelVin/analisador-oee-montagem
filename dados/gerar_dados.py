"""
Gerador de dados fictícios de uma fábrica com duas linhas de montagem.

Cria uma planilha com 4 abas:
  - producao: um registro por dia/turno/linha com tempo planejado e peças produzidas
  - paradas:  cada evento de parada com posto, motivo, categoria (6M) e duração
  - postos:   estudo de tempos de cada operação, por linha, posto e modelo (base do Yamazumi)
  - linhas:   parâmetros de cada linha (demanda diária e tempo disponível, para o takt)

As linhas têm perfis opostos, para o painel ter o que comparar:
  - Linha A (motores elétricos): o posto P04 é o gargalo e, no modelo X200, passa do takt;
    sofre com falta de peça e quebra de parafusadeira; troca de modelo gera setup
  - Linha B (controles eletrônicos): bem balanceada, atende a demanda, OEE mais alto

Padrões comuns às duas linhas:
  - poucas causas concentram a maior parte do tempo parado (princípio de Pareto)
  - há uma "crise de fornecedor" no meio do mês (mais paradas por falta de peça)
  - o 2º turno tem performance e qualidade um pouco piores

Os dados são 100% fictícios.

Uso:
    py dados/gerar_dados.py
    py dados/gerar_dados.py --inicio 2026-09-01 --fim 2026-09-30 --semente 7
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

TURNOS = ["T1", "T2"]
TEMPO_PLANEJADO_MIN = 480  # 8h de turno já descontadas as pausas programadas

AV = "Agrega valor"
NAV = "Não agrega valor necessário"
DESP = "Desperdício"

Operacoes = dict[tuple[str, str], list[tuple[str, int, str]]]

# ---------------------------------------------------------------------------
# Linha A — montagem de motores elétricos (estudo de tempos em segundos por peça)
# ---------------------------------------------------------------------------
OPERACOES_X100: Operacoes = {
    ("P01", "Montagem da base"): [
        ("Pegar base no rack", 6, NAV),
        ("Posicionar base no dispositivo", 9, AV),
        ("Fixar suportes laterais", 15, AV),
        ("Conferir código da base", 5, NAV),
        ("Ajustar posição do rack", 3, DESP),
    ],
    ("P02", "Fixação do motor"): [
        ("Pegar motor no carrinho", 7, NAV),
        ("Encaixar motor na base", 14, AV),
        ("Fixar motor (4 parafusos)", 18, AV),
        ("Aplicar marcação de torque", 4, NAV),
        ("Deslocamento até o carrinho", 3, DESP),
    ],
    ("P03", "Montagem do chicote elétrico"): [
        ("Separar chicote", 6, NAV),
        ("Conectar chicote ao motor", 16, AV),
        ("Fixar abraçadeiras", 14, AV),
        ("Organizar cabos", 8, AV),
        ("Desembaraçar chicote", 5, DESP),
    ],
    ("P04", "Parafusamento da carcaça"): [
        ("Posicionar carcaça", 10, AV),
        ("Parafusar carcaça", 24, AV),
        ("Buscar parafusos no supermercado", 6, DESP),
        ("Trocar bit da parafusadeira", 4, DESP),
        ("Conferir torque no display", 8, NAV),
    ],
    ("P05", "Teste elétrico"): [
        ("Conectar plugue de teste", 6, NAV),
        ("Executar teste de isolação", 20, AV),
        ("Executar teste funcional", 12, AV),
        ("Registrar resultado", 6, NAV),
    ],
    ("P06", "Montagem da tampa"): [
        ("Pegar tampa", 5, NAV),
        ("Encaixar tampa", 12, AV),
        ("Fixar tampa", 16, AV),
        ("Limpar peça", 4, NAV),
        ("Aguardar peça do P05", 3, DESP),
    ],
    ("P07", "Inspeção final"): [
        ("Inspeção visual", 16, NAV),
        ("Verificar acabamento", 10, NAV),
        ("Aplicar etiqueta de aprovação", 6, NAV),
        ("Registrar no sistema", 4, NAV),
    ],
    ("P08", "Embalagem"): [
        ("Montar caixa", 10, NAV),
        ("Embalar produto", 14, AV),
        ("Fechar e etiquetar caixa", 9, NAV),
    ],
}


def _derivar(base: Operacoes, ajustes: dict[str, int], extras: dict[str, list]) -> Operacoes:
    """Cria a variante de um modelo: muda tempos de algumas operações e acrescenta outras."""
    return {
        (posto, nome): [(op, ajustes.get(op, t), tipo) for op, t, tipo in ops] + extras.get(posto, [])
        for (posto, nome), ops in base.items()
    }


# O X200 é um modelo maior: algumas operações demoram mais e o P04 ganha uma operação extra
OPERACOES_X200 = _derivar(
    OPERACOES_X100,
    ajustes={
        "Fixar motor (4 parafusos)": 20,
        "Conectar chicote ao motor": 20,
        "Parafusar carcaça": 30,
        "Fixar tampa": 18,
    },
    extras={"P04": [("Parafusar reforço lateral", 3, AV)]},
)

# ---------------------------------------------------------------------------
# Linha B — montagem de controles eletrônicos
# ---------------------------------------------------------------------------
OPERACOES_C300: Operacoes = {
    ("P01", "Preparação da placa"): [
        ("Pegar placa", 4, NAV),
        ("Inserir componentes", 18, AV),
        ("Conferir polaridade", 6, NAV),
        ("Buscar componentes", 3, DESP),
    ],
    ("P02", "Solda seletiva"): [
        ("Posicionar no dispositivo", 6, NAV),
        ("Soldar componentes", 24, AV),
        ("Aguardar resfriamento", 8, DESP),
    ],
    ("P03", "Montagem no gabinete"): [
        ("Encaixar placa", 12, AV),
        ("Parafusar gabinete", 16, AV),
        ("Conectar display", 10, AV),
        ("Ajustar dispositivo", 4, DESP),
    ],
    ("P04", "Teste funcional"): [
        ("Conectar ao testador", 5, NAV),
        ("Executar teste", 22, AV),
        ("Registrar resultado", 6, NAV),
    ],
    ("P05", "Inspeção e etiquetagem"): [
        ("Inspeção visual", 14, NAV),
        ("Etiquetar", 8, NAV),
        ("Registrar no sistema", 5, NAV),
    ],
    ("P06", "Embalagem"): [
        ("Montar caixa", 8, NAV),
        ("Embalar produto", 16, AV),
        ("Fechar caixa", 9, NAV),
    ],
}

# Catálogo de paradas: (motivo, categoria 6M, postos possíveis, eventos/turno, duração min/moda/máx)
LINHAS = {
    "Linha A": {
        "modelos": {"X100": OPERACOES_X100, "X200": OPERACOES_X200},
        "prob_troca_modelo": 0.30,
        "demanda_diaria": 1000,
        "ritmo": {"T1": (0.86, 0.95), "T2": (0.82, 0.92)},
        "refugo": {"X100": 0.012, "X200": 0.018},
        "retrabalho": {"T1": 0.022, "T2": 0.035},
        "paradas": [
            ("Falta de peça", "Material", ["P03", "P02", "P01"], 1.1, (8, 18, 45)),
            ("Quebra de parafusadeira", "Máquina", ["P04"], 0.8, (5, 12, 30)),
            ("Falha no equipamento de teste", "Máquina", ["P05"], 0.4, (5, 10, 25)),
            ("Aguardando liberação da qualidade", "Qualidade", ["P07"], 0.3, (8, 12, 25)),
            ("Retrabalho no posto", "Qualidade", ["P04", "P06", "P03"], 0.35, (4, 7, 15)),
            ("Falta de operador", "Mão de obra", ["P02", "P06", "P08"], 0.15, (15, 25, 60)),
            ("Falta de embalagem", "Material", ["P08"], 0.15, (5, 10, 20)),
        ],
    },
    "Linha B": {
        "modelos": {"C300": OPERACOES_C300},
        "prob_troca_modelo": 0.0,
        "demanda_diaria": 1300,
        "ritmo": {"T1": (0.89, 0.96), "T2": (0.86, 0.94)},
        "refugo": {"C300": 0.008},
        "retrabalho": {"T1": 0.015, "T2": 0.024},
        "paradas": [
            ("Falha na estação de solda", "Máquina", ["P02"], 0.6, (8, 15, 35)),
            ("Falta de peça", "Material", ["P01", "P03"], 0.45, (6, 12, 30)),
            ("Ajuste de dispositivo", "Método", ["P03"], 0.4, (4, 8, 15)),
            ("Falha no equipamento de teste", "Máquina", ["P04"], 0.3, (5, 10, 20)),
            ("Aguardando liberação da qualidade", "Qualidade", ["P05"], 0.2, (8, 12, 20)),
            ("Falta de operador", "Mão de obra", ["P02", "P06"], 0.1, (15, 25, 45)),
        ],
    },
}
SETUP = ("Troca de modelo (setup)", "Método", "Linha", (18, 25, 40))

# Período de crise de fornecedor: falta de peça fica 3x mais frequente
CRISE_FORNECEDOR = (pd.Timestamp("2026-10-13"), pd.Timestamp("2026-10-16"))


def montar_postos() -> pd.DataFrame:
    """Tabela de estudo de tempos (uma linha por operação, por linha de produção e modelo)."""
    registros = [
        (linha, modelo, posto, nome, operacao, tempo, tipo)
        for linha, config in LINHAS.items()
        for modelo, operacoes in config["modelos"].items()
        for (posto, nome), lista in operacoes.items()
        for operacao, tempo, tipo in lista
    ]
    colunas = ["linha", "modelo", "posto", "nome_posto", "operacao", "tempo_s", "tipo"]
    return pd.DataFrame(registros, columns=colunas)


def ciclo_ideal(postos: pd.DataFrame) -> dict[tuple[str, str], int]:
    """Ciclo ideal de cada (linha, modelo) = tempo do posto mais lento (o gargalo dita o ritmo)."""
    por_posto = postos.groupby(["linha", "modelo", "posto"])["tempo_s"].sum()
    return por_posto.groupby(["linha", "modelo"]).max().to_dict()


def gerar(inicio: str, fim: str, semente: int) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(semente)
    postos = montar_postos()
    ciclos = ciclo_ideal(postos)
    dias = pd.bdate_range(inicio, fim)  # apenas dias úteis
    producao, paradas = [], []

    for linha, cfg in LINHAS.items():
        modelos = list(cfg["modelos"])
        modelo_atual = modelos[0]

        for dia in dias:
            em_crise = CRISE_FORNECEDOR[0] <= dia <= CRISE_FORNECEDOR[1]

            for turno in TURNOS:
                eventos = []

                # Programação: troca de modelo no início do turno -> parada de setup
                if len(modelos) > 1 and rng.random() < cfg["prob_troca_modelo"]:
                    modelo_atual = modelos[(modelos.index(modelo_atual) + 1) % len(modelos)]
                    motivo, categoria, posto, (a, m, b) = SETUP
                    eventos.append((posto, motivo, categoria, round(rng.triangular(a, m, b))))

                for motivo, categoria, postos_possiveis, taxa, (a, m, b) in cfg["paradas"]:
                    if motivo == "Falta de peça" and em_crise:
                        taxa *= 3
                    for _ in range(rng.poisson(taxa)):
                        posto = rng.choice(postos_possiveis)
                        eventos.append((posto, motivo, categoria, round(rng.triangular(a, m, b))))

                # Limite de segurança: paradas não passam de 50% do tempo planejado
                total, aceitos = 0, []
                for evento in eventos:
                    if total + evento[3] > TEMPO_PLANEJADO_MIN * 0.5:
                        break
                    aceitos.append(evento)
                    total += evento[3]

                for posto, motivo, categoria, duracao in aceitos:
                    paradas.append(
                        (dia.date(), turno, linha, modelo_atual, posto, motivo, categoria, duracao)
                    )

                # Performance: perdas de velocidade e microparadas não apontadas
                ciclo = ciclos[(linha, modelo_atual)]
                tempo_operando_s = (TEMPO_PLANEJADO_MIN - total) * 60
                pecas = int(tempo_operando_s / ciclo * rng.uniform(*cfg["ritmo"][turno]))

                # Qualidade: refugo e retrabalho
                refugo = int(rng.binomial(pecas, cfg["refugo"][modelo_atual]))
                retrabalho = int(rng.binomial(pecas - refugo, cfg["retrabalho"][turno]))

                producao.append(
                    (dia.date(), turno, linha, modelo_atual, TEMPO_PLANEJADO_MIN,
                     ciclo, pecas, refugo, retrabalho)
                )

    df_producao = pd.DataFrame(
        producao,
        columns=[
            "data", "turno", "linha", "modelo", "tempo_planejado_min",
            "ciclo_ideal_s", "pecas_produzidas", "pecas_refugo", "pecas_retrabalho",
        ],
    )
    df_paradas = pd.DataFrame(
        paradas,
        columns=["data", "turno", "linha", "modelo", "posto", "motivo", "categoria", "duracao_min"],
    )
    df_linhas = pd.DataFrame(
        [(linha, cfg["demanda_diaria"], TEMPO_PLANEJADO_MIN * len(TURNOS)) for linha, cfg in LINHAS.items()],
        columns=["linha", "demanda_diaria", "tempo_disponivel_min"],
    )
    return {"producao": df_producao, "paradas": df_paradas, "postos": postos, "linhas": df_linhas}


def salvar_excel(tabelas: dict[str, pd.DataFrame], caminho: Path) -> None:
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with pd.ExcelWriter(caminho, engine="openpyxl") as writer:
        for aba, df in tabelas.items():
            df.to_excel(writer, sheet_name=aba, index=False)
            # Ajusta a largura das colunas para a planilha abrir legível
            planilha = writer.sheets[aba]
            for i, coluna in enumerate(df.columns, start=1):
                largura = max(len(str(coluna)), *(len(str(v)) for v in df[coluna].head(200)))
                planilha.column_dimensions[planilha.cell(1, i).column_letter].width = largura + 2


def main() -> None:
    parser = argparse.ArgumentParser(description="Gera dados fictícios de linhas de montagem.")
    parser.add_argument("--inicio", default="2026-10-01")
    parser.add_argument("--fim", default="2026-10-31")
    parser.add_argument("--semente", type=int, default=42, help="mesma semente = mesmos dados")
    parser.add_argument(
        "--saida", type=Path, default=Path(__file__).parent / "exemplo_montagem.xlsx"
    )
    args = parser.parse_args()

    tabelas = gerar(args.inicio, args.fim, args.semente)
    salvar_excel(tabelas, args.saida)

    print(f"Planilha gerada: {args.saida}")
    for aba, df in tabelas.items():
        print(f"  {aba:<9} {len(df):>4} linhas")


if __name__ == "__main__":
    main()
