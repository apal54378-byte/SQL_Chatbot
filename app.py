import re
from pathlib import Path

import streamlit as st

from agent import execute_sql, generate_answer, generate_sql, is_safe_sql, is_select_query
from database import get_engine, missing_database_settings
from visualization import create_chart

st.set_page_config(
    page_title="Ask your data",
    page_icon=":material/query_stats:",
    layout="wide",
)


def load_css():
    css_path = Path(__file__).parent / "app.css"
    try:
        st.markdown(f"<style>{css_path.read_text(encoding='utf-8-sig')}</style>", unsafe_allow_html=True)
    except OSError:
        pass


load_css()

st.session_state.setdefault("query_history", [])
st.session_state.setdefault("result_view", "With graph")
st.session_state.setdefault("query_input", "")
st.session_state.setdefault("active_question", "")
st.session_state.setdefault("answer", "")
st.session_state.setdefault("result_df", None)
st.session_state.setdefault("chart", None)
st.session_state.setdefault("sql", "")
st.session_state.setdefault("error", "")


@st.cache_data(ttl=15, max_entries=1, show_spinner=False)
def database_health():
    missing = missing_database_settings()
    if missing:
        return False, f"Missing settings: {', '.join(missing)}"
    try:
        with get_engine().connect() as connection:
            connection.exec_driver_sql("SELECT 1")
        return True, "Connected"
    except Exception as exc:
        return False, str(exc)


def remember_question(question: str):
    question = question.strip()
    if question:
        history = [item for item in st.session_state.query_history if item != question]
        st.session_state.query_history = (history + [question])[-20:]


def select_question(question: str):
    st.session_state.query_input = question
    st.session_state.active_question = ""
    st.session_state.answer = ""
    st.session_state.result_df = None
    st.session_state.chart = None
    st.session_state.sql = ""
    st.session_state.error = ""



def query_count(question: str, sql: str, df):
    """Return an explicit count when the question asks how many."""
    if not re.search(r"\b(how many|count|number of|total number)\b", question, re.I):
        return None

    numeric_columns = set(df.select_dtypes(include="number").columns)
    count_columns = [
        column for column in df.columns
        if column in numeric_columns
        and re.search(r"(?<![a-z])(count|headcount|employees?_total|total_employees?)(?![a-z])", str(column), re.I)
    ]
    if count_columns and not df.empty:
        return df[count_columns].sum(numeric_only=True).sum()

    if re.search(r"\bcount\s*\(", sql, re.I) and df.shape == (1, 1):
        return df.iat[0, 0]

    return len(df) if not df.attrs.get("truncated") else None


def display_count(value):
    try:
        numeric = float(value)
        return f"{int(numeric):,}" if numeric.is_integer() else f"{numeric:,.2f}"
    except (TypeError, ValueError):
        return str(value)


def reset_workspace():
    select_question("")
    st.session_state.query_input = ""


def set_result_view(view: str):
    st.session_state.result_view = view


db_connected, db_message = database_health()

with st.sidebar:
    st.markdown("## Ask your data")
    st.caption("A simple way to explore your PostgreSQL database.")

    st.markdown("### Database")
    if db_connected:
        st.badge("Connected", icon=":material/check_circle:", color="green")
    else:
        st.badge("Unavailable", icon=":material/error:", color="red")
        st.caption(db_message)

    st.markdown("### Recent questions")
    if st.session_state.query_history:
        for index, question in enumerate(reversed(st.session_state.query_history[-8:])):
            st.button(
                question,
                key=f"recent_{index}",
                icon=":material/history:",
                width="stretch",
                on_click=select_question,
                args=(question,),
            )
    else:
        st.caption("Questions you ask will appear here.")

st.title("Ask your data")
st.caption("Write a question in plain language. We will find the answer and show you the results.")

