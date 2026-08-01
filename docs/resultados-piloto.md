# Resultados do piloto exploratório

Data do relatório: 01/08/2026. Protocolo pré-registrado em `protocolo-piloto.md`; dados brutos por operação em `analysis/results/`.

## Execução

Quatro janelas de execução, 52 operações de âncora confirmadas por janela (13 por mecanismo, ordem aleatorizada balanceada em blocos de 4), totalizando **208 operações confirmadas, 52 por mecanismo, sem nenhuma falha**:

| Janela | Data (UTC) | Duração | Tempo de parede por operação |
|---|---|---|---|
| 1 | 20/07/2026 16:44-16:46 | 2,2 min | 2,56 s |
| 2 | 22/07/2026 02:41-02:43 | 2,3 min | 2,76 s |
| 3 | 01/08/2026 16:16-16:18 | 2,1 min | 2,46 s |
| 4 | 01/08/2026 16:34-16:36 | 2,1 min | 2,53 s |

Critério de aceite 1 do protocolo (>= 50 operações confirmadas por mecanismo, CSV bruto no repositório): **atendido** (52 por mecanismo; `pilot-ops.csv`).

## Métricas (seção 5 do protocolo)

### 1. Latência por operação, por mecanismo e por janela (ms; mediana [IQR])

| Mecanismo | Janela 1 | Janela 2 | Janela 3 | Janela 4 | Geral (n=52) |
|---|---|---|---|---|---|
| Soroban | 4.688 [4.070-4.840] | 3.830 [3.688-4.608] | 4.518 [4.060-4.536] | 4.460 [4.445-4.520] | 4.460 [4.056-4.743] |
| Stellar clássico | 4.522 [4.471-4.574] | 4.240 [3.689-4.982] | 4.567 [4.464-4.853] | 4.863 [4.069-4.879] | 4.545 [4.162-4.876] |
| Rekor | 474 [422-489] | 458 [435-513] | 447 [403-473] | 423 [395-456] | 451 [406-485] |
| Controle | 4 [3-4] | 3 [3-3] | 3 [3-3] | 3 [3-3] | 3 [3-3] |

As medianas por mecanismo são estáveis entre janelas (variação máxima ~18% no Soroban); os dois mecanismos on-chain concentram-se em torno do intervalo de fechamento de ledger (~5 s) e o Rekor opera uma ordem de grandeza abaixo.

### 2. Tempo médio por operação confirmada

2,46 a 2,76 s de tempo de parede por operação (tabela acima; média ~2,6 s), com a orquestração incluída. Parâmetro de exequibilidade do fatorial completo: 4.200 operações a ~2,6 s/op equivalem a ~3,0 h de coleta ativa.

### 3. Variabilidade e forma

Desvio-padrão por janela (ms): Soroban 345 / 1.569 / 307 / 253; clássico 262 / 847 / 373 / 774; Rekor 103 / 58 / 124 / 181; controle <= 3. A dispersão dos mecanismos Stellar variou até ~5x entre janelas (madrugada da janela 2 com cauda longa), enquanto as medianas quase não se moveram — o "efeito de janela" observado é predominantemente de dispersão, não de nível. Distribuições assimétricas à direita; ajuste exploratório Gama/log-normal e simulação de poder serão conduzidos sobre estes dados para dimensionar as repetições do experimento completo.

### 4. Autocorrelação das latências sequenciais (lag 1; extremos dos lags 1-5)

| Mecanismo | Janela 1 | Janela 2 | Janela 3 | Janela 4 |
|---|---|---|---|---|
| Soroban | -0,21 | -0,20 | 0,00 | -0,10 |
| Stellar clássico | +0,38 | -0,23 | +0,55 | -0,19 |
| Rekor | -0,13 | +0,11 | +0,09 | -0,14 |
| Controle | -0,30 | -0,12 | -0,06 | -0,11 |

Com n = 13 por série (erro-padrão aproximado 0,28), nenhum padrão de correlação serial é consistente entre janelas — o sinal do clássico inverte de janela para janela. O piloto não estabelece estrutura serial; sustenta tratar a janela como bloco e verificar autocorrelação nos resíduos do modelo, com ação corretiva se detectada.

