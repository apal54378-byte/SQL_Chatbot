import os
import re
from functools import lru_cache

import pandas as pd
from dotenv import load_dotenv
from langchain_groq import ChatGroq
from sqlalchemy import text
from database import get_engine
from visualization import create_chart

load_dotenv()


@lru_cache(maxsize=1)
def _get_llm():
    if not os.getenv("GROQ_API_KEY"):
        raise ValueError("Missing GROQ_API_KEY. Add it to your .env file to generate answers.")
    return ChatGroq(model="openai/gpt-oss-120b", temperature=0)


def _response_text(response) -> str:
    content = response.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            str(block.get("text", "")) if isinstance(block, dict) else str(block)
            for block in content
        )
    return str(content)


def get_schema():
    from sqlalchemy import inspect
    inspector = inspect(get_engine())
    parts = []
    for table in inspector.get_table_names():
        parts.extend([f"Table: {table}", "Columns:"])
        parts.extend(f"{col['name']} {col['type']}" for col in inspector.get_columns(table))
        parts.append("")
    return "\n".join(parts) if parts else "No tables found."


def generate_sql(user_query: str) -> str:
    prompt = f"""
You are a SQL query generator. Database: PostgreSQL.
Database schema:
{get_schema()}

Convert the user's question into one PostgreSQL read-only query.
Return only SQL, without markdown or explanation. Use only schema tables and columns.
Generate only SELECT or WITH ... SELECT queries.
- When the user asks how many or asks for a count, use COUNT(*) and return a clear count column.
- If the question asks for a count within a group (such as employees in a department), filter to that group and return the matching count.
- If the user explicitly asks for counts by multiple groups, group by the requested category.

User question:
{user_query}
"""
    response = _get_llm().invoke(prompt)
    sql_query = _response_text(response).strip()
    sql_query = re.sub(r"^```[a-zA-Z0-9_+-]*\s*", "", sql_query)
    sql_query = re.sub(r"\s*```$", "", sql_query)
    sql_query = sql_query.replace("`", "").strip()
    return sql_query[:-1].strip() if sql_query.endswith(";") else sql_query


def _sql_tokens(sql_query: str) -> list[str]:
    cleaned = re.sub(r"/\*.*?\*/", " ", sql_query, flags=re.S)
    cleaned = re.sub(r"--[^\r\n]*", " ", cleaned)
    cleaned = re.sub(r"'(?:''|\\.|[^'])*'", "''", cleaned)
    cleaned = re.sub(r'"(?:""|[^"])*"', '""', cleaned)
    return re.findall(r"[a-z_][a-z0-9_$]*|;", cleaned.lower())


def is_select_query(sql_query: str) -> bool:
    if not sql_query or not sql_query.strip():
        return False
    tokens = _sql_tokens(sql_query)
    return bool(tokens) and tokens[0] in {"select", "with"}


def is_safe_sql(sql_query: str) -> bool:
    if not is_select_query(sql_query):
        return False
    tokens = _sql_tokens(sql_query)
    if tokens.count(";") > 1 or (";" in tokens and tokens[-1] != ";"):
        return False
    forbidden = {
        "insert", "update", "delete", "drop", "alter", "truncate", "create",
        "grant", "revoke", "execute", "call", "merge", "replace", "copy",
        "vacuum", "analyze", "into",
    }
    return not forbidden.intersection(tokens)


def execute_sql(sql_query: str) -> pd.DataFrame:
    if not is_select_query(sql_query) or not is_safe_sql(sql_query):
        raise ValueError("Only one read-only SELECT query is allowed.")
    with get_engine().connect() as connection:
        with connection.begin():
            connection.exec_driver_sql("SET TRANSACTION READ ONLY")
            connection.exec_driver_sql("SET LOCAL statement_timeout = '30000ms'")
            result = connection.execute(text(sql_query))
            rows, columns = result.fetchmany(10_001), result.keys()
    truncated = len(rows) > 10_000
    df = pd.DataFrame(rows[:10_000], columns=columns)
    df.attrs["truncated"] = truncated
    return df


def generate_answer(user_query: str, df: pd.DataFrame) -> str:
    if df is None or df.empty:
        return "No matching records were found."
    preview = df.head(100).to_string(index=False)
    omitted = len(df) - min(len(df), 100)
    note = f"{omitted} additional rows omitted from this summary." if omitted else ""
    if df.attrs.get("truncated"):
        note += " The query result was capped at 10,000 rows."
    prompt = f"""
Answer the user's question using only the database result. Be concise, do not mention SQL, and do not invent information.
Question: {user_query}
Database result (up to 100 rows):
{preview}
{note}
"""
    try:
        return _response_text(_get_llm().invoke(prompt))
    except Exception as exc:
        return f"Results were retrieved, but a summary could not be generated: {exc}"


def ask_database(user_query: str):
    try:
        sql_query = generate_sql(user_query)
        df = execute_sql(sql_query)
        return df, generate_answer(user_query, df), create_chart(df), sql_query
    except Exception as exc:
        return None, str(exc), None, None


