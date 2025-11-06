import React, { useState } from "react";
import axios from "axios";

const UploadForm = ({onParsed}) => {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    setFile(selectedFile);

    // Create preview URL
    if (selectedFile) {
      const previewUrl = URL.createObjectURL(selectedFile);
      setPreview(previewUrl);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) return alert("Please select a receipt image first.");

    const formData = new FormData();
    formData.append("file", file);

    setLoading(true);
    setResult(null);

    try {
      const response = await axios.post(
        import.meta.env.VITE_API_URL + "/parse",
        formData,
        {
          headers: {
            "Authorization": `Bearer ${import.meta.env.VITE_API_KEY}`,
            "Content-Type": "multipart/form-data",
          },
        }
      );

      setResult(response.data);
      if (onParsed){
        console.log("Seding parsed data to parent:", response.data)
        onParsed(response.data)
      } 
    } catch (error) {
      console.error("Error uploading:", error);
      alert("Failed to process receipt. Check console for details.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: "500px", margin: "auto", textAlign: "center" }}>
      <h2>Receipt Parser</h2>

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

            <button onClick={() => { setFile(null); setPreview(null); setResult(null); }}>
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
          {loading ? "Processing..." : "Upload & Parse"}
        </button>
      </form>

      {result && (
        <div style={{ marginTop: "30px", textAlign: "left" }}>
          <h3>Parsed Output</h3>
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

export default UploadForm;
