# Technical Architecture — Financial Reports Assistant

## Overview

The Financial Reports Assistant is a Retrieval-Augmented Generation (RAG) system built entirely on Databricks. It ingests PDF documents stored in a Unity Catalog Volume, indexes them using Databricks Agent Bricks (Knowledge Assistants), and serves answers via a managed REST endpoint backed by Databricks Foundation Models.

No external vector database, no third-party embedding service, no data egress from the Databricks environment.

---

## Component Diagram

```
┌───────────────────────────────────────────────────────────────────────────────┐
│  LOCAL DEVELOPER MACHINE                                                       │
│                                                                                │
│  ┌──────────────────────┐     ┌──────────────────────┐                        │
│  │   generate_pdfs.py   │     │   evaluate_rag.py    │                        │
│  │   (pdf-gen-rag repo) │     │   query_ka.py        │                        │
│  └──────────┬───────────┘     └──────────┬───────────┘                        │
│             │  Databricks SDK (Files API) │  Databricks SDK (Serving API)      │
└─────────────┼───────────────────────────-┼────────────────────────────────────┘
              │                            │
              │  HTTPS                     │  HTTPS
              ▼                            ▼
┌───────────────────────────────────────────────────────────────────────────────┐
│  DATABRICKS WORKSPACE                                                          │
│  https://adb-6417907769725610.10.azuredatabricks.net                          │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │  UNITY CATALOG  (catalog: unstructured, schema: rag_data)                │ │
│  │                                                                          │ │
│  │  ┌─────────────────────────────────────────────────────────────────┐    │ │
│  │  │  Volume: raw_data / pdf_documents                               │    │ │
│  │  │  /Volumes/unstructured/rag_data/raw_data/pdf_documents/         │    │ │
│  │  │                                                                 │    │ │
│  │  │   fin_report_001.pdf   Q1 2025 Earnings Report                 │    │ │
│  │  │   fin_report_002.pdf   Q2 2025 Earnings Report                 │    │ │
│  │  │   fin_report_003.pdf   Q3 2025 Earnings Report                 │    │ │
│  │  │   fin_report_004.pdf   Q4 2025 Annual Summary                  │    │ │
│  │  │   fin_report_005.pdf   Annual Budget Plan FY2026               │    │ │
│  │  │   …                    (20 documents total)                    │    │ │
│  │  └────────────────────────────┬────────────────────────────────────┘    │ │
│  │                               │  Agent Bricks ingestion                 │ │
│  │                               ▼                                          │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐   │ │
│  │  │  Delta Table: document_chunks                                    │   │ │
│  │  │  (managed by Agent Bricks — chunked text + metadata)            │   │ │
│  │  └─────────────────────┬────────────────────────────────────────────┘   │ │
│  │                        │  embedding (Databricks FM)                     │ │
│  │                        ▼                                                 │ │
│  │  ┌──────────────────────────────────────────────────────────────────┐   │ │
│  │  │  Delta Vector Index                                              │   │ │
│  │  │  (cosine similarity, managed sync from chunks table)            │   │ │
│  │  └─────────────────────────────────────────────────────────────────┘   │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │  AGENT BRICKS — KNOWLEDGE ASSISTANT                                      │ │
│  │  "Financial Reports Assistant"                                           │ │
│  │                                                                          │ │
│  │   1. Receive user question                                               │ │
│  │   2. Embed question via FM embedding model                               │ │
│  │   3. ANN search against Delta Vector Index → top-K chunks               │ │
│  │   4. Construct grounded prompt (system + chunks + question)              │ │
│  │   5. Call LLM (Databricks FM) → generate answer with citations          │ │
│  │   6. Return answer + source references                                   │ │
│  └────────────────────────────────┬─────────────────────────────────────────┘ │
│                                   │                                            │
│  ┌────────────────────────────────▼─────────────────────────────────────────┐ │
│  │  MODEL SERVING ENDPOINT                                                  │ │
│  │  agents-financial_reports_assistant                                      │ │
│  │  (REST API — POST /serving-endpoints/{name}/invocations)                 │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │  FOUNDATION MODELS (hosted in-workspace)                                 │ │
│  │  • Generation : databricks-meta-llama-3-3-70b-instruct (or DBRX)        │ │
│  │  • Embedding  : databricks-gte-large-en (or bge-large-en)               │ │
│  │  • Evaluation : databricks-meta-llama-3-3-70b-instruct (LLM-as-judge)   │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
│                                                                                │
│  ┌──────────────────────────────────────────────────────────────────────────┐ │
│  │  MLFLOW TRACKING SERVER (workspace-managed)                              │ │
│  │  Evaluation run traces stored automatically                              │ │
│  └──────────────────────────────────────────────────────────────────────────┘ │
└───────────────────────────────────────────────────────────────────────────────┘
```

