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
      <div style={{ flex: 1, padding: "20px" }}>
        <HealthCheck />
      </div>
      <div style={{ display: "flex", height: "100vh" }}>
        {/* Left side — Upload and controls */}
        <div style={{ flex: 1, padding: "20px" }}>
          <h1>🧾 Receipt Parser</h1>
          <UploadForm onParsed={handleParsed} />
        </div>

        {/* Right side — Table always visible */}
        <div
          style={{
            width: "50%",
            borderLeft: "1px solid #ccc",
            padding: "20px",
            overflowY: "auto",
            background: "#f8f8f874",
          }}
        >
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
