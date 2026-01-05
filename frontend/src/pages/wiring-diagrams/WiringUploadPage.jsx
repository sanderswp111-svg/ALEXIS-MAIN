import React, { useState, useCallback, useRef, useEffect } from "react";
import { Button } from "@/components/ui/button";
import { ZoomIn, ZoomOut, ChevronLeft, ChevronRight, FileText } from "lucide-react";
import { Document, Page, pdfjs } from "react-pdf";
import "react-pdf/dist/Page/AnnotationLayer.css";
import "react-pdf/dist/Page/TextLayer.css";
import ALEXISConversationPanel from "@/components/ALEXISConversationPanel";
import { useDiagramTeaching } from "@/context/DiagramTeachingContext";
import { DiagramOverlayCanvas } from "@/components/DiagramOverlayCanvas";

pdfjs.GlobalWorkerOptions.workerSrc = `//unpkg.com/pdfjs-dist@${pdfjs.version}/build/pdf.worker.min.mjs`;

const WiringUploadPage = () => {
  const [selectedFileUrl, setSelectedFileUrl] = useState(null);
  const [selectedFileName, setSelectedFileName] = useState("");
  const [numPages, setNumPages] = useState(null);
  const [currentPage, setCurrentPage] = useState(1);
  const [scale, setScale] = useState(0.9);
  const [pdfError, setPdfError] = useState(null);
  const [overlayCommands, setOverlayCommands] = useState([]);
  const pdfContainerRef = useRef(null);
  const addSystemMessageRef = useRef(null);

  const { diagramTeachingEnabled, enableDiagramTeaching, disableDiagramTeaching } =
    useDiagramTeaching();

  // Clean up teaching mode on unmount
  useEffect(() => {
    return () => {
      disableDiagramTeaching();
    };
  }, [disableDiagramTeaching]);

  const handleFileChange = (event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setPdfError(null);
    setSelectedFile(file);
    setNumPages(null);
    setCurrentPage(1);
    setScale(0.9);
    setOverlayCommands([]);

    // Activate diagram teaching as soon as a diagram is loaded
    enableDiagramTeaching();

    if (addSystemMessageRef.current) {
      addSystemMessageRef.current(`Wiring diagram loaded: ${file.name}`, [
        { name: file.name, type: "pdf" },
      ]);
    }
  };

  const onDocumentLoadSuccess = ({ numPages: pages }) => {
    setNumPages(pages);
    setPdfError(null);
  };

  const onDocumentLoadError = (error) => {
    console.error("PDF load error:", error);
    setPdfError("Failed to load PDF.");
  };

  const handleZoomIn = () => setScale((s) => Math.min(s + 0.1, 2.5));
  const handleZoomOut = () => setScale((s) => Math.max(s - 0.1, 0.4));
  const handlePrevPage = () => setCurrentPage((p) => Math.max(p - 1, 1));
  const handleNextPage = () => setCurrentPage((p) => Math.min(p + 1, numPages || 1));

  const handleDiagramTap = (event) => {
    if (!pdfContainerRef.current || !numPages) return;

    const rect = pdfContainerRef.current.getBoundingClientRect();
    const clientX = event.clientX;
    const clientY = event.clientY;

    const localX = clientX - rect.left;
    const localY = clientY - rect.top;

    const pdfX = localX / scale;
    const pdfY = localY / scale;

    const scrollLeft = pdfContainerRef.current.scrollLeft || 0;
    const scrollTop = pdfContainerRef.current.scrollTop || 0;

    const tapContext = {
      page: currentPage,
      x: pdfX,
      y: pdfY,
      zoom: scale,
      viewport: {
        width: rect.width / scale,
        height: rect.height / scale,
        offsetX: scrollLeft / scale,
        offsetY: scrollTop / scale,
      },
    };

    // Clear any existing overlays before new tap
    setOverlayCommands([]);
    window.__ALEXIS_DIAGRAM_TAP_CONTEXT__ = tapContext;
  };

  const handleAttachmentCallback = useCallback((addFn) => {
    addSystemMessageRef.current = addFn;
  }, []);

  const documentCanvas = (
    <div className="flex flex-col h-full bg-slate-950">
      {/* Slim header like ChatGPT */}
      <div className="flex items-center justify-between px-6 py-3 border-b border-slate-800 bg-slate-950/95">
        <div className="flex flex-col gap-1">
          <h2 className="text-sm font-semibold text-slate-100 tracking-wide">
            Wiring Diagram Viewer
          </h2>
          <div className="flex items-center gap-2">
            <span className="px-2 py-0.5 rounded-full border border-emerald-500/50 bg-emerald-500/10 text-[10px] font-semibold uppercase tracking-wider text-emerald-200">
              LIVE – DIAGRAM ASSISTANCE
            </span>
            <span className="text-[10px] text-slate-400">
              {selectedFile ? selectedFile.name : "No diagram loaded"}
            </span>
          </div>
        </div>
        <div className="flex flex-col gap-1 items-end">
          <span
            className={`px-2 py-0.5 rounded-full border text-[10px] font-semibold uppercase tracking-wider ${
              diagramTeachingEnabled
                ? "bg-emerald-500/10 border-emerald-400/70 text-emerald-200"
                : "bg-slate-800/80 border-slate-600 text-slate-300"
            }`}
          >
            DIAGRAM TEACHING MODE
          </span>
          {numPages && (
            <div className="flex items-center gap-2 text-[10px] text-slate-400">
              <span>
                Page {currentPage} of {numPages}
              </span>
              <div className="flex items-center gap-0.5 bg-slate-900/80 rounded px-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleZoomOut}
                  className="h-6 w-6 p-0 text-slate-300"
                >
                  <ZoomOut className="h-3 w-3" />
                </Button>
                <span className="w-9 text-center">{Math.round(scale * 100)}%</span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleZoomIn}
                  className="h-6 w-6 p-0 text-slate-300"
                >
                  <ZoomIn className="h-3 w-3" />
                </Button>
              </div>
              <div className="flex items-center gap-0.5 bg-slate-900/80 rounded px-1">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handlePrevPage}
                  disabled={currentPage <= 1}
                  className="h-6 w-6 p-0 text-slate-300 disabled:opacity-30"
                >
                  <ChevronLeft className="h-3 w-3" />
                </Button>
                <span className="w-10 text-center">
                  {currentPage}/{numPages}
                </span>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={handleNextPage}
                  disabled={currentPage >= numPages}
                  className="h-6 w-6 p-0 text-slate-300 disabled:opacity-30"
                >
                  <ChevronRight className="h-3 w-3" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Main PDF canvas */}
      <div className="flex-1 overflow-auto flex items-center justify-center">
        {selectedFile ? (
          <div
            ref={pdfContainerRef}
            className="relative max-w-5xl w-full h-full flex items-center justify-center p-6"
            onClick={handleDiagramTap}
          >
            <Document
              file={selectedFile}
              onLoadSuccess={onDocumentLoadSuccess}
              onLoadError={onDocumentLoadError}
              loading={
                <span className="text-slate-500 text-xs">
                  Loading wiring diagram...
                </span>
              }
            >
              <Page
                pageNumber={currentPage}
                scale={scale}
                renderTextLayer={false}
                renderAnnotationLayer={false}
              />
            </Document>

            <DiagramOverlayCanvas
              page={currentPage}
              zoom={scale}
              viewportOrigin={{ x: 0, y: 0 }}
              overlayCommands={overlayCommands}
            />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center text-slate-500 text-sm gap-2 py-10">
            <FileText className="h-6 w-6 mb-1" />
            <p>No wiring diagram loaded.</p>
            <p className="text-[12px] text-slate-500">
              Use the + button in the input bar to upload a wiring diagram PDF.
            </p>
          </div>
        )}
      </div>
    </div>
  );

  return (
    <div className="h-full flex flex-col">
      <ALEXISConversationPanel
        context="WIRING_DIAGRAM_INTERPRETATION"
        documentCanvas={documentCanvas}
        toolsPanel={null}
        onAttachment={handleAttachmentCallback}
        onOverlayCommands={setOverlayCommands}
        onUploadClick={() =>
          document.getElementById("wiring-pdf-input")?.click()
        }
      />

      {/* Hidden file input for ChatGPT-style + upload */}
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