---

## Data Flow Description

### Ingestion path (run once, or on document update)

1. **Content generation** (`generate_pdfs.py`) — Calls the Databricks Foundation Models API (`databricks-meta-llama-3-3-70b-instruct`) to generate realistic financial document content as structured JSON, then renders each document to PDF using ReportLab. A companion `.json` file containing a RAG evaluation question and guideline is written alongside each PDF.

2. **Volume upload** (`upload_pdfs.py` or inline in `generate_pdfs.py`) — Uses the Databricks SDK Files API to upload both PDF and JSON files to the UC Volume at `/Volumes/unstructured/rag_data/raw_data/pdf_documents/`.

3. **Agent Bricks indexing** — When the Knowledge Assistant is created (or the volume is updated), Agent Bricks:
   - Reads each PDF from the Volume
   - Parses and chunks the text (default chunk size ~512 tokens with overlap)
   - Calls the workspace embedding model to produce dense vectors
   - Writes chunks and vectors to managed Delta tables inside `unstructured.rag_data`
   - Builds and synchronizes a Delta Vector Index for approximate nearest-neighbour search

### Query path (per user question)

1. User sends a question to the serving endpoint via the Databricks SDK or direct HTTP.
2. Agent Bricks embeds the question using the same embedding model used at index time.
3. ANN search retrieves the top-K most relevant document chunks from the Delta Vector Index.
4. A grounded system prompt is assembled: instructions + retrieved chunks (with source metadata) + question.
5. The LLM generates an answer grounded in the provided context.
6. The response is returned with the answer text and source citations.

### Evaluation path (run on demand or in CI)

1. `evaluate_rag.py` reads the 20 eval JSONs from `pdf-gen-rag/output/`.
2. For each case, it calls the Knowledge Assistant endpoint with the `question` field.
3. A separate call to the judge model scores whether the answer satisfies the `guideline` field using the LLM-as-judge pattern.
4. Results are aggregated and written to `results/eval_results.json`.

---

## Component Inventory

| Component | Technology | Role | Managed by |
|---|---|---|---|
| PDF source documents | 20 × ReportLab-generated PDFs | Ground truth knowledge base | UC Volume |
| RAG eval questions | 20 × JSON files | Evaluation ground truth | Local filesystem |
| Unity Catalog Volume | Databricks UC | Governed object storage for PDFs | Databricks |
| Document chunk table | Delta table (`unstructured.rag_data`) | Stores parsed + chunked text | Agent Bricks |
| Delta Vector Index | Databricks Vector Search | ANN retrieval over embeddings | Agent Bricks |
| Embedding model | `databricks-gte-large-en` | Converts text to dense vectors | Databricks FM |
| LLM (generation) | `databricks-meta-llama-3-3-70b-instruct` | Generates grounded answers | Databricks FM |
| Knowledge Assistant | Databricks Agent Bricks | Orchestrates retrieve → generate | Agent Bricks |
| Serving endpoint | Databricks Model Serving | REST API for the Knowledge Assistant | Databricks |
| LLM judge | `databricks-meta-llama-3-3-70b-instruct` | Scores eval answers vs. guidelines | Databricks FM |
| MLflow tracking | Workspace-managed MLflow | Logs eval runs and traces | Databricks |
| `evaluate_rag.py` | Python script | Eval harness (batch query + score) | Developer |
| `query_ka.py` | Python script | Interactive CLI for ad-hoc queries | Developer |

