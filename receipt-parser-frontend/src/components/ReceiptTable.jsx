import React, { useMemo } from "react";

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

  const handleClear = () => emit([]);

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
    <div>
      <h2>Receipt Items</h2>

      <div className="controls">
        {canRestore && (
          <button
            type="button"
            onClick={onRestore}
            className="btn btn--primary"
            title="Discard edits and restore the original parsed items"
          >
            🔄 Restore Parsed Items
          </button>
        )}

        <button type="button" onClick={handleClear} className="btn btn--danger">
          ♻️ Clear
        </button>
      </div>

      <div className="table-scroll">
        <table className="receipt-table">
          <thead>
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
                      className="cell-input"
                      value={item.name || ""}
                      onChange={(e) => handleEdit(i, "name", e.target.value)}
                      aria-label={`Item ${i + 1} name`}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      className="cell-input"
                      min="1"
                      value={item.qty ?? 1}
                      onChange={(e) => handleEdit(i, "qty", parseInt(e.target.value) || 1)}
                      aria-label={`Item ${i + 1} quantity`}
                    />
                  </td>
                  <td>
                    <input
                      type="number"
                      className="cell-input"
                      min="0"
                      step="0.01"
                      value={item.price ?? 0}
                      onChange={(e) =>
                        handleEdit(i, "price", parseFloat(e.target.value) || 0)
                      }
                      aria-label={`Item ${i + 1} amount`}
                    />
                  </td>
                  <td>
                    <input
                      type="text"
                      className="cell-input"
                      value={item.buyer || ""}
                      onChange={(e) => handleEdit(i, "buyer", e.target.value)}
                      placeholder="e.g. Alex"
                      aria-label={`Item ${i + 1} buyer`}
                    />
                  </td>
                  <td style={{ width: "1%" }}>
                    <button
                      type="button"
                      onClick={() => handleRemoveRow(i)}
                      className="btn btn--icon"
                      aria-label={`Remove ${item.name || `item ${i + 1}`}`}
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))
            ) : (
              <tr>
                <td colSpan="5" className="table-empty">
                  No items yet
                </td>
              </tr>
            )}
          </tbody>
          {items.length > 0 && (
            <tfoot>
              <tr>
                <td colSpan="5" className="total-row">
                  <strong>Total: ${totalAmount.toFixed(2)}</strong>
                  {totalsDisagree && (
                    <span className="total-mismatch">
                      (receipt said ${parsedTotal.toFixed(2)})
                    </span>
                  )}
                </td>
              </tr>
              {Object.entries(totalsByBuyer).map(([buyer, total]) => (
                <tr key={buyer}>
                  <td colSpan="5" className="buyer-row">
                    {buyer}: ${total.toFixed(2)}
                  </td>
                </tr>
              ))}
            </tfoot>
          )}
        </table>
      </div>

      <button
        type="button"
        onClick={handleAddRow}
        className="btn btn--success"
        style={{ marginTop: "12px" }}
      >
        ➕ Add Item
      </button>
    </div>
  );
};

export default ReceiptTable;
