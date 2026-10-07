import re

import pandas as pd
import plotly.express as px


RED_SCALE = ["#EF4444", "#F87171", "#B91C1C", "#FCA5A5", "#7F1D1D"]


def _name_score(column) -> int:
    name = str(column).lower()
    preferred = ("salary", "wage", "revenue", "amount", "total", "count", "score", "quantity", "price", "age")
    return next((len(preferred) - index for index, word in enumerate(preferred) if word in name), 0)


def _dimension_score(column, series) -> tuple[int, int]:
    name = str(column).lower()
    preferred = ("employee", "name", "department", "category", "date", "month", "year", "label")
    score = next((len(preferred) - index for index, word in enumerate(preferred) if word in name), 0)
    return score, int(series.nunique(dropna=True))


def _style(fig):
    fig.update_layout(
        template="plotly_dark",
        colorway=RED_SCALE,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=12, r=12, t=55, b=12),
    )
    return fig


def create_chart(df: pd.DataFrame):
    """Build a chart appropriate to the columns and values returned by a query."""
    if df is None or df.empty or len(df.columns) == 0:
        return None

    data = df.dropna(how="all").copy()
    if data.empty:
        return None

    numeric = [
        column for column in data.columns
        if pd.api.types.is_numeric_dtype(data[column])
        and not pd.api.types.is_bool_dtype(data[column])
    ]
    dates = [
        column for column in data.columns
        if pd.api.types.is_datetime64_any_dtype(data[column])
        or re.search(r"(date|time|month|year)", str(column), re.I)
    ]
    try:
        if numeric and dates:
            date_column = dates[0]
            chart_data = data[[date_column, numeric[0]]].copy()
            chart_data[date_column] = pd.to_datetime(chart_data[date_column], errors="coerce")
            chart_data = chart_data.dropna().sort_values(date_column)
            if not chart_data.empty:
                return _style(px.line(
                    chart_data,
                    x=date_column,
                    y=numeric[0],
                    markers=True,
                    title=f"{numeric[0]} over time",
                ))

        dimensions = [
            column for column in data.columns
            if column not in numeric and data[column].nunique(dropna=True) > 0
        ]
        if numeric and dimensions and len(data) > 1:
            dimension = max(dimensions, key=lambda col: _dimension_score(col, data[col]))
            measure = max(numeric, key=_name_score)
            chart_data = data[[dimension, measure]].dropna().sort_values(measure, ascending=False).head(30)
            return _style(px.bar(
                chart_data,
                x=dimension,
                y=measure,
                title=f"{measure} by {dimension}",
                color_discrete_sequence=RED_SCALE,
            ))

        if len(numeric) >= 2 and len(data) > 1:
            return _style(px.scatter(
                data,
                x=numeric[0],
                y=numeric[1],
                title=f"{numeric[1]} by {numeric[0]}",
                color_discrete_sequence=RED_SCALE,
            ))

        if len(numeric) > 1 and len(data) == 1:
            values = data[numeric].iloc[0]
            summary = pd.DataFrame({"Measure": values.index, "Value": values.values})
            return _style(px.bar(
                summary,
                x="Measure",
                y="Value",
                title="Query values",
                color_discrete_sequence=RED_SCALE,
            ))

        if numeric:
            column = numeric[0]
            if len(data) == 1:
                chart_data = pd.DataFrame({"Measure": [str(column)], "Value": [data[column].iloc[0]]})
                return _style(px.bar(
                    chart_data,
                    x="Measure",
                    y="Value",
                    title=str(column),
                    color_discrete_sequence=RED_SCALE,
                ))
            return _style(px.histogram(
                data,
                x=column,
                title=f"{column} distribution",
                color_discrete_sequence=RED_SCALE,
            ))

        column = max(data.columns, key=lambda col: data[col].nunique(dropna=True))
        counts = data[column].astype(str).value_counts().head(20).rename_axis(str(column)).reset_index(name="Count")
        return _style(px.bar(
            counts,
            x=str(column),
            y="Count",
            title=f"Records by {column}",
            color_discrete_sequence=RED_SCALE,
        ))
    except (TypeError, ValueError, KeyError):
        return None
