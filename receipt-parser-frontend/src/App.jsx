import React, { useState } from "react";
import UploadForm from "./components/UploadForm";
import ReceiptTable from "./components/ReceiptTable";
import HealthCheck from "./components/HealthCheck";

const EMPTY = { store: "", date: "", total: 0, items: [] };

const App = () => {
  // The working copy the table edits.
  const [parsedData, setParsedData] = useState(EMPTY);
  // The untouched parser output, so edits can be discarded.
  const [lastParsed, setLastParsed] = useState(null);

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
            canRestore={lastParsed !== null && parsedData !== lastParsed}
          />
        </div>
      </div>
    </div>
  );
};

export default App;
