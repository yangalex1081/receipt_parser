/**
 * Bill-splitting maths, kept free of React so it can be tested with plain
 * `node --test`.
 *
 * Everything is done in integer cents. Splitting $10.00 three ways in floats
 * gives 3.33 + 3.33 + 3.33 = 9.99, and a split that doesn't add back up to
 * the receipt is exactly the kind of thing people argue about. Leftover cents
 * are handed out one at a time (largest remainder first) so the shares always
 * sum to the total.
 */

export const UNASSIGNED = "Unassigned";

export const toCents = (amount) => Math.round((parseFloat(amount) || 0) * 100);

/**
 * "Alex, sam ,Alex" -> ["Alex", "sam"]. Names are comma separated; duplicates
 * (case-insensitive) collapse so "Alex, alex" is not a two-way split.
 */
export const parseBuyers = (buyer) => {
  const seen = new Set();
  const out = [];
  for (const raw of String(buyer ?? "").split(",")) {
    const name = raw.trim();
    const key = name.toLowerCase();
    if (!name || seen.has(key)) continue;
    seen.add(key);
    out.push(name);
  }
  return out;
};

/**
 * Split `cents` across `weights`, proportionally, returning integer cents that
 * sum exactly to `cents`. Works for negative amounts (discounts) too. With all
 * weights zero the amount is split evenly.
 */
export const allocate = (cents, weights) => {
  const n = weights.length;
  if (n === 0) return [];

  const totalWeight = weights.reduce((a, b) => a + b, 0);
  const w = totalWeight === 0 ? weights.map(() => 1) : weights;
  const sumW = totalWeight === 0 ? n : totalWeight;

  const sign = cents < 0 ? -1 : 1;
  const abs = Math.abs(cents);

  const exact = w.map((x) => (abs * x) / sumW);
  const shares = exact.map(Math.floor);
  let leftover = abs - shares.reduce((a, b) => a + b, 0);

  // Hand out the remaining cents to the largest fractional parts; ties go to
  // whoever comes first so the result is deterministic.
  const order = exact
    .map((x, i) => [x - Math.floor(x), i])
    .sort((a, b) => b[0] - a[0] || a[1] - b[1]);
  for (let k = 0; leftover > 0; k = (k + 1) % n, leftover--) {
    shares[order[k][1]] += 1;
  }

  return shares.map((s) => s * sign);
};

/**
 * Work out what each person owes.
 *
 * `items[].price` is the line total (see ReceiptTable). An item whose buyer is
 * "Alex, Sam" is split evenly between them; an item with no buyer goes to
 * UNASSIGNED. `extrasCents` (tax, tip, fees; negative for a discount) is then
 * shared in proportion to each person's item subtotal, which is how tax and a
 * percentage tip actually accrue.
 *
 * Returns { people: [{ name, subtotal, extras, total }], subtotal, extras,
 * total }, all in cents, people in first-seen order with UNASSIGNED last.
 */
export const computeSplit = (items, extrasCents = 0) => {
  // Keyed by lower-case name so "alex" and "Alex" are one person; the first
  // spelling seen is the one shown.
  const people = new Map();
  const person = (name) => {
    const key = name.toLowerCase();
    if (!people.has(key)) people.set(key, { name, subtotal: 0 });
    return people.get(key);
  };

  let subtotal = 0;
  for (const item of items) {
    const cents = toCents(item.price);
    subtotal += cents;

    const buyers = parseBuyers(item.buyer);
    const names = buyers.length > 0 ? buyers : [UNASSIGNED];
    allocate(cents, names.map(() => 1)).forEach((share, i) => {
      person(names[i]).subtotal += share;
    });
  }

  const list = [...people.values()].sort(
    (a, b) => (a.name === UNASSIGNED) - (b.name === UNASSIGNED)
  );

  // Nobody to charge extras to yet: still account for them so the grand
  // total is right, under UNASSIGNED.
  if (list.length === 0 && extrasCents !== 0) {
    list.push({ name: UNASSIGNED, subtotal: 0 });
  }

  const extraShares = allocate(
    extrasCents,
    list.map((p) => Math.max(p.subtotal, 0))
  );

  return {
    people: list.map((p, i) => ({
      name: p.name,
      subtotal: p.subtotal,
      extras: extraShares[i] ?? 0,
      total: p.subtotal + (extraShares[i] ?? 0),
    })),
    subtotal,
    extras: extrasCents,
    total: subtotal + extrasCents,
  };
};

export const formatCents = (cents) => {
  const sign = cents < 0 ? "−" : "";
  return `${sign}$${(Math.abs(cents) / 100).toFixed(2)}`;
};

/** Plain-text summary for pasting into a group chat. */
export const summaryText = (split, store) => {
  const lines = [];
  lines.push(store ? `🧾 ${store} split` : "🧾 Receipt split");
  for (const p of split.people) {
    const detail =
      split.extras !== 0
        ? ` (${formatCents(p.subtotal)} + ${formatCents(p.extras)} tax/tip)`
        : "";
    lines.push(`${p.name}: ${formatCents(p.total)}${detail}`);
  }
  lines.push(`Total: ${formatCents(split.total)}`);
  return lines.join("\n");
};
