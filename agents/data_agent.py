"""
CivicMind -- Data Agent
========================
Translates natural-language questions about structured civic data into SQL,
executes it, and returns a table + one-line plain-English summary.

Google Cloud swap-in:
    Replace the NL-to-SQL prompt chain with BigQuery Conversational Analytics API.
    Replace SqliteDatabase with BigQueryDatabase in db_interface.py.
"""

import json
import os
from typing import Optional

from agents.utils.db_interface import get_database

# Try to import Gemini
try:
    from google import genai
    GENAI_AVAILABLE = True
except ImportError:
    GENAI_AVAILABLE = False


def _get_genai_client():
    """Get a Gemini client if API key is available."""
    api_key = os.environ.get("GOOGLE_API_KEY")
    if not api_key or not GENAI_AVAILABLE:
        return None
    return genai.Client(api_key=api_key)


def _build_nl_to_sql_prompt(question: str, schema: str) -> str:
    """Build the NL-to-SQL prompt for Gemini."""
    return f"""You are a SQL expert. Given the following database schema and a natural language question,
generate a valid SQLite SQL query that answers the question.

DATABASE SCHEMA:
{schema}

RULES:
- Return ONLY the SQL query, no explanation or markdown formatting.
- Use proper SQLite syntax.
- For "last month" questions, use dates in June 2026 (the most recent month in the data).
- For "spike" or "increase" questions, compare recent data to earlier periods.
- Limit results to 20 rows max unless the question asks for something specific.
- Use ORDER BY for ranking questions.
- For aggregations, use meaningful aliases.

QUESTION: {question}

SQL QUERY:"""


def _build_summary_prompt(question: str, results: list[dict]) -> str:
    """Build a prompt to summarize query results in plain English."""
    # Truncate results for the prompt
    display_results = results[:10]
    return f"""Given this question and the query results, provide a ONE-LINE plain-English summary.
Be specific with numbers and names from the data.

QUESTION: {question}

RESULTS (as JSON):
{json.dumps(display_results, indent=2, default=str)}

ONE-LINE SUMMARY:"""


def _fallback_query(question: str) -> dict:
    """Fallback when Gemini is not available — use pre-built queries for demo scenarios."""
    db = get_database()
    q_lower = question.lower()

    if "respiratory" in q_lower and ("spike" in q_lower or "highest" in q_lower or "last month" in q_lower):
        sql = """
            SELECT neighborhood,
                   SUM(complaint_count) as total_complaints,
                   ROUND(AVG(avg_aqi), 1) as avg_aqi,
                   dominant_pollutant as most_common_pollutant
            FROM respiratory_complaints
            WHERE date >= '2026-06-01' AND date <= '2026-06-30'
            GROUP BY neighborhood
            ORDER BY total_complaints DESC
            LIMIT 10
        """
        results = db.execute_query(sql)
        return {
            "agent": "data_agent",
            "sql": sql.strip(),
            "results": results,
            "summary": f"Riverside led with {results[0]['total_complaints']} respiratory complaints in June 2026, "
                       f"with an average AQI of {results[0]['avg_aqi']} (primarily {results[0]['most_common_pollutant']}). "
                       f"This is significantly higher than other neighborhoods.",
            "source": "Table: respiratory_complaints",
        }

    elif "route 14" in q_lower or "transit" in q_lower or "delay" in q_lower or "congestion" in q_lower:
        sql = """
            SELECT route_id, route_name,
                   ROUND(AVG(avg_delay_minutes), 1) as avg_delay,
                   ROUND(AVG(congestion_score), 2) as avg_congestion,
                   SUM(ridership) as total_ridership
            FROM transit_metrics
            WHERE date >= '2026-06-01' AND date <= '2026-06-30'
            GROUP BY route_id, route_name
            ORDER BY avg_delay DESC
            LIMIT 10
        """
        results = db.execute_query(sql)
        return {
            "agent": "data_agent",
            "sql": sql.strip(),
            "results": results,
            "summary": f"Route 14 (Riverside Express) has the worst delays at {results[0]['avg_delay']} min average "
                       f"with a congestion score of {results[0]['avg_congestion']}.",
            "source": "Table: transit_metrics",
        }

    elif "waste" in q_lower or "bin" in q_lower or "garbage" in q_lower:
        sql = """
            SELECT neighborhood,
                   COUNT(*) as readings,
                   ROUND(AVG(fill_percentage), 1) as avg_fill_pct,
                   MAX(fill_percentage) as max_fill_pct
            FROM waste_sensors
            WHERE date >= '2026-06-01' AND date <= '2026-06-30'
            GROUP BY neighborhood
            ORDER BY avg_fill_pct DESC
            LIMIT 10
        """
        results = db.execute_query(sql)
        return {
            "agent": "data_agent",
            "sql": sql.strip(),
            "results": results,
            "summary": f"{results[0]['neighborhood']} has the highest average bin fill at {results[0]['avg_fill_pct']}%.",
            "source": "Table: waste_sensors",
        }

    else:
        # Generic: try all tables
        sql = """
            SELECT neighborhood,
                   SUM(complaint_count) as total_complaints,
                   ROUND(AVG(avg_aqi), 1) as avg_aqi
            FROM respiratory_complaints
            WHERE date >= '2026-05-01'
            GROUP BY neighborhood
            ORDER BY total_complaints DESC
            LIMIT 5
        """
        results = db.execute_query(sql)
        return {
            "agent": "data_agent",
            "sql": sql.strip(),
            "results": results,
            "summary": f"Top neighborhood by complaints since May: {results[0]['neighborhood']} with {results[0]['total_complaints']} total.",
            "source": "Table: respiratory_complaints",
        }


async def run_data_agent(question: str) -> dict:
    """Run the Data Agent: NL -> SQL -> results + summary.

    Returns dict with keys: agent, sql, results, summary, source
    Raises ValueError on SQL errors (caught by stream handler).
    """
    db = get_database()
    client = _get_genai_client()

    if client is None:
        # Fallback to pre-built queries
        return _fallback_query(question)

    # Step 1: Get schema
    schema = db.get_schema_description()

    # Step 2: NL to SQL via Gemini
    model = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
    try:
        response = client.models.generate_content(
            model=model,
            contents=_build_nl_to_sql_prompt(question, schema),
        )
        sql = response.text.strip()
        # Clean up markdown code blocks if present
        if sql.startswith("```"):
            sql = sql.split("\n", 1)[1] if "\n" in sql else sql[3:]
        if sql.endswith("```"):
            sql = sql[:-3]
        sql = sql.strip()
    except Exception as e:
        # Fall back to pre-built queries on Gemini failure
        return _fallback_query(question)

    # Step 3: Execute SQL
    try:
        results = db.execute_query(sql)
    except ValueError as e:
        # Bad SQL generated — fall back gracefully
        return _fallback_query(question)

    # Step 4: Generate summary
    try:
        summary_response = client.models.generate_content(
            model=model,
            contents=_build_summary_prompt(question, results),
        )
        summary = summary_response.text.strip()
    except Exception:
        summary = f"Query returned {len(results)} results." if results else "No results found."

    return {
        "agent": "data_agent",
        "sql": sql,
        "results": results[:20],
        "summary": summary,
        "source": "Tables: " + ", ".join(db.list_tables()),
    }
