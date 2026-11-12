# Enterprise Writing-to-Text: Production Engineering Roadmap & TODO

This document tracks the core production limitations being addressed sequentially to elevate the system into an enterprise-grade, on-prem deployable document intelligence engine.

---

## ✅ Completed & Verified

### Phase 1: Robust Preprocessing & Deterministic Arithmetic Reconciler
- [x] **OpenCV / PIL Preprocessing**: CLAHE illumination normalization on LAB space, Hough transform deskewing, and rolling-ball background division.
- [x] **Bipartite Consensus Engine**: Kuhn-Munkres algorithm (`scipy.optimize.linear_sum_assignment`) for line item row matching across multiple models.
- [x] **RapidFuzz Fuzzy Consensus**: Levenshtein / Token Sort Ratio scoring for text and vendor fields.
- [x] **Zero-Trust Arithmetic Verification**: Deterministic validation of line totals ($Qty \times Rate = Total$) and grand totals ($Subtotal + Tax - Discount = GrandTotal$), plus sequential running balance checks for Khatas/Cash books ($Balance_t = Balance_{t-1} + In_t - Out_t$).
- [x] **Local Dual OCR Integration**: Local CPU-based RapidOCR (ONNX) and Surya Multilingual OCR (PyTorch Transformer for English + Hindi Devanagari).

### Phase 2: Hybrid Vision Runtime Adapter & Circuit Breaking
- [x] **Martin Fowler Circuit Breaker (`circuit_breaker.py`)**:
  - `CLOSED` $\rightarrow$ `OPEN` $\rightarrow$ `HALF_OPEN` state machine.
  - Zero-latency (0ms) fail-fast when upstream models hit HTTP 429 rate limits or network outages, preventing thread starvation.
  - Automatic canary trials after cooldown to recover healthy connections.
- [x] **Native Ollama Vision Extractor (`ollama_extractor.py`)**:
  - Connects to Ollama `/api/chat` with raw base64 images.
  - Enforces `"format": "json"` for token-sampler level grammar-constrained JSON output.
  - Native support for local VLMs (`gemma3:12b`, `qwen2.5-vl`, `llama3.2-vision`).
- [x] **Generic OpenAI-Compatible Extractor (`openai_compat.py`)**:
  - Full compatibility with LM Studio (`http://127.0.0.1:1234/v1`), vLLM, and FreeLLMAPI (`http://127.0.0.1:3001/v1`).
- [x] **Non-Blocking Runtime Discovery (`runtime_probe.py`)**:
  - Asynchronous probing of all local/cloud AI runtimes via `/api/v1/health/runtimes`.
- [x] **Zero-Trust Fallback Fleet (`ensemble.py`)**:
  - Graceful degradation: if external/local VLMs trip or fail, local Surya + RapidOCR automatically guarantee structured extraction.
- [x] **Frontend Observability (`Header.tsx` & `Workspace.tsx`)**:
  - Real-time status pill matrix showing Ollama, LM Studio, FreeLLMAPI, Surya, and RapidOCR connectivity.
- [x] **Test Coverage**: 73 passing unit and integration tests (`pytest`).

### Phase 3: Dynamic Layout & Table Structure Recognition (Problem 2)
- [x] **Document Macro-Zoning (`backend/app/services/layout/zoner.py`)**:
  - Separates Header, Table Grid, Summary, and Footer zones using spatial anchors.
  - Eliminates vertical region contamination (bottom terms and totals never leak into table line items).
  - Handles standalone `Total:` trigger rows and headerless invoices gracefully.
- [x] **Adaptive Column Gutter Detection (`backend/app/services/layout/gutter_detector.py`)**:
  - 1D horizontal projection and whitespace valley analysis for dynamic column discovery across 3-to-7+ column layouts.
  - Extended column typing (`INDEX`, `DESCRIPTION`, `QUANTITY`, `RATE`, `TOTAL`, `UNIT`, `VOUCHER`, `HSN`, `DEBIT`, `CREDIT`, `BALANCE`).
  - Alpha-ratio filtering on numeric columns to prevent product descriptions (e.g. `3-Pin Multi Plug`) from stealing quantity/rate slots.
  - Missing-rate mathematical derivation ($Rate = Total / Qty$).
- [x] **Bilateral Summary Disambiguation (`backend/app/services/layout/bilateral_splitter.py`)**:
  - Horizontally splits summary zone along midline gutter.
  - Left zone parses narrative fields (`terms_and_conditions`, `amount_in_words`, `notes`).
  - Right zone parses accounting numbers (`subtotal`, `cgst`, `sgst`, `igst`, `discount`, `round_off`, `grand_total`).
  - Generalized symmetric digit confusion repair with rate consistency verification.
  - Words-to-number parser supporting rupee/paisa syntax and fractional amounts.
