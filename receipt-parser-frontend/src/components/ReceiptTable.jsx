import React, { useMemo, useState } from "react";

/**
 * Fully controlled: rows are rendered straight from `parsedData` and every
 * change goes up through `onChange`. There is deliberately no local copy of
 * the items — mirroring props into state and re-syncing in an effect meant
 * each keystroke round-tripped through the parent, and would fight any
 * normalization the parent applied.
 */
const ReceiptTable = ({
  parsedData = {},
  onChange,
  onRestore,
  canRestore,
  people = [],
  onPeopleChange,
}) => {
  const [newPerson, setNewPerson] = useState("");

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
    emit([...items, { name: "", qty: 1, price: 0, buyers: [] }]);
  };

  const handleRemoveRow = (index) => {
    emit(items.filter((_, i) => i !== index));
  };

  const handleClear = () => emit([]);

  /**
   * Turn one "qty 3" row into three "qty 1" rows, so each can go to a
   * different person. The amount is divided in whole cents and the remainder
   * goes on the last row, so the rows still add up to exactly the original.
   */
  const handleSplitRow = (index) => {
    const item = items[index];
    const n = parseInt(item.qty) || 1;
    if (n < 2) return;
    const cents = Math.round((parseFloat(item.price) || 0) * 100);
    const each = Math.trunc(cents / n);
    const rows = Array.from({ length: n }, (_, k) => ({
      ...item,
      qty: 1,
      price: (k === n - 1 ? cents - each * (n - 1) : each) / 100,
    }));
    emit([...items.slice(0, index), ...rows, ...items.slice(index + 1)]);
  };

  // --- People --------------------------------------------------------------
  //
  // The list of people lives in the parent so it survives a new parse. A row
  // holds the names sharing it in `buyers`; a name no longer in `people` is
  // ignored rather than trusted.

  const buyersOf = (item) =>
    Array.isArray(item.buyers) ? item.buyers.filter((b) => people.includes(b)) : [];

  const handleAddPerson = () => {
    const name = newPerson.trim();
    setNewPerson("");
    if (!name || !onPeopleChange) return;
    if (people.some((p) => p.toLowerCase() === name.toLowerCase())) return;
    onPeopleChange([...people, name]);
  };

  const handleRemovePerson = (name) => {
    if (onPeopleChange) onPeopleChange(people.filter((p) => p !== name));
  };

  const toggleBuyer = (index, name) => {
    const current = buyersOf(items[index]);
    handleEdit(
      index,
      "buyers",
      current.includes(name) ? current.filter((b) => b !== name) : [...current, name]
    );
  };

  const toggleEveryone = (index) => {
    const everyone = buyersOf(items[index]).length === people.length;
    handleEdit(index, "buyers", everyone ? [] : [...people]);
  };

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

  // A row shared by several people is split evenly between them. Listed in
  // the order people were added, with anything unassigned last.
  const totalsByBuyer = useMemo(() => {
    const map = new Map(people.map((p) => [p, 0]));
    let unassigned = 0;
    let anyUnassigned = false;
    for (const i of items) {
      const sharing = Array.isArray(i.buyers)
        ? i.buyers.filter((b) => map.has(b))
        : [];
      if (sharing.length === 0) {
        unassigned += lineTotal(i);
        anyUnassigned = true;
        continue;
      }
      for (const b of sharing) map.set(b, map.get(b) + lineTotal(i) / sharing.length);
    }
    const rows = [...map.entries()];
    if (anyUnassigned) rows.push(["Unassigned", unassigned]);
    return rows;
  }, [items, people]);

  // The total printed on the receipt itself, when the parser could read it.
  // A gap between that and the sum of the rows usually means a line was
  // missed — the most common extraction failure — so it is worth showing.
  const printedTotal = Array.isArray(parsedData) ? null : parsedData?.printed_total;
  const hasPrintedTotal = typeof printedTotal === "number" && printedTotal > 0;
  const difference = hasPrintedTotal ? printedTotal - totalAmount : 0;
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

      <div className="people">
        <span className="people-label">People:</span>
        {people.map((p) => (
          <span key={p} className="chip chip--on chip--static">
            {p}
            <button
              type="button"
              className="chip-remove"
              onClick={() => handleRemovePerson(p)}
              aria-label={`Remove ${p}`}
            >
              ✕
            </button>
          </span>
        ))}
        <input
          type="text"
          className="people-input"
          value={newPerson}
          onChange={(e) => setNewPerson(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") {
              e.preventDefault();
              handleAddPerson();
            }
          }}
          placeholder="Add a name"
          aria-label="Add a person"
        />
        <button type="button" className="btn" onClick={handleAddPerson}>
          Add
        </button>
      </div>

      <div className="table-scroll">
        <table className="receipt-table">
          <thead>
            <tr>
              <th>Name</th>
              <th>Qty</th>
              <th title="Total for this line, not the unit price">Amount ($)</th>
              <th title="Tap everyone sharing the item; it is split evenly">Who</th>
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
                    <div className="chips">
                      {people.length === 0 ? (
                        <span className="chips-hint">Add people above</span>
                      ) : (
                        <>
                          {people.map((p) => {
                            const on = buyersOf(item).includes(p);
                            return (
                              <button
                                type="button"
                                key={p}
                                className={on ? "chip chip--on" : "chip"}
                                aria-pressed={on}
                                onClick={() => toggleBuyer(i, p)}
                              >
                                {p}
                              </button>
                            );
                          })}
                          {people.length > 1 && (
                            <button
                              type="button"
                              className="chip chip--all"
                              onClick={() => toggleEveryone(i)}
                              title="Split between everyone"
                            >
                              All
                            </button>
                          )}
                        </>
                      )}
                    </div>
                  </td>
                  <td className="row-actions">
                    {(parseInt(item.qty) || 1) > 1 && (
                      <button
                        type="button"
                        onClick={() => handleSplitRow(i)}
                        className="btn btn--icon"
                        title={`Split into ${item.qty} separate rows`}
                        aria-label={`Split ${item.name || `item ${i + 1}`} into ${item.qty} rows`}
                      >
                        ⑂
                      </button>
                    )}
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
                </td>
              </tr>
              {totalsByBuyer.map(([buyer, total]) => (
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
