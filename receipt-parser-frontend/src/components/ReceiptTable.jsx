import React, { useMemo } from "react";

const inputStyle = {
  width: "100%",
  background: "transparent",
  border: "none",
  borderBottom: "1px solid #ddd",
  color: "#333",
};

const buttonStyle = {
  padding: "8px 12px",
  color: "white",
  border: "none",
  borderRadius: "4px",
  cursor: "pointer",
};

/**
 * Fully controlled: rows are rendered straight from `parsedData` and every
 * change goes up through `onChange`. There is deliberately no local copy of
 * the items — mirroring props into state and re-syncing in an effect meant
 * each keystroke round-tripped through the parent, and would fight any
 * normalization the parent applied.
 */
const ReceiptTable = ({ parsedData = {}, onChange, onRestore, canRestore }) => {
  // The parser has returned a bare array in some shapes; tolerate both.
  const items = useMemo(() => {
    if (Array.isArray(parsedData)) return parsedData;
    if (Array.isArray(parsedData?.items)) return parsedData.items;
    return [];
  }, [parsedData]);

  const emit = (nextItems) => {
    if (!onChange) return;
    onChange(
      Array.isArray(parsedData) ? nextItems : { ...parsedData, items: nextItems }
    );
  };

  // --- Editing handlers ----------------------------------------------------

  const handleEdit = (index, field, value) => {
    emit(items.map((item, i) => (i === index ? { ...item, [field]: value } : item)));
  };

  const handleAddRow = () => {
    emit([...items, { name: "", qty: 1, price: 0, buyer: "" }]);
  };

  const handleRemoveRow = (index) => {
    emit(items.filter((_, i) => i !== index));
  };

  const handleReset = () => emit([]);

  // --- Totals --------------------------------------------------------------
  //
  // `price` is the LINE TOTAL for a row, not a unit price — that is the CORD
  // schema the model is fine-tuned on ("MUFFIN, cnt 3, price 9000" is 9000 for
  // all three). So totals sum price directly; multiplying by qty would count
  // quantity twice. `qty` is informational, and unit price is price / qty.

  const lineTotal = (i) => parseFloat(i.price) || 0;

  const totalAmount = useMemo(
    () => items.reduce((sum, i) => sum + lineTotal(i), 0),
    [items]
  );

  const totalsByBuyer = useMemo(() => {
    const map = {};
    for (const i of items) {
      const buyer = i.buyer?.trim() || "Unassigned";
      map[buyer] = (map[buyer] || 0) + lineTotal(i);
    }
    return map;
  }, [items]);

  // What the parser reported, for comparison against the edited rows.
  const parsedTotal = Array.isArray(parsedData) ? null : parsedData?.total;
  const totalsDisagree =
    typeof parsedTotal === "number" &&
    Math.abs(parsedTotal - totalAmount) > 0.005;

  // --- Rendering -----------------------------------------------------------

  return (
    <div style={{ color: "#222" }}>
      <h2 style={{ marginBottom: "10px" }}>Receipt Items</h2>

      {/* Controls */}
      <div style={{ marginBottom: "10px" }}>
        {canRestore && (
          <button
            type="button"
            onClick={onRestore}
            style={{ ...buttonStyle, marginRight: "8px", backgroundColor: "#0070f3" }}
            title="Discard edits and restore the original parsed items"
          >
            🔄 Restore Parsed Items
          </button>
        )}

        <button
          type="button"
          onClick={handleReset}
          style={{ ...buttonStyle, backgroundColor: "#d9534f" }}
        >
          ♻️ Clear
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
            <th title="Total for this line, not the unit price">Amount ($)</th>
            <th>Buyer</th>
            <th aria-label="Remove row" />
          </tr>
        </thead>
        <tbody>
          {items.length > 0 ? (
            items.map((item, i) => (
              <tr key={i}>
                <td>
                  <input
                    type="text"
                    value={item.name || ""}
                    onChange={(e) => handleEdit(i, "name", e.target.value)}
                    style={inputStyle}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min="1"
                    value={item.qty ?? 1}
                    onChange={(e) => handleEdit(i, "qty", parseInt(e.target.value) || 1)}
                    style={inputStyle}
                  />
                </td>
                <td>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={item.price ?? 0}
                    onChange={(e) =>
                      handleEdit(i, "price", parseFloat(e.target.value) || 0)
                    }
                    style={inputStyle}
                  />
                </td>
                <td>
                  <input
                    type="text"
                    value={item.buyer || ""}
                    onChange={(e) => handleEdit(i, "buyer", e.target.value)}
                    placeholder="e.g. Alex"
                    style={inputStyle}
                  />
                </td>
                <td style={{ width: "1%" }}>
                  <button
                    type="button"
                    onClick={() => handleRemoveRow(i)}
                    aria-label={`Remove ${item.name || "row"}`}
                    style={{
                      background: "transparent",
                      border: "none",
                      color: "#999",
                      cursor: "pointer",
                      padding: "0 6px",
                    }}
                  >
                    ✕
                  </button>
                </td>
              </tr>
            ))
          ) : (
            <tr>
              <td colSpan="5" style={{ textAlign: "center", color: "#888" }}>
                No items yet
              </td>
            </tr>
          )}
        </tbody>
        {items.length > 0 && (
          <tfoot style={{ backgroundColor: "#fafafa" }}>
            <tr>
              <td colSpan="5" style={{ borderTop: "1px solid #ccc", padding: "8px" }}>
                <strong>Total: ${totalAmount.toFixed(2)}</strong>
                {totalsDisagree && (
                  <span
                    style={{ marginLeft: "10px", color: "#b8860b", fontWeight: "normal" }}
                  >
                    (receipt said ${parsedTotal.toFixed(2)})
                  </span>
                )}
              </td>
            </tr>
            {Object.entries(totalsByBuyer).map(([buyer, total]) => (
              <tr key={buyer}>
                <td colSpan="5" style={{ paddingLeft: "16px", color: "#444" }}>
                  {buyer}: ${total.toFixed(2)}
                </td>
              </tr>
            ))}
          </tfoot>
        )}
      </table>

      {/* Add row */}
      <button
        type="button"
        onClick={handleAddRow}
        style={{ ...buttonStyle, marginTop: "12px", backgroundColor: "#28a745" }}
      >
        ➕ Add Item
      </button>
    </div>
  );
};

export default ReceiptTable;
