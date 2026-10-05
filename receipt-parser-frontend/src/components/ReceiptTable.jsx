import React, { useMemo, useState } from "react";
import {
  computeSplit,
  formatCents,
  parseBuyers,
  summaryText,
  toCents,
} from "../split";

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

  const base = Array.isArray(parsedData) ? { items: parsedData } : parsedData;

  const update = (patch) => {
    if (onChange) onChange({ ...base, ...patch });
  };

  const emit = (nextItems) => update({ items: nextItems });

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

  // Tax, tip, service charge or discount. The parser deliberately keeps these
  // out of the items, so they have to be entered (or pulled from the printed
  // total below) and are then shared in proportion to what each person had.
  const extras = parseFloat(base?.extras) || 0;

  const split = useMemo(
    () => computeSplit(items, toCents(extras)),
    [items, extras]
  );

  // Every name used so far, offered as autocomplete in the Buyer column.
  const knownNames = useMemo(() => {
    const names = new Map();
    for (const i of items) {
      for (const n of parseBuyers(i.buyer)) names.set(n.toLowerCase(), n);
    }
    return [...names.values()];
  }, [items]);

  const [copied, setCopied] = useState(false);
  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(summaryText(split, base?.store));
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  };

  // The total printed on the receipt itself, when the parser could read it.
  // A gap between that and the sum of the rows usually means a line was
  // missed — the most common extraction failure — so it is worth showing.
  const printedTotal = base?.printed_total;
  const hasPrintedTotal = typeof printedTotal === "number" && printedTotal > 0;
  const difference = hasPrintedTotal ? printedTotal - totalAmount - extras : 0;
  const totalsDisagree = hasPrintedTotal && Math.abs(difference) > 0.005;

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
                      placeholder="e.g. Alex, Sam"
                      list="known-buyers"
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
                  <strong>Items: ${totalAmount.toFixed(2)}</strong>
                  {totalsDisagree && (
                    <span
                      className="total-mismatch"
                      title={
                        difference > 0
                          ? "The receipt total is higher than these rows — a line may be missing."
                          : "These rows exceed the receipt total — a line may be duplicated."
                      }
                    >
                      ⚠ receipt says ${printedTotal.toFixed(2)} (
                      {difference > 0 ? "+" : "−"}$
                      {Math.abs(difference).toFixed(2)} unaccounted)
                    </span>
                  )}
                  {totalsDisagree && difference > 0 && (
                    <button
                      type="button"
                      className="btn btn--link"
                      onClick={() =>
                        update({ extras: Math.round((extras + difference) * 100) / 100 })
                      }
                      title="If the gap is tax, tip or a fee rather than a missed item"
                    >
                      Count it as tax/tip
                    </button>
                  )}
                </td>
              </tr>
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

      <datalist id="known-buyers">
        {knownNames.map((n) => (
          <option key={n} value={n} />
        ))}
      </datalist>

      <section className="split" aria-labelledby="split-heading">
        <h2 id="split-heading">Split</h2>

        <label className="extras">
          <span>Tax, tip &amp; fees ($)</span>
          <input
            type="number"
            step="0.01"
            value={base?.extras ?? ""}
            placeholder="0.00"
            onChange={(e) =>
              update({ extras: e.target.value === "" ? "" : parseFloat(e.target.value) })
            }
          />
          <small>Shared in proportion to what each person had. Use a negative number for a discount.</small>
        </label>

        {split.people.length > 0 ? (
          <>
            <table className="split-table">
              <thead>
                <tr>
                  <th>Person</th>
                  <th>Items</th>
                  {split.extras !== 0 && <th>Tax/tip</th>}
                  <th>Owes</th>
                </tr>
              </thead>
              <tbody>
                {split.people.map((p) => (
                  <tr key={p.name}>
                    <td>{p.name}</td>
                    <td>{formatCents(p.subtotal)}</td>
                    {split.extras !== 0 && <td>{formatCents(p.extras)}</td>}
                    <td>
                      <strong>{formatCents(p.total)}</strong>
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr>
                  <td>Total</td>
                  <td>{formatCents(split.subtotal)}</td>
                  {split.extras !== 0 && <td>{formatCents(split.extras)}</td>}
                  <td>
                    <strong>{formatCents(split.total)}</strong>
                  </td>
                </tr>
              </tfoot>
            </table>

            <button type="button" className="btn btn--primary" onClick={handleCopy}>
              {copied ? "✓ Copied" : "📋 Copy summary"}
            </button>
          </>
        ) : (
          <p className="table-empty">
            Add items and put a name in the Buyer column. Use commas to share an
            item, e.g. “Alex, Sam”.
          </p>
        )}
      </section>
    </div>
  );
};

export default ReceiptTable;
