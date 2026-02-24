# Agent Bricks RAG Demo — Financial Reports Assistant

A production-ready Retrieval-Augmented Generation (RAG) demo built on Databricks Agent Bricks (Knowledge Assistants), powered by 20 synthetic financial report PDFs stored in Unity Catalog. Demonstrates enterprise document Q&A with grounded citations, out-of-the-box evaluation, and a governed data pipeline end to end.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DATA INGESTION PIPELINE                            │
│                                                                             │
│  generate_pdfs.py                                                           │
│  ┌─────────────┐    Databricks FM API     ┌──────────────┐                 │
│  │  20 Topics  │ ─── LLaMA-3.3-70B ────▶ │  20 PDFs     │                 │
│  │  (TOPICS[]) │                          │  20 JSONs    │                 │
│  └─────────────┘                          └──────┬───────┘                 │
│                                                  │ upload_pdfs.py          │
│                                                  ▼                         │
│                          ┌───────────────────────────────────┐             │
│                          │  Unity Catalog Volume             │             │
│                          │  /Volumes/unstructured/           │             │
│                          │    rag_data/raw_data/             │             │
│                          │      pdf_documents/               │             │
│                          │        fin_report_001.pdf … 020   │             │
│                          └───────────────────────────────────┘             │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │  Databricks Agent Bricks
                                       │  (automatic chunking + embedding)
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                        KNOWLEDGE ASSISTANT                                  │
│                                                                             │
│   ┌────────────────────┐    vector search    ┌──────────────────────┐      │
│   │  User Question     │ ──────────────────▶ │  Delta Vector Index  │      │
│   └────────────────────┘                     │  (unstructured.      │      │
│                                              │   rag_data schema)   │      │
│   ┌────────────────────┐   retrieved chunks  └──────────────────────┘      │
│   │  Grounded Answer   │ ◀──────────────────                               │
│   │  + Citations       │      LLM synthesis                                │
│   └────────────────────┘   (Databricks FM)                                 │
│                                                                             │
│   Serving endpoint: agents-financial_reports_assistant                      │
└──────────────────────────────────────┬──────────────────────────────────────┘
                                       │
                                       ▼
┌─────────────────────────────────────────────────────────────────────────────┐
│                           EVALUATION LAYER                                  │
│                                                                             │
│   evaluate_rag.py                                                           │
│   ┌───────────────────┐    SDK query      ┌──────────────────────────┐     │
│   │  20 eval JSONs    │ ─────────────────▶│  Knowledge Assistant     │     │
│   │  (question +      │                   │  Endpoint                │     │
│   │   guideline)      │ ◀─────────────────│                          │     │
│   └───────────────────┘    answers        └──────────────────────────┘     │
│            │                                                                │
│            ▼  LLM-as-judge                                                  │
│   ┌───────────────────┐                                                     │
│   │  results/         │                                                     │
│   │  eval_results.json│                                                     │
│   └───────────────────┘                                                     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Prerequisites

| Requirement | Details |
|---|---|
| Databricks workspace | `https://adb-6417907769725610.10.azuredatabricks.net` |
| Unity Catalog enabled | Catalog `unstructured`, schema `rag_data` must exist |
| UC Volume | `/Volumes/unstructured/rag_data/raw_data/pdf_documents/` populated with PDFs |
| Databricks SDK | `pip install databricks-sdk>=0.20.0` |
| Authentication | `DATABRICKS_HOST` + `DATABRICKS_TOKEN` env vars, or `~/.databrickscfg` profile |
| Python | 3.10+ |
| Knowledge Assistant | "Financial Reports Assistant" created and deployed in the workspace |

### Python dependencies

```bash
pip install databricks-sdk>=0.20.0 mlflow>=2.14.0 reportlab>=4.0 rich>=13.0 tabulate>=0.9
```

---

## Quick Start

**Step 1 — Generate and upload the source PDFs** (skip if already done)

```bash
cd /path/to/pdf-gen-rag
export DATABRICKS_HOST=https://adb-6417907769725610.10.azuredatabricks.net
export DATABRICKS_TOKEN=<your-pat>
python generate_pdfs.py
```

**Step 2 — Create the Knowledge Assistant in Databricks**

1. Open the workspace: `https://adb-6417907769725610.10.azuredatabricks.net`
2. Navigate to **Playground → Knowledge Assistants → Create**
3. Name it `Financial Reports Assistant`
4. Point data source to `/Volumes/unstructured/rag_data/raw_data/pdf_documents/`
5. Click **Create** — indexing runs automatically (~2-5 minutes for 20 PDFs)

