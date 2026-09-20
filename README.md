# BI de Produção

Dashboard em Streamlit para analisar movimentação de produção por setor, facção, coleção, grupo e referência.

## Objetivo

Oferecer indicadores operacionais a partir de uma exportação do ERP, com filtros e análises que apoiam o acompanhamento da produção.

## Análises disponíveis

- Visão geral da produção
- Produção mensal e por setor
- Produção por coleção e grupo
- Fluxo entre setores
- Análise de facções
- Coleções e referências

## Regras de negócio

- A produção consolidada é calculada pela soma de `Qt Aprovada` na etapa **EXPEDIÇÃO**, evitando duplicidade entre as etapas produtivas.
- Ao selecionar apenas um setor, os indicadores passam a refletir o volume daquele setor.
- Sem filtro de setor, os agrupamentos por coleção e grupo consideram somente a etapa **EXPEDIÇÃO**.
- Na análise de facções, `ONCA PRETA DENIM LTDA` inicia desmarcada, mas pode ser incluída manualmente no filtro.
- Os filtros de período usam `Data Saída` e exibem datas no formato `DD/MM/AAAA`.

## Estrutura do projeto

```text
app.py                  # Ponto de entrada do dashboard
pages/                  # Páginas de análise
data/loader.py          # Upload, leitura e validação do arquivo Parquet
requirements.txt        # Dependências Python
```

## Requisitos

- Python 3.12 ou superior
- Um arquivo Parquet de movimentação de produção e um arquivo Parquet de ordens geradas, ambos com a estrutura esperada pela aplicação

## Instalação

```bash
git clone <URL_DO_REPOSITORIO>
cd dados
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

No Windows, ative o ambiente virtual com:

```bash
venv\Scripts\activate
```

## Execução

```bash
streamlit run app.py
```

Ao abrir a aplicação, envie os dois arquivos Parquet solicitados. As bases ficam apenas na sessão do dashboard e não são armazenadas no repositório.

## Tecnologias

- Python
- Streamlit
- Pandas
- PyArrow
