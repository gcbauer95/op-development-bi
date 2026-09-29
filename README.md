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
- Pedidos vendidos e SKUs da coleção AV27
- Estoque pronta-entrega por referência, grade, cor e SKU
- Análise de faturamento potencial, reservas e grade cheia por cor na coleção AV27

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

## Design System

A interface segue uma adaptação do design system do OpenCode.ai para dashboards Streamlit. A especificação técnica de referência é o [`DESIGN.md`](https://getdesign.md/design-md/opencode.ai/DESIGN.md), com o [preview visual](https://getdesign.md/design-md/opencode.ai/preview) usado para validar composição e hierarquia.

### Organização

- `assets/css/style.css`: tokens CSS e estilos globais do app.
- `utils/styles.py`: carregamento centralizado do CSS e tema opcional para figuras Plotly.
- `utils/charts.py`: renderizadores compartilhados de linhas e barras, com margens, legenda e tema consistentes.
- `utils/shared.py`: filtros e funções de análise compartilhadas.
- `etl-pedidos.py`: tratamento dos Excel de pedidos, criação de SKU e geração dos arquivos Parquet.
- `etl-estoque.py`: tratamento da posição de estoque AV27 e geração dos arquivos Parquet.

### Tokens principais

- Canvas: `#fdfcfc`.
- Tinta principal: `#201d1d`; tinta pressionada: `#0f0000`.
- Superfícies: `#f8f7f7` e `#f1eeee`.
- Texto secundário: `#424245`, `#646262` e `#6e6e73`.
- Bordas: hairline `rgba(15, 0, 0, 0.12)` e forte `#646262`.
- Tipografia: pilha monoespaçada com Berkeley Mono como primeira opção.
- Raios: `0px` para estruturas e `4px` para controles interativos.
- Espaçamento: escala baseada em 8px, com ritmo de seção de 96px.
- Profundidade: sem sombras; a hierarquia usa superfícies planas e bordas finas.

### Componentes

KPIs, filtros, uploads, tabelas, alertas, navegação e controles nativos do Streamlit recebem o mesmo tratamento de cores, tipografia, bordas, estados de foco e espaçamento. A sidebar concentra navegação e filtros, com a página ativa destacada por fundo escuro e texto claro.

### Gráficos

Para novas figuras Plotly, use `line_chart` e `bar_chart` de `utils.charts`, ou aplique `apply_chart_theme` de `utils.styles` a uma figura customizada. Os helpers aplicam canvas, tipografia, grid, eixos, margens, legendas e hover consistentes com o design system. Os gráficos existentes mantêm os mesmos DataFrames e regras de negócio.

### Como criar uma nova página

1. Coloque o arquivo em `pages/` seguindo o padrão de nomenclatura existente.
2. Importe `apply_theme` de `pages._shared` e execute-o após `st.set_page_config`.
3. Reutilize `sidebar_filters`, `production_caption` e as funções compartilhadas antes de criar novos estilos.
4. Para alterar globalmente cores, fonte, cards, sidebar, tabelas ou gráficos, edite `assets/css/style.css` ou `utils/styles.py`; não replique CSS dentro das páginas.
