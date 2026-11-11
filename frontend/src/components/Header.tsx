import React, { useState } from "react";
import { Cpu, BarChart3, FileText, Server, ShieldCheck, ChevronDown } from "lucide-react";
import { RuntimeProbeReport } from "../services/api";

interface HeaderProps {
  activeTab: "workspace" | "leaderboard";
  setActiveTab: (tab: "workspace" | "leaderboard") => void;
  runtimesReport?: RuntimeProbeReport | null;
  onRefreshHealth?: () => void;
  documentStatus?: string;
  overallConfidence?: number;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  runtimesReport,
  onRefreshHealth,
  documentStatus,
  overallConfidence,
}) => {
  const [showRuntimeModal, setShowRuntimeModal] = useState(false);

  const ollama = runtimesReport?.runtimes?.ollama;
  const lmstudio = runtimesReport?.runtimes?.lmstudio;
  const freellm = runtimesReport?.runtimes?.freellm;

  return (
    <header className="sticky top-0 z-50 glass-panel border-b border-slate-800/80 px-6 py-3 flex items-center justify-between">
      {/* Brand & Title */}
      <div className="flex items-center space-x-3.5">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-500/20 to-cyan-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shadow-lg shadow-emerald-500/5">
          <Cpu className="w-5 h-5" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-base font-bold tracking-tight text-white">Paper-to-Structured-Data</h1>
            <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              Hybrid Ensemble v1.1
            </span>
          </div>
          <p className="text-xs text-slate-400">Multi-Model Consensus & Local VLM Studio</p>
        </div>
      </div>

      {/* Navigation Tabs */}
      <div className="flex items-center space-x-1 bg-dark-900/80 p-1 rounded-xl border border-slate-800">
        <button
          onClick={() => setActiveTab("workspace")}
          className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
            activeTab === "workspace"
              ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 shadow-sm"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <FileText className="w-3.5 h-3.5" />
          <span>Review Studio</span>
        </button>
        <button
          onClick={() => setActiveTab("leaderboard")}
          className={`flex items-center space-x-2 px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all ${
            activeTab === "leaderboard"
              ? "bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 shadow-sm"
              : "text-slate-400 hover:text-slate-200"
          }`}
        >
          <BarChart3 className="w-3.5 h-3.5" />
          <span>Leaderboard & Benchmarks</span>
        </button>
      </div>

      {/* Status Badges & Runtime Matrix */}
      <div className="flex items-center space-x-3 text-xs">
        {/* Document Status */}
        {documentStatus && (
          <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg glass-card border border-slate-700/60">
            <span className="text-slate-400">Status:</span>
            <span
              className={`font-semibold ${
                documentStatus === "VERIFIED"
                  ? "text-emerald-400"
                  : documentStatus === "NEEDS_REVIEW"
                  ? "text-rose-400"
                  : "text-amber-400"
              }`}
            >
              {documentStatus}
            </span>
            {overallConfidence !== undefined && (
              <span className="text-slate-500">
                ({(overallConfidence * 100).toFixed(0)}%)
              </span>
            )}
          </div>
        )}

        {/* Dynamic Hybrid Runtime Diagnostics Pill */}
        <div className="relative">
          <button
            type="button"
            onClick={() => setShowRuntimeModal(!showRuntimeModal)}
            title="Inspect active AI runtimes and circuit breaker status"
            className="flex items-center space-x-2 px-3 py-1.5 rounded-lg glass-card border border-slate-700/60 hover:border-slate-500 transition-colors cursor-pointer"
          >
            <Server className="w-3.5 h-3.5 text-cyan-400" />
            <span className="text-slate-400 font-medium">Runtimes:</span>
            <div className="flex items-center space-x-1.5 font-mono text-[11px]">
              <span
                className={`inline-flex items-center space-x-1 px-1.5 py-0.5 rounded ${
                  ollama?.status === "ONLINE"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                    : "bg-slate-800 text-slate-500"
                }`}
              >
                <span>Ollama</span>
              </span>
              <span
                className={`inline-flex items-center space-x-1 px-1.5 py-0.5 rounded ${
                  lmstudio?.status === "ONLINE"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                    : "bg-slate-800 text-slate-500"
                }`}
              >
                <span>LMStudio</span>
              </span>
              <span
                className={`inline-flex items-center space-x-1 px-1.5 py-0.5 rounded ${
                  freellm?.status === "ONLINE"
                    ? "bg-emerald-500/20 text-emerald-300 border border-emerald-500/30"
                    : "bg-slate-800 text-slate-500"
                }`}
              >
                <span>FreeLLM</span>
              </span>
              <span className="inline-flex items-center space-x-1 px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                <span>Surya+Rapid</span>
              </span>
            </div>
            <ChevronDown className="w-3 h-3 text-slate-400 ml-1" />
          </button>

          {/* Runtime Matrix Dropdown Drawer */}
          {showRuntimeModal && (
            <div className="absolute right-0 top-12 w-80 p-4 rounded-xl glass-card border border-slate-700 shadow-2xl z-50 animate-in fade-in slide-in-from-top-2 text-xs space-y-3">
              <div className="flex items-center justify-between pb-2 border-b border-slate-800">
                <span className="font-bold text-slate-200 flex items-center space-x-1.5">
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                  <span>Hybrid Runtime Telemetry</span>
                </span>
                <button
                  type="button"
                  onClick={onRefreshHealth}
                  className="text-[11px] text-cyan-400 hover:text-cyan-300 font-medium cursor-pointer"
                >
                  Refresh
                </button>
              </div>

              {/* Ollama Status */}
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-300">Ollama (11434)</span>
                  <span
                    className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
                      ollama?.status === "ONLINE"
                        ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                        : "bg-rose-500/20 text-rose-400"
                    }`}
                  >
                    {ollama?.status || "OFFLINE"}
                  </span>
                </div>
                {ollama?.models && ollama.models.length > 0 ? (
                  <p className="text-[10px] text-slate-400 font-mono truncate">
                    Models: {ollama.models.join(", ")}
                  </p>
                ) : (
                  <p className="text-[10px] text-slate-500">
                    Run `ollama serve` or open Ollama to enable local vision.
                  </p>
                )}
              </div>

              {/* LM Studio Status */}
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-300">LM Studio (1234)</span>
                  <span
                    className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
                      lmstudio?.status === "ONLINE"
                        ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                        : "bg-rose-500/20 text-rose-400"
                    }`}
                  >
                    {lmstudio?.status || "OFFLINE"}
                  </span>
                </div>
                {lmstudio?.models && lmstudio.models.length > 0 ? (
                  <p className="text-[10px] text-slate-400 font-mono truncate">
                    Loaded: {lmstudio.models.join(", ")}
                  </p>
                ) : (
                  <p className="text-[10px] text-slate-500">Start local server on port 1234 in LM Studio.</p>
                )}
              </div>

              {/* FreeLLMAPI Status */}
              <div className="space-y-1">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-300">FreeLLMAPI (3001)</span>
                  <span
                    className={`font-mono text-[10px] px-1.5 py-0.5 rounded ${
                      freellm?.status === "ONLINE"
                        ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                        : "bg-rose-500/20 text-rose-400"
                    }`}
                  >
                    {freellm?.status || "OFFLINE"}
                  </span>
                </div>
              </div>

              {/* Local Deterministic OCR Engines */}
              <div className="pt-2 border-t border-slate-800 space-y-1">
                <div className="flex items-center justify-between text-slate-300">
                  <span>Surya Multilingual OCR</span>
                  <span className="text-emerald-400 font-mono text-[10px]">ACTIVE (CPU/Torch)</span>
                </div>
                <div className="flex items-center justify-between text-slate-300">
                  <span>RapidOCR ONNX</span>
                  <span className="text-emerald-400 font-mono text-[10px]">ACTIVE (CPU/ONNX)</span>
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </header>
  );
};
