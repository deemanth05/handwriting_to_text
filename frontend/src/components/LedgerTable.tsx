import React from "react";
import { CheckCircle2, AlertTriangle, Trash2, Plus, Calculator, Wrench } from "lucide-react";
import { LedgerTransactionItem } from "../types/document";

interface LedgerTableProps {
  items: LedgerTransactionItem[];
  onItemsChange: (items: LedgerTransactionItem[]) => void;
}

export const LedgerTable: React.FC<LedgerTableProps> = ({ items, onItemsChange }) => {
  const recomputeBalances = (rawItems: LedgerTransactionItem[]): LedgerTransactionItem[] => {
    if (rawItems.length === 0) return [];
    const updated = rawItems.map((item) => ({ ...item }));

    const initBal = Number(updated[0].running_balance.value);
    const initIn = Number(updated[0].cash_in_credit.value || 0);
    const initOut = Number(updated[0].cash_out_debit.value || 0);
    let prevBal = (!isNaN(initBal) && initBal !== 0) ? initBal : (initIn - initOut);
    updated[0].balance_math_valid = true;

    for (let i = 1; i < updated.length; i++) {
      const outVal = Number(updated[i].cash_out_debit.value || 0);
      const inVal = Number(updated[i].cash_in_credit.value || 0);
      const balVal = Number(updated[i].running_balance.value || 0);

      const expected = Math.round((prevBal + inVal - outVal) * 100) / 100;
      const diff = Math.abs(expected - balVal);

      updated[i].balance_math_valid = diff <= 0.05;
      updated[i].needs_review = !updated[i].balance_math_valid;
      prevBal = balVal;
    }

    return updated;
  };

  const handleCellChange = (
    rowIndex: number,
    field: "entry_date" | "particulars" | "cash_out_debit" | "cash_in_credit" | "running_balance",
    value: any
  ) => {
    const updated = items.map((it) => ({ ...it }));
    const targetItem = { ...updated[rowIndex] };

    if (field === "entry_date" || field === "particulars") {
      targetItem[field] = { ...targetItem[field], value: String(value) };
    } else {
      const numVal = parseFloat(value) || 0;
      targetItem[field] = { ...targetItem[field], value: numVal };
    }

    updated[rowIndex] = targetItem;
    const finalItems = recomputeBalances(updated);
    onItemsChange(finalItems);
  };

  const handleFixBalance = (rowIndex: number) => {
    if (rowIndex === 0) return;
    const updated = items.map((it) => ({ ...it }));
    const prevBal = Number(updated[rowIndex - 1].running_balance.value || 0);
    const outVal = Number(updated[rowIndex].cash_out_debit.value || 0);
    const inVal = Number(updated[rowIndex].cash_in_credit.value || 0);
    const expected = Math.round((prevBal + inVal - outVal) * 100) / 100;

    updated[rowIndex].running_balance = {
      ...updated[rowIndex].running_balance,
      value: expected,
      confidence: 0.95,
      needs_review: false,
    };
    updated[rowIndex].balance_math_valid = true;
    updated[rowIndex].needs_review = false;

    const finalItems = recomputeBalances(updated);
    onItemsChange(finalItems);
  };

  const handleAddRow = () => {
    const lastBal = items.length > 0 ? Number(items[items.length - 1].running_balance.value || 0) : 0;
    const newRow: LedgerTransactionItem = {
      row_id: items.length + 1,
      entry_date: {
        value: "",
        confidence: 1.0,
        agreement: "1/1",
        candidates: {},
        needs_review: false,
      },
      particulars: {
        value: "New Transaction",
        confidence: 1.0,
        agreement: "1/1",
        candidates: {},
        needs_review: false,
      },
      voucher_no: null,
      cash_out_debit: {
        value: 0.0,
        confidence: 1.0,
        agreement: "1/1",
        candidates: {},
        needs_review: false,
      },
      cash_in_credit: {
        value: 0.0,
        confidence: 1.0,
        agreement: "1/1",
        candidates: {},
        needs_review: false,
      },
      running_balance: {
        value: lastBal,
        confidence: 1.0,
        agreement: "1/1",
        candidates: {},
        needs_review: false,
      },
      balance_math_valid: true,
      needs_review: false,
    };
    onItemsChange([...items, newRow]);
  };

  const handleDeleteRow = (index: number) => {
    const updated = items.filter((_, i) => i !== index);
    const finalItems = recomputeBalances(updated);
    onItemsChange(finalItems);
  };

  // Summaries
  const totalOut = items.reduce((sum, it) => sum + (Number(it.cash_out_debit.value) || 0), 0);
  const totalIn = items.reduce((sum, it) => sum + (Number(it.cash_in_credit.value) || 0), 0);
  const closingBalance = items.length > 0 ? Number(items[items.length - 1].running_balance.value || 0) : 0;
  const invalidRowsCount = items.filter((it) => !it.balance_math_valid).length;

  return (
    <div className="flex flex-col space-y-3 bg-dark-900/60 p-4 rounded-xl border border-slate-800">
      <div className="flex items-center justify-between">
        <div className="flex items-center space-x-2">
          <Calculator className="w-4 h-4 text-emerald-400" />
          <h3 className="text-xs font-semibold uppercase tracking-wider text-slate-300">
            Cash Book / Ledger Entries ({items.length})
          </h3>
          {invalidRowsCount > 0 ? (
            <span className="flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-rose-500/10 text-rose-400 border border-rose-500/30">
              <AlertTriangle className="w-3 h-3" />
              <span>{invalidRowsCount} Balance Discrepancies</span>
            </span>
          ) : (
            <span className="flex items-center space-x-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/30">
              <CheckCircle2 className="w-3 h-3" />
              <span>Running Balances Verified</span>
            </span>
          )}
        </div>
        <button
          type="button"
          onClick={handleAddRow}
          className="flex items-center space-x-1 px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-xs font-medium text-slate-200 transition-colors border border-slate-700"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Add Entry</span>
        </button>
      </div>

      <div className="overflow-x-auto rounded-lg border border-slate-800">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-slate-800/80 text-slate-400 border-b border-slate-700 font-medium">
              <th className="py-2.5 px-3 w-10 text-center">#</th>
              <th className="py-2.5 px-3 w-24">Date</th>
              <th className="py-2.5 px-3">Particulars / Details</th>
              <th className="py-2.5 px-3 w-28 text-right">Cash Out (Debit)</th>
              <th className="py-2.5 px-3 w-28 text-right">Cash In (Credit)</th>
              <th className="py-2.5 px-3 w-32 text-right">Balance</th>
              <th className="py-2.5 px-3 w-36 text-center">Audit Status</th>
              <th className="py-2.5 px-3 w-12 text-center"></th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-mono">
            {items.map((item, idx) => {
              const prevBal = idx > 0 ? Number(items[idx - 1].running_balance.value || 0) : 0;
              const outV = Number(item.cash_out_debit.value || 0);
              const inV = Number(item.cash_in_credit.value || 0);
              const expectedBal = idx === 0 ? Number(item.running_balance.value || 0) : Math.round((prevBal + inV - outV) * 100) / 100;
              const actualBal = Number(item.running_balance.value || 0);
              const diff = Math.abs(expectedBal - actualBal);
              const isValid = idx === 0 || diff <= 0.05;

              return (
                <tr
                  key={item.row_id || idx}
                  className={`hover:bg-slate-800/40 transition-colors ${
                    !isValid ? "bg-rose-950/20" : ""
                  }`}
                >
                  <td className="py-2 px-3 text-center text-slate-500 font-sans text-[11px]">
                    {idx + 1}
                  </td>
                  <td className="py-2 px-3">
                    <input
                      type="text"
                      value={item.entry_date.value || ""}
                      onChange={(e) => handleCellChange(idx, "entry_date", e.target.value)}
                      placeholder="DD/MM"
                      className="w-full bg-transparent px-2 py-1 rounded border border-transparent hover:border-slate-700 focus:border-emerald-500 focus:bg-slate-900 text-slate-200 outline-none transition-colors"
                    />
                  </td>
                  <td className="py-2 px-3 font-sans">
                    <input
                      type="text"
                      value={item.particulars.value || ""}
                      onChange={(e) => handleCellChange(idx, "particulars", e.target.value)}
                      className="w-full bg-transparent px-2 py-1 rounded border border-transparent hover:border-slate-700 focus:border-emerald-500 focus:bg-slate-900 text-slate-100 outline-none transition-colors"
                    />
                  </td>
                  <td className="py-2 px-3 text-right">
                    <input
                      type="number"
                      step="0.01"
                      value={item.cash_out_debit.value !== null && item.cash_out_debit.value !== undefined ? item.cash_out_debit.value : ""}
                      onChange={(e) => handleCellChange(idx, "cash_out_debit", e.target.value)}
                      placeholder="0.00"
                      className="w-full text-right bg-transparent px-2 py-1 rounded border border-transparent hover:border-slate-700 focus:border-emerald-500 focus:bg-slate-900 text-amber-300 outline-none transition-colors"
                    />
                  </td>
                  <td className="py-2 px-3 text-right">
                    <input
                      type="number"
                      step="0.01"
                      value={item.cash_in_credit.value !== null && item.cash_in_credit.value !== undefined ? item.cash_in_credit.value : ""}
                      onChange={(e) => handleCellChange(idx, "cash_in_credit", e.target.value)}
                      placeholder="0.00"
                      className="w-full text-right bg-transparent px-2 py-1 rounded border border-transparent hover:border-slate-700 focus:border-emerald-500 focus:bg-slate-900 text-emerald-300 outline-none transition-colors"
                    />
                  </td>
                  <td className="py-2 px-3 text-right">
                    <input
                      type="number"
                      step="0.01"
                      value={item.running_balance.value !== null && item.running_balance.value !== undefined ? item.running_balance.value : ""}
                      onChange={(e) => handleCellChange(idx, "running_balance", e.target.value)}
                      className={`w-full text-right bg-transparent px-2 py-1 rounded border font-semibold outline-none transition-colors ${
                        isValid
                          ? "border-transparent hover:border-slate-700 text-white"
                          : "border-rose-500 bg-rose-500/10 text-rose-300"
                      }`}
                    />
                  </td>
                  <td className="py-2 px-3 text-center font-sans">
                    {isValid ? (
                      <span className="inline-flex items-center space-x-1 text-emerald-400 text-[11px] font-medium">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Verified</span>
                      </span>
                    ) : (
                      <div className="flex items-center justify-center space-x-1.5">
                        <span className="text-[10px] text-rose-400 font-medium">
                          Diff: Rs. {diff.toFixed(2)}
                        </span>
                        <button
                          type="button"
                          onClick={() => handleFixBalance(idx)}
                          title={`Auto-correct balance to expected: Rs. ${expectedBal.toFixed(2)}`}
                          className="flex items-center space-x-1 px-1.5 py-0.5 rounded bg-amber-500/20 hover:bg-amber-500/30 text-amber-300 border border-amber-500/40 text-[10px] transition-colors"
                        >
                          <Wrench className="w-3 h-3" />
                          <span>Fix</span>
                        </button>
                      </div>
                    )}
                  </td>
                  <td className="py-2 px-3 text-center">
                    <button
                      type="button"
                      onClick={() => handleDeleteRow(idx)}
                      className="p-1 rounded text-slate-500 hover:text-rose-400 hover:bg-slate-800 transition-colors"
                      title="Delete Entry"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="bg-slate-800/90 font-mono text-xs font-semibold text-slate-200 border-t border-slate-700">
              <td colSpan={3} className="py-2.5 px-3 text-right font-sans text-slate-400">
                Totals:
              </td>
              <td className="py-2.5 px-3 text-right text-amber-300">
                Rs. {totalOut.toFixed(2)}
              </td>
              <td className="py-2.5 px-3 text-right text-emerald-300">
                Rs. {totalIn.toFixed(2)}
              </td>
              <td className="py-2.5 px-3 text-right text-white">
                Rs. {closingBalance.toFixed(2)}
              </td>
              <td colSpan={2} className="py-2.5 px-3 text-center font-sans text-slate-400 text-[11px]">
                Net: Rs. {(totalIn - totalOut).toFixed(2)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
};
