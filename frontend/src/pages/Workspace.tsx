import React, { useState } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, ExternalLink, Save, Sparkles } from "lucide-react";
import { DocumentExtractionResponse, DocumentType, LedgerTransactionItem, LineItem } from "../types/document";
import { ImageCanvas } from "../components/ImageCanvas";
import { FieldInspector } from "../components/FieldInspector";
import { LineItemsTable } from "../components/LineItemsTable";
import { LedgerTable } from "../components/LedgerTable";
import { DemoGallery } from "../components/DemoGallery";
import { extractDocument, verifyDocument, getDocumentImageUrl } from "../services/api";

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

  const showNotification = (type: "success" | "error", text: string) => {
    setNotification({ type, text });
    setTimeout(() => setNotification(null), 4000);
  };

  const handleUpload = async (file: File, docType: DocumentType) => {
    setIsLoading(true);
    try {
      const res = await extractDocument(file, docType);
      setCurrentDoc(res);
      setImageUrl(getDocumentImageUrl(res.document_id));
      if (res.models_participated && res.models_participated.length > 0) {
        showNotification("success", `Document extracted successfully (${res.models_participated.length} models)`);
      } else {
        showNotification("error", "Router Warning: 0 vision models responded. Upstream rate limit or missing provider key.");
      }
      onRefreshList();
    } catch (e: any) {
      showNotification("error", e.message || "Extraction failed");
    } finally {
      setIsLoading(false);
    }
  };

  const handleSelectSample = async (sampleType: "invoice" | "khata" | "prescription" | "cash_book") => {
    setIsLoading(true);
    try {
      const sampleNames: Record<string, { filename: string; type: DocumentType }> = {
        invoice: { filename: "sample_invoice.png", type: "INVOICE" },
        cash_book: { filename: "sample_petty_cash.webp", type: "CASH_BOOK" },
        khata: { filename: "sample_khata.png", type: "KHATA_LEDGER" },
        prescription: { filename: "sample_prescription.png", type: "PRESCRIPTION" },
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
        fileBlob = await new Promise((r) => canvas.toBlob((b) => r(b!), "image/png"));
      }

      const sampleFile = new File([fileBlob], selected.filename, { type: "image/png" });
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
          {currentDoc.models_participated.length === 0 && (
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

          {/* Split-Screen Grid: Left Canvas / Right Inspector */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 min-h-[680px]">
            {/* Left Column: Image Canvas Sidecar (5 cols) */}
            <div className="lg:col-span-5 h-[680px]">
              <ImageCanvas imageUrl={imageUrl} filename={currentDoc.document_id} />
            </div>

            {/* Right Column: Fields & Line Items Studio (7 cols) */}
            <div className="lg:col-span-7 flex flex-col space-y-5 glass-panel rounded-2xl p-5 border border-slate-800 overflow-y-auto max-h-[680px]">
              {/* Studio Header Bar */}
              <div className="flex items-center justify-between pb-3 border-b border-slate-800/80">
                <div className="space-y-0.5">
                  <div className="flex items-center space-x-2">
                    <span className="font-bold text-sm text-white capitalize">
                      {currentDoc.document_type.replace("_", " ")}
                    </span>
                    <span className="text-[11px] font-mono text-slate-400">
                      ID: {currentDoc.document_id.slice(0, 8)}...
                    </span>
                  </div>
                  <div className="text-[11px] text-slate-400 flex items-center space-x-2">
                    <span>Ensemble Consensus:</span>
                    <span className="text-emerald-400 font-medium">
                      {currentDoc.models_participated.join(", ")}
                    </span>
                    <span>• {currentDoc.processing_time_ms.toFixed(0)}ms</span>
                  </div>
                </div>

                {/* Save Ground Truth Action */}
                <button
                  type="button"
                  onClick={handleSaveGroundTruth}
                  className="flex items-center space-x-2 px-4 py-2 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-500 hover:from-emerald-400 hover:to-teal-400 text-dark-950 font-bold text-xs shadow-lg shadow-emerald-500/20 transition-all"
                >
                  <Save className="w-4 h-4" />
                  <span>Verify & Save Ground Truth</span>
                </button>
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
                />
              ) : (
                <LineItemsTable
                  items={currentDoc.line_items || []}
                  onItemsChange={handleLineItemsChange}
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
    </div>
  );
};
