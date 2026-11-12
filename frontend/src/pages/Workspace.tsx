import React, { useState, useEffect } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, Download, ExternalLink, FileCode, FileSpreadsheet, Layers, Save, Sparkles, Trash2, X } from "lucide-react";
import { DocumentExtractionResponse, DocumentType, LedgerTransactionItem, LineItem, VendorTemplateSummary } from "../types/document";
import { ImageCanvas } from "../components/ImageCanvas";
import { FieldInspector } from "../components/FieldInspector";
import { LineItemsTable } from "../components/LineItemsTable";
import { LedgerTable } from "../components/LedgerTable";
import { DemoGallery } from "../components/DemoGallery";
import { extractDocument, verifyDocument, getDocumentImageUrl, downloadDocumentExport, listTemplates, deleteTemplate } from "../services/api";

interface WorkspaceProps {
  currentDoc: DocumentExtractionResponse | null;
  setCurrentDoc: (doc: DocumentExtractionResponse | null) => void;
  imageUrl: string | null;
  setImageUrl: (url: string | null) => void;
  isLoading: boolean;
  setIsLoading: (loading: boolean) => void;
  onRefreshList: () => void;
}

export const Workspace: React.FC<WorkspaceProps> = ({
  currentDoc,
  setCurrentDoc,
  imageUrl,
  setImageUrl,
  isLoading,
  setIsLoading,
  onRefreshList,
}) => {
  const [notification, setNotification] = useState<{ type: "success" | "error"; text: string } | null>(null);
  const [currentPage, setCurrentPage] = useState<number>(1);

  // Reset page to 1 whenever document changes
  useEffect(() => {
    setCurrentPage(1);
    if (currentDoc) {
      setImageUrl(getDocumentImageUrl(currentDoc.document_id, 1));
    }
  }, [currentDoc?.document_id]);

  const handlePageChange = (newPage: number) => {
    setCurrentPage(newPage);
    if (currentDoc) {
      setImageUrl(getDocumentImageUrl(currentDoc.document_id, newPage));
    }
  };

  const showNotification = (type: "success" | "error", text: string) => {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 4000);
  };

  const handleUpload = async (file: File, docType: DocumentType) => {
    setIsLoading(true);
    try {
      const res = await extractDocument(file, docType);
      setCurrentDoc(res);
      setCurrentPage(1);
      setImageUrl(getDocumentImageUrl(res.document_id, 1));
      if (res.models_participated && res.models_participated.length > 0) {
        showNotification("success", `Document extracted successfully (${res.models_participated.length} models)`);
      } else if (res.error_summary) {
        showNotification("error", "Router Warning: 0 vision models responded. Upstream rate limit or missing provider key.");
      }
      onRefreshList();
    } catch (e: any) {
      showNotification("error", e.message || "Extraction failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectSample = async (
    sampleType: "invoice" | "khata" | "prescription" | "cash_book" | "multipage_invoice"
  ) => {
    setIsLoading(true);
    try {
      const sampleNames: Record<string, { filename: string; type: DocumentType; mime: string }> = {
        invoice: { filename: "sample_invoice.png", type: "INVOICE", mime: "image/png" },
        cash_book: { filename: "sample_petty_cash.webp", type: "CASH_BOOK", mime: "image/webp" },
        khata: { filename: "sample_khata.png", type: "KHATA_LEDGER", mime: "image/png" },
        prescription: { filename: "sample_prescription.png", type: "PRESCRIPTION", mime: "image/png" },
        multipage_invoice: { filename: "sample_multipage_invoice.pdf", type: "INVOICE", mime: "application/pdf" },
      };

      const selected = sampleNames[sampleType];
      // Fetch sample from backend sample_dataset via fetch
      const resp = await fetch(`/api/v1/health`);
      if (!resp.ok) {
        throw new Error("Backend server not responding");
      }

      // Convert local sample to File
      // For instant testing, create synthetic File from data URI or sample path
      const sampleImgResp = await fetch(`/sample_dataset/${selected.filename}`).catch(() => null);
      let fileBlob: Blob;
      if (sampleImgResp && sampleImgResp.ok) {
        fileBlob = await sampleImgResp.blob();
      } else if (selected.mime === "application/pdf") {
        const minimalPdf = `%PDF-1.4
1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj
2 0 obj << /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >> endobj
3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
4 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] >> endobj
xref
0 5
0000000000 65535 f 
0000000009 00000 n 
0000000058 00000 n 
0000000121 00000 n 
0000000192 00000 n 
trailer << /Size 5 /Root 1 0 R >>
startxref
263
%%EOF`;
        fileBlob = new Blob([minimalPdf], { type: "application/pdf" });
      } else {
        // Fallback: draw 1-pixel or test canvas
        const canvas = document.createElement("canvas");
        canvas.width = 400;
        canvas.height = 500;
        const ctx = canvas.getContext("2d");
        if (ctx) {
          ctx.fillStyle = "#faf8f2";
          ctx.fillRect(0, 0, 400, 500);
          ctx.fillStyle = "#222";
          ctx.font = "16px sans-serif";
          ctx.fillText(`Sample ${selected.type}`, 40, 50);
        }
        fileBlob = await new Promise((r) => canvas.toBlob((b) => r(b!), selected.mime));
      }

      const sampleFile = new File([fileBlob], selected.filename, { type: selected.mime });
      await handleUpload(sampleFile, selected.type);
    } catch (e: any) {
      showNotification("error", e.message || "Failed to load sample document");
    } finally {
      setIsLoading(false);
    }
  };

  const handleFieldChange = (key: string, newValue: any) => {
    if (!currentDoc) return;
    const updatedFields = { ...currentDoc.fields };
    if (updatedFields[key]) {
      updatedFields[key] = {
        ...updatedFields[key],
        value: newValue,
        confidence: 1.0, // Human verified
        needs_review: false,
      };
    }
    setCurrentDoc({
      ...currentDoc,
      fields: updatedFields,
    });
  };

  const handleLineItemsChange = (items: LineItem[]) => {
    if (!currentDoc) return;
    setCurrentDoc({
      ...currentDoc,
      line_items: items,
    });
  };

  const handleLedgerItemsChange = (items: LedgerTransactionItem[]) => {
    if (!currentDoc) return;
    setCurrentDoc({
      ...currentDoc,
      ledger_items: items,
    });
  };

  const handleSaveGroundTruth = async () => {
    if (!currentDoc) return;
    try {
      const verifiedFields: Record<string, any> = {};
      Object.entries(currentDoc.fields).forEach(([k, f]) => {
        verifiedFields[k] = f.value;
      });

      const verifiedItems = (currentDoc.line_items || []).map((it) => ({
        description: it.description.value,
        quantity: it.quantity.value,
        unit_price: it.unit_price.value,
        line_total: it.line_total.value,
      }));

      const verifiedLedgerItems = (currentDoc.ledger_items || []).map((it) => ({
        entry_date: it.entry_date.value,
        particulars: it.particulars.value,
        voucher_no: it.voucher_no,
        cash_out_debit: it.cash_out_debit.value,
        cash_in_credit: it.cash_in_credit.value,
        running_balance: it.running_balance.value,
      }));

      await verifyDocument(currentDoc.document_id, verifiedFields, verifiedItems, verifiedLedgerItems);
      setCurrentDoc({
        ...currentDoc,
        status: "VERIFIED",
      });
      showNotification("success", "Verified ground truth saved to evaluation benchmark dataset.");
      onRefreshList();
    } catch (e: any) {
      showNotification("error", e.message || "Failed to save verification");
    }
  };

  const [isExporting, setIsExporting] = useState<string | null>(null);
  const [isTemplateModalOpen, setIsTemplateModalOpen] = useState(false);
  const [templatesList, setTemplatesList] = useState<VendorTemplateSummary[]>([]);
  const [isLoadingTemplates, setIsLoadingTemplates] = useState(false);

  const fetchTemplates = async () => {
    setIsLoadingTemplates(true);
    try {
      const data = await listTemplates();
      setTemplatesList(data);
    } catch (e: any) {
      showNotification("error", e.message || "Failed to load templates");
    } finally {
      setIsLoadingTemplates(false);
    }
  };

  const handleDeleteTemplate = async (templateId: string) => {
    try {
      await deleteTemplate(templateId);
      showNotification("success", "Template removed from memory cache");
      setTemplatesList((prev) => prev.filter((t) => t.id !== templateId));
    } catch (e: any) {
      showNotification("error", e.message || "Failed to delete template");
    }
  };

  const handleExport = async (format: "tally" | "excel" | "gst") => {
    if (!currentDoc) return;
    try {
      setIsExporting(format);
      await downloadDocumentExport(currentDoc.document_id, format);
      const label =
        format === "tally"
          ? "Tally Prime XML"
          : format === "excel"
          ? "Reconciled Excel (.xlsx)"
          : "GST E-Invoice JSON";
      showNotification("success", `Successfully exported ${label}.`);
    } catch (e: any) {
      showNotification("error", e.message || `Failed to export ${format}`);
    } finally {
      setIsExporting(null);
    }
  };

  return (
    <div className="flex flex-col space-y-4 p-6 max-w-[1700px] mx-auto w-full">
      {/* Toast Notification */}
      {notification && (
        <div
          className={`fixed top-16 right-6 z-50 flex items-center space-x-2 px-4 py-2.5 rounded-xl border shadow-2xl backdrop-blur animate-in fade-in slide-in-from-top-2 text-xs font-medium ${
            notification.type === "success"
              ? "bg-emerald-950/90 text-emerald-200 border-emerald-500/40"
              : "bg-rose-950/90 text-rose-200 border-rose-500/40"
          }`}
        >
          {notification.type === "success" ? (
            <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          ) : (
            <AlertCircle className="w-4 h-4 text-rose-400" />
          )}
          <span>{notification.text}</span>
        </div>
      )}

      {/* Top Section: Upload & Demo Gallery */}
      <DemoGallery
        onUpload={handleUpload}
        onSelectSample={handleSelectSample}
        isLoading={isLoading}
      />

      {/* Split-Screen Studio Viewport */}
      {currentDoc ? (
        <div className="flex flex-col space-y-4">
          {/* Document Math Audit Alert (if discrepancy detected) */}
          {!currentDoc.math_validation.is_valid && (
            <div className="flex items-center justify-between p-3.5 rounded-xl bg-rose-950/40 border border-rose-500/50 text-rose-200 text-xs">
              <div className="flex items-center space-x-2.5">
                <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
                <div className="space-y-0.5">
                  <span className="font-bold">Deterministic Arithmetic Discrepancy Detected:</span>
                  <span className="text-rose-300 ml-1.5">
                    {currentDoc.math_validation.error_details.join(" | ")}
                  </span>
                </div>
              </div>
              <span className="font-mono text-[11px] bg-rose-500/20 px-2 py-0.5 rounded border border-rose-500/30 text-rose-300">
                Diff: Rs. {currentDoc.math_validation.discrepancy_amount.toFixed(2)}
              </span>
            </div>
          )}

          {/* Upstream Provider Exhaustion / Rate Limit Warning */}
          {currentDoc.models_participated.length === 0 && Boolean(currentDoc.error_summary) && (
            <div className="p-4 rounded-xl bg-amber-950/40 border border-amber-500/50 text-amber-200 text-xs space-y-2.5">
              <div className="flex items-center justify-between">
                <div className="flex items-center space-x-2 font-bold text-amber-300">
                  <AlertTriangle className="w-4 h-4 text-amber-400 flex-shrink-0" />
                  <span>Upstream Router Alert: No Vision Models Responded</span>
                </div>
                <a
                  href="http://localhost:3001"
                  target="_blank"
                  rel="noreferrer"
                  className="flex items-center space-x-1.5 px-3 py-1 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 font-medium transition-colors"
                >
                  <span>Open FreeLLMAPI Dashboard</span>
                  <ExternalLink className="w-3 h-3" />
                </a>
              </div>
              <p className="text-amber-200/90 leading-relaxed">
                The models did not fail on this handwriting—the request was blocked upstream at the local FreeLLMAPI router before reaching vision models (HTTP 429 rate limit or expired provider key).
              </p>
              {currentDoc.error_summary && (
                <div className="font-mono text-[11px] bg-dark-900/80 p-2.5 rounded border border-amber-500/30 text-amber-300 break-all">
                  Upstream Error: {currentDoc.error_summary}
                </div>
              )}
              <div className="text-[11px] text-slate-300">
                💡 <strong>How to activate vision:</strong> Open the FreeLLMAPI dashboard at <code className="text-emerald-400">http://localhost:3001</code>, navigate to <strong>Providers</strong>, and enter a free Google AI Studio (Gemini) or OpenRouter API key.
              </div>
            </div>
          )}

          {/* Fast-Path Vendor Template Cache Indicator */}
          {currentDoc.template_matched && (
            <div className="flex items-center justify-between px-3.5 py-2.5 rounded-xl bg-amber-950/40 border border-amber-500/50 text-amber-200 text-xs shadow-lg">
              <div className="flex items-center space-x-2 font-medium">
                <span className="text-amber-400 font-bold flex items-center space-x-1">
                  <span>⚡</span>
                  <span>Fast Path Memory Cache:</span>
                </span>
                <span className="text-amber-100">
                  Recognized repeat supplier <strong>{currentDoc.template_vendor || "Vendor Template"}</strong>. Bypassed heuristic zoner & VLM inference.
                </span>
              </div>
              <span className="text-[11px] text-amber-300 font-mono font-bold bg-amber-500/20 px-2 py-0.5 rounded border border-amber-500/40">
                ⚡ {currentDoc.processing_time_ms.toFixed(0)}ms (Sub-second)
              </span>
            </div>
          )}

          {/* Local High-Speed Engine Resilient Status Badge */}
          {!currentDoc.template_matched && currentDoc.models_participated.some((m) => m === "rapidocr_local" || m === "surya_local") && (
            <div className="flex items-center justify-between px-3.5 py-2.5 rounded-xl bg-emerald-950/40 border border-emerald-500/40 text-emerald-200 text-xs">
              <div className="flex items-center space-x-2 font-medium">
                <CheckCircle2 className="w-4 h-4 text-emerald-400 flex-shrink-0" />
                <span>
                  ✓ Extracted via Local Engine ({currentDoc.models_participated.filter((m) => m === "rapidocr_local" || m === "surya_local").map((m) => m === "surya_local" ? "Surya OCR" : "RapidOCR").join(" + ")} - Offline Resilient)
                </span>
              </div>
              <span className="text-[11px] text-emerald-400/80 font-mono">
                Latency: {currentDoc.processing_time_ms.toFixed(0)}ms
              </span>
            </div>
          )}

          {/* Split-Screen Grid: Left Canvas / Right Inspector */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-[680px]">
            {/* Left Column: Image Canvas Sidecar (5 cols) */}
            <div className="lg:col-span-5 h-[680px]">
              <ImageCanvas
                imageUrl={
                  currentDoc && (currentDoc.page_count ?? 1) > 1
                    ? getDocumentImageUrl(currentDoc.document_id, currentPage)
                    : imageUrl
                }
                filename={
                  currentDoc
                    ? (currentDoc.page_count ?? 1) > 1
                      ? `${currentDoc.document_id} (Page ${currentPage}/${currentDoc.page_count})`
                      : currentDoc.document_id
                    : undefined
                }
                pageCount={currentDoc?.page_count || 1}
                currentPage={currentPage}
                onPageChange={handlePageChange}
              />
            </div>

            {/* Right Column: Fields & Line Items Studio (7 cols) */}
            <div className="lg:col-span-7 flex flex-col space-y-5 glass-panel rounded-2xl p-5 border border-slate-800 overflow-y-auto max-h-[680px]">
              {/* Studio Header Bar */}
              <div className="flex items-center justify-between pb-3 border-b border-slate-800/80">
                <div className="space-y-0.5">
                  <div className="flex items-center space-x-2 flex-wrap gap-y-1">
                    <span className="font-bold text-sm text-white capitalize">
                      {currentDoc.document_type.replace("_", " ")}
                    </span>
                    <span className="text-[11px] font-mono text-slate-400">
                      ID: {currentDoc.document_id.slice(0, 8)}...
                    </span>
                    {currentDoc.page_count && currentDoc.page_count > 1 && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 font-mono">
                        {currentDoc.page_count} Pages
                      </span>
                    )}
                    {currentDoc.template_matched && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                        ⚡ Fast Path (Vendor Template: {currentDoc.template_vendor || "Cached"}) - {currentDoc.processing_time_ms.toFixed(0)}ms
                      </span>
                    )}
                    {!currentDoc.template_matched && currentDoc.models_participated.some((m) => m === "rapidocr_local" || m === "surya_local") && (
                      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                        ✓ {currentDoc.models_participated.filter((m) => m === "rapidocr_local" || m === "surya_local").map((m) => m === "surya_local" ? "Surya OCR" : "RapidOCR").join(" + ")} (Local)
                      </span>
                    )}
                  </div>
                  <div className="text-[11px] text-slate-400 flex items-center space-x-2">
                    <span>Ensemble Consensus:</span>
                    <span className="text-emerald-400 font-medium">
                      {currentDoc.models_participated.join(", ")}
                    </span>
                    <span>• {currentDoc.processing_time_ms.toFixed(0)}ms</span>
                  </div>
                </div>

                <div className="flex items-center space-x-2.5 flex-wrap gap-y-2">
                  {/* 1-Click Accounting & Compliance Exports */}
                  <div className="flex items-center rounded-xl bg-slate-900 border border-slate-700/80 p-0.5 shadow-sm">
                    <button
                      type="button"
                      disabled={Boolean(isExporting)}
                      onClick={() => handleExport("tally")}
                      title="Export to Tally Prime XML (Balanced Double-Entry)"
                      className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800 transition-colors disabled:opacity-50"
                    >
                      <Download className="w-3.5 h-3.5 text-amber-400" />
                      <span>{isExporting === "tally" ? "Exporting..." : "Tally XML"}</span>
                    </button>

                    <button
                      type="button"
                      disabled={Boolean(isExporting)}
                      onClick={() => handleExport("excel")}
                      title="Export to Multi-sheet Reconciled Excel (.xlsx) with Math Audit"
                      className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800 transition-colors disabled:opacity-50 border-l border-slate-800"
                    >
                      <FileSpreadsheet className="w-3.5 h-3.5 text-emerald-400" />
                      <span>{isExporting === "excel" ? "Exporting..." : "Excel (.xlsx)"}</span>
                    </button>

                    {currentDoc.document_type === "INVOICE" && (
                      <button
                        type="button"
                        disabled={Boolean(isExporting)}
                        onClick={() => handleExport("gst")}
                        title="Export to Indian GST E-Invoice (v1.1) JSON"
                        className="flex items-center space-x-1.5 px-2.5 py-1.5 rounded-lg text-xs font-semibold text-slate-300 hover:text-white hover:bg-slate-800 transition-colors disabled:opacity-50 border-l border-slate-800"
                      >
                        <FileCode className="w-3.5 h-3.5 text-cyan-400" />
                        <span>{isExporting === "gst" ? "Exporting..." : "GST JSON"}</span>
                      </button>
                    )}
                  </div>

                  {/* Template Memory Cache Management */}
                  <button
                    type="button"
                    onClick={() => {
                      setIsTemplateModalOpen(true);
                      fetchTemplates();
                    }}
                    title="Inspect & Manage Vendor Template Memory Cache"
                    className="flex items-center space-x-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-amber-300 hover:text-amber-100 bg-amber-500/10 hover:bg-amber-500/20 border border-amber-500/30 transition-all shadow-sm"
                  >
                    <Layers className="w-3.5 h-3.5 text-amber-400" />
                    <span>Vendor Templates</span>
                  </button>

                  {/* Save Ground Truth Action */}
                  <button
                    type="button"
                    onClick={handleSaveGroundTruth}
                    className="flex items-center space-x-2 px-3.5 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-dark-950 font-bold text-xs shadow-lg shadow-emerald-500/20 transition-all"
                  >
                    <Save className="w-4 h-4" />
                    <span>Verify & Save Ground Truth</span>
                  </button>
                </div>
              </div>

              {/* Scalar Field Inspector */}
              <FieldInspector fields={currentDoc.fields} onFieldChange={handleFieldChange} />

              {/* Polymorphic Table Rendering: LedgerTable for Cash Books / Khatas vs LineItemsTable for Invoices */}
              {(currentDoc.document_type === "CASH_BOOK" ||
                currentDoc.document_type === "KHATA_LEDGER" ||
                (currentDoc.ledger_items && currentDoc.ledger_items.length > 0)) ? (
                <LedgerTable
                  items={currentDoc.ledger_items || []}
                  onItemsChange={handleLedgerItemsChange}
                  onPageClick={handlePageChange}
                />
              ) : (
                <LineItemsTable
                  items={currentDoc.line_items || []}
                  onItemsChange={handleLineItemsChange}
                  onPageClick={handlePageChange}
                />
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="flex flex-col items-center justify-center p-16 rounded-2xl border border-dashed border-slate-800 bg-dark-900/40 text-center space-y-3">
          <div className="p-4 rounded-2xl bg-slate-800/60 text-slate-400">
            <Sparkles className="w-8 h-8 text-emerald-400 opacity-60" />
          </div>
          <h3 className="text-sm font-semibold text-white">No Document Currently Loaded</h3>
          <p className="text-xs text-slate-400 max-w-md">
            Click one of the 1-click test cards above or upload a messy handwritten receipt to inspect the multi-model consensus extraction in real-time.
          </p>
        </div>
      )}

      {/* Vendor Template Memory Cache Management Modal */}
      {isTemplateModalOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-in fade-in duration-150">
          <div className="bg-dark-900 border border-slate-800 rounded-2xl max-w-2xl w-full shadow-2xl flex flex-col overflow-hidden max-h-[85vh]">
            <div className="flex items-center justify-between px-6 py-4 border-b border-slate-800 bg-dark-950/50">
              <div className="flex items-center space-x-2.5">
                <div className="p-1.5 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/30">
                  <Layers className="w-4 h-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold text-white">Vendor Template Memory Cache</h3>
                  <p className="text-[11px] text-slate-400">
                    Recognized repeat suppliers bypass VLM inference for sub-second extraction
                  </p>
                </div>
              </div>
              <button
                type="button"
                onClick={() => setIsTemplateModalOpen(false)}
                className="p-1.5 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-3 flex-1">
              {isLoadingTemplates ? (
                <div className="flex items-center justify-center py-12 text-xs text-slate-400">
                  Loading cached vendor templates...
                </div>
              ) : templatesList.length === 0 ? (
                <div className="text-center py-12 space-y-2">
                  <p className="text-xs text-slate-400">No cached vendor templates in database yet.</p>
                  <p className="text-[11px] text-slate-500">
                    Templates are automatically learned when documents are verified or cold-path processed.
                  </p>
                </div>
              ) : (
                templatesList.map((tmpl) => (
                  <div
                    key={tmpl.id}
                    className="flex items-center justify-between p-3.5 rounded-xl bg-slate-900/60 border border-slate-800 hover:border-slate-700 transition-colors"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center space-x-2">
                        <span className="text-xs font-bold text-white">{tmpl.vendor_name}</span>
                        <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/30">
                          {tmpl.document_type}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono">
                          ⚡ {tmpl.sample_count} {tmpl.sample_count === 1 ? "doc" : "docs"}
                        </span>
                      </div>
                      <div className="flex items-center space-x-3 text-[11px] text-slate-400">
                        {tmpl.gstin && (
                          <span>
                            GSTIN: <span className="font-mono text-slate-300">{tmpl.gstin}</span>
                          </span>
                        )}
                        <span>
                          pHash: <span className="font-mono text-slate-400">{tmpl.phash.slice(0, 8)}...</span>
                        </span>
                      </div>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleDeleteTemplate(tmpl.id)}
                      title="Delete template from memory"
                      className="p-2 text-rose-400 hover:text-rose-300 hover:bg-rose-950/40 rounded-lg border border-transparent hover:border-rose-500/30 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                ))
              )}
            </div>

            <div className="px-6 py-3 border-t border-slate-800 bg-dark-950/50 flex items-center justify-between text-[11px] text-slate-400">
              <span>{templatesList.length} cached vendor {templatesList.length === 1 ? "layout" : "layouts"}</span>
              <button
                type="button"
                onClick={() => setIsTemplateModalOpen(false)}
                className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-white font-medium text-xs transition-colors"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
