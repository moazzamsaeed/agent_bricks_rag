# Demo Script — Financial Reports Assistant

**Audience:** Customers and stakeholders evaluating Databricks Agent Bricks for enterprise document Q&A
**Duration:** 20–30 minutes
**Prerequisites:** Knowledge Assistant deployed and indexed; browser open to the Databricks workspace

---

## Scene-Setter (2 minutes)

**Say:**
> "Every finance team drowns in PDFs — earnings releases, audit reports, policies, forecasts. Finding a specific number or interpretation across dozens of documents today means keyword search, manual scrolling, or emailing the analyst who wrote it three quarters ago.
>
> What if you could ask a plain-English question and get a direct, cited answer in seconds — pulled from the exact paragraph of the relevant document — without moving the data outside your secure environment?
>
> That's what we're going to show you today. We've loaded 20 realistic financial documents into Databricks Unity Catalog and connected them to a Knowledge Assistant built on Agent Bricks. No custom code, no third-party vector database, no data leaving the platform. Let's walk through it."

---

## Demo Flow

### Step 1 — Show the Data (2 minutes)

Navigate to: **Catalog Explorer → unstructured → rag_data → Volumes → raw_data → pdf_documents**

**Say:**
> "Here are the 20 source PDFs sitting in a Unity Catalog Volume. These are synthetic but realistic financial documents — quarterly earnings, internal audits, policy documents, ESG disclosures. The same approach works with your actual documents on day one.
>
> Notice these files have never left Databricks. There's no external upload step, no API call to a third-party embedding service. Unity Catalog governs access the same way it governs any table."

**Show:** Click a PDF to confirm it renders. Point out the breadth of document types.

---

### Step 2 — Show the Knowledge Assistant (2 minutes)

Navigate to: **Playground → Knowledge Assistants → Financial Reports Assistant**

**Say:**
> "This is the Knowledge Assistant. Databricks Agent Bricks automatically chunked and embedded the PDFs when we pointed it at the volume — roughly two to five minutes for 20 documents. There's no pipeline to build, no chunking strategy to hand-tune for a proof of concept.
>
> It's backed by a Delta vector index inside the same catalog, so all UC permissions apply automatically. If a user can't read a document, they can't retrieve chunks from it either."

---

### Step 3 — Run the First Question (3 minutes)

Type into the Knowledge Assistant chat:

> **"What was the year-over-year growth in revenue for the software segment in Q1 2025?"**

**Say:**
> "Watch the response — it gives us a specific percentage figure and, critically, it cites the exact source document. Scroll down and you'll see the chunk reference. This is grounded generation: the model is not hallucinating from training data, it is quoting the document."

**Talking points:**
- The answer should reference the 20% YoY growth figure from the Q1 2025 Earnings Report
- Point out the citation card / source reference that Agent Bricks appends
- If the answer is slightly different, note: "This is a synthetic document — in production, the numbers come straight from your real filings"

---

### Step 4 — Cross-Document Question (3 minutes)

Type:

> **"Compare the risk ratings found in the Q1 2025 and Q3 2025 internal audit reports. Were any findings repeated?"**

**Say:**
> "Now let's stress-test it. This question requires the assistant to retrieve relevant chunks from two separate documents, synthesize them, and present a coherent comparison. This is where traditional keyword search completely breaks down."

**Talking points:**
- The assistant pulls from both `fin_report_009.pdf` (Q1 audit) and `fin_report_010.pdf` (Q3 audit)
- Highlight that both source citations appear in the response
- "In a real deployment, your analysts would use this to spot repeat findings across audit cycles in seconds, not hours"

---

### Step 5 — Policy Lookup (2 minutes)

Type:

> **"What is the approval threshold for capital expenditures, and who has signing authority?"**

**Say:**
> "Policy documents are a classic RAG use case — they're long, they change, and nobody can ever remember the exact rule. Let's see what the CapEx policy says."

**Talking points:**
- Response should reference the Capital Expenditure Policy (`fin_report_006.pdf`)
- Approval thresholds and depreciation schedules are in the document
- "Imagine your procurement team asking this question instead of calling Finance. You've just saved ten emails."

---

### Step 6 — Forward-Looking Question (3 minutes)

Type:

> **"What are the key assumptions in the 2026 cash flow forecast for the investing activities section?"**

**Say:**
> "Forecasting documents are rich with assumptions buried in footnotes and sub-sections. Let's pull out the investing activities assumptions."

**Talking points:**
- Response should reference `fin_report_012.pdf` (Cash Flow Forecast 2026)
- Highlight that the model finds the specific section rather than summarizing the whole document
- "This kind of targeted retrieval is why enterprises care about chunk quality — Agent Bricks handles that automatically"

---

### Step 7 — Run the Evaluation (4 minutes)

Switch to terminal. Run:

```bash
python evaluate_rag.py
```

**Say:**
> "Let me show you something powerful. We pre-generated 20 evaluation questions — one per document — each with a human-written guideline describing what a correct answer must include. Our evaluation script queries the Knowledge Assistant for each question and uses an LLM-as-judge to score whether the answer meets the guideline.
>
> This is how you measure RAG quality systematically before going to production."

**Show:** The printed results table. Point out pass/fail per question and the overall score.

**Talking points:**
- Typical score on this dataset is 80–95% — if it's lower, use it to start a conversation about chunk size tuning
- "This eval harness is three dozen lines of Python. In a production deployment you'd run this in CI/CD after every document update."
- Results are saved to `results/eval_results.json` for audit trail