- [x] **Surya Deep-Learning Table Integration (`backend/app/services/layout/surya_table_adapter.py`)**:
  - Polygon-to-bbox cell mapping with zero coordinate leakage.
- [x] **Test Coverage & Verification**:
  - 100 / 100 pytest test suite passing.
  - Verified on real documents: `real_handwritten_invoice.jpg` (extracts exactly 7 true items, 0 summary items), `sample_petty_cash.webp` (12 ledger entries), `sample_invoice.png` (4 items).

### Phase 4: Enterprise Accounting Interop & Multi-Format Exporters (Problem 3)
- [x] **Tally Prime XML Exporter (`backend/app/services/exporters/tally_exporter.py`)**:
  - Purchase vouchers (`<VOUCHER VCHTYPE="Purchase">`) with balanced double-entry accounting: Credit party ledger, Debit purchase ledger, Debit Input CGST/SGST/IGST, and Round-Off adjustments ($\sum \text{Debit} + \sum \text{Credit} = 0$).
  - Inventory items allocation breakdown (`<ALLINVENTORYENTRIES.LIST>`) with rates, billed quantities, and accounting allocations.
  - Payment and Receipt vouchers (`<VOUCHER VCHTYPE="Payment">`, `<VOUCHER VCHTYPE="Receipt">`) for Cash Books and Khatas.
  - Robust date normalization to Tally canonical `YYYYMMDD` format and XML escaping.
- [x] **Multi-Sheet Reconciled Excel Workbook (`backend/app/services/exporters/excel_exporter.py`)**:
  - Powered by `openpyxl` with corporate visual hierarchy.
  - Sheet 1 (*Audit Summary*): Document metadata, overall confidence, model participation, and deterministic arithmetic audit logs.
  - Sheet 2 (*Itemized Register* / *Transactions Register*): Line items / ledger items with cell-level confidence coloring (green for high confidence, yellow/red for review flags).
  - Sheet 3 (*GST E-Invoice Schedule*): Pre-formatted B2B table for direct import into GST filing utilities.
- [x] **Indian GST E-Invoice v1.1 JSON Exporter (`backend/app/services/exporters/gst_json_exporter.py`)**:
  - Standard schema adhering to NIC / GST Suvidha Provider (GSP) specifications (`Version`, `TranDtls`, `DocDtls`, `SellerDtls`, `BuyerDtls`, `ItemList`, `ValDtls`).
  - Dynamic HSN code resolution and automated assessable value calculations.
- [x] **FastAPI Export Endpoints (`backend/app/api/routes_export.py`)**:
  - `GET /api/v1/documents/{document_id}/export/tally` -> `application/xml`
  - `GET /api/v1/documents/{document_id}/export/excel` -> `application/vnd.openxmlformats-officedocument.spreadsheetml.sheet`
  - `GET /api/v1/documents/{document_id}/export/gst` -> `application/json`
  - Authoritative Ground Truth precedence: human verifications stored in `GroundTruthRecord` automatically override baseline AI extractions.
- [x] **Split-Screen Studio Frontend 1-Click UI (`Workspace.tsx`, `api.ts`)**:
  - Integrated 1-click export button group in the Review Studio toolbar next to "Verify & Save Ground Truth".
  - Instant client-side download triggers with proper Content-Disposition filenames.
- [x] **Test Coverage & Verification**:
  - 109 / 109 pytest tests passing in 26s.
  - Full test suite passing across all exporters, XML schemas, math invariants, and HTTP routes.

### Phase 5: Multi-Page PDF & Stapled Document Batch Processor (Problem 4)
- [x] **Container Ingestion & Rasterization (`backend/app/services/multipage/rasterizer.py`)**:
  - High-fidelity PDF rendering via `pypdfium2` at 144 DPI with strict page limit enforcement ($\le 25$ pages).
  - Safe in-memory `.zip` batch extraction with natural numerical sorting (`page_1`, `page_2`, `page_10`), directory traversal protection, and uncompressed size guardrails.
  - Direct pass-through for single images (JPEG, PNG, WEBP).
