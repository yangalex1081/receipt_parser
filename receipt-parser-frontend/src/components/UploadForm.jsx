import React, { useState, useEffect, useRef } from "react";
import axios from "axios";

// Netlify proxies /api/* to Modal and signs each request (see netlify.toml).
// Same-origin, so the browser sends no credentials of its own.
const API_BASE = "/api";

// Netlify functions/redirects cap request bodies at 6MB, ~4.5MB once binary is
// base64-encoded. Phone photos routinely exceed that, so downscale first.
const MAX_DIMENSION = 1600;
const JPEG_QUALITY = 0.85;

const POLL_START_MS = 1500;
const POLL_MAX_MS = 3000;
const POLL_TIMEOUT_MS = 150000; // cold start measured at ~66s; leave headroom

/** Downscale to at most MAX_DIMENSION on the long edge and re-encode as JPEG. */
const downscaleImage = (file) =>
  new Promise((resolve, reject) => {
    const img = new Image();
    const url = URL.createObjectURL(file);

    img.onload = () => {
      URL.revokeObjectURL(url);

      const scale = Math.min(1, MAX_DIMENSION / Math.max(img.width, img.height));
      if (scale === 1 && file.size < 2 * 1024 * 1024) {
        resolve(file); // already small enough, don't re-encode
        return;
      }

      const canvas = document.createElement("canvas");
      canvas.width = Math.round(img.width * scale);
      canvas.height = Math.round(img.height * scale);
      canvas.getContext("2d").drawImage(img, 0, 0, canvas.width, canvas.height);

      canvas.toBlob(
        (blob) => {
          if (!blob) {
            reject(new Error("Could not process image"));
            return;
          }
          resolve(new File([blob], "receipt.jpg", { type: "image/jpeg" }));
        },
        "image/jpeg",
        JPEG_QUALITY
      );
    };

    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error("Could not read image"));
    };

    img.src = url;
  });

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const UploadForm = ({ onParsed }) => {
  const [file, setFile] = useState(null);
  const [preview, setPreview] = useState(null);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState("");

  // Lets an in-flight poll loop know it should stop (reset, or unmount).
  const cancelledRef = useRef(false);
  useEffect(() => () => { cancelledRef.current = true; }, []);

  // Revoke the previous object URL whenever it is replaced or unmounted.
  useEffect(() => {
    if (!preview) return undefined;
    return () => URL.revokeObjectURL(preview);
  }, [preview]);

  const handleFileChange = (e) => {
    const selectedFile = e.target.files[0];
    if (!selectedFile) return;

    setFile(selectedFile);
    setPreview(URL.createObjectURL(selectedFile));
    setResult(null);
    setError("");
    setStatus("");
  };

  const handleReset = () => {
    cancelledRef.current = true;
    setFile(null);
    setPreview(null);
    setResult(null);
    setError("");
    setStatus("");
    setLoading(false);
  };

  /** Poll /api/result/:id until the job finishes, fails, or we give up. */
  const pollForResult = async (callId) => {
    const startedAt = Date.now();
    let delay = POLL_START_MS;

    while (!cancelledRef.current) {
      if (Date.now() - startedAt > POLL_TIMEOUT_MS) {
        throw new Error("Timed out waiting for the parser. Please try again.");
      }

      await sleep(delay);
      delay = Math.min(delay * 1.3, POLL_MAX_MS);

      const elapsed = Math.round((Date.now() - startedAt) / 1000);
      setStatus(`Parsing… ${elapsed}s (first run of the day can take ~60s)`);

      let res;
      try {
        res = await axios.get(`${API_BASE}/result/${callId}`);
      } catch (err) {
        const code = err?.response?.status;
        if (code === 410) throw new Error("That result expired. Please upload again.");
        if (code === 429) throw new Error("Too many requests — wait a minute and retry.");
        if (code === 500) throw new Error("The parser failed on this image.");
        throw err;
      }

      if (res.data?.status === "done") return res.data.result;
    }

    return null; // cancelled
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!file || loading) return;

    cancelledRef.current = false;
    setLoading(true);
    setResult(null);
    setError("");
    setStatus("Preparing image…");

    try {
      const upload = await downscaleImage(file);

      const formData = new FormData();
      formData.append("file", upload);

      setStatus("Uploading…");
      const { data } = await axios.post(`${API_BASE}/parse`, formData);

      if (!data?.call_id) throw new Error("Server did not return a job id.");

      const parsed = await pollForResult(data.call_id);
      if (cancelledRef.current || parsed == null) return;

      setResult(parsed);
      setStatus("");
      if (onParsed) onParsed(parsed);
    } catch (err) {
      const code = err?.response?.status;
      if (code === 429) {
        setError("Too many uploads — please wait a minute and try again.");
      } else if (code === 413) {
        setError("That image is too large even after compression.");
      } else if (code === 400) {
        setError("That file was not a readable image.");
      } else {
        setError(err?.message || "Failed to process receipt.");
      }
      setStatus("");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="upload">
      <h2>Upload a receipt</h2>

      <form onSubmit={handleSubmit}>
        <input
          type="file"
          accept="image/*"
          onChange={handleFileChange}
          disabled={loading}
        />

        {preview && (
          <div className="preview">
            <img src={preview} alt="Receipt preview" />

            <button type="button" onClick={handleReset} className="btn">
              Reset
            </button>
          </div>
        )}

        <button
          type="submit"
          disabled={loading || !file}
          className="btn btn--primary"
          style={{ marginTop: "20px" }}
        >
          {loading ? "Processing…" : "Upload & Parse"}
        </button>
      </form>

      {status && (
        <p className="status-line" aria-live="polite">
          {status}
        </p>
      )}

      {error && (
        <p className="error-line" role="alert">
          {error}
        </p>
      )}

      {result && (
        <div className="output">
          <h3>Parsed output</h3>
          <pre>{JSON.stringify(result, null, 2)}</pre>
        </div>
      )}
    </div>
  );
};

export default UploadForm;
