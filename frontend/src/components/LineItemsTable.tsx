import React from "react";
import { CheckCircle2, AlertTriangle, Trash2, Plus, Calculator, Wrench } from "lucide-react";
import { LineItem } from "../types/document";

interface LineItemsTableProps {
  items: LineItem[];
  onItemsChange: (items: LineItem[]) => void;
  onPageClick?: (page: number) => void;
}

export const LineItemsTable: React.FC<LineItemsTableProps> = ({ items, onItemsChange, onPageClick }) => {
  const handleCellChange = (
    rowIndex: number,
    field: "description" | "quantity" | "unit_price" | "line_total",
    value: any
  ) => {
    const updated = [...items];
    const targetItem = { ...updated[rowIndex] };

    if (field === "description") {
      targetItem.description = { ...targetItem.description, value: String(value) };
    } else {
      const numVal = parseFloat(value) || 0;
      targetItem[field] = { ...targetItem[field], value: numVal };
    }

    // Re-verify deterministic row math
    const q = Number(targetItem.quantity.value || 0);
    const p = Number(targetItem.unit_price.value || 0);
    const t = Number(targetItem.line_total.value || 0);
    const expected = Math.round(q * p * 100) / 100;
    const diff = Math.abs(expected - t);

    targetItem.row_math_valid = diff <= 0.05;
    targetItem.needs_review = !targetItem.row_math_valid;

    updated[rowIndex] = targetItem;
    onItemsChange(updated);
  };

  const handleFixTotal = (rowIndex: number) => {
    const updated = [...items];
    const targetItem = { ...updated[rowIndex] };
    const q = Number(targetItem.quantity.value || 0);
    const p = Number(targetItem.unit_price.value || 0);
    const expected = Math.round(q * p * 100) / 100;

    targetItem.line_total = {
      ...targetItem.line_total,
      value: expected,
      confidence: 0.95,
      needs_review: false,
    };
    targetItem.row_math_valid = true;
    targetItem.needs_review = false;

    updated[rowIndex] = targetItem;
    onItemsChange(updated);
  };

  const handleAddRow = () => {
    const newRow: LineItem = {
      row_id: items.length + 1,
      description: {
        value: "New Item",
        confidence: 1.0,
        agreement: "1/1",
        candidates: {},
        needs_review: false,
      },
      quantity: {
        value: 1.0,
        confidence: 1.0,
        agreement: "1/1",
        candidates: {},
        needs_review: false,
      },
      unit_price: {
        value: 0.0,
        confidence: 1.0,
        agreement: "1/1",
        candidates: {},
        needs_review: false,
      },
      line_total: {
        value: 0.0,
        confidence: 1.0,
        agreement: "1/1",
        candidates: {},
        needs_review: false,
      },
      row_math_valid: true,
      needs_review: false,
    };
    onItemsChange([...items, newRow]);
  };

  const handleDeleteRow = (index: number) => {
    const updated = items.filter((_, i) => i !== index);
    onItemsChange(updated);
  };

  return (
    <div className="flex flex-col space-y-3">
      {/* Table Header Controls */}
      <div className="flex items-center justify-between pb-1 border-b border-slate-800/80">
        <div className="flex items-center space-x-2">
          <Calculator className="w-3.5 h-3.5 text-emerald-400" />
          <h3 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Line Items & Deterministic Row Math
          </h3>
          <span className="text-[10px] px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 font-mono">
            {items.length} rows
          </span>
        </div>
        <button
          type="button"
          onClick={handleAddRow}
          className="flex items-center space-x-1.5 px-3 py-1 rounded-lg bg-emerald-500/10 hover:bg-emerald-500/20 text-emerald-400 border border-emerald-500/30 text-xs font-medium transition-all"
        >
          <Plus className="w-3.5 h-3.5" />
          <span>Add Row</span>
        </button>
      </div>

      {/* Table Container */}
      <div className="overflow-x-auto rounded-xl border border-slate-800 bg-dark-900/60 shadow-xl">
        <table className="w-full text-left text-xs border-collapse">
          <thead>
            <tr className="bg-dark-850/90 border-b border-slate-800 text-slate-400 uppercase text-[10px] tracking-wider font-semibold">
              <th className="py-2.5 px-3 w-16 text-center">#</th>
              <th className="py-2.5 px-3 min-w-[200px]">Description</th>
              <th className="py-2.5 px-3 w-20 text-right">Qty</th>
              <th className="py-2.5 px-3 w-28 text-right">Rate</th>
              <th className="py-2.5 px-3 w-28 text-right">Total</th>
              <th className="py-2.5 px-3 min-w-[170px]">Arithmetic Verification</th>
              <th className="py-2.5 px-3 w-12 text-center">Del</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-800/60 font-medium">
            {items.map((row, idx) => {
              const q = Number(row.quantity.value || 0);
              const p = Number(row.unit_price.value || 0);
              const expected = Math.round(q * p * 100) / 100;
              const isMathValid = row.row_math_valid;

              return (
                <tr
                  key={idx}
                  className={`hover:bg-slate-800/40 transition-colors ${
                    !isMathValid ? "bg-rose-950/15" : ""
                  }`}
                >
                  {/* Row Index & Page Pill */}
                  <td className="py-2.5 px-2 text-center text-slate-400 font-mono text-[11px] whitespace-nowrap">
                    <span className="inline-flex items-center justify-center space-x-1">
                      <span>{idx + 1}</span>
                      {row.page_number && (
                        onPageClick ? (
                          <button
                            type="button"
                            onClick={() => onPageClick(row.page_number!)}
                            title={`Jump to Page ${row.page_number} in viewer`}
                            className="text-[9px] px-1 py-0.5 rounded bg-dark-950 hover:bg-emerald-500/20 text-emerald-400 hover:text-emerald-300 font-mono border border-slate-700/80 hover:border-emerald-500/50 leading-none cursor-pointer transition-all"
                          >
                            p.{row.page_number}
                          </button>
                        ) : (
                          <span
                            title={`Extracted from Page ${row.page_number}`}
                            className="text-[9px] px-1 py-0.5 rounded bg-dark-950 text-emerald-400 font-mono border border-slate-700/80 leading-none"
                          >
                            p.{row.page_number}
                          </span>
                        )
                      )}
                    </span>
                  </td>

                  {/* Description Input */}
                  <td className="py-2 px-3">
                    <input
                      type="text"
                      value={row.description.value || ""}
                      onChange={(e) => handleCellChange(idx, "description", e.target.value)}
                      className="w-full bg-transparent text-white focus:bg-dark-800 px-2 py-1 rounded border border-transparent focus:border-slate-700 outline-none transition-all"
                    />
                  </td>

                  {/* Quantity Input */}
                  <td className="py-2 px-3 text-right">
                    <input
                      type="number"
                      step="any"
                      value={row.quantity.value ?? ""}
                      onChange={(e) => handleCellChange(idx, "quantity", e.target.value)}
                      className="w-full text-right bg-transparent text-white focus:bg-dark-800 px-2 py-1 rounded border border-transparent focus:border-slate-700 outline-none font-mono transition-all"
                    />
                  </td>

                  {/* Unit Price Input */}
                  <td className="py-2 px-3 text-right">
                    <input
                      type="number"
                      step="any"
                      value={row.unit_price.value ?? ""}
                      onChange={(e) => handleCellChange(idx, "unit_price", e.target.value)}
                      className="w-full text-right bg-transparent text-white focus:bg-dark-800 px-2 py-1 rounded border border-transparent focus:border-slate-700 outline-none font-mono transition-all"
                    />
                  </td>

                  {/* Line Total Input */}
                  <td className="py-2 px-3 text-right">
                    <input
                      type="number"
                      step="any"
                      value={row.line_total.value ?? ""}
                      onChange={(e) => handleCellChange(idx, "line_total", e.target.value)}
                      className={`w-full text-right px-2 py-1 rounded border outline-none font-mono font-semibold transition-all ${
                        isMathValid
                          ? "bg-transparent text-white border-transparent focus:border-slate-700 focus:bg-dark-800"
                          : "bg-rose-950/50 text-rose-300 border-rose-500/50 focus:border-rose-400"
                      }`}
                    />
                  </td>

                  {/* Math Verification Badge & Quick Fix */}
                  <td className="py-2 px-3">
                    {isMathValid ? (
                      <div className="flex items-center space-x-1.5 text-emerald-400 text-[11px] font-mono">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                        <span>Valid (Exact)</span>
                      </div>
                    ) : (
                      <div className="flex items-center space-x-2">
                        <div className="flex items-center space-x-1 text-rose-400 text-[11px] font-mono">
                          <AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                          <span>Exp: {expected.toFixed(2)}</span>
                        </div>
                        <button
                          type="button"
                          onClick={() => handleFixTotal(idx)}
                          title="Correct line total to match quantity * unit price"
                          className="flex items-center space-x-1 text-[10px] font-medium bg-rose-500/20 hover:bg-rose-500/30 text-rose-300 px-2 py-0.5 rounded border border-rose-500/40 transition-all"
                        >
                          <Wrench className="w-2.5 h-2.5" />
                          <span>Fix</span>
                        </button>
                      </div>
                    )}
                  </td>

                  {/* Delete Action */}
                  <td className="py-2.5 px-3 text-center">
                    <button
                      type="button"
                      onClick={() => handleDeleteRow(idx)}
                      className="p-1 text-slate-500 hover:text-rose-400 hover:bg-rose-500/10 rounded transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>

        {items.length === 0 && (
          <div className="text-center py-6 text-slate-500 text-xs">
            No line items extracted. Click "Add Row" to add items manually.
          </div>
        )}
      </div>
    </div>
  );
};
