import React, { useState, useEffect } from "react";
import UploadForm from "./components/UploadForm";
import ReceiptTable from "./components/ReceiptTable";
import HealthCheck from "./components/HealthCheck";
import UploadFake from "./components/UploadFake";

const App = () => {
  const [parsedData, setParsedData] = useState({
    store: "",
    date: "",
    total: 0,
    items: [],
  });

  return (
    <div>
      <div style={{ flex: 1, padding: "20px" }}>
        <HealthCheck />
      </div>
      <div style={{ display: "flex", height: "100vh" }}>
        {/* Left side — Upload and controls */}
        <div style={{ flex: 1, padding: "20px" }}>
          <h1>🧾 Receipt Parser</h1>
          <UploadForm onParsed={setParsedData} />
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
          <ReceiptTable parsedData={parsedData} onChange={setParsedData} />
        </div>
      </div>
    </div>
  );
};

export default App;
