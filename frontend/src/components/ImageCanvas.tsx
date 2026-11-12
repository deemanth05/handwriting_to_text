import React, { useState, useRef, useEffect } from "react";
import { ZoomIn, ZoomOut, RotateCw, Maximize2, RefreshCw, Eye, Sparkles, ChevronLeft, ChevronRight } from "lucide-react";

interface ImageCanvasProps {
  imageUrl: string | null;
  filename?: string;
  deskewAngle?: number;
  pageCount?: number;
  currentPage?: number;
  onPageChange?: (page: number) => void;
}

export const ImageCanvas: React.FC<ImageCanvasProps> = ({
  imageUrl,
  filename,
  deskewAngle = 0,
  pageCount = 1,
  currentPage = 1,
  onPageChange,
}) => {
  const [scale, setScale] = useState<number>(1);
  const [position, setPosition] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [rotation, setRotation] = useState<number>(0);
  const [isDragging, setIsDragging] = useState<boolean>(false);
  const [dragStart, setDragStart] = useState<{ x: number; y: number }>({ x: 0, y: 0 });
  const [highContrast, setHighContrast] = useState<boolean>(false);

  const containerRef = useRef<HTMLDivElement>(null);

  // Keyboard navigation for multi-page documents (Left/Right arrow keys)
  useEffect(() => {
    if (!pageCount || pageCount <= 1 || !onPageChange) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      // Do not intercept if browser modifier keys are held (e.g. Alt+Left for back)
      if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;

      const tag = (document.activeElement?.tagName || "").toLowerCase();
      if (
        tag === "input" ||
        tag === "textarea" ||
        tag === "select" ||
        (document.activeElement as HTMLElement)?.isContentEditable
      ) {
        return;
      }

      if (e.key === "ArrowLeft") {
        e.preventDefault();
        onPageChange(Math.max(1, currentPage - 1));
      } else if (e.key === "ArrowRight") {
        e.preventDefault();
        onPageChange(Math.min(pageCount, currentPage + 1));
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [pageCount, currentPage, onPageChange]);

  // Reset view when image changes
  useEffect(() => {
    setScale(1);
    setPosition({ x: 0, y: 0 });
    setRotation(0);
  }, [imageUrl]);

  const handleZoomIn = () => setScale((s) => Math.min(s + 0.25, 4.0));
  const handleZoomOut = () => setScale((s) => Math.max(s - 0.25, 0.4));
  const handleReset = () => {
    setScale(1);
    setPosition({ x: 0, y: 0 });
    setRotation(0);
  };
  const handleRotate = () => setRotation((r) => (r + 90) % 360);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (e.button !== 0) return; // Primary button only
    setIsDragging(true);
    setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    if (!isDragging) return;
    setPosition({
      x: e.clientX - dragStart.x,
      y: e.clientY - dragStart.y,
    });
  };

  const handleMouseUp = () => setIsDragging(false);

  const handleWheel = (e: React.WheelEvent) => {
    e.preventDefault();
    const delta = e.deltaY < 0 ? 0.15 : -0.15;
    setScale((s) => Math.max(0.4, Math.min(4.0, s + delta)));
  };

  return (
    <div className="relative flex flex-col h-full bg-dark-900 rounded-2xl border border-slate-800 overflow-hidden shadow-2xl">
      {/* Canvas Top Toolbar */}
      <div className="flex items-center justify-between px-4 py-2.5 bg-dark-850/90 border-b border-slate-800/80 backdrop-blur z-10 text-xs">
        <div className="flex items-center space-x-2 text-slate-300 truncate">
          <Eye className="w-3.5 h-3.5 text-slate-400" />
          <span className="font-medium truncate max-w-[180px]">{filename || "Document Viewer"}</span>
          {deskewAngle !== 0 && (
            <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              Auto-Deskew {deskewAngle.toFixed(1)}°
            </span>
          )}
        </div>

        {/* Multi-Page Navigation Controls */}
        {pageCount > 1 && (
          <div className="flex items-center space-x-1 px-1.5 py-0.5 rounded-lg bg-dark-950 border border-slate-700/80 shadow-inner">
            <button
              type="button"
              onClick={() => onPageChange && onPageChange(Math.max(1, currentPage - 1))}
              disabled={currentPage <= 1}
              title="Previous Page (Left Arrow)"
              className="flex items-center space-x-0.5 px-1.5 py-0.5 rounded text-[11px] text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-slate-800/60 transition-all font-medium"
            >
              <ChevronLeft className="w-3.5 h-3.5" />
              <span>Prev</span>
            </button>
            <span className="font-mono text-[11px] text-emerald-400 font-semibold px-1.5 select-none whitespace-nowrap">
              Page {currentPage} of {pageCount}
            </span>
            <button
              type="button"
              onClick={() => onPageChange && onPageChange(Math.min(pageCount, currentPage + 1))}
              disabled={currentPage >= pageCount}
              title="Next Page (Right Arrow)"
              className="flex items-center space-x-0.5 px-1.5 py-0.5 rounded text-[11px] text-slate-400 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed hover:bg-slate-800/60 transition-all font-medium"
            >
              <span>Next</span>
              <ChevronRight className="w-3.5 h-3.5" />
            </button>
          </div>
        )}

        {/* Toolbar Controls */}
        <div className="flex items-center space-x-1.5">
          <button
            onClick={() => setHighContrast(!highContrast)}
            title="Toggle High-Contrast Filter"
            className={`p-1.5 rounded-lg border transition-all ${
              highContrast
                ? "bg-amber-500/20 border-amber-500/40 text-amber-300"
                : "border-slate-700/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
            }`}
          >
            <Sparkles className="w-3.5 h-3.5" />
          </button>
          <div className="h-3.5 w-px bg-slate-700 mx-1" />
          <button
            onClick={handleZoomOut}
            title="Zoom Out"
            className="p-1.5 rounded-lg border border-slate-700/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all"
          >
            <ZoomOut className="w-3.5 h-3.5" />
          </button>
          <span className="font-mono text-[11px] text-slate-400 min-w-[40px] text-center">
            {Math.round(scale * 100)}%
          </span>
          <button
            onClick={handleZoomIn}
            title="Zoom In"
            className="p-1.5 rounded-lg border border-slate-700/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all"
          >
            <ZoomIn className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleRotate}
            title="Rotate 90°"
            className="p-1.5 rounded-lg border border-slate-700/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all"
          >
            <RotateCw className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={handleReset}
            title="Reset View"
            className="p-1.5 rounded-lg border border-slate-700/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-all"
          >
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Interactive Image Viewport */}
      <div
        ref={containerRef}
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        onWheel={handleWheel}
        className="flex-1 w-full h-full overflow-hidden flex items-center justify-center cursor-grab active:cursor-grabbing select-none relative bg-gradient-to-b from-dark-950 to-dark-900"
      >
        {imageUrl ? (
          <div
            style={{
              transform: `translate(${position.x}px, ${position.y}px) scale(${scale}) rotate(${rotation}deg)`,
              transition: isDragging ? "none" : "transform 0.15s ease-out",
            }}
            className="origin-center"
          >
            <img
              src={imageUrl}
              alt="Document Scan"
              draggable={false}
              className={`max-w-[85vw] max-h-[85vh] object-contain rounded-lg shadow-2xl border border-slate-800/80 transition-all ${
                highContrast ? "contrast-150 brightness-95 grayscale" : ""
              }`}
            />
          </div>
        ) : (
          <div className="text-center p-8 text-slate-500">
            <Maximize2 className="w-10 h-10 mx-auto mb-2 opacity-40 animate-pulse" />
            <p className="text-xs font-medium">Select or upload a document to inspect</p>
          </div>
        )}
      </div>

      {/* Footer Info Pill */}
      <div className="absolute bottom-3 left-3 z-10 text-[11px] text-slate-400 bg-dark-950/80 border border-slate-800 px-3 py-1 rounded-full backdrop-blur">
        Drag to Pan • Scroll to Zoom{pageCount > 1 ? " • ← / → Page Flip" : ""}
      </div>
    </div>
  );
};
