import React, { useState, useEffect, useMemo } from "react";

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
    const updated = [...items, { name: "", qty: 1, price: 0, buyer: "" }];
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
    const dataToFill = Array.isArray(parsedData)
      ? parsedData
      : Array.isArray(parsedData.items)
      ? parsedData.items
      : [];

    const enriched = dataToFill.map((i) => ({
      ...i,
      buyer: i.buyer || "",
    }));

    setItems(enriched);
    if (onChange) onChange({ ...parsedData, items: enriched });
  };

  // --- Totals --------------------------------------------------------------

  const totalAmount = useMemo(
    () =>
      items.reduce((sum, i) => sum + (parseFloat(i.price || 0) * (i.qty || 1)), 0),
    [items]
  );

  const totalsByBuyer = useMemo(() => {
    const map = {};
    for (const i of items) {
      const buyer = i.buyer?.trim() || "Unassigned";
      const subtotal = parseFloat(i.price || 0) * (i.qty || 1);
      map[buyer] = (map[buyer] || 0) + subtotal;
    }
    return map;
  }, [items]);

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
            <th>Buyer</th>
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
                <td>
                  <input
                    type="text"
                    value={item.buyer || ""}
                    onChange={(e) => handleEdit(i, "buyer", e.target.value)}
                    placeholder="e.g. Alex"
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
              <td colSpan="4" style={{ textAlign: "center", color: "#888" }}>
                No items yet
              </td>
            </tr>
          )}
        </tbody>
        {items.length > 0 && (
          <tfoot style={{ backgroundColor: "#fafafa" }}>
            <tr>
              <td colSpan="4" style={{ borderTop: "1px solid #ccc", padding: "8px" }}>
                <strong>Total: ${totalAmount.toFixed(2)}</strong>
              </td>
            </tr>
            {Object.entries(totalsByBuyer).map(([buyer, total]) => (
              <tr key={buyer}>
                <td colSpan="4" style={{ paddingLeft: "16px", color: "#444" }}>
                  {buyer}: ${total.toFixed(2)}
                </td>
              </tr>
            ))}
          </tfoot>
        )}
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
