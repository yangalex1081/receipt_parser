import { test } from "node:test";
import assert from "node:assert/strict";
import {
  allocate,
  computeSplit,
  parseBuyers,
  summaryText,
  UNASSIGNED,
} from "./split.js";

const sum = (xs) => xs.reduce((a, b) => a + b, 0);

test("parseBuyers splits on commas, trims, and dedupes case-insensitively", () => {
  assert.deepEqual(parseBuyers(" Alex, sam ,alex,, "), ["Alex", "sam"]);
  assert.deepEqual(parseBuyers(""), []);
  assert.deepEqual(parseBuyers(undefined), []);
});

test("allocate always sums back to the amount", () => {
  assert.deepEqual(allocate(1000, [1, 1, 1]), [334, 333, 333]);
  assert.deepEqual(allocate(-1000, [1, 1, 1]), [-334, -333, -333]);
  assert.deepEqual(allocate(100, [0, 0]), [50, 50]);
  assert.deepEqual(allocate(5, []), []);

  for (const [cents, weights] of [
    [1, [3, 3, 3]],
    [9999, [1, 2, 3, 4, 5]],
    [123, [700, 1, 1]],
  ]) {
    assert.equal(sum(allocate(cents, weights)), cents);
  }
});

test("shared items are split evenly between the named buyers", () => {
  const split = computeSplit([
    { name: "Pizza", price: 10, buyer: "Alex, Sam, Jo" },
    { name: "Soda", price: 2.5, buyer: "alex" },
  ]);
  const byName = Object.fromEntries(split.people.map((p) => [p.name, p.total]));
  assert.deepEqual(byName, { Alex: 584, Sam: 333, Jo: 333 });
  assert.equal(split.total, 1250);
});

test("extras are shared in proportion to each person's subtotal", () => {
  const split = computeSplit(
    [
      { price: 30, buyer: "Alex" },
      { price: 10, buyer: "Sam" },
    ],
    400
  );
  const [alex, sam] = split.people;
  assert.equal(alex.extras, 300);
  assert.equal(sam.extras, 100);
  assert.equal(split.total, 4400);
  assert.equal(sum(split.people.map((p) => p.total)), split.total);
});

test("unassigned items are listed last and still counted", () => {
  const split = computeSplit([
    { price: 5, buyer: "" },
    { price: 7, buyer: "Alex" },
  ]);
  assert.deepEqual(
    split.people.map((p) => p.name),
    ["Alex", UNASSIGNED]
  );
  assert.equal(split.total, 1200);
});

test("extras with no items still land somewhere", () => {
  const split = computeSplit([], 250);
  assert.equal(split.people.length, 1);
  assert.equal(split.people[0].total, 250);
});

test("summaryText mentions tax/tip only when there are extras", () => {
  const plain = summaryText(computeSplit([{ price: 1, buyer: "Alex" }]), "Costco");
  assert.equal(plain, "🧾 Costco split\nAlex: $1.00\nTotal: $1.00");

  const withExtras = summaryText(computeSplit([{ price: 1, buyer: "Alex" }], 10));
  assert.match(withExtras, /Alex: \$1\.10 \(\$1\.00 \+ \$0\.10 tax\/tip\)/);
});
