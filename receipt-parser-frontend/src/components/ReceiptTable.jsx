import React, { useState, useEffect } from "react";

const ReceiptTable = ({ parsedData = {}, onChange }) => {
  const [items, setItems] = useState([]);

  // 🧠 Watch for parsedData changes and handle both possible shapes
  useEffect(() => {
    if (Array.isArray(parsedData)) {
      setItems(parsedData);
    } else if (parsedData && Array.isArray(parsedData.items)) {
      setItems(parsedData.items);
    } else {
      setItems([]);
    }
  }, [parsedData]);

  // --- Editing handlers ----------------------------------------------------

  const handleEdit = (index, field, value) => {
    const updated = [...items];
    updated[index] = { ...updated[index], [field]: value };
    setItems(updated);
    if (onChange) onChange({ ...parsedData, items: updated });
  };

  const handleAddRow = () => {
    const updated = [...items, { name: "", qty: 1, price: 0 }];
    setItems(updated);
    if (onChange) onChange({ ...parsedData, items: updated });
  };

  const handleReset = () => {
    setItems([]);
    if (onChange) onChange({ ...parsedData, items: [] });
  };

  const handleFill = () => {
    if (!parsedData) {
      alert("No parsed data available to fill.");
      return;
    }
    console.log("Filling data with: ", parsedData)
    // Handle both array and object data structures
    const dataToFill = Array.isArray(parsedData)
      ? parsedData
      : Array.isArray(parsedData.items)
      ? parsedData.items
      : [];

    setItems(dataToFill);
    if (onChange) onChange({ ...parsedData, items: dataToFill });
  };

  // --- Rendering -----------------------------------------------------------

  return (
    <div style={{ color: "#222" }}>
      <h2 style={{ marginBottom: "10px" }}>Receipt Items</h2>

      {/* Controls */}
      <div style={{ marginBottom: "10px" }}>
        <button
          onClick={handleFill}
          style={{
            marginRight: "8px",
            padding: "8px 12px",
            backgroundColor: "#0070f3",
            color: "white",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
          }}
        >
          🔄 Fill with Parsed Data
        </button>

        <button
          onClick={handleReset}
          style={{
            padding: "8px 12px",
            backgroundColor: "#d9534f",
            color: "white",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
          }}
        >
          ♻️ Reset
        </button>
      </div>

      {/* Table */}
      <table
        style={{
          borderCollapse: "collapse",
          width: "100%",
          backgroundColor: "transparent",
          border: "1px solid #ccc",
          borderRadius: "6px",
          overflow: "hidden",
        }}
      >
        <thead style={{ backgroundColor: "#f0f0f0" }}>
          <tr>
            <th>Name</th>
            <th>Qty</th>
            <th>Price ($)</th>
          </tr>
        </thead>
        <tbody>
          {Array.isArray(items) && items.length > 0 ? (
            items.map((item, i) => (
              <tr key={i}>
                <td>
                  <input
                    type="text"
                    value={item.name || ""}
                    onChange={(e) => handleEdit(i, "name", e.target.value)}
                    style={{
                      width: "100%",
                      background: "transparent",
                      border: "none",
                      borderBottom: "1px solid #ddd",
                      color: "#333",
                    }}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min="1"
                    value={item.qty || 1}
                    onChange={(e) =>
                      handleEdit(i, "qty", parseInt(e.target.value) || 1)
                    }
                    style={{
                      width: "100%",
                      background: "transparent",
                      border: "none",
                      borderBottom: "1px solid #ddd",
                      color: "#333",
                    }}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={item.price || 0}
                    onChange={(e) =>
                      handleEdit(i, "price", parseFloat(e.target.value) || 0)
                    }
                    style={{
                      width: "100%",
                      background: "transparent",
                      border: "none",
                      borderBottom: "1px solid #ddd",
                      color: "#333",
                    }}
                  />
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan="3" style={{ textAlign: "center", color: "#888" }}>
                No items yet
              </td>
            </tr>
          )}
        </tbody>
      </table>

      {/* Add row */}
      <button
        onClick={handleAddRow}
        style={{
          marginTop: "12px",
          padding: "8px 12px",
          backgroundColor: "#28a745",
          color: "white",
          border: "none",
          borderRadius: "4px",
          cursor: "pointer",
        }}
      >
        ➕ Add Item
      </button>
    </div>
  );
};

export default ReceiptTable;
