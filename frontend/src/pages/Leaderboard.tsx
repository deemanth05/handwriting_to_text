import { useState, useEffect } from "react";
import {
  Award,
  CheckCircle2,
  ShieldCheck,
  Zap,
  AlertTriangle,
  FileSearch,
  X,
  TrendingUp,
} from "lucide-react";
import { BenchmarkSummaryResponse, DocumentDiffResponse, DocumentListItem } from "../types/document";
import { getBenchmarkSummary, getDocumentDiff } from "../services/api";

interface LeaderboardProps {
  documents: DocumentListItem[];
  onSelectDocument: (id: string) => void;
}

export const Leaderboard: React.FC<LeaderboardProps> = ({ documents, onSelectDocument }) => {
  const [summary, setSummary] = useState<BenchmarkSummaryResponse | null>(null);
  const [activeDiffDocId, setActiveDiffDocId] = useState<string | null>(null);
  const [activeDiff, setActiveDiff] = useState<DocumentDiffResponse | null>(null);
  const [loadingDiff, setLoadingDiff] = useState<boolean>(false);

  useEffect(() => {
    const fetchSummary = async () => {
      try {
        const data = await getBenchmarkSummary();
        setSummary(data);
      } catch (e) {
        console.error("Failed to load benchmark summary:", e);
      }
    };
    fetchSummary();
  }, [documents]);

  const handleOpenDiff = async (docId: string, e: React.MouseEvent) => {
    e.stopPropagation();
    setActiveDiffDocId(docId);
    setLoadingDiff(true);
    try {
      const diff = await getDocumentDiff(docId);
      setActiveDiff(diff);
    } catch {
      setActiveDiff(null);
    } finally {
      setLoadingDiff(false);
    }
  };

  const handleCloseDiff = () => {
    setActiveDiffDocId(null);
    setActiveDiff(null);
  };

  const verifiedCount = summary?.verified_ground_truths_count ?? documents.filter((d) => d.status === "VERIFIED").length;
  const needsReviewCount = summary?.needs_review_count ?? documents.filter((d) => d.status === "NEEDS_REVIEW").length;
  const totalDocs = summary?.total_documents_processed ?? documents.length;

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
            Real-time evaluation against golden ground truth • ECE Calibration & CER
          </p>
        </div>
        <div className="flex items-center space-x-3 text-xs font-mono">
          {summary && summary.ensemble_accuracy_gain > 0 && (
            <span className="flex items-center space-x-1 px-3 py-1 rounded-lg bg-emerald-500/15 text-emerald-300 border border-emerald-500/30">
              <TrendingUp className="w-3.5 h-3.5" />
              <span>+{summary.ensemble_accuracy_gain.toFixed(1)}% Ensemble Gain</span>
            </span>
          )}
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
        {(summary?.models || []).map((m, idx) => {
          const isLeader = idx === 0 || m.model_name.includes("Ensemble");

          return (
            <div
              key={m.model_name}
              className={`glass-card rounded-2xl p-4 border relative overflow-hidden shadow-xl transition-all ${
                isLeader
                  ? "border-emerald-500/40 bg-emerald-950/15"
                  : "border-slate-800 hover:border-slate-700"
              }`}
            >
              {isLeader && (
                <div className="absolute top-0 right-0 px-2.5 py-0.5 rounded-bl-xl bg-emerald-500 text-dark-950 font-bold text-[10px] uppercase">
                  Leader
                </div>
              )}

              <div className="text-xs font-bold text-slate-300 mb-1 flex items-center space-x-1.5">
                {isLeader ? (
                  <ShieldCheck className="w-4 h-4 text-emerald-400" />
                ) : (
                  <Zap className="w-4 h-4 text-cyan-400" />
                )}
                <span className={isLeader ? "text-emerald-300" : ""}>{m.model_name}</span>
              </div>

              <div className="text-2xl font-bold font-mono text-white mt-2">
                {m.exact_match_accuracy.toFixed(1)}%
              </div>
              <div className="text-[11px] text-slate-400 mt-0.5">Field-Level Exact Match</div>

              <div className="mt-4 pt-3 border-t border-slate-800 text-[11px] space-y-1.5 font-mono text-slate-300">
                <div className="flex justify-between">
                  <span className="text-slate-400">CER (Char Error):</span>
                  <span className={m.cer <= 2.0 ? "text-emerald-400 font-semibold" : "text-slate-300"}>
                    {m.cer.toFixed(1)}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Math Intercept:</span>
                  <span className={m.math_error_intercept_rate === 100 ? "text-emerald-400 font-semibold" : "text-amber-400"}>
                    {m.math_error_intercept_rate.toFixed(0)}%
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">Fields Evaluated:</span>
                  <span className="text-slate-200">{m.total_fields_evaluated}</span>
                </div>
              </div>
            </div>
          );
        })}
      </div>

      {/* Calibration & Expected Calibration Error (ECE) Section */}
      {summary && summary.calibration_curve && summary.calibration_curve.length > 0 && (
        <div className="glass-panel rounded-2xl p-4 border border-slate-800">
          <div className="flex items-center justify-between pb-2 mb-3 border-b border-slate-800/80">
            <div className="flex items-center space-x-2">
              <span className="text-xs font-bold uppercase tracking-wider text-slate-300">
                Confidence Calibration (ECE: {(summary.expected_calibration_error * 100).toFixed(1)}%)
              </span>
            </div>
            <span className="text-[11px] text-slate-400">
              Evaluates if a 90% confidence score accurately reflects 90% real-world accuracy
            </span>
          </div>

          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {summary.calibration_curve.map((b) => (
              <div key={b.confidence_bin} className="glass-card rounded-xl p-3 border border-slate-800/80">
                <div className="flex justify-between text-xs font-mono text-slate-400 mb-1">
                  <span>Bin: {b.confidence_bin}</span>
                  <span className="text-slate-300">n = {b.sample_count}</span>
                </div>
                <div className="flex justify-between items-baseline">
                  <span className="text-sm font-bold font-mono text-emerald-400">
                    {b.accuracy.toFixed(0)}% Acc
                  </span>
                  <span className="text-[11px] font-mono text-slate-400">
                    Conf: {(b.avg_confidence * 100).toFixed(0)}%
                  </span>
                </div>
                {/* Progress bar comparing conf vs acc */}
                <div className="w-full bg-slate-800 h-1.5 rounded-full mt-2 overflow-hidden flex">
                  <div
                    style={{ width: `${Math.min(100, b.accuracy)}%` }}
                    className="bg-emerald-500 h-full"
                  />
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Document History & Review Queue */}
      <div className="glass-panel rounded-2xl border border-slate-800 overflow-hidden shadow-2xl">
        <div className="px-5 py-3.5 bg-dark-850/80 border-b border-slate-800 flex items-center justify-between">
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Document Extraction History ({totalDocs})
          </h3>
          <span className="text-[11px] text-slate-400">Click row to open in Review Studio</span>
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
                <th className="py-2.5 px-4 text-center">Ablation Diff</th>
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
                  <td className="py-3 px-4 text-center">
                    {doc.status === "VERIFIED" ? (
                      <button
                        type="button"
                        onClick={(e) => handleOpenDiff(doc.id, e)}
                        className="inline-flex items-center space-x-1 text-[11px] px-2 py-1 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-all"
                      >
                        <FileSearch className="w-3.5 h-3.5 text-emerald-400" />
                        <span>View Diff</span>
                      </button>
                    ) : (
                      <span className="text-[11px] text-slate-500 font-mono">Unverified</span>
                    )}
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
              No documents processed yet.
            </div>
          )}
        </div>
      </div>

      {/* Model Diff Modal */}
      {activeDiffDocId && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-6 bg-dark-950/80 backdrop-blur-sm animate-in fade-in">
          <div className="glass-panel w-full max-w-4xl max-h-[80vh] rounded-2xl border border-slate-700 flex flex-col overflow-hidden shadow-2xl">
            {/* Modal Header */}
            <div className="flex items-center justify-between p-4 border-b border-slate-800 bg-dark-900/90">
              <div className="flex items-center space-x-2">
                <FileSearch className="w-4 h-4 text-emerald-400" />
                <h3 className="text-sm font-bold text-white">
                  Multi-Model Diff Report vs Ground Truth
                </h3>
                <span className="font-mono text-xs text-slate-400">
                  ({activeDiffDocId.slice(0, 8)}...)
                </span>
              </div>
              <button
                onClick={handleCloseDiff}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-all"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* Modal Content */}
            <div className="p-5 overflow-y-auto space-y-4">
              {loadingDiff ? (
                <div className="text-center py-10 text-xs text-slate-400">
                  Computing multi-model evaluation diff...
                </div>
              ) : activeDiff ? (
                <div className="space-y-4">
                  {/* Per-model accuracy summary bar */}
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                    {Object.entries(activeDiff.per_model_accuracy).map(([mName, acc]) => (
                      <div key={mName} className="glass-card rounded-xl p-2.5 border border-slate-800">
                        <div className="text-[10px] text-slate-400 capitalize">{mName.replace("_", " ")}</div>
                        <div className="text-base font-bold font-mono text-emerald-400 mt-0.5">{acc}%</div>
                      </div>
                    ))}
                  </div>

                  {/* Field diffs table */}
                  <div className="rounded-xl border border-slate-800 overflow-hidden">
                    <table className="w-full text-left text-xs border-collapse">
                      <thead>
                        <tr className="bg-dark-900 border-b border-slate-800 text-slate-400 text-[10px] uppercase font-semibold">
                          <th className="py-2 px-3">Field</th>
                          <th className="py-2 px-3">Verified Ground Truth</th>
                          <th className="py-2 px-3">Ensemble Reconciled</th>
                          <th className="py-2 px-3">Individual Model Predictions</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-medium">
                        {activeDiff.field_diffs.map((fd) => (
                          <tr key={fd.field_name} className="hover:bg-slate-800/30">
                            <td className="py-2.5 px-3 font-semibold text-slate-300">
                              {fd.field_name}
                            </td>
                            <td className="py-2.5 px-3 font-mono text-emerald-300">
                              {fd.ground_truth_value !== null ? String(fd.ground_truth_value) : "null"}
                            </td>
                            <td className="py-2.5 px-3">
                              <span
                                className={`font-mono ${
                                  fd.ensemble_correct ? "text-emerald-400" : "text-rose-400"
                                }`}
                              >
                                {fd.ensemble_value !== null ? String(fd.ensemble_value) : "null"}
                              </span>
                            </td>
                            <td className="py-2.5 px-3">
                              <div className="flex flex-col space-y-1">
                                {Object.entries(fd.model_predictions).map(([mName, p]) => (
                                  <div key={mName} className="flex items-center space-x-2 text-[11px]">
                                    <span className="text-slate-400 capitalize w-20 truncate">
                                      {mName.split("_")[0]}:
                                    </span>
                                    <span
                                      className={`font-mono truncate max-w-[150px] ${
                                        p.correct ? "text-slate-200" : "text-rose-400"
                                      }`}
                                    >
                                      {p.value !== null && p.value !== undefined ? String(p.value) : "null"}
                                    </span>
                                    {p.cer > 0 && (
                                      <span className="text-[10px] font-mono text-slate-500">
                                        (CER: {p.cer}%)
                                      </span>
                                    )}
                                  </div>
                                ))}
                              </div>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : (
                <div className="text-center py-10 text-xs text-rose-400">
                  Could not load diff for this document.
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
