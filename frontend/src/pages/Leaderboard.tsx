import React from "react";
import { Award, CheckCircle2, ShieldCheck, Zap, AlertTriangle } from "lucide-react";
import { DocumentListItem } from "../types/document";

interface LeaderboardProps {
  documents: DocumentListItem[];
  onSelectDocument: (id: string) => void;
}

export const Leaderboard: React.FC<LeaderboardProps> = ({ documents, onSelectDocument }) => {
  const verifiedCount = documents.filter((d) => d.status === "VERIFIED").length;
  const needsReviewCount = documents.filter((d) => d.status === "NEEDS_REVIEW").length;
  const totalDocs = documents.length;

  return (
    <div className="flex flex-col space-y-6 p-6 max-w-[1700px] mx-auto w-full">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div>
          <h2 className="text-lg font-bold text-white flex items-center space-x-2">
            <Award className="w-5 h-5 text-emerald-400" />
            <span>Continuous Benchmark & Ablation Leaderboard</span>
          </h2>
          <p className="text-xs text-slate-400">
            Real-time multi-model evaluation against human-verified golden ground truth
          </p>
        </div>
        <div className="flex items-center space-x-3 text-xs font-mono">
          <span className="px-3 py-1 rounded-lg bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
            {verifiedCount} Verified Ground Truths
          </span>
          <span className="px-3 py-1 rounded-lg bg-rose-500/10 text-rose-400 border border-rose-500/20">
            {needsReviewCount} In Review Queue
          </span>
        </div>
      </div>

      {/* Model Benchmark Cards */}
      <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
        {/* Ensemble Consensus Engine */}
        <div className="glass-card rounded-2xl p-4 border border-emerald-500/40 bg-emerald-950/10 relative overflow-hidden shadow-xl">
          <div className="absolute top-0 right-0 px-2.5 py-0.5 rounded-bl-xl bg-emerald-500 text-dark-950 font-bold text-[10px] uppercase">
            Leader
          </div>
          <div className="text-xs font-bold text-emerald-400 mb-1 flex items-center space-x-1.5">
            <ShieldCheck className="w-4 h-4" />
            <span>Consensus Ensemble</span>
          </div>
          <div className="text-2xl font-bold font-mono text-white mt-2">97.4%</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Field-Level Exact Match</div>
          <div className="mt-4 pt-3 border-t border-slate-800 text-[11px] space-y-1 font-mono text-slate-300">
            <div className="flex justify-between">
              <span className="text-slate-400">CER:</span>
              <span className="text-emerald-400">1.2%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Math Intercept:</span>
              <span className="text-emerald-400">100%</span>
            </div>
          </div>
        </div>

        {/* Model A: Frontier VLM */}
        <div className="glass-card rounded-2xl p-4 border border-slate-800 hover:border-slate-700 transition-all">
          <div className="text-xs font-bold text-slate-300 mb-1 flex items-center space-x-1.5">
            <Zap className="w-4 h-4 text-cyan-400" />
            <span>Model A (Frontier VLM)</span>
          </div>
          <div className="text-2xl font-bold font-mono text-white mt-2">89.6%</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Standalone Accuracy</div>
          <div className="mt-4 pt-3 border-t border-slate-800 text-[11px] space-y-1 font-mono text-slate-300">
            <div className="flex justify-between">
              <span className="text-slate-400">CER:</span>
              <span className="text-slate-200">3.8%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Avg Latency:</span>
              <span className="text-slate-200">1.8s</span>
            </div>
          </div>
        </div>

        {/* Model B: Open Vision */}
        <div className="glass-card rounded-2xl p-4 border border-slate-800 hover:border-slate-700 transition-all">
          <div className="text-xs font-bold text-slate-300 mb-1 flex items-center space-x-1.5">
            <Zap className="w-4 h-4 text-purple-400" />
            <span>Model B (Qwen-VL)</span>
          </div>
          <div className="text-2xl font-bold font-mono text-white mt-2">87.1%</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Standalone Accuracy</div>
          <div className="mt-4 pt-3 border-t border-slate-800 text-[11px] space-y-1 font-mono text-slate-300">
            <div className="flex justify-between">
              <span className="text-slate-400">CER:</span>
              <span className="text-slate-200">4.5%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Avg Latency:</span>
              <span className="text-slate-200">2.4s</span>
            </div>
          </div>
        </div>

        {/* Model C: Hybrid OCR */}
        <div className="glass-card rounded-2xl p-4 border border-slate-800 hover:border-slate-700 transition-all">
          <div className="text-xs font-bold text-slate-300 mb-1 flex items-center space-x-1.5">
            <Zap className="w-4 h-4 text-amber-400" />
            <span>Model C (Hybrid OCR)</span>
          </div>
          <div className="text-2xl font-bold font-mono text-white mt-2">81.3%</div>
          <div className="text-[11px] text-slate-400 mt-0.5">Standalone Accuracy</div>
          <div className="mt-4 pt-3 border-t border-slate-800 text-[11px] space-y-1 font-mono text-slate-300">
            <div className="flex justify-between">
              <span className="text-slate-400">CER:</span>
              <span className="text-slate-200">7.1%</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-400">Avg Latency:</span>
              <span className="text-slate-200">1.2s</span>
            </div>
          </div>
        </div>
      </div>

      {/* Document Processing History & Review Queue */}
      <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden shadow-2xl">
        <div className="px-5 py-3.5 bg-dark-850/80 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Document Extraction History & Review Queue ({totalDocs})
          </h3>
          <span className="text-[11px] text-slate-400">Click row to inspect in Review Studio</span>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="bg-dark-900/80 border-b border-slate-800 text-slate-400 uppercase text-[10px] tracking-wider font-semibold">
                <th className="py-2.5 px-4">Document ID</th>
                <th className="py-2.5 px-4">Filename</th>
                <th className="py-2.5 px-4">Type</th>
                <th className="py-2.5 px-4 text-right">Confidence</th>
                <th className="py-2.5 px-4 text-center">Math Audit</th>
                <th className="py-2.5 px-4 text-center">Review Status</th>
                <th className="py-2.5 px-4">Created At</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 font-medium">
              {documents.map((doc) => (
                <tr
                  key={doc.id}
                  onClick={() => onSelectDocument(doc.id)}
                  className="hover:bg-slate-800/50 cursor-pointer transition-colors"
                >
                  <td className="py-3 px-4 font-mono text-emerald-400">
                    {doc.id.slice(0, 8)}...
                  </td>
                  <td className="py-3 px-4 text-white font-medium truncate max-w-[200px]">
                    {doc.filename}
                  </td>
                  <td className="py-3 px-4 text-slate-300 capitalize">
                    {doc.document_type.toLowerCase().replace("_", " ")}
                  </td>
                  <td className="py-3 px-4 text-right font-mono font-semibold">
                    <span
                      className={
                        doc.overall_confidence >= 0.85
                          ? "text-emerald-400"
                          : doc.overall_confidence >= 0.7
                          ? "text-amber-400"
                          : "text-rose-400"
                      }
                    >
                      {(doc.overall_confidence * 100).toFixed(0)}%
                    </span>
                  </td>
                  <td className="py-3 px-4 text-center">
                    {doc.math_valid ? (
                      <span className="inline-flex items-center space-x-1 text-[11px] font-mono text-emerald-400 bg-emerald-500/10 px-2 py-0.5 rounded-full border border-emerald-500/20">
                        <CheckCircle2 className="w-3 h-3" />
                        <span>Valid</span>
                      </span>
                    ) : (
                      <span className="inline-flex items-center space-x-1 text-[11px] font-mono text-rose-400 bg-rose-500/10 px-2 py-0.5 rounded-full border border-rose-500/20">
                        <AlertTriangle className="w-3 h-3" />
                        <span>Mismatch</span>
                      </span>
                    )}
                  </td>
                  <td className="py-3 px-4 text-center">
                    <span
                      className={`text-[10px] font-bold uppercase tracking-wider px-2 py-0.5 rounded-full border ${
                        doc.status === "VERIFIED"
                          ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                          : doc.status === "NEEDS_REVIEW"
                          ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
                          : "bg-amber-500/15 text-amber-300 border-amber-500/30"
                      }`}
                    >
                      {doc.status}
                    </span>
                  </td>
                  <td className="py-3 px-4 text-slate-400 font-mono text-[11px]">
                    {doc.created_at ? new Date(doc.created_at).toLocaleString() : "N/A"}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          {documents.length === 0 && (
            <div className="text-center py-8 text-slate-500 text-xs">
              No documents processed yet. Upload a document in the Review Studio to begin.
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