---

## Sample Questions for the Knowledge Assistant

Use these during the demo or leave them open for audience-driven Q&A:

| # | Question | Target Document |
|---|---|---|
| 1 | What was the year-over-year growth in revenue for the software segment in Q1 2025? | Q1 2025 Earnings Report |
| 2 | What is the expected full-year revenue growth range for 2025 based on forward guidance? | Q2 2025 Earnings Report |
| 3 | Summarize the key highlights from the Q4 2025 annual summary, including dividends declared. | Q4 2025 Annual Summary |
| 4 | What is the total budget allocated across Sales & Marketing, R&D, and Operations for FY2026? | Annual Budget Plan FY2026 |
| 5 | What are the CapEx approval thresholds and who has signing authority at each level? | Capital Expenditure Policy |
| 6 | What per diem rates are allowed for domestic travel under the expense reimbursement policy? | Expense Reimbursement Policy |
| 7 | What is the risk rating and remediation timeline for the "Lack of monitoring" finding in Q3 2025? | Internal Audit Q3 2025 |
| 8 | How does the company treat variable consideration under ASC 606 revenue recognition? | Revenue Recognition Policy |
| 9 | What was the effective tax rate for 2025 and what drove deferred tax movement? | Tax Compliance Summary 2025 |
| 10 | What percentage reduction in Scope 1 and 2 emissions did the company achieve in 2025? | ESG Financial Disclosure 2025 |
| 11 | What synergy estimates and integration costs are cited in the M&A due diligence report? | M&A Due Diligence |
| 12 | Is the company in compliance with all debt covenants, and what is the current interest coverage ratio? | Debt & Credit Facility Report |
| 13 | Which SKUs had the highest obsolescence reserve write-downs in the inventory analysis? | Inventory & COGS Analysis |
| 14 | How many SOX control deficiencies were identified and how are they classified? | Financial Controls & SOX Compliance |
| 15 | What liquidity risk thresholds are defined in the risk management framework? | Risk Management Framework |

---

## Expected Outputs and Talking Points

**For earnings questions (1–3):** The assistant returns specific figures and references the relevant quarter. Use this to highlight that the model distinguishes between Q1, Q2, Q3, and Q4 despite similar document structure — retrieval quality matters.

**For policy questions (5–6, 8):** Responses should be precise and actionable ("the threshold is $X, approved by Y"). This is the most immediately compelling use case for most finance audiences — policy compliance without digging through SharePoint.

**For audit questions (7):** The risk rating + timeline combination demonstrates that the assistant can extract structured data embedded in prose. Connect to internal audit teams who currently maintain manual trackers.

**For ESG question (10):** Resonates with CFOs and IR teams. Sustainability disclosures are increasingly scrutinized and often live in PDFs that are hard to query programmatically.

**For cross-document questions:** When the assistant cites two sources in a single answer, explicitly call it out. "It retrieved the right chunk from each document independently and synthesized them. That's the RAG pattern working as designed."

---

## "So What" — Business Value

**Time to insight:** Finance analysts spend 30–60% of their time locating information. A Knowledge Assistant over corporate documents cuts lookup time from hours to seconds for factual questions.

**Audit trail:** Every answer is grounded in a cited source chunk. When a regulator asks "where does this number come from?", the analyst has an answer.

**Governance without extra work:** Because the documents live in Unity Catalog, all existing access controls apply automatically. No duplicate permission model to maintain.

**No infrastructure overhead:** Agent Bricks manages the vector index, chunking pipeline, and serving endpoint. The entire setup for this 20-document demo took under 10 minutes of human effort.

**Evaluation baked in:** The eval harness demonstrates that RAG quality is measurable and improvable — this is the conversation that differentiates a proof of concept from a production system.

**Scalability path:** This demo uses 20 PDFs. The same architecture handles 20,000. Databricks Delta vector indexes scale horizontally; Unity Catalog volumes have no practical storage ceiling.

---

## Q&A Handling Tips

**"How do you handle documents that are updated frequently?"**
> Re-upload the new version to the UC Volume. Agent Bricks detects the change and re-indexes the affected file automatically. The old chunks are replaced; you don't need to rebuild the entire index.

**"Can it handle tables and structured data inside PDFs?"**
> Agent Bricks uses Databricks's document parsing pipeline which handles tables reasonably well for standard PDFs. For highly complex layouts — scanned documents, multi-column tables — there are additional parsing options available, including integration with partner OCR providers.

**"What model is powering the generation?"**
> By default, Databricks Foundation Models (typically a Llama or DBRX variant hosted in your region). You can swap in any model available on Databricks Model Serving, including Azure OpenAI if the workspace is configured for it.

**"How do you prevent the assistant from making things up?"**
> Grounded generation — the system prompt instructs the model to answer only from retrieved context. If the answer isn't in the documents, the assistant says so. That's visible in the eval results: questions about topics not covered in the corpus get low scores, which is the correct behavior.

**"What does production deployment look like?"**
> The serving endpoint (`agents-financial_reports_assistant`) is already a REST API. Embed it in a Slack bot, an internal portal, or your ERP's help interface with a single HTTP call. The `query_ka.py` script in this repo is a minimal reference implementation.

**"How is this different from ChatGPT with a file upload?"**
> Three things: data stays inside your Databricks environment and never leaves your cloud account; Unity Catalog governs access so row-level and column-level security applies; and the vector index and model serving are enterprise-grade, observable, and auditable via MLflow.
