# Analisador de OEE e Gargalos · Linha de Montagem

Painel em Python que transforma a planilha de apontamentos de uma linha de montagem em **diagnóstico pronto**: OEE decomposto, Pareto das paradas, gargalo vs. takt time (Yamazumi) e um simulador que traduz melhoria em **peças boas a mais**.

**[▶ Abrir o app online](https://SEU-APP.streamlit.app)** · dados 100% fictícios, gerados por script

![Aba de diagnóstico](docs/img/diagnostico.png)

---

## O problema

Em muitas fábricas o OEE é calculado à mão numa planilha, uma vez por mês, e chega à reunião como um número solto ("71%"). Ninguém sabe **onde** está a perda nem **quanto vale** atacá-la. Este projeto automatiza esse caminho:

> planilha de apontamentos → validação → indicadores → causas → gargalo → "e se?" → relatório

## O que o app faz

| Aba | Pergunta que responde |
|---|---|
| 🧭 **Diagnóstico** | O que está errado e por onde começar? Achados em frases prontas, ordenados por prioridade. |
| 📈 **OEE** | Para onde foi o tempo? Cascata do tempo planejado até o efetivo, evolução por dia e turno. |
| 📊 **Pareto de paradas** | Quais poucas causas concentram a maior parte da perda? Classes ABC por motivo, categoria 6M ou posto. |
| ⚙️ **Gargalo e balanceamento** | A linha atende a demanda? Yamazumi por posto (agrega valor / não agrega / desperdício) contra o takt. |
| 🔮 **Simulador** | Se reduzirmos a causa X pela metade, quanto ganhamos em OEE e em peças? |
| 📥 **Relatório** | Excel formatado com resumo, achados, OEE por dia/turno, Pareto e Yamazumi, pronto para a reunião. |

<table>
<tr>
<td><img src="docs/img/oee.png" alt="Aba OEE"></td>
<td><img src="docs/img/pareto.png" alt="Aba Pareto"></td>
</tr>
<tr>
<td><img src="docs/img/gargalo.png" alt="Aba Gargalo com Yamazumi"></td>
<td><img src="docs/img/simulador.png" alt="Aba Simulador"></td>
</tr>
</table>

### Exemplo de leitura (dados fictícios da Linha A)

- OEE de **71,1%**: Disponibilidade 84,3% × Performance 88,0% × Qualidade 95,8%.
- **Falta de peça** responde por 46% do tempo parado. Reduzi-la pela metade leva o OEE a **74,1%**, o que significa **+676 peças boas** no mês.
- No modelo **X200**, o posto **P04** leva 61 s contra um takt de 57,6 s, e a linha não atende a demanda. Eliminar os 10 s de desperdício do posto resolve sem investimento.
- O turno T2 está 6,1 p.p. abaixo do T1, e a diferença está na **performance**, o que aponta para padronização do trabalho.
- A queda de 13/10 (crise de fornecedor simulada no gerador) é **detectada automaticamente**.

## Como os números são calculados

### OEE como cascata de tempo

Em vez de multiplicar percentuais soltos, o cálculo segue o tempo:

| Tempo | Definição | Índice |
|---|---|---|
| Planejado | turno − pausas programadas | |
| Operando | planejado − paradas | **Disponibilidade** = operando ÷ planejado |
| Ideal | peças produzidas × ciclo ideal | **Performance** = ideal ÷ operando |
| Efetivo | peças boas × ciclo ideal | **Qualidade** = efetivo ÷ ideal |

**OEE = Disponibilidade × Performance × Qualidade = efetivo ÷ planejado**

Ao agregar vários turnos, o app **soma os tempos primeiro e só depois divide**. Fazer a média dos percentuais de cada turno distorce o resultado quando os turnos têm durações diferentes.

| Faixa | Classificação |
|---|---|
| ≥ 85% | Classe mundial |
| ≥ 75% | Bom |
| ≥ 65% | Regular |
| < 65% | Crítico |

### Takt time, gargalo e balanceamento

- **Takt time** = tempo disponível por dia (s) ÷ demanda diária. É o ritmo que o cliente exige.
- **Gargalo** = posto com o maior tempo de ciclo. Se ele passa do takt, a linha não atende a demanda.
- **Capacidade** = 3600 ÷ tempo do gargalo (peças/h).
- **Eficiência de balanceamento** = soma dos tempos ÷ (nº de postos × tempo do gargalo).
- **Postos mínimos teóricos** = ⌈soma dos tempos ÷ takt⌉.

### Pareto com classes ABC

As causas são ordenadas por tempo parado ou por ocorrências. A classe vem do percentual acumulado **antes** de cada item:
- **A**: começa abaixo de 80%
- **B**: abaixo de 95%
- **C**: o restante

Assim a primeira causa é sempre classe A.

### Premissas do simulador

- O tempo de parada eliminado vira tempo operando.
- Esse tempo roda com a performance e a qualidade atuais, mais os ganhos informados.
- Só o **tempo ganho** é convertido em peças, pelo ciclo médio do período, que respeita o mix de modelos.

## Usando com a planilha da sua empresa

Cada fábrica nomeia as colunas de um jeito ("Qtd Produzida", "Célula", "Rework", "Downtime"...). O app **não exige que você renomeie nada**:

1. Ao carregar a planilha, o painel **🔗 Mapeamento de colunas** tenta reconhecer cada campo em três etapas:
   1. pelo nome exato;
   2. por uma lista de sinônimos de fábrica;
   3. por nome parecido, o que pega erros de digitação.
2. O que não for reconhecido aparece para você escolher a coluna correta.
3. Salve o mapeamento em `.json`. No mês seguinte, basta carregar a planilha nova com esse arquivo.

O app também aceita **várias linhas de produção** no mesmo arquivo: coluna `linha` nas abas e aba opcional `linhas` com demanda e tempo disponível de cada uma. Toda a planilha passa por **validação com mensagens que apontam a linha do Excel** (*"Aba 'producao': refugo + retrabalho maior que as peças produzidas (linhas 14, 27)."*).

### Formato esperado (após o mapeamento)

| Aba | Colunas |
|---|---|
| `producao` | data, turno, linha, modelo, tempo_planejado_min, ciclo_ideal_s, pecas_produzidas, pecas_refugo, pecas_retrabalho |
| `paradas` | data, turno, linha, posto, motivo, categoria, duracao_min |
| `postos` | linha, modelo, posto, nome_posto, operacao, tempo_s, tipo |
| `linhas` *(opcional)* | linha, demanda_diaria, tempo_disponivel_min |

Baixe a planilha modelo pelo botão na barra lateral do app.

## Como rodar localmente

```powershell
git clone https://github.com/SEU-USUARIO/analisador-oee-montagem.git
cd analisador-oee-montagem
python -m venv .venv
.\.venv\Scripts\activate          # Linux/Mac: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

Gerar outro conjunto de dados fictícios:

```powershell
python dados/gerar_dados.py --inicio 2026-10-01 --fim 2026-10-31 --semente 7
```

Rodar os testes (68 testes):

```powershell
pytest
```

## Estrutura

```
app.py                 interface Streamlit (abas, filtros, simulador, download)
src/
  leitor.py            leitura e validação da planilha (mensagens com linha do Excel)
  mapeamento.py        reconhecimento automático de colunas (nome, sinônimos, similaridade)
  indicadores.py       OEE como cascata de tempo, takt time, agregações
  pareto.py            Pareto com classes ABC
  gargalo.py           Yamazumi, gargalo, capacidade, balanceamento
  simulador.py         cenários "e se"
  diagnostico.py       achados automáticos em linguagem de chão de fábrica
  relatorio.py         exportação para Excel
  graficos.py          gráficos Plotly (paleta segura para daltonismo, padrão numérico BR)
dados/gerar_dados.py   gerador de dados fictícios com cenários realistas
tests/                 testes com casos calculados à mão (ex.: 90% × 90% × 90% = 72,9%)
```

## Stack

Python · pandas · Plotly · Streamlit · openpyxl · pytest

## Sobre os dados

Todos os dados do repositório são **fictícios**, gerados por `dados/gerar_dados.py`, com cenários plantados para o diagnóstico encontrar:
- crise de fornecedor;
- turno com performance pior;
- posto acima do takt.

Nenhum dado real de empresa foi usado.

## Licença

[MIT](LICENSE)