with st.container(border=True):
    st.markdown("#### What would you like to know?")
    st.caption("Choose how you want to see the result")
    graph_col, table_col = st.columns(2)
    graph_col.button(
        "With graph",
        icon=":material/bar_chart:",
        type="primary" if st.session_state.result_view == "With graph" else "secondary",
        width="stretch",
        on_click=set_result_view,
        args=("With graph",),
    )
    table_col.button(
        "Results only",
        icon=":material/table_rows:",
        type="primary" if st.session_state.result_view == "Results only" else "secondary",
        width="stretch",
        on_click=set_result_view,
        args=("Results only",),
    )
    with st.form("question_form", border=False):
        query = st.text_area(
            "Your question",
            placeholder="For example: Which department has the highest average salary?",
            height=92,
            key="query_input",
        )
        submitted = st.form_submit_button(
            "Ask question",
            type="primary",
            icon=":material/arrow_forward:",
            disabled=not db_connected,
        )

if st.session_state.result_df is None and not st.session_state.active_question:
    st.caption("A few ideas to get started")
    suggestion_columns = st.columns(2)
    suggestions = [
        "Show all employees",
        "Which department has the highest average salary?",
        "Show employees who joined after 2023",
        "Count records in each department",
    ]
    for index, suggestion in enumerate(suggestions):
        suggestion_columns[index % 2].button(
            suggestion,
            key=f"suggestion_{index}",
            icon=":material/arrow_outward:",
            width="stretch",
            on_click=select_question,
            args=(suggestion,),
        )

if submitted:
    question = query.strip()
    st.session_state.error = ""
    st.session_state.active_question = question
    st.session_state.answer = ""
    st.session_state.result_df = None
    st.session_state.chart = None
    st.session_state.sql = ""

    if not question:
        st.session_state.error = "Write a question first."
    else:
        remember_question(question)
        try:
            with st.spinner("Finding your answer..."):
                sql_query = generate_sql(question)
                if not is_select_query(sql_query) or not is_safe_sql(sql_query):
                    raise ValueError("The generated query did not pass the read-only safety check.")
                result_df = execute_sql(sql_query)
                answer = generate_answer(question, result_df)
                chart = create_chart(result_df)

            st.session_state.sql = sql_query
            st.session_state.result_df = result_df
            st.session_state.answer = answer
            st.session_state.chart = chart
        except Exception as exc:
            st.session_state.error = f"We couldn’t answer that question: {exc}"

if st.session_state.error:
    st.error(st.session_state.error)


if st.session_state.result_df is not None:
    result_df = st.session_state.result_df
    count = query_count(st.session_state.active_question, st.session_state.sql, result_df)

    st.markdown("### Your result")
    with st.container(border=True):
        st.caption(st.session_state.active_question)
        if count is not None:
            count_label = (
                "Employees matching your question"
                if re.search(r"\b(employee|employees|staff)\b", st.session_state.active_question, re.I)
                else "Count matching your question"
            )
            st.metric(count_label, display_count(count))
        st.write(st.session_state.answer or "No matching records were found.")

    if result_df.attrs.get("truncated"):
        st.caption("Showing the first 10,000 rows. Make your question more specific to narrow the results.")

    st.markdown("### Matching data")
    st.caption(f"{len(result_df):,} rows | {len(result_df.columns):,} columns")
    st.dataframe(result_df, hide_index=True, height="auto")

    download_col, new_question_col, _ = st.columns([1.4, 1.7, 5])
    with download_col:
        st.download_button(
            "Download CSV",
            result_df.to_csv(index=False).encode("utf-8"),
            file_name="query-results.csv",
            mime="text/csv",
            icon=":material/download:",
        )
    with new_question_col:
        st.button("Ask another question", icon=":material/add:", on_click=reset_workspace)

    if st.session_state.result_view == "With graph" and st.session_state.chart is not None:
        with st.container(border=True):
            st.markdown("#### Chart")
            st.plotly_chart(st.session_state.chart, width="stretch")
    elif st.session_state.result_view == "With graph":
        st.caption("A suitable chart could not be generated for this result.")

    if st.session_state.sql:
        with st.expander("View generated SQL"):
            st.code(st.session_state.sql, language="sql")
