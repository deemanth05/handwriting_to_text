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

---

## 📋 Remaining Tasks (TODO)

### [TODO] Problem 2: Dynamic Layout & Table Structure Recognition
- [ ] Replace static coordinate heuristics (`(desc_x + out_x) / 2`) in local OCR extractors.
- [ ] Integrate Surya Table Recognition / Layout Transformer (`surya.layout`, `surya.tables`) to detect true column boundaries (S.No, Description, HSN/SAC, Qty, Rate, Amount, Debit, Credit, Balance).
- [ ] Implement adaptive DBSCAN spatial clustering fallback for borderless tables and varied column counts.
- [ ] Add unit tests for multi-column invoices and 6-column cash ledgers.

### [TODO] Problem 3: Enterprise Accounting Interop (Tally Prime XML & GST Export)
- [ ] Build `backend/app/services/exporters/tally_exporter.py` generating Tally Prime XML import vouchers (`<VOUCHER VCHTYPE="Purchase">` and `<VOUCHER VCHTYPE="Payment">`).
- [ ] Build multi-sheet Excel / CSV export with color-coded confidence cells and arithmetic audit logs.
- [ ] Add Indian GST E-Invoice JSON schema compliance for CA workflows.
- [ ] Expose 1-click export endpoints: `/api/v1/documents/{id}/export/tally` and `/api/v1/documents/{id}/export/excel`.

### [TODO] Problem 4: Multi-Page PDF & Stapled Document Batch Processor
- [ ] Add PDF rasterization pipeline (`pypdfium2` / `pdf2image`) to process multi-page bills and monthly khatas.
- [ ] Implement page-by-page consensus extraction and cross-page table continuation stitching.
- [ ] Implement cross-page ledger running-balance validation (carrying forward closing balance of Page $N$ to opening balance of Page $N+1$).
- [ ] Support batch zip/folder uploads with background job queue.

### [TODO] Problem 5: Vendor Fingerprint & Template Memory Cache
- [ ] Implement `VendorTemplateStore` to cache spatial bounding boxes for repeat suppliers and standard notebooks.
- [ ] Match incoming documents via perceptual hash + header text similarity ($>90\%$).
- [ ] Apply cached column coordinates directly to bypass heuristic layout discovery for known vendors.
- [ ] Enable active learning: saving user corrections in the review studio updates the vendor template anchors.