- [x] **Cross-Page Table Continuation Stitching (`backend/app/services/multipage/stitcher.py`)**:
  - Metadata & header inheritance prioritizing primary header pages.
  - Automatic detection and filtering of transitional "Carried Forward" (C/F) and "Brought Forward" (B/F) subtotal rows.
  - Sequential row renumbering with originating `page_number` attribution on all items.
  - Global cross-page arithmetic validation ($\sum \text{Item Totals} == \text{Subtotal}$ and $\text{Subtotal} + \text{Tax} - \text{Discount} == \text{Grand Total}$).
- [x] **Cross-Page Ledger Continuity Verification (`stitcher.py`)**:
  - Mathematical continuity enforcement for multi-page Khatas and Cash Books ($\text{ClosingBalance}_N == \text{OpeningBalance}_{N+1}$).
  - Explicit discrepancy error generation on missing pages or mistranscriptions.
- [x] **Multi-Page Split-Screen Studio Frontend (`ImageCanvas.tsx`, `Workspace.tsx`, `LineItemsTable.tsx`, `LedgerTable.tsx`)**:
  - Built-in canvas pagination toolbar (`< Prev`, `Page X of Y`, `Next >`) with guarded keyboard navigation.
  - Interactive clickable page badges (`p.1`, `p.2`) on item and transaction rows that jump directly to that page in the canvas.
  - 1-click multi-page sample demo in `DemoGallery.tsx` with offline synthetic PDF generator.
- [x] **Test Coverage & Verification**:
  - 126 / 126 pytest tests passing across 21 test suites in 35s.
  - Frontend builds with 0 TypeScript errors.

### Phase 6: Vendor Fingerprint & Template Memory Cache (Problem 5)
- [x] **Visual & Identity Fingerprinting (`backend/app/services/templates/fingerprint.py`)**:
  - 64-bit DCT perceptual hash (`pHash`) computed with `cv2.dct` on normalized $32 \times 32$ grayscale pixels with median AC frequency thresholding.
  - Indian 15-character GSTIN regex identifier parser with vendor legal name candidate extraction.
  - Bitwise Hamming distance and normalized similarity scoring with illumination and contrast invariance ($\le 4$ bits divergence) and cross-document discrimination ($\ge 20$ bits).
- [x] **Persistent Template Memory Store (`backend/app/services/templates/store.py`)**:
  - `VendorTemplateRecord` in SQLite via SQLAlchemy with indices on `vendor_key`, `gstin`, and `phash`.
  - Dual-Key matching: exact GSTIN priority or visual pHash ($\le 8$ bits) + vendor fuzzy name match ($\ge 85\%$).
  - Layout harvesting: derives normalized coordinates (`table_zone`, `header_zone`, `summary_zone`, column X-gutter ratios) directly from real OCR boxes.
- [x] **Sub-Second Fast-Path Vision Extractor (`backend/app/services/templates/fast_extractor.py`)**:
  - Bypasses slow VLM calls and heuristic whitespace valley discovery for repeat suppliers.
  - Crops and slices pre-indexed column channels directly with local RapidOCR.
  - Strict zero-trust deterministic arithmetic validation ($Qty \times Rate = LineTotal$, $Subtotal + Tax - Discount = GrandTotal$).
  - Automatic Cold-Path Fallback: if vendor altered layout or row math fails, seamlessly degrades to Cold Path without failing request.
- [x] **Active Learning Feedback Loop (`backend/app/api/routes_review.py`)**:
  - `POST /documents/{id}/verify` ground truth confirmation automatically locks verified vendor coordinates into template cache.
- [x] **Observability & Management API & UI (`backend/app/api/routes_template.py`, `Workspace.tsx`)**:
  - `GET /api/v1/templates`, `GET /api/v1/templates/{id}`, `DELETE /api/v1/templates/{id}`.
  - Split-Screen Studio indicator badge: `⚡ Fast Path (Vendor Template: <Vendor Name>) - <latency>ms`.
  - Frontend Template Manager Modal in Workspace toolbar for auditing and deleting cached repeat vendor profiles.
- [x] **Test Coverage & Verification**:
  - 150 / 150 pytest tests passing across 25 suites in 46s (including 24 tests in `test_fingerprint.py`, `test_template_store.py`, `test_fast_extractor.py`, and `test_routes_template.py`).
  - Frontend builds cleanly with 0 TypeScript errors (`tsc && vite build`).

---

## 📋 Remaining Tasks (TODO)
- All 5 core roadmap problems (Preprocessing & Math, Vision Runtimes & Fallbacks, Dynamic Layout & Table Recognition, Enterprise Accounting Exporters, Multi-Page PDF & Stapled Document Batching, and Vendor Fingerprint & Template Memory Cache) are fully implemented and verified!
