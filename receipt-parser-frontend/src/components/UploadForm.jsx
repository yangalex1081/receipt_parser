import { useState } from "react";
import axios from "axios";

const UploadForm = () => {
  const [file, setFile] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);

  const API_URL = import.meta.env.VITE_API_URL;
  const API_KEY = import.meta.env.VITE_API_KEY;

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file) return alert("Please upload a receipt image first!");
    setLoading(true);
    setResult(null);

    try {
      const formData = new FormData();
      formData.append("file", file);

      const response = await axios.post(`${API_URL}/parse`, formData, {
        headers: {
          "Content-Type": "multipart/form-data",
          "Authorization": `Bearer ${API_KEY}`,
        },
      });

      setResult(response.data);
    } catch (error) {
      console.error(error);
      alert("Error parsing receipt. Check console for details.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ padding: 20 }}>
      <h2>🧾 Receipt Parser</h2>
      <form onSubmit={handleSubmit}>
        <input
          type="file"
          accept="image/*"
          onChange={(e) => setFile(e.target.files[0])}
        />
        <button type="submit" disabled={loading}>
          {loading ? "Processing..." : "Upload"}
        </button>
      </form>

      {result && (
        <div style={{ marginTop: 20 }}>
          <h3>Parsed JSON:</h3>
          <pre
            style={{
              textAlign: "left",
              background: "#f4f4f4",
              padding: 10,
              borderRadius: 6,
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
