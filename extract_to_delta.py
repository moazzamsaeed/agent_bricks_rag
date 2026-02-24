"""
extract_to_delta.py — Financial KPI Extractor
==============================================
Queries the Financial Reports Knowledge Assistant for structured data from
each of the 20 documents and writes results to two Delta tables:

  unstructured.rag_data.fin_kpis           — numeric KPIs per document
  unstructured.rag_data.fin_audit_findings — control findings from audit docs

Usage:
    python3.11 extract_to_delta.py [--dry-run]

Environment:
    DATABRICKS_HOST   Workspace URL (or ~/.databrickscfg)
    DATABRICKS_TOKEN  Personal access token (or ~/.databrickscfg)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any

HOST          = "https://adb-6417907769725610.10.azuredatabricks.net"
KA_ENDPOINT   = "ka-e53ea1a5-endpoint"
WAREHOUSE_ID  = "2f0c6e5a9e9d67d1"
CATALOG       = "unstructured"
SCHEMA        = "rag_data"

try:
    from databricks.sdk import WorkspaceClient
    from databricks.sdk.service.sql import StatementState
except ImportError:
    print("ERROR: pip install databricks-sdk>=0.20.0")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Extraction prompts per document type
# ---------------------------------------------------------------------------

@dataclass
class DocSpec:
    doc_id: str
    title: str
    doc_type: str
    period: str
    kpi_prompt: str          # returns JSON list of {metric_name, metric_value, metric_unit, notes}
    findings_prompt: str     # returns JSON list of findings (empty string = skip)


DOCS: list[DocSpec] = [
    DocSpec("fin_report_001", "Q1 2025 Earnings Report", "earnings", "Q1 2025",
        kpi_prompt='From the Q1 2025 Earnings Report, extract these metrics as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Extract: total revenue (millions), software segment revenue growth (%), operating income (millions), EPS (dollars), net income (millions). Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_002", "Q2 2025 Earnings Report", "earnings", "Q2 2025",
        kpi_prompt='From the Q2 2025 Earnings Report, extract these metrics as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Extract: total revenue (millions), revenue growth YoY (%), operating income (millions), EPS (dollars), full-year revenue growth guidance (%). Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_003", "Q3 2025 Earnings Report", "earnings", "Q3 2025",
        kpi_prompt='From the Q3 2025 Earnings Report, extract these metrics as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Extract: total revenue (millions), revenue growth YoY (%), operating income (millions), EPS (dollars), gross margin (%). Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_004", "Q4 2025 Annual Summary", "earnings", "Q4 2025",
        kpi_prompt='From the Q4 2025 Annual Summary, extract these metrics as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Extract: full-year revenue (millions), revenue growth YoY (%), net income (millions), EPS (dollars), dividends declared per share (dollars). Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_005", "Annual Budget Plan FY2026", "budget", "FY2026",
        kpi_prompt='From the Annual Budget Plan FY2026, extract departmental budgets as a JSON array. Each element: {"metric_name":"<department> budget","metric_value":<number>,"metric_unit":"millions","notes":"..."}. Include Sales & Marketing, R&D, Operations, and total budget. Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_006", "Capital Expenditure Policy", "policy", "FY2025",
        kpi_prompt='From the Capital Expenditure Policy, extract approval thresholds as a JSON array. Each element: {"metric_name":"<tier> approval threshold","metric_value":<number>,"metric_unit":"USD","notes":"<approver>"}. Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_007", "Expense Reimbursement Policy", "policy", "FY2025",
        kpi_prompt='From the Expense Reimbursement Policy, extract per diem rates and limits as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"USD","notes":"..."}. Include NYC meal rate, NYC lodging rate, domestic meal rate, domestic lodging rate. Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_008", "Procurement & Vendor Policy", "policy", "FY2025",
        kpi_prompt='From the Procurement & Vendor Policy, extract PO thresholds and payment discount rates as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_009", "Internal Audit Report Q1 2025", "audit", "Q1 2025",
        kpi_prompt='From the Internal Audit Report Q1 2025, extract summary metrics as a JSON array: total findings count, high risk findings count, medium risk findings count. Format: {"metric_name":"...","metric_value":<number>,"metric_unit":"count","notes":"..."}. Return only valid JSON array.',
        findings_prompt='From the Internal Audit Report Q1 2025, list all control findings as a JSON array. Each element: {"finding_name":"...","risk_rating":"High|Medium|Low","remediation_days":<number>,"status":"Open|In Progress|Closed"}. Return only valid JSON array.'),
    DocSpec("fin_report_010", "Internal Audit Report Q3 2025", "audit", "Q3 2025",
        kpi_prompt='From the Internal Audit Report Q3 2025, extract summary metrics as a JSON array: total findings count, high risk findings count, medium risk findings count. Format: {"metric_name":"...","metric_value":<number>,"metric_unit":"count","notes":"..."}. Return only valid JSON array.',
        findings_prompt='From the Internal Audit Report Q3 2025, list all control findings as a JSON array. Each element: {"finding_name":"...","risk_rating":"High|Medium|Low","remediation_days":<number>,"status":"Open|In Progress|Closed"}. Return only valid JSON array.'),
    DocSpec("fin_report_011", "Revenue Recognition Policy", "policy", "FY2025",
        kpi_prompt='From the Revenue Recognition Policy, extract key thresholds or percentages as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_012", "Cash Flow Forecast 2026", "forecast", "FY2026",
        kpi_prompt='From the Cash Flow Forecast 2026, extract quarterly operating cash flow figures as a JSON array. Each element: {"metric_name":"<quarter> operating cash flow","metric_value":<number>,"metric_unit":"millions","notes":"..."}. Include Q1-Q4 2026. Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_013", "Tax Compliance Summary 2025", "tax", "FY2025",
        kpi_prompt='From the Tax Compliance Summary 2025, extract key tax metrics as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Include effective tax rate, deferred tax asset/liability, transfer pricing adjustments. Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_014", "Risk Management Framework", "risk", "FY2025",
        kpi_prompt='From the Risk Management Framework, extract risk thresholds as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Include market risk threshold, credit risk threshold, liquidity risk threshold. Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_015", "ESG Financial Disclosure 2025", "esg", "FY2025",
        kpi_prompt='From the ESG Financial Disclosure 2025, extract key ESG metrics as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Include Scope 1 emissions reduction (%), Scope 2 emissions reduction (%), sustainability capex (millions), green finance commitment (millions). Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_016", "Merger & Acquisition Due Diligence", "m_and_a", "FY2025",
        kpi_prompt='From the M&A Due Diligence report, extract valuation and synergy metrics as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Include target valuation low, target valuation high, synergy estimate, integration cost. Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_017", "Debt & Credit Facility Report", "debt", "FY2025",
        kpi_prompt='From the Debt & Credit Facility Report, extract key debt metrics as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Include total debt (millions), interest coverage ratio, debt-to-equity ratio, credit facility size (millions). Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_018", "Inventory & COGS Analysis", "operations", "FY2025",
        kpi_prompt='From the Inventory & COGS Analysis, extract key inventory metrics as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Include gross margin (%), inventory turnover, obsolescence reserve (millions), top SKU margin (%). Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_019", "Employee Compensation & Benefits", "hr", "FY2025",
        kpi_prompt='From the Employee Compensation & Benefits document, extract compensation metrics as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Include total comp budget (millions), bonus pool (% of base), equity grant pool (millions), benefits cost per employee. Return only valid JSON array.',
        findings_prompt=""),
    DocSpec("fin_report_020", "Financial Controls & SOX Compliance", "audit", "FY2025",
        kpi_prompt='From the Financial Controls & SOX Compliance document, extract control metrics as a JSON array. Each element: {"metric_name":"...","metric_value":<number>,"metric_unit":"...","notes":"..."}. Include total controls tested, material weaknesses, significant deficiencies, control deficiencies, remediation completion rate (%). Return only valid JSON array.',
        findings_prompt='From the Financial Controls & SOX Compliance document, list all control deficiencies as a JSON array. Each element: {"finding_name":"...","risk_rating":"Material Weakness|Significant Deficiency|Control Deficiency","remediation_days":<number>,"status":"Open|In Progress|Closed"}. Return only valid JSON array.'),
]


# ---------------------------------------------------------------------------
# KA query helper
# ---------------------------------------------------------------------------

def query_ka(client: WorkspaceClient, prompt: str, retries: int = 3) -> str:
    for attempt in range(1, retries + 1):
        try:
            resp = client.api_client.do(
                "POST",
                f"/serving-endpoints/{KA_ENDPOINT}/invocations",
                body={"input": [{"role": "user", "content": prompt}]},
            )
            parts = []
            for msg in resp.get("output", []):
                for part in msg.get("content", []):
                    if part.get("type") == "output_text":
                        parts.append(part.get("text", ""))
            return "".join(parts).strip()
        except Exception as exc:
            if attempt == retries:
                raise
            time.sleep(2 ** attempt)
    return ""


def parse_json_list(raw: str) -> list[dict]:
    """Extract a JSON array from raw text, stripping markdown fences."""
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```[a-z]*\n?", "", raw)
        raw = re.sub(r"\n?```$", "", raw)
        raw = raw.strip()
    # Find first '[' to last ']'
    start = raw.find("[")
    end   = raw.rfind("]")
    if start == -1 or end == -1:
        return []
    try:
        return json.loads(raw[start:end + 1])
    except json.JSONDecodeError:
        return []


# ---------------------------------------------------------------------------
# SQL execution helper
# ---------------------------------------------------------------------------

def run_sql(client: WorkspaceClient, sql: str) -> None:
    result = client.statement_execution.execute_statement(
        warehouse_id=WAREHOUSE_ID,
        statement=sql,
        wait_timeout="50s",
    )
    # If still running, poll until done
    while result.status.state in (StatementState.RUNNING, StatementState.PENDING):
        time.sleep(3)
        result = client.statement_execution.get_statement(result.statement_id)
    if result.status.state != StatementState.SUCCEEDED:
        raise RuntimeError(f"SQL failed [{result.status.state}]: {result.status.error}")


def escape(val: Any) -> str:
    if val is None:
        return "NULL"
    return str(val).replace("'", "''")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Extract financial KPIs to Delta tables.")
    p.add_argument("--dry-run", action="store_true", help="Print SQL instead of executing")
    return p.parse_args()


def main() -> None:
    args = parse_args()

    print("Connecting to Databricks…")
    client = WorkspaceClient(host=HOST)
    print(f"Connected as {client.current_user.me().user_name}\n")

    kpi_rows:      list[dict] = []
    findings_rows: list[dict] = []
    errors:        list[str]  = []

    for doc in DOCS:
        print(f"[{doc.doc_id}] {doc.title}")

        # Extract KPIs
        print("  → extracting KPIs…", end=" ", flush=True)
        try:
            raw  = query_ka(client, doc.kpi_prompt)
            kpis = parse_json_list(raw)
            for k in kpis:
                try:
                    kpi_rows.append({
                        "doc_id":       doc.doc_id,
                        "title":        doc.title,
                        "doc_type":     doc.doc_type,
                        "period":       doc.period,
                        "metric_name":  str(k.get("metric_name", "")),
                        "metric_value": float(k.get("metric_value", 0)),
                        "metric_unit":  str(k.get("metric_unit", "")),
                        "notes":        str(k.get("notes", "")),
                    })
                except (ValueError, TypeError):
                    pass
            print(f"{len(kpis)} metrics")
        except Exception as exc:
            errors.append(f"{doc.doc_id} KPI: {exc}")
            print(f"ERROR: {exc}")

        # Extract audit findings if applicable
        if doc.findings_prompt:
            print("  → extracting findings…", end=" ", flush=True)
            try:
                raw      = query_ka(client, doc.findings_prompt)
                findings = parse_json_list(raw)
                for f in findings:
                    try:
                        findings_rows.append({
                            "doc_id":           doc.doc_id,
                            "title":            doc.title,
                            "finding_name":     str(f.get("finding_name", "")),
                            "risk_rating":      str(f.get("risk_rating", "")),
                            "remediation_days": int(f.get("remediation_days", 0)),
                            "status":           str(f.get("status", "")),
                        })
                    except (ValueError, TypeError):
                        pass
                print(f"{len(findings)} findings")
            except Exception as exc:
                errors.append(f"{doc.doc_id} findings: {exc}")
                print(f"ERROR: {exc}")

    print(f"\nExtracted {len(kpi_rows)} KPI rows and {len(findings_rows)} findings rows.")

    # ---- Write KPIs ----
    if kpi_rows:
        print(f"\nWriting {len(kpi_rows)} rows to {CATALOG}.{SCHEMA}.fin_kpis…")
        truncate_sql = f"TRUNCATE TABLE {CATALOG}.{SCHEMA}.fin_kpis"
        values = ",\n  ".join(
            f"('{escape(r['doc_id'])}','{escape(r['title'])}','{escape(r['doc_type'])}',"
            f"'{escape(r['period'])}','{escape(r['metric_name'])}',{r['metric_value']},"
            f"'{escape(r['metric_unit'])}','{escape(r['notes'])}')"
            for r in kpi_rows
        )
        insert_sql = (
            f"INSERT INTO {CATALOG}.{SCHEMA}.fin_kpis "
            f"(doc_id,title,doc_type,period,metric_name,metric_value,metric_unit,notes)\n"
            f"VALUES\n  {values}"
        )
        if args.dry_run:
            print(truncate_sql)
            print(insert_sql[:500], "…")
        else:
            run_sql(client, truncate_sql)
            run_sql(client, insert_sql)
            print("  ✓ fin_kpis written")

    # ---- Write findings ----
    if findings_rows:
        print(f"\nWriting {len(findings_rows)} rows to {CATALOG}.{SCHEMA}.fin_audit_findings…")
        truncate_sql = f"TRUNCATE TABLE {CATALOG}.{SCHEMA}.fin_audit_findings"
        values = ",\n  ".join(
            f"('{escape(r['doc_id'])}','{escape(r['title'])}','{escape(r['finding_name'])}',"
            f"'{escape(r['risk_rating'])}',{r['remediation_days']},'{escape(r['status'])}')"
            for r in findings_rows
        )
        insert_sql = (
            f"INSERT INTO {CATALOG}.{SCHEMA}.fin_audit_findings "
            f"(doc_id,title,finding_name,risk_rating,remediation_days,status)\n"
            f"VALUES\n  {values}"
        )
        if args.dry_run:
            print(truncate_sql)
            print(insert_sql[:500], "…")
        else:
            run_sql(client, truncate_sql)
            run_sql(client, insert_sql)
            print("  ✓ fin_audit_findings written")

    if errors:
        print(f"\nErrors ({len(errors)}):")
        for e in errors:
            print(f"  {e}")
    else:
        print("\nAll done — no errors.")


if __name__ == "__main__":
    main()
