# prov-anchor-bench

Avaliação experimental comparativa de mecanismos de ancoragem criptográfica de proveniência para artefatos de aprendizado de máquina (conjuntos de dados, transformações, configurações e modelos).

Um mesmo harness de medição compara quatro formas de ancorar a cadeia de proveniência dos artefatos de um pipeline:

| Mecanismo | Instância | Modelo de confiança |
|---|---|---|
| Contrato inteligente Soroban | Stellar testnet | Consenso de rede pública |
| Operação nativa Stellar (`manageData`) | Stellar testnet | Consenso de rede pública |
| Rekor (`hashedrekord`) | Log de transparência público do Sigstore | Operador único auditável |
| Log local append-only | Sistema de arquivos (controle) | Nenhum (linha de base) |

Cada artefato é descrito por um registro mínimo W3C PROV-DM. A âncora registra o SHA-256 do artefato e do seu registro de proveniência, encadeados ao registro anterior.

## Situação

- **Piloto v1: concluído** (20/07 a 01/08/2026). 208 operações de ancoragem confirmadas, 52 por mecanismo, em quatro janelas, sem falhas. Estado de referência: tag [`pilot-v1`](../../tree/pilot-v1).
  - Protocolo (publicado antes do código de medição): [`docs/protocolo-piloto.md`](docs/protocolo-piloto.md)
  - Resultados: [`docs/resultados-piloto.md`](docs/resultados-piloto.md)
- **Piloto v2: em preparação.** Corrige os limites de medição e de desenho declarados no relatório do v1. O protocolo v2 será publicado antes de qualquer alteração no código de medição.

O piloto é exploratório: produz caracterização descritiva e parâmetros de planejamento, sem teste de hipóteses.

## Verificar os resultados publicados (sem credenciais)

Requer Python 3.11 ou superior.

```bash
pip install -r harness/requirements.txt
python -m tools.fetch_inmet                 # prepara o arquivo oficial do INMET e confere o SHA-256
python -m tools.verify_published            # confere tudo contra a evidência arquivada em evidence/pilot-v1/
python -m tools.verify_published --online   # o mesmo, direto nos serviços públicos (Horizon, Rekor, Soroban RPC)
```

O verificador reconstrói os 20 artefatos a partir do arquivo oficial do INMET e confere, para cada operação publicada em `analysis/results/pilot-ops.csv`:

1. o hash gravado em cada uma das 104 transações Stellar é igual ao hash do artefato reconstruído;
2. a taxa cobrada e o horário de fechamento do ledger batem com o registro;
3. as 52 transações Soroban invocam `anchor()` no contrato do piloto;
4. cada uma das 52 entradas do Rekor existe, tem o `logIndex` registrado e uma prova de inclusão Merkle válida (RFC 6962) contra a raiz publicada;
5. os logs locais do controle batem com o registro;
6. o bytecode do contrato implantado é o arquivado;
7. as medianas recalculadas são as publicadas no relatório.

A evidência pública (transações, entradas do Rekor e bytecode do contrato) está arquivada em [`evidence/pilot-v1/`](evidence/pilot-v1/), o que mantém a verificação possível mesmo depois de um reset da testnet.

## Dados de entrada

| Campo | Valor |
|---|---|
| Fonte | INMET, Banco de Dados Meteorológicos, dados históricos anuais: https://portal.inmet.gov.br/dadoshistoricos |
| Arquivo | `2003.zip` → `INMET_CO_MT_A901_CUIABA_01-01-2003_A_31-12-2003.CSV` |
| Estação | A901, Cuiabá (MT), estação automática |
| SHA-256 | `0cecf2fdf3a9c26db24289d956b13522d9fc763b5a503d142df784069a58ee0b` |

Somente dados públicos são usados. Uma cópia do arquivo bruto está versionada em [`data/inmet/`](data/inmet/), para que a verificação não dependa da disponibilidade do portal; `tools/fetch_inmet.py` confere o SHA-256 dessa cópia e só recorre ao portal do INMET se ela estiver ausente. Os dados são do INMET, que os disponibiliza publicamente.

## Contrato do piloto v1

| Campo | Valor |
|---|---|
| Endereço (testnet) | `CB6CW2PRULKUBZWJPONROCSV7L6TXQEIVR4N2SZURQX56XHYA5I6LCGM` |
| SHA-256 do bytecode | `ba4ca84ac354cb74248ec32d4057d45ddf9cfab85961de36ce21df47346abea5` |
| Código-fonte | [`contracts/anchor/src/lib.rs`](contracts/anchor/src/lib.rs) |
| Explorador | https://stellar.expert/explorer/testnet/contract/CB6CW2PRULKUBZWJPONROCSV7L6TXQEIVR4N2SZURQX56XHYA5I6LCGM |

## Reproduzir o experimento

Pré-requisitos: Python 3.11+, Rust (com o target `wasm32v1-none`) e [`stellar-cli`](https://developers.stellar.org/docs/tools/cli). No Windows, o Rust exige as Build Tools do Visual Studio. Um ambiente em Docker será publicado com o piloto v2.

```bash
# 1. Dependências e dados
pip install -r harness/requirements.txt
python -m tools.fetch_inmet

# 2. Contas descartáveis de teste (financiadas pelo friendbot) e implantação do contrato
stellar keys generate pilot-soroban --network testnet --fund
stellar keys generate pilot-classic --network testnet --fund
cd contracts/anchor && stellar contract build && cd ../..
stellar contract deploy --wasm contracts/anchor/target/wasm32v1-none/release/anchor.wasm \
    --source-account pilot-soroban --network testnet      # imprime o endereço do contrato (C...)

# 3. Arquivo de chaves local (nunca versionado), a partir de .pilot-secrets.example.json
#    sorobanSecret = saída de: stellar keys secret pilot-soroban
#    classicSecret = saída de: stellar keys secret pilot-classic
#    contractId    = endereço impresso no passo 2
cp harness/.pilot-secrets.example.json harness/.pilot-secrets.json

# 4. Execução
python -m harness.run_pilot --smoke            # 3 operações por mecanismo
python -m harness.run_pilot --window 1         # uma janela: 13 operações por mecanismo, ordem aleatorizada
python -m harness.baseline_probe --minutes 10  # em paralelo, em outro terminal
python -m harness.registration_phase --without --reps 3
python -m harness.registration_phase --with-mechanism control --reps 3
python -m harness.local_primitive
python -m harness.verify_chain

# 5. Análise descritiva
python analysis/pilot_analysis.py
```

As entradas do Rekor são públicas e permanentes por projeto; só hashes são enviados. As chaves de testnet são descartáveis.

## Estrutura

```
contracts/anchor/    Contrato Soroban de ancoragem (Rust, soroban-sdk; contratos Soroban são escritos em Rust)
harness/             Harness de medição (Python)
analysis/            Análise descritiva e resultados brutos por operação (analysis/results/)
tools/               Obtenção dos dados, arquivamento da evidência pública e verificação independente
data/inmet/          Cópia versionada do arquivo bruto do INMET (dados públicos)
evidence/pilot-v1/   Evidência pública arquivada do piloto v1
docs/                Protocolo e resultados
```

## Licença

Apache-2.0. Ver [LICENSE](LICENSE). Os dados meteorológicos são públicos, disponibilizados pelo INMET.
