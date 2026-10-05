import React, { useEffect, useState } from "react";
import UploadForm from "./components/UploadForm";
import ReceiptTable from "./components/ReceiptTable";
import HealthCheck from "./components/HealthCheck";

const EMPTY = { store: "", date: "", total: 0, items: [] };

// The receipt being split is kept in localStorage so a refresh, or the phone
// dropping the tab while you switch to the group chat, doesn't lose the edits.
// Storage can be unavailable (private mode, blocked site data), so every
// access is guarded and the app works the same without it.
const STORAGE_KEY = "receipt-parser:session";

const loadSession = () => {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved && typeof saved === "object" && saved.parsedData) return saved;
  } catch {
    // fall through to a fresh session
  }
  return { parsedData: EMPTY, lastParsed: null };
};

const App = () => {
  const [session] = useState(loadSession);
  // The working copy the table edits.
  const [parsedData, setParsedData] = useState(session.parsedData);
  // The untouched parser output, so edits can be discarded.
  const [lastParsed, setLastParsed] = useState(session.lastParsed);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ parsedData, lastParsed }));
    } catch {
      // not fatal; the session just won't survive a reload
    }
  }, [parsedData, lastParsed]);

  const handleParsed = (data) => {
    setParsedData(data);
    setLastParsed(data);
  };

  const handleRestore = () => {
    if (lastParsed) setParsedData(lastParsed);
  };

  return (
    <div>
      <div className="app-body">
        <div className="pane">
          <h1>🧾 Receipt Parser</h1>
          <p className="tagline">
            Snap a receipt, tag who had what, and get everyone’s share — tax and
            tip included.
          </p>
          <UploadForm onParsed={handleParsed} />

          <details className="dev-tools">
            <summary>Troubleshooting</summary>
            <HealthCheck />
          </details>
        </div>

        <div className="pane pane--table">
          <ReceiptTable
            parsedData={parsedData}
            onChange={setParsedData}
            onRestore={handleRestore}
            // JSON round-tripping through storage breaks reference equality,
            // so compare by content rather than identity.
            canRestore={
              lastParsed !== null &&
              JSON.stringify(parsedData) !== JSON.stringify(lastParsed)
            }
          />
        </div>
      </div>
    </div>
  );
};

export default App;
