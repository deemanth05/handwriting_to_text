import React, { useState } from "react";
import { UploadCloud, FileSpreadsheet, Stethoscope, BookOpen } from "lucide-react";
import { DocumentType } from "../types/document";

interface DemoGalleryProps {
  onUpload: (file: File, docType: DocumentType) => void;
  onSelectSample: (sampleType: "invoice" | "khata" | "prescription") => void;
  isLoading: boolean;
}

export const DemoGallery: React.FC<DemoGalleryProps> = ({
  onUpload,
  onSelectSample,
  isLoading,
}) => {
  const [selectedType, setSelectedType] = useState<DocumentType>("INVOICE");
  const [dragOver, setDragOver] = useState<boolean>(false);

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onUpload(e.target.files[0], selectedType);
    }
  };

  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onUpload(e.dataTransfer.files[0], selectedType);
    }
  };

  return (
    <div className="flex flex-col space-y-4">
      {/* 1-Click Demo Pre-loaded Cards */}
      <div>
        <div className="flex items-center justify-between mb-2">
          <span className="text-[11px] font-bold uppercase tracking-wider text-slate-400">
            1-Click Demo Portfolio (Messy Test Documents)
          </span>
          <span className="text-[10px] text-emerald-400 font-mono">Instant Ensemble Extraction</span>
        </div>
        <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
          {/* Demo 1: Stamped Invoice */}
          <button
            type="button"
            disabled={isLoading}
            onClick={() => onSelectSample("invoice")}
            className="flex items-start space-x-3 p-3 rounded-xl glass-card border border-slate-800 hover:border-emerald-500/50 hover:bg-slate-800/60 transition-all text-left group"
          >
            <div className="p-2 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 group-hover:scale-110 transition-transform">
              <FileSpreadsheet className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-200 group-hover:text-emerald-300">
                Stamped Hardware Bill
              </div>
              <div className="text-[11px] text-slate-400">
                INV-2026-089 • Mixed ink & stamp
              </div>
            </div>
          </button>

          {/* Demo 2: Regional Khata */}
          <button
            type="button"
            disabled={isLoading}
            onClick={() => onSelectSample("khata")}
            className="flex items-start space-x-3 p-3 rounded-xl glass-card border border-slate-800 hover:border-amber-500/50 hover:bg-slate-800/60 transition-all text-left group"
          >
            <div className="p-2 rounded-lg bg-amber-500/10 text-amber-400 border border-amber-500/20 group-hover:scale-110 transition-transform">
              <BookOpen className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-200 group-hover:text-amber-300">
                Rameshwar Khata Ledger
              </div>
              <div className="text-[11px] text-slate-400">
                Hindi / Devanagari (०-९) • Jama/Baki
              </div>
            </div>
          </button>

          {/* Demo 3: Prescription */}
          <button
            type="button"
            disabled={isLoading}
            onClick={() => onSelectSample("prescription")}
            className="flex items-start space-x-3 p-3 rounded-xl glass-card border border-slate-800 hover:border-cyan-500/50 hover:bg-slate-800/60 transition-all text-left group"
          >
            <div className="p-2 rounded-lg bg-cyan-500/10 text-cyan-400 border border-cyan-500/20 group-hover:scale-110 transition-transform">
              <Stethoscope className="w-4 h-4" />
            </div>
            <div>
              <div className="text-xs font-semibold text-slate-200 group-hover:text-cyan-300">
                Handwritten Prescription
              </div>
              <div className="text-[11px] text-slate-400">
                Dr. Sharma • Rx dosage notes
              </div>
            </div>
          </button>
        </div>
      </div>

      {/* Upload Drop Zone */}
      <div
        onDragOver={(e) => {
          e.preventDefault();
          setDragOver(true);
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
        className={`relative border-2 border-dashed rounded-2xl p-5 text-center transition-all ${
          dragOver
            ? "border-emerald-500 bg-emerald-500/5"
            : "border-slate-800 hover:border-slate-700 bg-dark-900/40"
        }`}
      >
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-center space-x-3.5 text-left">
            <div className="p-3 rounded-xl bg-slate-800/80 border border-slate-700 text-slate-300">
              <UploadCloud className="w-6 h-6 text-emerald-400" />
            </div>
            <div>
              <h4 className="text-xs font-semibold text-white">Upload New Document Scan</h4>
              <p className="text-[11px] text-slate-400">
                Supports JPEG, PNG, WEBP up to 10MB (Auto CLAHE + Deskew)
              </p>
            </div>
          </div>

          {/* Document Type Selector & Browse Button */}
          <div className="flex items-center space-x-2">
            <select
              value={selectedType}
              onChange={(e) => setSelectedType(e.target.value as DocumentType)}
              className="bg-dark-850 text-xs font-medium text-slate-200 px-3 py-2 rounded-xl border border-slate-700 focus:outline-none focus:border-emerald-500 transition-all"
            >
              <option value="INVOICE">Invoice</option>
              <option value="KHATA_LEDGER">Khata Ledger</option>
              <option value="PRESCRIPTION">Prescription</option>
              <option value="GENERAL">General</option>
            </select>

            <label className="cursor-pointer px-4 py-2 rounded-xl bg-emerald-500 hover:bg-emerald-400 text-dark-950 font-semibold text-xs shadow-lg shadow-emerald-500/20 transition-all flex items-center space-x-1.5">
              <span>{isLoading ? "Processing..." : "Select File"}</span>
              <input
                type="file"
                accept="image/jpeg,image/png,image/webp"
                className="hidden"
                disabled={isLoading}
                onChange={handleFileChange}
              />
            </label>
          </div>
        </div>
      </div>
    </div>
  );
};
