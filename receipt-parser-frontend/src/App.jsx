import React, { useEffect, useState } from "react";
import axios from "axios";
import UploadForm from "./components/UploadForm";
import ReceiptTable from "./components/ReceiptTable";

const EMPTY = { store: "", date: "", total: 0, items: [] };

const App = () => {
  // The working copy the table edits.
  const [parsedData, setParsedData] = useState(EMPTY);
  // The untouched parser output, so edits can be discarded.
  const [lastParsed, setLastParsed] = useState(null);

  // Start the GPU container as soon as the page opens, so the model loads
  // while the user is choosing a photo instead of after they upload it.
  // Best-effort: if it fails, the upload simply pays the cold start itself.
  useEffect(() => {
    axios.post("/api/warm").catch(() => {});
  }, []);

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
          <UploadForm onParsed={handleParsed} />
        </div>

        <div className="pane pane--table">
          <ReceiptTable
            parsedData={parsedData}
            onChange={setParsedData}
            onRestore={handleRestore}
            canRestore={lastParsed !== null && parsedData !== lastParsed}
          />
        </div>
      </div>
    </div>
  );
};

export default App;