### 5. Taxa por âncora e estado do contrato

- Stellar clássico (`manageData`): 200 stroops por operação, constante nas 52 operações.
- Soroban (contrato com `extend_ttl` a cada âncora): 10.434 stroops em 50 das 52 operações. Duas exceções, ambas na primeira operação após período de inatividade: 31.173 stroops (janela 2) e 1.925.729 stroops (janela 3, primeira operação após 10 dias) — padrão compatível com renovação acumulada do aluguel de estado (TTL). Observação com n = 2, não controlada; registrada como insumo para a caracterização de custo de manutenção de estado do experimento completo.
- Rekor: sem cobrança.
- Footprint de recursos por operação (além da taxa) não foi coletado neste piloto (ver Desvios).

### 6. Carga-base das instâncias

Sonda de 1 requisição/min executada em paralelo às janelas 1 e 2 (`baseline-probe.csv`): sem falhas; latência de consulta com cauda maior na janela 2 (máximo 1.915 ms contra 688 ms na janela 1, RPC Stellar), consistente com a maior dispersão observada naquela janela. Não executada nas janelas 3 e 4 (ver Desvios).

### 7. Primitivo criptográfico local

SHA-256: 0,0004 ms (82 bytes) a 0,089 ms (227 KB) por artefato; assinatura ed25519: ~0,104 ms (`local-primitive.csv`). Cerca de quatro ordens de grandeza abaixo da âncora em rede — referência determinística que separa o custo criptográfico do custo de rede.

### 8. Fase de registro com e sem ancoragem

Pipeline dos 20 artefatos (`registration-phase.csv`): sem âncora 29,7 ms (n=3); controle local 100,0 ms (n=3); Rekor 9.791,5 ms (n=1); Stellar clássico 99.800,4 ms (n=1); Soroban 100.593,2 ms (n=1). No regime tabular deste piloto, a fase de registro com âncora remota é dominada pela latência de rede por artefato — dado de planejamento que motivou a definição do sobrecusto do experimento completo sobre o tempo total de execução do pipeline, e não apenas sobre a fase de registro.

## Verificação da cadeia

Critério de aceite 3: **atendido**. Verificação automatizada dos 20 elos passando; a supressão do elo 5 é detectada pela quebra do encadeamento (`verify_chain`).

## Desvios do protocolo (seção 8)

1. **Espaçamento das janelas**: o protocolo previa 4 janelas em horários distintos distribuídas em >= 2 dias. As janelas 1 e 2 cumpriram o espaçamento (dias e horários distintos); as janelas 3 e 4 foram executadas no mesmo dia (01/08/2026), com ~18 min de intervalo, 10 dias após a janela 2. Motivo: janela de disponibilidade antes da submissão do projeto de pesquisa. Efeito: as janelas 3 e 4 compartilham condições de rede próximas; a análise por janela as trata como blocos distintos, mas a diversidade temporal do conjunto vem principalmente do contraste entre os três dias cobertos.
2. **Fase de registro**: 3 repetições nas condições locais (sem âncora; controle) e 1 repetição nas três condições remotas, contra 3 previstas. Motivo: custo de tempo das condições on-chain (~100 s por repetição). As repetições faltantes serão coletadas antes do experimento completo.
3. **Sonda de carga-base**: executada nas janelas 1 e 2; não executada nas janelas 3 e 4.
4. **Footprint de recursos (métrica 5)**: coletada somente a taxa cobrada; o footprint detalhado de recursos Soroban não foi extraído neste piloto.
5. Este relatório foi publicado em 01/08/2026, após a conclusão das 4 janelas; as janelas 1 e 2 haviam sido executadas em 20-22/07/2026.

## Limites

Conforme a seção 1 do protocolo: este piloto não testa hipóteses e não sustenta comparação estatística entre mecanismos. Os números acima são caracterização descritiva e parâmetros de planejamento para o experimento fatorial completo.
