"""
Leitura e validação da planilha de apontamentos.

A ideia é nunca calcular indicador em cima de dado errado: se algo está inconsistente,
o usuário recebe uma mensagem dizendo O QUE está errado e EM QUAL LINHA do Excel.

Dois níveis de problema:
  - erro  -> impede o cálculo (coluna faltando, número inválido, refugo > produção...)
  - aviso -> o cálculo roda, mas o usuário deve conferir (ex.: performance acima de 100%)

Planilhas com nomes de colunas diferentes passam antes pelo módulo `mapeamento`,
que renomeia tudo para os nomes padrão definidos aqui.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import BinaryIO

import pandas as pd

# Colunas obrigatórias de cada aba e o tipo esperado
ESQUEMA: dict[str, dict[str, str]] = {
    "producao": {
        "data": "data",
        "turno": "texto",
        "linha": "texto",
        "modelo": "texto",
        "tempo_planejado_min": "numero",
        "ciclo_ideal_s": "numero",
        "pecas_produzidas": "numero",
        "pecas_refugo": "numero",
        "pecas_retrabalho": "numero",
    },
    "paradas": {
        "data": "data",
        "turno": "texto",
        "linha": "texto",
        "posto": "texto",
        "motivo": "texto",
        "categoria": "texto",
        "duracao_min": "numero",
    },
    "postos": {
        "modelo": "texto",
        "posto": "texto",
        "nome_posto": "texto",
        "operacao": "texto",
        "tempo_s": "numero",
        "tipo": "texto",
    },
}

# Colunas opcionais dentro de abas obrigatórias
COLUNAS_OPCIONAIS: dict[str, dict[str, str]] = {
    # Obrigatória só quando a planilha tem mais de uma linha de produção
    "postos": {"linha": "texto"},
}

# Abas opcionais: parâmetros de cada linha (demanda diária e tempo disponível para o takt)
ABAS_OPCIONAIS: dict[str, dict[str, str]] = {
    "linhas": {"linha": "texto", "demanda_diaria": "numero", "tempo_disponivel_min": "numero"},
}

# Um registro de produção por turno: é por essa chave que as paradas são ligadas à produção
CHAVE_TURNO = ["data", "turno", "linha"]

# Colunas que não podem ser zero (além de não poderem ser negativas)
ESTRITAMENTE_POSITIVAS = {
    "tempo_planejado_min", "ciclo_ideal_s", "tempo_s", "duracao_min",
    "demanda_diaria", "tempo_disponivel_min",
}

MAX_LINHAS_NA_MENSAGEM = 5


class ErroPlanilha(Exception):
    """Planilha com problemas que impedem o cálculo. `erros` lista cada problema."""

    def __init__(self, erros: list[str]):
        self.erros = erros
        super().__init__("\n".join(erros))


@dataclass
class DadosValidados:
    producao: pd.DataFrame
    paradas: pd.DataFrame
    postos: pd.DataFrame
    avisos: list[str] = field(default_factory=list)
    linhas: pd.DataFrame | None = None  # parâmetros por linha, se a aba existir


# ---------------------------------------------------------------------------
# Normalização
# ---------------------------------------------------------------------------
def normalizar_texto(texto: str) -> str:
    """'Peças Produzidas ' -> 'pecas_produzidas' (minúsculo, sem acento, com _)."""
    sem_acento = unicodedata.normalize("NFKD", str(texto)).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", sem_acento.lower()).strip("_")


def _linhas_excel(mascara: pd.Series) -> str:
    """Converte índices do DataFrame em números de linha do Excel (cabeçalho = linha 1)."""
    linhas = [str(i + 2) for i in mascara[mascara].index[:MAX_LINHAS_NA_MENSAGEM]]
    extra = int(mascara.sum()) - len(linhas)
    return ", ".join(linhas) + (f" (e mais {extra})" if extra > 0 else "")


# ---------------------------------------------------------------------------
# Carregamento
# ---------------------------------------------------------------------------
def carregar_excel(fonte: str | BinaryIO) -> dict[str, pd.DataFrame]:
    """Lê todas as abas de um .xlsx. Nomes de abas são normalizados ('Produção' -> 'producao')."""
    abas = pd.read_excel(fonte, sheet_name=None)
    return {normalizar_texto(nome): df for nome, df in abas.items()}


def carregar_csvs(fontes: dict[str, str | BinaryIO]) -> dict[str, pd.DataFrame]:
    """Lê um CSV por aba, ex.: {'producao': 'producao.csv', ...}. Aceita ';' ou ','."""
    return {
        normalizar_texto(aba): pd.read_csv(fonte, sep=None, engine="python")
        for aba, fonte in fontes.items()
    }


# ---------------------------------------------------------------------------
# Validação
# ---------------------------------------------------------------------------
def _converter_colunas(
    df: pd.DataFrame, aba: str, esquema: dict[str, str], erros: list[str]
) -> pd.DataFrame:
    df = df.copy()
    for coluna, tipo in esquema.items():
        original = df[coluna]
        vazio = original.isna() | (original.astype(str).str.strip() == "")

        if tipo == "data":
            convertido = pd.to_datetime(original, errors="coerce", dayfirst=True, format="mixed")
            df[coluna] = convertido.dt.normalize()
            descricao = "data inválida"
        elif tipo == "numero":
            texto = original.astype(str).str.strip().str.replace(",", ".", regex=False)
            convertido = pd.to_numeric(texto.where(~vazio), errors="coerce")
            df[coluna] = convertido
            descricao = "número inválido"
        else:
            convertido = original.astype(str).str.strip().where(~vazio)
            df[coluna] = convertido
            descricao = "texto vazio"

        invalido = convertido.isna()
        if invalido.any():
            erros.append(
                f"Aba '{aba}', coluna '{coluna}': {descricao} nas linhas {_linhas_excel(invalido)}."
            )
    return df


def _checar_valores(df: pd.DataFrame, aba: str, esquema: dict[str, str], erros: list[str]) -> None:
    for coluna, tipo in esquema.items():
        if tipo != "numero":
            continue
        if coluna in ESTRITAMENTE_POSITIVAS:
            ruim, regra = df[coluna] <= 0, "deve ser maior que zero"
        else:
            ruim, regra = df[coluna] < 0, "não pode ser negativo"
        if ruim.any():
            erros.append(f"Aba '{aba}', coluna '{coluna}': valor {regra} (linhas {_linhas_excel(ruim)}).")


def _preparar(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [normalizar_texto(c) for c in df.columns]
    return df.dropna(how="all")


def _validar_aba_linhas(df: pd.DataFrame, erros: list[str]) -> pd.DataFrame | None:
    esquema = ABAS_OPCIONAIS["linhas"]
    df = _preparar(df)
    sem_coluna = [c for c in esquema if c not in df.columns]
    if sem_coluna:
        erros.append(f"Aba 'linhas': colunas obrigatórias ausentes: {', '.join(sem_coluna)}.")
        return None
    n_erros = len(erros)
    df = _converter_colunas(df, "linhas", esquema, erros)
    if len(erros) > n_erros:
        return None
    _checar_valores(df, "linhas", esquema, erros)
    duplicado = df.duplicated("linha", keep=False)
    if duplicado.any():
        erros.append(f"Aba 'linhas': linha repetida (linhas {_linhas_excel(duplicado)}).")
    return df


def validar(tabelas: dict[str, pd.DataFrame]) -> DadosValidados:
    erros: list[str] = []
    avisos: list[str] = []

    # 1. Abas obrigatórias
    faltando = [aba for aba in ESQUEMA if aba not in tabelas]
    if faltando:
        raise ErroPlanilha(
            [f"Aba obrigatória não encontrada: '{aba}'." for aba in faltando]
            + [f"Abas encontradas: {', '.join(tabelas) or 'nenhuma'}."]
        )

    # 2. Colunas obrigatórias (nomes normalizados) e remoção de linhas totalmente vazias
    limpas: dict[str, pd.DataFrame] = {}
    for aba, colunas in ESQUEMA.items():
        df = _preparar(tabelas[aba])
        sem_coluna = [c for c in colunas if c not in df.columns]
        if sem_coluna:
            erros.append(f"Aba '{aba}': colunas obrigatórias ausentes: {', '.join(sem_coluna)}.")
            continue
        if df.empty and aba != "paradas":  # um período sem paradas é possível
            erros.append(f"Aba '{aba}' está vazia.")
            continue
        limpas[aba] = df
    if erros:
        raise ErroPlanilha(erros)

    # 3. Coluna 'linha' dos postos: obrigatória só se houver mais de uma linha de produção
    linhas_producao = sorted(limpas["producao"]["linha"].dropna().astype(str).str.strip().unique())
    esquema_postos = dict(ESQUEMA["postos"])
    if "linha" in limpas["postos"].columns:
        esquema_postos.update(COLUNAS_OPCIONAIS["postos"])
    elif len(linhas_producao) == 1:
        limpas["postos"]["linha"] = linhas_producao[0]
    else:
        raise ErroPlanilha([
            "Aba 'postos': a planilha tem mais de uma linha de produção "
            f"({', '.join(linhas_producao)}), então os postos precisam da coluna 'linha'."
        ])

    # 4. Tipos e faixas de valores
    esquemas = {**ESQUEMA, "postos": esquema_postos}
    for aba, esquema in esquemas.items():
        limpas[aba] = _converter_colunas(limpas[aba], aba, esquema, erros)
    if erros:  # sem tipos corretos, as checagens seguintes não fazem sentido
        raise ErroPlanilha(erros)
    for aba, esquema in esquemas.items():
        _checar_valores(limpas[aba], aba, esquema, erros)

    producao, paradas, postos = limpas["producao"], limpas["paradas"], limpas["postos"]
    linhas = _validar_aba_linhas(tabelas["linhas"], erros) if "linhas" in tabelas else None

    # 5. Regras de negócio
    perdas = producao["pecas_refugo"] + producao["pecas_retrabalho"]
    ruim = perdas > producao["pecas_produzidas"]
    if ruim.any():
        erros.append(
            "Aba 'producao': refugo + retrabalho maior que as peças produzidas "
            f"(linhas {_linhas_excel(ruim)})."
        )

    duplicado = producao.duplicated(CHAVE_TURNO, keep=False)
    if duplicado.any():
        erros.append(
            "Aba 'producao': mais de um registro para o mesmo data/turno/linha "
            f"(linhas {_linhas_excel(duplicado)}). Use um registro por turno."
        )

    sem_postos = sorted(set(producao["linha"]) - set(postos["linha"]))
    if sem_postos:
        avisos.append(
            f"Sem estudo de tempos (aba 'postos') para: {', '.join(sem_postos)}. "
            "A análise de gargalo não estará disponível para essas linhas."
        )

    if not paradas.empty:
        total_parado = paradas.groupby(CHAVE_TURNO)["duracao_min"].sum().rename("total_parado")
        juntos = producao.join(total_parado, on=CHAVE_TURNO)
        estourou = juntos["total_parado"] > juntos["tempo_planejado_min"]
        if estourou.any():
            erros.append(
                "Paradas somam mais que o tempo planejado do turno "
                f"(aba 'producao', linhas {_linhas_excel(estourou)})."
            )

        chaves_producao = pd.MultiIndex.from_frame(producao[CHAVE_TURNO])
        orfas = ~pd.MultiIndex.from_frame(paradas[CHAVE_TURNO]).isin(chaves_producao)
        orfas = pd.Series(orfas, index=paradas.index)
        if orfas.any():
            avisos.append(
                "Aba 'paradas': paradas sem registro de produção correspondente foram ignoradas "
                f"(linhas {_linhas_excel(orfas)})."
            )
            paradas = paradas[~orfas]

        # Performance > 100% quase sempre indica ciclo ideal cadastrado errado
        operando_min = juntos["tempo_planejado_min"] - juntos["total_parado"].fillna(0)
        tempo_ideal_min = juntos["ciclo_ideal_s"] * juntos["pecas_produzidas"] / 60
        acima = (tempo_ideal_min > operando_min * 1.001) & ~estourou
        if acima.any():
            avisos.append(
                "Performance acima de 100% em alguns turnos: confira o ciclo ideal ou as paradas "
                f"(aba 'producao', linhas {_linhas_excel(acima)})."
            )

    if erros:
        raise ErroPlanilha(erros)

    return DadosValidados(
        producao=producao.reset_index(drop=True),
        paradas=paradas.reset_index(drop=True),
        postos=postos.reset_index(drop=True),
        avisos=avisos,
        linhas=linhas.reset_index(drop=True) if linhas is not None else None,
    )


def carregar_e_validar(fonte: str | BinaryIO) -> DadosValidados:
    """Atalho: lê o .xlsx e valida (sem mapeamento de colunas)."""
    return validar(carregar_excel(fonte))
