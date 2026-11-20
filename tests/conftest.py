import pandas as pd
import pytest


@pytest.fixture
def tabelas_validas() -> dict[str, pd.DataFrame]:
    """Planilha mínima e válida: 1 turno com 50 min de paradas (caso clássico 90% × 90% × 90%)."""
    producao = pd.DataFrame(
        {
            "data": ["2026-10-01"],
            "turno": ["T1"],
            "linha": ["Linha A"],
            "modelo": ["X100"],
            "tempo_planejado_min": [500],
            "ciclo_ideal_s": [30],
            "pecas_produzidas": [810],
            "pecas_refugo": [41],
            "pecas_retrabalho": [40],
        }
    )
    paradas = pd.DataFrame(
        {
            "data": ["2026-10-01", "2026-10-01"],
            "turno": ["T1", "T1"],
            "linha": ["Linha A", "Linha A"],
            "posto": ["P03", "P04"],
            "motivo": ["Falta de peça", "Quebra de parafusadeira"],
            "categoria": ["Material", "Máquina"],
            "duracao_min": [30, 20],
        }
    )
    postos = pd.DataFrame(
        {
            "modelo": ["X100"] * 2,
            "posto": ["P01", "P02"],
            "nome_posto": ["Base", "Motor"],
            "operacao": ["Fixar base", "Fixar motor"],
            "tempo_s": [40, 50],
            "tipo": ["Agrega valor", "Agrega valor"],
        }
    )
    return {"producao": producao, "paradas": paradas, "postos": postos}
