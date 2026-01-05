import React, { useState, useCallback, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ZoomIn, ZoomOut, ChevronLeft, ChevronRight, X, FileText } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import ALEXISConversationPanel from "@/components/ALEXISConversationPanel";
import { useDiagramTeaching } from "@/context/DiagramTeachingContext";
import { DiagramOverlayCanvas } from "@/components/DiagramOverlayCanvas";

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

/**
 * Wiring Diagram Upload Page
 * ChatGPT-style layout: Single scrollable conversation stream + fixed input bar
 * PDF viewer appears INLINE in the conversation stream when uploaded
 */
const WiringUploadPage = () => {
  // PDF state
  const [pdfFile, setPdfFile] = useState(null);
  const [pdfFileName, setPdfFileName] = useState("");
  const [numPages, setNumPages] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [scale, setScale] = useState(1.0);
  const [pdfError, setPdfError] = useState(null);
  const [overlayCommands, setOverlayCommands] = useState([]);
  
  const pdfContainerRef = useRef(null);
  const addSystemMessageRef = useRef(null);

  const { 
    diagramTeachingEnabled, 
    enableDiagramTeaching, 
    disableDiagramTeaching,
    diagramMetadata,
    updateDiagramPage,
    updateDiagramPages 
  } = useDiagramTeaching();

  // Clean up teaching mode on unmount
  useEffect(() => {
    return () => {
      disableDiagramTeaching();
    };
  }, [disableDiagramTeaching]);

  // Handle file selection
  const handleFileChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    console.log("File selected:", file.name, file.type, file.size);
    
    setPdfError(null);
    setPdfFile(file);
    setPdfFileName(file.name);
    setNumPages(null);
    setCurrentPage(1);
    setScale(1.0);
    setOverlayCommands([]);

    // Activate diagram teaching WITH METADATA for ALEXIS context binding
    enableDiagramTeaching({
      filename: file.name,
      fileSize: file.size,
      totalPages: null, // Will be updated on load success
      currentPage: 1,
    });

    if (addSystemMessageRef.current) {
      addSystemMessageRef.current(`Wiring diagram loaded: ${file.name}`, [
        { name: file.name, type: "pdf" },
      ]);
    }
  };

  const onDocumentLoadSuccess = ({ numPages: pages }) => {
    console.log("PDF loaded successfully, pages:", pages);
    setNumPages(pages);
    setPdfError(null);
    // Update diagram context with total pages
    updateDiagramPages(pages);
  };

  const onDocumentLoadError = (error) => {
    console.error("PDF load error:", error);
    setPdfError("Failed to load PDF. Please try another file.");
  };

  const handleZoomIn = () => setScale((s) => Math.min(s + 0.15, 3.0));
  const handleZoomOut = () => setScale((s) => Math.max(s - 0.15, 0.5));
  const handlePrevPage = () => {
    const newPage = Math.max(currentPage - 1, 1);
    setCurrentPage(newPage);
    updateDiagramPage(newPage);
  };
  const handleNextPage = () => {
    const newPage = Math.min(currentPage + 1, numPages || 1);
    setCurrentPage(newPage);
    updateDiagramPage(newPage);
  };

  const handleDiagramTap = (event) => {
    if (!pdfContainerRef.current || !numPages) return;

    const rect = pdfContainerRef.current.getBoundingClientRect();
    const localX = event.clientX - rect.left;
    const localY = event.clientY - rect.top;

    const pdfX = localX / scale;
    const pdfY = localY / scale;

    const tapContext = {
      page: currentPage,
      x: pdfX,
      y: pdfY,
      zoom: scale,
      viewport: {
        width: rect.width / scale,
        height: rect.height / scale,
        offsetX: (pdfContainerRef.current.scrollLeft || 0) / scale,
        offsetY: (pdfContainerRef.current.scrollTop || 0) / scale,
      },
    };

    // Clear existing overlays
    setOverlayCommands([]);
    window.__ALEXIS_DIAGRAM_TAP_CONTEXT__ = tapContext;
  };

  const handleAttachmentCallback = useCallback((addFn) => {
    addSystemMessageRef.current = addFn;
  }, []);

  const clearPdf = () => {
    setPdfFile(null);
    setPdfFileName("");
    setNumPages(null);
    setCurrentPage(1);
    setOverlayCommands([]);
    disableDiagramTeaching();
  };

  // Inline content: PDF viewer that appears IN the conversation stream
  const inlineContent = pdfFile ? (
    <div className="bg-slate-900/80">
      {/* PDF Header with controls */}
      <div className="flex items-center justify-between px-4 py-2 border-b border-slate-700/50 bg-slate-800/50">
        <div className="flex items-center gap-3">
          <FileText className="h-4 w-4 text-slate-400" />
          <span className="text-sm text-slate-200 font-medium truncate max-w-[200px]">
            {pdfFileName}
          </span>
          {diagramTeachingEnabled && (
            <span className="px-2 py-0.5 rounded-full text-[9px] font-semibold uppercase tracking-wider bg-emerald-500/15 text-emerald-400 border border-emerald-500/30">
              Teaching Mode
            </span>
          )}
        </div>
        
        <div className="flex items-center gap-2">
          {/* Page navigation */}
          {numPages && (
            <>
              <Button
                variant="ghost"
                size="sm"
                onClick={handlePrevPage}
                disabled={currentPage <= 1}
                className="h-7 w-7 p-0 text-slate-400 hover:text-slate-200 disabled:opacity-30"
              >
                <ChevronLeft className="h-4 w-4" />
              </Button>
              <span className="text-xs text-slate-400 min-w-[60px] text-center">
                {currentPage} / {numPages}
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleNextPage}
                disabled={currentPage >= numPages}
                className="h-7 w-7 p-0 text-slate-400 hover:text-slate-200 disabled:opacity-30"
              >
                <ChevronRight className="h-4 w-4" />
              </Button>
              
              <div className="w-px h-5 bg-slate-700 mx-1" />
            </>
          )}
          
          {/* Zoom controls */}
          <Button
            variant="ghost"
            size="sm"
            onClick={handleZoomOut}
            className="h-7 w-7 p-0 text-slate-400 hover:text-slate-200"
          >
            <ZoomOut className="h-4 w-4" />
          </Button>
          <span className="text-xs text-slate-400 min-w-[40px] text-center">
            {Math.round(scale * 100)}%
          </span>
          <Button
            variant="ghost"
            size="sm"
            onClick={handleZoomIn}
            className="h-7 w-7 p-0 text-slate-400 hover:text-slate-200"
          >
            <ZoomIn className="h-4 w-4" />
          </Button>

          <div className="w-px h-5 bg-slate-700 mx-1" />
          
          {/* Close button */}
          <Button
            variant="ghost"
            size="sm"
            onClick={clearPdf}
            className="h-7 w-7 p-0 text-slate-400 hover:text-red-400"
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>

      {/* PDF Canvas */}
      <div 
        ref={pdfContainerRef}
        className="relative overflow-auto max-h-[400px] flex items-center justify-center p-4 bg-slate-950/50"
        onClick={handleDiagramTap}
      >
        {pdfError ? (
          <div className="text-red-400 text-sm py-8">{pdfError}</div>
        ) : (
          <>
            <Document
              file={pdfFile}
              onLoadSuccess={onDocumentLoadSuccess}
              onLoadError={onDocumentLoadError}
              loading={
                <div className="flex items-center gap-2 text-slate-400 py-8">
                  <span className="animate-spin">⏳</span>
                  <span className="text-sm">Loading diagram...</span>
                </div>
              }
            >
              <Page
                pageNumber={currentPage}
                scale={scale}
                renderTextLayer={false}
                renderAnnotationLayer={false}
              />
            </Document>

            {/* Overlay canvas for teaching mode */}
            <DiagramOverlayCanvas
              page={currentPage}
              zoom={scale}
              viewportOrigin={{ x: 0, y: 0 }}
              overlayCommands={overlayCommands}
            />
          </>
        )}
      </div>
      
      {/* Hint text */}
      <p className="text-[10px] text-slate-500 text-center py-2 border-t border-slate-800/50">
        Tap any symbol on the diagram to ask ALEXIS about it
      </p>
    </div>
  ) : null;

  return (
    <div className="h-full">
      <ALEXISConversationPanel
        context="WIRING_DIAGRAM_INTERPRETATION"
        onAttachment={handleAttachmentCallback}
        onOverlayCommands={setOverlayCommands}
        onUploadClick={() => document.getElementById("wiring-pdf-input")?.click()}
        inlineContent={inlineContent}
      />

      {/* Hidden file input */}
      <input
        id="wiring-pdf-input"
        type="file"
        accept=".pdf"
        className="hidden"
        onChange={handleFileChange}
      />
    </div>
  );
};

export default WiringUploadPage;