---

## Scalability Notes

### Document volume

The demo uses 20 PDFs. The same architecture supports tens of thousands of documents:

- **Delta Vector Index** scales horizontally; Databricks manages index partitioning automatically.
- **Ingestion throughput** is governed by the Vector Search endpoint compute size. For bulk ingestion of thousands of documents, increase the endpoint size in the Agent Bricks configuration.
- **Storage** is Delta + UC Volume; there is no practical ceiling for a Databricks workspace.

### Concurrent users

The serving endpoint auto-scales. Provisioned throughput (PT) endpoints guarantee a minimum throughput for SLA-sensitive deployments; pay-per-token endpoints are appropriate for low-to-medium concurrency demos.

### Document updates

Re-uploading a file to the same UC Volume path and triggering a sync (or enabling continuous sync in Agent Bricks) will re-index only the changed document. Stale chunks from the old version are replaced automatically.

### Multi-domain extensions

The pattern generalises beyond finance:

- Add a second volume and a second Knowledge Assistant for a different document corpus (e.g., legal contracts, HR policies).
- Unity Catalog ACLs ensure each assistant only retrieves from its authorised volume.
- Multiple assistants can be fronted by a single orchestrating agent using the Databricks Agent SDK.

---

## Security Model

### Authentication

All API calls (SDK, REST) require a Databricks personal access token (PAT) or OAuth M2M credential. Tokens are never stored in code; they are read from environment variables (`DATABRICKS_TOKEN`) or `~/.databrickscfg`.

### Unity Catalog permissions

Access to the PDF Volume, Delta tables, and Vector Index is governed by Unity Catalog grants. The minimum required permissions for a user or service principal running the scripts are:

| Permission | Object | Required for |
|---|---|---|
| `READ VOLUME` | `unstructured.rag_data.raw_data` | Reading PDFs during indexing |
| `WRITE VOLUME` | `unstructured.rag_data.raw_data` | Uploading PDFs (`generate_pdfs.py`) |
| `USE SCHEMA` | `unstructured.rag_data` | Accessing all objects in the schema |
| `USE CATALOG` | `unstructured` | Accessing the catalog |
| `EXECUTE` (serving) | `agents-financial_reports_assistant` | Querying the endpoint |

### Data residency

All data — PDFs, chunk embeddings, vector index, model serving — remains inside the Databricks workspace in the customer's Azure subscription. No data is sent to external services.

### Network

The workspace endpoint is reachable over HTTPS only. For production deployments, place the workspace behind a private endpoint (Azure Private Link) to restrict access to the corporate network.

### Service principals

For CI/CD use of `evaluate_rag.py`, create a Databricks service principal with `EXECUTE` permission on the serving endpoint and the minimum UC grants above. Store credentials in a secrets manager (Azure Key Vault or Databricks Secrets) — never in source control.

---

## Deployment Checklist

- [ ] Unity Catalog catalog `unstructured` and schema `rag_data` exist
- [ ] UC Volume `raw_data` exists under `unstructured.rag_data`
- [ ] 20 PDFs uploaded to `/Volumes/unstructured/rag_data/raw_data/pdf_documents/`
- [ ] Knowledge Assistant "Financial Reports Assistant" created and indexing complete
- [ ] Serving endpoint `agents-financial_reports_assistant` is in `Ready` state
- [ ] `DATABRICKS_HOST` and `DATABRICKS_TOKEN` environment variables set (or `~/.databrickscfg` configured)
- [ ] Python dependencies installed: `databricks-sdk>=0.20.0`, `rich>=13.0`, `mlflow>=2.14.0`
- [ ] `results/` directory writable (created automatically by `evaluate_rag.py`)
