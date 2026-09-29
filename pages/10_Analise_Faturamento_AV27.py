"""Análise de reserva, estoque e pedidos da coleção AV27."""

from pathlib import Path
import sys

import pandas as pd
import streamlit as st

PAGES_DIR = Path(__file__).resolve().parent
if str(PAGES_DIR) not in sys.path:
    sys.path.insert(0, str(PAGES_DIR))

from data.loader import load_data  # noqa: E402
from utils.charts import bar_chart  # noqa: E402
from utils.display import display_dataframe, format_br_number  # noqa: E402
from utils.shared import apply_theme  # noqa: E402


st.set_page_config(page_title="Análise de faturamento AV27 | PPCP", page_icon="📦", layout="wide")
apply_theme()
st.title("Análise de faturamento com estoque — AV27")
st.caption("Reserva, demanda, disponibilidade de faturamento e oportunidades de reposição da coleção AV27.")

stock = load_data("estoque_av27")
orders = load_data("pedidos_venda")
order_items = load_data("pedidos_itens")
if stock is None:
    st.info("Envie o Parquet gerado pelo etl-estoque.py para carregar a posição de estoque.")
    st.stop()

stock = stock.copy()
stock["estoque_pronta_entrega"] = pd.to_numeric(stock["estoque_pronta_entrega"], errors="coerce").fillna(0)
stock["ordem_grade"] = pd.to_numeric(stock["ordem_grade"], errors="coerce")

st.sidebar.header("Filtros de estoque")
selected_references = st.sidebar.multiselect("Referência", sorted(stock["referencia"].dropna().unique().tolist()))
selected_grades = st.sidebar.multiselect("Grade", sorted(stock["grade"].dropna().unique().tolist()))
selected_colors = st.sidebar.multiselect("Cor", sorted(stock["cor"].dropna().unique().tolist()))
only_available = st.sidebar.checkbox("Mostrar somente SKUs com estoque", value=False)

filtered = stock.copy()
if selected_references:
    filtered = filtered.loc[filtered["referencia"].isin(selected_references)]
if selected_grades:
    filtered = filtered.loc[filtered["grade"].isin(selected_grades)]
if selected_colors:
    filtered = filtered.loc[filtered["cor"].isin(selected_colors)]
if only_available:
    filtered = filtered.loc[filtered["estoque_pronta_entrega"] > 0]

if filtered.empty:
    st.warning("Nenhum SKU encontrado com os filtros selecionados.")
    st.stop()

total_stock = filtered["estoque_pronta_entrega"].sum()
total_skus = filtered["sku"].nunique()
available_skus = filtered.loc[filtered["estoque_pronta_entrega"] > 0, "sku"].nunique()
zero_skus = total_skus - available_skus

c1, c2, c3, c4 = st.columns(4)
c1.metric("Peças em estoque pronta-entrega", format_br_number(total_stock), help="Quantidade total de peças disponíveis para pronta-entrega.")
c2.metric("SKUs", format_br_number(total_skus), help="SKU é a combinação única de referência | grade | cor.")
c3.metric("SKUs disponíveis", format_br_number(available_skus), help="Combinações únicas de referência | grade | cor com pelo menos uma peça em estoque.")
c4.metric("SKUs sem estoque", format_br_number(zero_skus), help="Combinações únicas de referência | grade | cor sem nenhuma peça em estoque.")

st.subheader("Demanda de pedidos versus estoque")
if orders is None or order_items is None:
    st.info("Envie também os Parquets de pedidos para calcular sobra e falta por SKU.")
