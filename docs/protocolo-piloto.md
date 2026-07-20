# Protocolo do piloto exploratório — pré-registro

> Este protocolo é registrado no repositório ANTES da implementação do harness de medição e de qualquer execução. O histórico de commits documenta a ordem. Resultados serão reportados em `resultados-piloto.md`.

## 1. Objetivo

Demonstrar a exequibilidade ponta a ponta da ancoragem criptográfica de proveniência para artefatos de aprendizado de máquina em quatro mecanismos, e produzir estimativas exploratórias de latência, custo, variabilidade e autocorrelação que informem o desenho de um experimento fatorial completo posterior.

Este piloto NÃO é o experimento: não testa hipóteses, não compara estatisticamente os mecanismos e não sustenta conclusões comparativas — produz caracterização descritiva e parâmetros de planejamento (variância para análise de poder, tempo por operação, estrutura de dependência temporal).

## 2. Mecanismos comparados (como implantados)

| Mecanismo | Instância de referência | Operação de âncora |
|---|---|---|
| M1 Contrato Soroban | Stellar testnet | Invocação de função `anchor` em contrato dedicado |
| M2 Stellar clássico | Stellar testnet | Operação `manageData` (chave = id do artefato; valor = hash) |
| M3 Rekor | Log público rekor.sigstore.dev | Entrada `hashedrekord` via API REST |
| M4 Controle | Sistema de arquivos local | Append em log local com `fsync` |

O construto é o mecanismo tal como implantado em sua instância de referência; carga e condições de cada instância integram o tratamento. Uma sonda de carga-base registra o estado de cada instância remota durante as janelas.

## 3. Material

- **Artefatos**: 20 artefatos derivados de uma série meteorológica pública do INMET/BDMEP por um pipeline tabular simples (ingestão, limpeza, agregações, partição treino/teste, modelo de classificação serializado, métricas) — somente dados públicos.
- **Registro de proveniência**: um registro PROV-DM mínimo por artefato (entidade, atividade, agente), serializado em JSON canônico; hash SHA-256 do artefato e do registro, encadeados ao registro anterior.
- **Chaves**: par de chaves de testnet descartável (financiado via friendbot); chave de assinatura ed25519 gerada para o piloto. Nenhuma chave de produção.
- **Privacidade**: entradas do Rekor são públicas e permanentes; somente hashes de artefatos derivados de dados públicos são enviados.

## 4. Desenho da execução

- **Janelas**: 4 janelas de execução em horários distintos (distribuídas em >= 2 dias), funcionando como blocos.
- **Dentro de cada janela**: >= 13 operações de âncora por mecanismo, em ordem aleatorizada balanceada (blocos de 4 mecanismos embaralhados), totalizando >= 50 operações confirmadas por mecanismo no piloto.
- **Medição por operação**: t_submissão, t_confirmação (inclusão em ledger para M1/M2; inclusão no log com UUID para M3; retorno do `fsync` para M4), latência = diferença; taxa cobrada e footprint de recursos (M1/M2); identificadores públicos de verificação (hash da transação; UUID do Rekor).
- **Sonda de carga-base**: 1 requisição trivial por minuto por instância remota (consulta de status), em paralelo às janelas.
- **Primitivo local isolado**: tempo de SHA-256 + assinatura ed25519 local sobre cada artefato (referência determinística independente de rede), medido separadamente.
- **Fase de registro (sobrecusto)**: o pipeline dos 20 artefatos executado 3 vezes COM e 3 vezes SEM ancoragem, cronometrando a fase de registro dos artefatos — numerador e denominador do sobrecusto.
- **Verificação**: ao final, verificação automatizada da cadeia completa (cada elo e a completude; a supressão de um elo deve ser detectada).

## 5. Métricas de saída

1. Latência por operação, por mecanismo e por janela (mediana, IQR, distribuição).
2. Tempo médio por operação confirmada (parâmetro de exequibilidade do fatorial completo).
3. Variância/forma da distribuição de latência (insumo para análise de poder por simulação).
4. Função de autocorrelação (lag 1-5) das latências sequenciais dentro de cada janela.
5. Taxa cobrada por âncora e footprint de recursos (M1 vs M2); configuração de TTL aplicada ao estado do contrato.
6. Carga-base por instância por janela.
7. Tempo do primitivo criptográfico local por artefato.
8. Duração da fase de registro com vs sem ancoragem (3 repetições cada).

## 6. Análise planejada

Somente descritiva: tabelas de mediana/IQR por mecanismo e janela; ACF por janela; ajuste exploratório de distribuição (Gama/log-normal) às latências; simulação de poder usando a variância observada para dimensionar repetições do experimento completo. Sem testes de hipótese.

## 7. Critérios de aceite do piloto

1. >= 50 operações confirmadas por mecanismo, com CSV bruto por operação no repositório;
2. as 8 métricas da seção 5 computadas e reportadas em `resultados-piloto.md`;
3. verificação automatizada da cadeia passando, incluindo detecção de supressão de elo;
4. reprodutível a partir do README (build do contrato, instalação do harness, execução, análise).

## 8. Desvios

Qualquer desvio deste protocolo (redução de janelas ou de N por instabilidade de rede, reset da testnet, indisponibilidade de instância) será registrado em `resultados-piloto.md` com data e motivo. Corte pré-declarado em caso de restrição de tempo: reduzir para 2 janelas x 50 operações por mecanismo.