**Step 3 — Run the interactive CLI or evaluation**

```bash
# Interactive Q&A
python query_ka.py

# Ask a single question
python query_ka.py --question "What was the Q1 2025 revenue growth in the software segment?"

# Run full RAG evaluation against all 20 eval questions
python evaluate_rag.py
```

---

## File Structure

```
agent-bricks-rag/
├── README.md               This file
├── DEMO.md                 Customer-facing demo script
├── architecture.md         Technical architecture reference
├── evaluate_rag.py         RAG evaluation harness (20 questions)
├── query_ka.py             Interactive CLI for the Knowledge Assistant
└── results/
    └── eval_results.json   Output from evaluate_rag.py (generated at runtime)

pdf-gen-rag/                (companion repo — source data generation)
├── generate_pdfs.py        Generates 20 PDFs + eval JSONs via LLM
├── upload_pdfs.py          Uploads files to UC Volume
└── output/
    ├── fin_report_001.pdf … fin_report_020.pdf
    └── fin_report_001.json … fin_report_020.json
```

---

## Configuration Reference

| Variable | Location | Default | Description |
|---|---|---|---|
| `HOST` | `evaluate_rag.py`, `query_ka.py` | `https://adb-6417907769725610.10.azuredatabricks.net` | Databricks workspace URL |
| `ENDPOINT_NAME` | `evaluate_rag.py`, `query_ka.py` | `agents-financial_reports_assistant` | Serving endpoint name |
| `EVAL_DIR` | `evaluate_rag.py` | `../pdf-gen-rag/output/` | Directory containing eval JSONs |
| `RESULTS_DIR` | `evaluate_rag.py` | `./results/` | Output directory for eval results |
| `DATABRICKS_TOKEN` | environment | — | Personal access token (never hard-code) |

The endpoint name is derived from the Knowledge Assistant name by lowercasing and replacing spaces/special chars with underscores, prefixed with `agents-`. If your workspace assigned a different name, check **Serving → Endpoints** in the Databricks UI and update `ENDPOINT_NAME` in both scripts.

---

## Source Documents

| # | File | Topic |
|---|---|---|
| 001 | `fin_report_001.pdf` | Q1 2025 Earnings Report |
| 002 | `fin_report_002.pdf` | Q2 2025 Earnings Report |
| 003 | `fin_report_003.pdf` | Q3 2025 Earnings Report |
| 004 | `fin_report_004.pdf` | Q4 2025 Annual Summary |
| 005 | `fin_report_005.pdf` | Annual Budget Plan FY2026 |
| 006 | `fin_report_006.pdf` | Capital Expenditure Policy |
| 007 | `fin_report_007.pdf` | Expense Reimbursement Policy |
| 008 | `fin_report_008.pdf` | Procurement & Vendor Policy |
| 009 | `fin_report_009.pdf` | Internal Audit Report Q1 2025 |
| 010 | `fin_report_010.pdf` | Internal Audit Report Q3 2025 |
| 011 | `fin_report_011.pdf` | Revenue Recognition Policy |
| 012 | `fin_report_012.pdf` | Cash Flow Forecast 2026 |
| 013 | `fin_report_013.pdf` | Tax Compliance Summary 2025 |
| 014 | `fin_report_014.pdf` | Risk Management Framework |
| 015 | `fin_report_015.pdf` | ESG Financial Disclosure 2025 |
| 016 | `fin_report_016.pdf` | Merger & Acquisition Due Diligence |
| 017 | `fin_report_017.pdf` | Debt & Credit Facility Report |
| 018 | `fin_report_018.pdf` | Inventory & COGS Analysis |
| 019 | `fin_report_019.pdf` | Employee Compensation & Benefits |
| 020 | `fin_report_020.pdf` | Financial Controls & SOX Compliance |

---

## Links

- Databricks workspace: https://adb-6417907769725610.10.azuredatabricks.net
- Databricks Agent Bricks docs: https://docs.databricks.com/en/generative-ai/agent-framework/index.html
- Databricks SDK (Python): https://databricks-sdk-py.readthedocs.io/
- MLflow GenAI evaluation: https://mlflow.org/docs/latest/llms/llm-evaluate/index.html
- Unity Catalog Volumes: https://docs.databricks.com/en/connect/unity-catalog/volumes.html
