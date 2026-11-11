import { useState, useEffect } from "react";
import { Header } from "./components/Header";
import { Workspace } from "./pages/Workspace";
import { Leaderboard } from "./pages/Leaderboard";
import { DocumentExtractionResponse, DocumentListItem } from "./types/document";
import {
  checkRuntimesHealth,
  RuntimeProbeReport,
  getDocument,
  getDocumentImageUrl,
  listDocuments,
} from "./services/api";

export function App() {
  const [activeTab, setActiveTab] = useState<"workspace" | "leaderboard">("workspace");
  const [currentDoc, setCurrentDoc] = useState<DocumentExtractionResponse | null>(null);
  const [imageUrl, setImageUrl] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(false);
  const [runtimesReport, setRuntimesReport] = useState<RuntimeProbeReport | null>(null);
  const [documents, setDocuments] = useState<DocumentListItem[]>([]);

  // Health and document list initial load
  const refreshDocuments = async () => {
    try {
      const docs = await listDocuments();
      setDocuments(docs);
    } catch {
      // Ignored if backend empty
    }
  };

  const refreshHealth = async () => {
    try {
      const report = await checkRuntimesHealth();
      setRuntimesReport(report);
    } catch {
      setRuntimesReport(null);
    }
  };

  useEffect(() => {
    refreshHealth();
    refreshDocuments();
    const interval = setInterval(refreshHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleSelectDocument = async (id: string) => {
    setIsLoading(true);
    try {
      const doc = await getDocument(id);
      setCurrentDoc(doc);
      setImageUrl(getDocumentImageUrl(id));
      setActiveTab("workspace");
    } catch (e: any) {
      console.error("Failed to load document:", e);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-dark-950 text-slate-100">
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        runtimesReport={runtimesReport}
        onRefreshHealth={refreshHealth}
        documentStatus={currentDoc?.status}
        overallConfidence={currentDoc?.overall_confidence}
      />

      <main className="flex-1 flex flex-col">
        {activeTab === "workspace" ? (
          <Workspace
            currentDoc={currentDoc}
            setCurrentDoc={setCurrentDoc}
            imageUrl={imageUrl}
            setImageUrl={setImageUrl}
            isLoading={isLoading}
            setIsLoading={setIsLoading}
            onRefreshList={refreshDocuments}
          />
        ) : (
          <Leaderboard documents={documents} onSelectDocument={handleSelectDocument} />
        )}
      </main>
    </div>
  );
}

export default App;
