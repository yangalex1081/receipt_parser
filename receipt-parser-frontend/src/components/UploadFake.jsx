import React, { useState } from "react";

const UploadFake = ({ onParsed }) => {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    setFile(selectedFile);

    if (selectedFile) {
      const previewUrl = URL.createObjectURL(selectedFile);
      setPreview(previewUrl);
    }
  };

  // 🧪 Fake upload test — returns mock data instantly
  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) return alert("Please select a receipt image first.");

    setLoading(true);
    setResult(null);

    try {
      // Simulate processing delay
      await new Promise((resolve) => setTimeout(resolve, 800));

      // 🎭 Fake parsed receipt data
      const fakeResponse = {
        store: "Fake Mart",
        date: "2025-11-05",
        total: 42.69,
        items: [
          { name: "Apples", qty: 3, price: 5.99 },
          { name: "Bananas", qty: 2, price: 3.49 },
          { name: "Toothpaste", qty: 1, price: 4.99 },
          { name: "Soda", qty: 6, price: 14.22 },
        ],
      };

      console.log("🧩 Fake parsed data:", fakeResponse);
      setResult(fakeResponse);

      if (onParsed) onParsed(fakeResponse);
    } catch (error) {
      console.error("❌ Simulated upload failed:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: "500px", margin: "auto", textAlign: "center" }}>
      <h2>Receipt Parser (Test Mode)</h2>

      <form onSubmit={handleSubmit}>
        <input type="file" accept="image/*" onChange={handleFileChange} />

        {preview && (
          <div style={{ marginTop: "20px" }}>
            <img
              src={preview}
              alt="Receipt Preview"
              style={{
                maxWidth: "100%",
                borderRadius: "8px",
                boxShadow: "0 0 10px rgba(0,0,0,0.2)",
              }}
            />

            <button
              onClick={() => {
                setFile(null);
                setPreview(null);
                setResult(null);
              }}
            >
              Reset
            </button>
          </div>
        )}

        <button
          type="submit"
          style={{
            marginTop: "20px",
            padding: "10px 20px",
            cursor: "pointer",
            borderRadius: "6px",
            border: "none",
            background: "#007bff",
            color: "white",
            fontWeight: "bold",
          }}
        >
          {loading ? "Processing..." : "Fake Upload & Parse"}
        </button>
      </form>

      {result && (
        <div style={{ marginTop: "30px", textAlign: "left" }}>
          <h3>Parsed Output (Simulated)</h3>
          <pre
            style={{
              background: "#008000",
              padding: "15px",
              borderRadius: "8px",
              overflowX: "auto",
            }}
          >
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
};

export default UploadFake;
