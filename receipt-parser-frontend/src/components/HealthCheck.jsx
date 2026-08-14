import React, { useState } from "react";
import axios from "axios";

const HealthCheck = () => {
  const [response, setResponse] = useState(null);
  const [loading, setLoading] = useState(false);

  // Same-origin: Netlify proxies /api/* to Modal and signs the request.
  const handleHealthCheck = async () => {
    setLoading(true);
    setResponse(null);

    try {
      const url = "/api/health";
      console.log("[HealthCheck] GET", url);

      const res = await axios.get(url);
      setResponse(JSON.stringify(res.data, null, 2));
    } catch (err) {
      console.error("Health check failed:", err);
      // Helpful debug dump:
      try {
        const dump = {
          message: err?.message,
          url: err?.config?.url,
          baseURL: err?.config?.baseURL,
          status: err?.response?.status,
          data: err?.response?.data,
        };
        setResponse(JSON.stringify({ error: "request_failed", ...dump }, null, 2));
      } catch {
        setResponse(JSON.stringify({ error: "request_failed" }, null, 2));
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ marginTop: 20 }}>
      <button onClick={handleHealthCheck} disabled={loading}>
        {loading ? "Checking..." : "Check API Health"}
      </button>
      {response && (
        <pre style={{ marginTop: 12, background: "#008000", padding: 12, borderRadius: 6 }}>
          {response}
        </pre>
      )}
    </div>
  );
};

export default HealthCheck;