else:
    orders_work = orders.copy()
    orders_work["codpedido"] = pd.to_numeric(orders_work["codpedido"], errors="coerce").astype("Int64")
    orders_work["codcliente"] = pd.to_numeric(orders_work["codcliente"], errors="coerce").astype("Int64")
    open_order_ids = orders_work.loc[
        orders_work["situacaopedido"].isin(["EM ANALISE", "PARCIAL"])
        & orders_work["codcliente"].ne(1),
        "codpedido",
    ].dropna().unique()
    demand = order_items.copy()
    demand["codpedido"] = pd.to_numeric(demand["codpedido"], errors="coerce").astype("Int64")
    demand = demand.loc[demand["codpedido"].isin(open_order_ids)].copy()
    if selected_references:
        demand = demand.loc[demand["referencia"].isin(selected_references)]
    if selected_grades:
        demand = demand.loc[demand["grade"].isin(selected_grades)]
    if selected_colors:
        demand = demand.loc[demand["cor"].isin(selected_colors)]

    demand_sku = (
        demand.groupby(["sku", "referencia", "grade", "cor"], as_index=False)
        .agg(
            DEMANDA_PEDIDA=("qtdepedida", "sum"),
            DEMANDA_PENDENTE=("qtdesaldo", "sum"),
            FATURADO=("qtdefaturado", "sum"),
        )
    )
    stock_sku = filtered[["sku", "referencia", "grade", "cor", "estoque_pronta_entrega", "ordem_grade"]].copy()
    comparison = stock_sku.merge(
        demand_sku,
        on=["sku", "referencia", "grade", "cor"],
        how="outer",
    )
    for column in ["estoque_pronta_entrega", "DEMANDA_PEDIDA", "DEMANDA_PENDENTE", "FATURADO"]:
        comparison[column] = pd.to_numeric(comparison[column], errors="coerce").fillna(0)
    comparison["ordem_grade"] = pd.to_numeric(comparison["ordem_grade"], errors="coerce")
    comparison["SALDO_APOS_DEMANDA"] = comparison["estoque_pronta_entrega"] - comparison["DEMANDA_PENDENTE"]
    comparison["SOBRA"] = comparison["SALDO_APOS_DEMANDA"].clip(lower=0)
    comparison["FALTA"] = (-comparison["SALDO_APOS_DEMANDA"]).clip(lower=0)
    comparison["SITUACAO"] = comparison["SALDO_APOS_DEMANDA"].map(
        lambda value: "Falta" if value < 0 else "Sobra" if value > 0 else "Equilibrado"
    )
    comparison = comparison.sort_values(["FALTA", "referencia", "cor", "ordem_grade"], ascending=[False, True, True, True])

    shortage = comparison["FALTA"].sum()
    surplus = comparison["SOBRA"].sum()
    demand_total = comparison["DEMANDA_PENDENTE"].sum()
    d1, d2, d3, d4 = st.columns(4)
    d1.metric("Demanda pendente", format_br_number(demand_total))
    d2.metric("Estoque para atendimento", format_br_number(comparison["estoque_pronta_entrega"].sum()))
    d3.metric("Falta estimada", format_br_number(shortage))
    d4.metric("Sobra estimada", format_br_number(surplus))
    display_dataframe(
        comparison,
        labels={"sku": "SKU", "referencia": "Referência", "grade": "Grade", "cor": "Cor", "ordem_grade": "Ordem da grade", "estoque_pronta_entrega": "Estoque", "DEMANDA_PEDIDA": "Demanda pedida", "DEMANDA_PENDENTE": "Demanda pendente", "FATURADO": "Faturado", "SALDO_APOS_DEMANDA": "Saldo após demanda", "SOBRA": "Sobra", "FALTA": "Falta", "SITUACAO": "Situação"},
        number_formats={"ordem_grade": 0, "estoque_pronta_entrega": 0, "DEMANDA_PEDIDA": 0, "DEMANDA_PENDENTE": 0, "FATURADO": 0, "SALDO_APOS_DEMANDA": 0, "SOBRA": 0, "FALTA": 0},
        hide_index=True,
    )

    st.subheader("Modelo de faturamento com estoque disponível")
    st.caption(
        "A análise desconsidera a previsão de entrega. Os pedidos em aberto são priorizados pelo maior valor pendente e, em seguida, pela menor quebra. "
        "O pedido só entra no valor disponível quando todos os seus SKUs podem ser atendidos com o estoque restante."
    )
    allocation = demand.copy()
    allocation["qtdesaldo"] = pd.to_numeric(allocation["qtdesaldo"], errors="coerce").fillna(0)
    allocation["valorunitariobruto"] = pd.to_numeric(allocation["valorunitariobruto"], errors="coerce").fillna(0)
    allocation = allocation.loc[allocation["qtdesaldo"] > 0].copy()

    if allocation.empty:
        st.info("Não há demanda pendente para simular o faturamento com o estoque disponível.")
    else:
        allocation["VALOR_PENDENTE"] = allocation["qtdesaldo"] * allocation["valorunitariobruto"]
        order_sku = (
            allocation.groupby(["codpedido", "sku"], as_index=False)
            .agg(
                DEMANDA=("qtdesaldo", "sum"),
                VALOR_PENDENTE=("VALOR_PENDENTE", "sum"),
            )
        )
        stock_by_sku = filtered.groupby("sku")["estoque_pronta_entrega"].sum().to_dict()
        order_rows = []
        for order_id, order_group in order_sku.groupby("codpedido", sort=False):
            shortages = [
                max(float(row.DEMANDA) - float(stock_by_sku.get(row.sku, 0)), 0)
                for row in order_group.itertuples()
            ]
            order_rows.append(
                {
                    "codpedido": order_id,
                    "VALOR_PENDENTE": order_group["VALOR_PENDENTE"].sum(),
                    "DEMANDA": order_group["DEMANDA"].sum(),
                    "SKUS": order_group["sku"].nunique(),
                    "SKUS_COM_FALTA": sum(value > 0 for value in shortages),
                    "UNIDADES_EM_FALTA": sum(shortages),
                }
            )
        allocation_summary = pd.DataFrame(order_rows)
        allocation_summary = allocation_summary.merge(
            orders_work[["codpedido", "nomecliente", "dataemissao"]].drop_duplicates("codpedido"),
            on="codpedido",
            how="left",
        )
        allocation_summary = allocation_summary.sort_values(
            ["VALOR_PENDENTE", "SKUS_COM_FALTA", "UNIDADES_EM_FALTA", "codpedido"],
            ascending=[False, True, True, True],
        ).reset_index(drop=True)

        remaining_stock = stock_by_sku.copy()
        selected_orders = []
        for row in allocation_summary.itertuples():
            requirements = order_sku.loc[order_sku["codpedido"].eq(row.codpedido)]
            can_fulfill = all(
                float(remaining_stock.get(item.sku, 0)) >= float(item.DEMANDA)
                for item in requirements.itertuples()
            )
            selected_orders.append(can_fulfill)
            if can_fulfill:
                for item in requirements.itertuples():
                    remaining_stock[item.sku] = float(remaining_stock.get(item.sku, 0)) - float(item.DEMANDA)
        allocation_summary["ATENDIMENTO_100"] = selected_orders
        allocation_summary["SITUACAO"] = allocation_summary["ATENDIMENTO_100"].map(
            {True: "Selecionado para faturamento", False: "Não selecionado"}
        )

        selected = allocation_summary.loc[allocation_summary["ATENDIMENTO_100"]]
        potential_value = allocation_summary["VALOR_PENDENTE"].sum()
        available_value = selected["VALOR_PENDENTE"].sum()
        a1, a2, a3, a4 = st.columns(4)
        a1.metric("Valor pendente total", f"R$ {format_br_number(potential_value, 2)}")
        a2.metric("Disponível para faturar", f"R$ {format_br_number(available_value, 2)}")
        a3.metric("Pedidos atendidos em 100%", format_br_number(len(selected)))
        a4.metric("Unidades faturáveis", format_br_number(selected["DEMANDA"].sum()))
        display_dataframe(
            allocation_summary,
            labels={"codpedido": "Pedido", "nomecliente": "Cliente", "dataemissao": "Data de emissão", "VALOR_PENDENTE": "Valor pendente (R$)", "DEMANDA": "Unidades pendentes", "SKUS": "SKUs", "SKUS_COM_FALTA": "SKUs com falta", "UNIDADES_EM_FALTA": "Unidades em falta", "SITUACAO": "Situação"},
            number_formats={"codpedido": 0, "VALOR_PENDENTE": 2, "DEMANDA": 0, "SKUS": 0, "SKUS_COM_FALTA": 0, "UNIDADES_EM_FALTA": 0},
            date_formats={"dataemissao": "DD/MM/YYYY"},
            hide_index=True,
        )

        st.subheader("Referências e SKUs para aumentar o faturamento disponível")
        st.caption(
            "O relatório prioriza os SKUs que, quando repostos, desbloqueiam pedidos com uma única pendência. "
            "Retorno é o valor pendente do pedido desbloqueado; esforço é o valor de venda estimado das unidades necessárias."
        )
        unit_prices = (
            allocation.groupby("sku", as_index=False)
            .agg(QTD=("qtdesaldo", "sum"), VALOR=("VALOR_PENDENTE", "sum"))
        )
        unit_prices["PRECO_UNITARIO"] = unit_prices["VALOR"].div(unit_prices["QTD"].replace(0, pd.NA)).fillna(0)
        sku_metadata = allocation[["sku", "referencia", "grade", "cor"]].drop_duplicates("sku")
        unit_prices = unit_prices.merge(sku_metadata, on="sku", how="left")

        blocked_orders = allocation_summary.loc[~allocation_summary["ATENDIMENTO_100"]].copy()
        blocker_rows = []
        for row in blocked_orders.itertuples():
            requirements = order_sku.loc[order_sku["codpedido"].eq(row.codpedido)].copy()
            requirements["ESTOQUE_RESTANTE"] = requirements["sku"].map(remaining_stock).fillna(0)
            requirements["FALTA"] = (requirements["DEMANDA"] - requirements["ESTOQUE_RESTANTE"]).clip(lower=0)
            requirements = requirements.loc[requirements["FALTA"] > 0]
            for item in requirements.itertuples():
                unit_price = float(unit_prices.loc[unit_prices["sku"].eq(item.sku), "PRECO_UNITARIO"].iloc[0]) if item.sku in set(unit_prices["sku"]) else 0
                blocker_rows.append(
                    {
                        "codpedido": row.codpedido,
                        "sku": item.sku,
                        "FALTA": float(item.FALTA),
                        "ESFORCO": float(item.FALTA) * unit_price,
                        "VALOR_PEDIDO": float(row.VALOR_PENDENTE),
                        "SKUS_COM_FALTA": int(row.SKUS_COM_FALTA),
                    }
                )

        if not blocker_rows:
            st.info("Não há SKUs pendentes identificados para desbloquear faturamento adicional.")
        else:
            blockers = pd.DataFrame(blocker_rows).merge(sku_metadata, on="sku", how="left")
            single_blockers = blockers.loc[blockers["SKUS_COM_FALTA"].eq(1)].copy()
            sku_unlock = (
                single_blockers.groupby(["sku", "referencia", "grade", "cor"], as_index=False)
                .agg(
                    PEDIDOS_DESBLOQUEADOS=("codpedido", "nunique"),
                    UNIDADES_NECESSARIAS=("FALTA", "sum"),
                    ESFORCO_R=("ESFORCO", "sum"),
                    RETORNO_R=("VALOR_PEDIDO", "sum"),
                )
            )
            sku_unlock["RETORNO_SOBRE_ESFORCO"] = sku_unlock["RETORNO_R"].div(sku_unlock["ESFORCO_R"].replace(0, pd.NA)).fillna(0)
            sku_unlock = sku_unlock.sort_values(["RETORNO_SOBRE_ESFORCO", "RETORNO_R"], ascending=[False, False])
            if sku_unlock.empty:
                st.info("Nenhum SKU isolado desbloqueia um pedido integralmente; avalie a tabela de referências abaixo para reposições combinadas.")
            else:
                display_dataframe(
                    sku_unlock,
                    labels={"sku": "SKU", "referencia": "Referência", "grade": "Grade", "cor": "Cor", "PEDIDOS_DESBLOQUEADOS": "Pedidos desbloqueados", "UNIDADES_NECESSARIAS": "Unidades necessárias", "ESFORCO_R": "Esforço estimado (R$)", "RETORNO_R": "Retorno potencial (R$)", "RETORNO_SOBRE_ESFORCO": "Retorno / esforço (x)"},
                    number_formats={"PEDIDOS_DESBLOQUEADOS": 0, "UNIDADES_NECESSARIAS": 0, "ESFORCO_R": 2, "RETORNO_R": 2, "RETORNO_SOBRE_ESFORCO": 2},
                    hide_index=True,
                )

            reference_unlock = (
                blockers.groupby("referencia", as_index=False)
                .agg(
                    PEDIDOS_COM_FALTA=("codpedido", "nunique"),
                    UNIDADES_NECESSARIAS=("FALTA", "sum"),
                    ESFORCO_R=("ESFORCO", "sum"),
                    RETORNO_ASSOCIADO_R=("VALOR_PEDIDO", "sum"),
                )
            )
            reference_unlock["RETORNO_SOBRE_ESFORCO"] = reference_unlock["RETORNO_ASSOCIADO_R"].div(reference_unlock["ESFORCO_R"].replace(0, pd.NA)).fillna(0)
            reference_unlock = reference_unlock.sort_values(["RETORNO_SOBRE_ESFORCO", "RETORNO_ASSOCIADO_R"], ascending=[False, False])
            st.markdown("**Visão consolidada por referência**")
            display_dataframe(
                reference_unlock,
                labels={"referencia": "Referência", "PEDIDOS_COM_FALTA": "Pedidos com falta", "UNIDADES_NECESSARIAS": "Unidades necessárias", "ESFORCO_R": "Esforço estimado (R$)", "RETORNO_ASSOCIADO_R": "Retorno associado (R$)", "RETORNO_SOBRE_ESFORCO": "Retorno / esforço (x)"},
                number_formats={"PEDIDOS_COM_FALTA": 0, "UNIDADES_NECESSARIAS": 0, "ESFORCO_R": 2, "RETORNO_ASSOCIADO_R": 2, "RETORNO_SOBRE_ESFORCO": 2},
                hide_index=True,
            )

        st.subheader("Faturamento parcial com grade cheia por cor")
        st.caption(
            "Neste cenário, o pedido pode ser faturado parcialmente. Uma referência só é considerada faturável quando todos os tamanhos requisitados daquela cor têm estoque suficiente, evitando furo de grade."
        )
        grade_items = allocation.groupby(
            ["codpedido", "referencia", "cor", "grade", "sku"], as_index=False
        ).agg(
            DEMANDA=("qtdesaldo", "sum"),
            VALOR_PENDENTE=("VALOR_PENDENTE", "sum"),
        )
        grade_groups = (
            grade_items.groupby(["codpedido", "referencia", "cor"], as_index=False)
            .agg(
                DEMANDA=("DEMANDA", "sum"),
                VALOR_PENDENTE=("VALOR_PENDENTE", "sum"),
                GRADES=("grade", "nunique"),
            )
        )
        grade_stock = filtered.groupby("sku")["estoque_pronta_entrega"].sum().to_dict()
        grade_rows = []
        for group_key, group in grade_items.groupby(["codpedido", "referencia", "cor"], sort=False):
            order_id, reference, color = group_key
            missing = [
                max(float(item.DEMANDA) - float(grade_stock.get(item.sku, 0)), 0)
                for item in group.itertuples()
            ]
            grade_rows.append(
                {
                    "codpedido": order_id,
                    "referencia": reference,
                    "cor": color,
                    "DEMANDA": group["DEMANDA"].sum(),
                    "VALOR_PENDENTE": group["VALOR_PENDENTE"].sum(),
                    "GRADES": group["grade"].nunique(),
                    "GRADES_COM_FALTA": sum(value > 0 for value in missing),
                    "UNIDADES_EM_FALTA": sum(missing),
                }
            )
        grade_summary = pd.DataFrame(grade_rows).sort_values(
            ["VALOR_PENDENTE", "GRADES_COM_FALTA", "UNIDADES_EM_FALTA", "codpedido"],
            ascending=[False, True, True, True],
        ).reset_index(drop=True)
        grade_remaining = filtered.groupby("sku")["estoque_pronta_entrega"].sum().to_dict()
        grade_selected = []
        for row in grade_summary.itertuples():
            requirements = grade_items.loc[
                grade_items["codpedido"].eq(row.codpedido)
                & grade_items["referencia"].eq(row.referencia)
                & grade_items["cor"].eq(row.cor)
            ]
            can_fulfill = all(
                float(grade_remaining.get(item.sku, 0)) >= float(item.DEMANDA)
                for item in requirements.itertuples()
            )
            grade_selected.append(can_fulfill)
            if can_fulfill:
                for item in requirements.itertuples():
                    grade_remaining[item.sku] = float(grade_remaining.get(item.sku, 0)) - float(item.DEMANDA)
        grade_summary["GRADE_CHEIA"] = grade_selected
        grade_summary["SITUACAO"] = grade_summary["GRADE_CHEIA"].map(
            {True: "Faturável — grade cheia", False: "Não faturável — há furo de grade"}
        )
        grade_selected_summary = grade_summary.loc[grade_summary["GRADE_CHEIA"]]
        g1, g2, g3, g4 = st.columns(4)
        g1.metric("Valor com grade cheia", f"R$ {format_br_number(grade_selected_summary['VALOR_PENDENTE'].sum(), 2)}")
        g2.metric("Referências faturáveis", format_br_number(grade_selected_summary["referencia"].nunique()))
        g3.metric("Grades por cor faturáveis", format_br_number(len(grade_selected_summary)))
        g4.metric("Unidades faturáveis", format_br_number(grade_selected_summary["DEMANDA"].sum()))
        display_dataframe(
            grade_summary,
            labels={"codpedido": "Pedido", "referencia": "Referência", "cor": "Cor", "DEMANDA": "Unidades pendentes", "VALOR_PENDENTE": "Valor pendente (R$)", "GRADES": "Tamanhos requisitados", "GRADES_COM_FALTA": "Tamanhos em falta", "UNIDADES_EM_FALTA": "Unidades em falta", "SITUACAO": "Situação"},
            number_formats={"codpedido": 0, "DEMANDA": 0, "VALOR_PENDENTE": 2, "GRADES": 0, "GRADES_COM_FALTA": 0, "UNIDADES_EM_FALTA": 0},
            hide_index=True,
        )
