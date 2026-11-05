import React from "react";
import { Cpu, Activity, BarChart3, FileText } from "lucide-react";

interface HeaderProps {
  activeTab: "workspace" | "leaderboard";
  setActiveTab: (tab: "workspace" | "leaderboard") => void;
  routerStatus: "ONLINE" | "OFFLINE" | "LOADING";
  documentStatus?: string;
  overallConfidence?: number;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  routerStatus,
  documentStatus,
  overallConfidence,
}) => {
  return (
    <header className="sticky top-0 z-50 glass-panel border-b border-slate-800/80 px-6 py-3.5 flex items-center justify-between">
      {/* Brand & Title */}
      <div className="flex items-center space-x-3.5">
        <div className="w-9 h-9 rounded-xl bg-gradient-to-tr from-emerald-500/20 to-cyan-500/20 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shadow-lg shadow-emerald-500/5">
          <Cpu className="w-5 h-5" />
        </div>
        <div>
          <div className="flex items-center space-x-2">
            <h1 className="text-base font-bold tracking-tight text-white">Paper-to-Structured-Data</h1>
            <span className="text-[10px] font-semibold uppercase tracking-wider px-2 py-0.5 rounded-full bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              Ensemble v1.0
            </span>
          </div>
          <p className="text-xs text-slate-400">Multi-Model Consensus & Human-in-the-Loop Studio</p>
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

      {/* Status Badges */}
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

        {/* FreeLLMAPI Router Health */}
        <div className="flex items-center space-x-2 px-3 py-1.5 rounded-lg glass-card border border-slate-700/60">
          <Activity
            className={`w-3.5 h-3.5 ${
              routerStatus === "ONLINE"
                ? "text-emerald-400 animate-pulse"
                : routerStatus === "LOADING"
                ? "text-amber-400"
                : "text-rose-400"
            }`}
          />
          <span className="text-slate-400">FreeLLMAPI:</span>
          <span
            className={`font-semibold ${
              routerStatus === "ONLINE"
                ? "text-emerald-400"
                : routerStatus === "LOADING"
                ? "text-amber-400"
                : "text-rose-400"
            }`}
          >
            {routerStatus}
          </span>
        </div>
      </div>
    </header>
  );
};
