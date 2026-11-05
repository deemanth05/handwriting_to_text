import React, { useState } from "react";
import { AlertCircle, CheckCircle2, ChevronDown, Layers } from "lucide-react";
import { ExtractedField } from "../types/document";

interface FieldInspectorProps {
  fields: Record<string, ExtractedField<any>>;
  onFieldChange: (fieldKey: string, newValue: any) => void;
}

export const FieldInspector: React.FC<FieldInspectorProps> = ({ fields, onFieldChange }) => {
  const [activePopover, setActivePopover] = useState<string | null>(null);

  const getConfidenceBadge = (confidence: number, agreement: string, needsReview: boolean) => {
    let colorClass = "bg-rose-500/10 text-rose-400 border-rose-500/30";
    if (confidence >= 0.9 && !needsReview) {
      colorClass = "bg-emerald-500/10 text-emerald-400 border-emerald-500/30";
    } else if (confidence >= 0.75 && !needsReview) {
      colorClass = "bg-amber-500/10 text-amber-400 border-amber-500/30";
    }

    return (
      <div className="flex items-center space-x-1.5">
        <span
          className={`text-[11px] font-mono font-semibold px-2 py-0.5 rounded-full border ${colorClass} flex items-center space-x-1`}
        >
          {confidence >= 0.85 ? (
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
          ) : (
            <AlertCircle className="w-3 h-3 text-rose-400" />
          )}
          <span>{(confidence * 100).toFixed(0)}%</span>
        </span>
        <span className="text-[10px] font-mono text-slate-400 bg-slate-800/80 px-1.5 py-0.5 rounded border border-slate-700/60">
          {agreement}
        </span>
      </div>
    );
  };

  const formatFieldLabel = (key: string) => {
    return key
      .split("_")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
  };

  return (
    <div className="flex flex-col space-y-3">
      <div className="flex items-center justify-between pb-1 border-b border-slate-800/80">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center space-x-2">
          <Layers className="w-3.5 h-3.5 text-emerald-400" />
          <span>Extracted Header & Scalar Fields</span>
        </h3>
        <span className="text-[11px] text-slate-400">Click field to inspect multi-model consensus</span>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        {Object.entries(fields).map(([key, field]) => {
          const isContested = field.confidence < 0.85 || field.needs_review;
          const isPopoverOpen = activePopover === key;

          return (
            <div
              key={key}
              className={`relative glass-card rounded-xl p-3 border transition-all ${
                isContested
                  ? "border-rose-500/30 hover:border-rose-500/50 bg-rose-950/10"
                  : "border-slate-800 hover:border-slate-700"
              }`}
            >
              {/* Field Header */}
              <div className="flex items-center justify-between mb-1.5">
                <label className="text-xs font-semibold text-slate-300">
                  {formatFieldLabel(key)}
                </label>
                {getConfidenceBadge(field.confidence, field.agreement, field.needs_review)}
              </div>

              {/* Editable Value Input */}
              <div className="flex items-center space-x-2">
                <input
                  type="text"
                  value={field.value !== null && field.value !== undefined ? String(field.value) : ""}
                  onChange={(e) => onFieldChange(key, e.target.value)}
                  className="w-full bg-dark-900/90 text-sm font-medium text-white px-3 py-1.5 rounded-lg border border-slate-700 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500/20 transition-all"
                  placeholder="Empty / null"
                />
                <button
                  type="button"
                  onClick={() => setActivePopover(isPopoverOpen ? null : key)}
                  title="View Model Candidates"
                  className={`p-2 rounded-lg border text-xs flex items-center space-x-1 transition-all ${
                    isPopoverOpen
                      ? "bg-emerald-500/20 border-emerald-500/40 text-emerald-300"
                      : "border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
                  }`}
                >
                  <ChevronDown className={`w-3.5 h-3.5 transition-transform ${isPopoverOpen ? "rotate-180" : ""}`} />
                </button>
              </div>

              {/* Multi-Model Candidate Popover */}
              {isPopoverOpen && (
                <div className="mt-2.5 pt-2.5 border-t border-slate-800/80 flex flex-col space-y-1.5 bg-dark-950/90 rounded-lg p-2.5 border border-slate-800 text-xs shadow-xl animate-in fade-in slide-in-from-top-1">
                  <div className="flex items-center justify-between text-[11px] text-slate-400 font-semibold mb-1">
                    <span>Model Predictions Comparison:</span>
                    <span className="text-[10px] text-emerald-400 font-mono">1-Click to apply</span>
                  </div>

                  {Object.entries(field.candidates || {}).map(([modelName, candVal]) => (
                    <div
                      key={modelName}
                      onClick={() => {
                        onFieldChange(key, candVal);
                        setActivePopover(null);
                      }}
                      className="flex items-center justify-between px-2.5 py-1.5 rounded-md hover:bg-slate-800/80 cursor-pointer border border-transparent hover:border-slate-700 transition-all"
                    >
                      <span className="font-mono text-[11px] text-slate-400 capitalize">
                        {modelName.replace("_", " ")}:
                      </span>
                      <span className="font-medium text-slate-200 truncate max-w-[200px]">
                        {candVal !== null && candVal !== undefined ? String(candVal) : "null"}
                      </span>
                    </div>
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
