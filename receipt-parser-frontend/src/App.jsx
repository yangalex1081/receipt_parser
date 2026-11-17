import React, { useEffect, useState } from "react";
import UploadForm from "./components/UploadForm";
import ReceiptTable from "./components/ReceiptTable";
import HealthCheck from "./components/HealthCheck";

const EMPTY = { store: "", date: "", total: 0, items: [] };

// The table is saved in the browser so a refresh, or the phone dropping the tab
// while you check a price, does not throw away twenty assigned rows. Storage
// can be unavailable (private windows, blocked site data), so every access is
// guarded and the app works without it.
const STORAGE_KEY = "receipt-parser:v1";

const loadSaved = () => {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (saved && Array.isArray(saved.parsedData?.items)) return saved;
  } catch {
    // unreadable or unavailable: start empty
  }
  return null;
};

const App = () => {
  const [saved] = useState(loadSaved);
  // The working copy the table edits.
  const [parsedData, setParsedData] = useState(saved?.parsedData ?? EMPTY);
  // The untouched parser output, so edits can be discarded.
  const [lastParsed, setLastParsed] = useState(saved?.lastParsed ?? null);

  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify({ parsedData, lastParsed }));
    } catch {
      // storage full or unavailable: nothing to do
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
      <header className="app-header">
        <HealthCheck />
      </header>

      <div className="app-body">
        <div className="pane">
          <h1>🧾 Receipt Parser</h1>
          <UploadForm onParsed={handleParsed} />
        </div>

        <div className="pane pane--table">
          <ReceiptTable
            parsedData={parsedData}
            onChange={setParsedData}
            onRestore={handleRestore}
            // Compared by value: after a reload the two are separate objects
            // even when nothing has been edited.
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
