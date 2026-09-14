# Prompt eval harness

Scores a prompt against six hand-labelled receipts (77 line items) using a local
copy of the production model. A full sweep is free and takes about half an hour.

## This is not the test suite

`backend/tests/` answers yes/no questions — does auth reject a forged token,
does normalize_output drop a TOTAL row — and every one of them is free,
offline, and deterministic. Run it with `pytest` from the repo root.

This directory answers *how well*, which has no yes/no answer. It prints a table
and writes JSON; it never asserts. That split is deliberate. A quality bar
written as an assert is either loose enough that it never fires or tight enough
that ordinary run-to-run drift breaks the build, and neither tells you anything
you would act on.

## Running it

```bash
ollama pull qwen3-vl:4b-instruct-bf16     # once, ~8.9GB

cd local_testing/eval
../../venv/bin/python run_eval.py                    # every prompt, every receipt
../../venv/bin/python run_eval.py -p v0_production   # one prompt
../../venv/bin/python run_eval.py -c bar sample21    # one or more receipts
```

Each run writes `results/<timestamp>.json` with per-receipt scores and every raw
reply, which is what you actually read when a number moves.

## Scoring the deployment

```bash
../../venv/bin/python run_eval.py --modal      # costs GPU time
```

This swaps Ollama for the deployed `transcript_receipt` and scores the same
labelled set, so you can confirm that a prompt which won locally also wins on
the real weights.

It cannot sweep prompts. `transcript_receipt` takes only image bytes — the
prompt is `funcs.PROMPT`, baked in at deploy time — so `--modal` scores exactly
one thing and ignores `-p`. Pick a winner locally, deploy it, then confirm here.

One difference from the local path: `prepare_image` skips its MAX_PIXELS
downsample under `--modal`, because the deployed processor applies that itself
and doing it twice would score the deployment against an image it would never
be sent.

## Use the `instruct` tag

`qwen3-vl:4b-instruct-bf16` is the same checkpoint and dtype `config.py` loads on
Modal, so scores are comparable to production rather than merely rankable.

The bare `qwen3-vl:4b` tag is **the Thinking variant**. It spends the whole
`MAX_NEW_TOKENS` budget on hidden reasoning and returns an empty string, and
`think: false` does not suppress it. Scored against it, the production prompt
looks like it fails on five of six receipts. It does not.

## Adding a case

Drop the photo in `test_photos/`, then write `ground_truth/<stem>.json`:

```json
{
  "_note":  "why this receipt is interesting",
  "store":  "merchant, or null to leave the field unscored",
  "date":   "YYYY-MM-DD, or null",
  "total":  0.00,
  "items":  [{"name": "as printed", "qty": 1, "price": 0.00}]
}
```

`null` means "not legible on the receipt itself" and excludes the field from
scoring — use it rather than guessing, so the score measures the model and not
your eyesight. Cross-check the item list against the printed subtotal before
trusting it.

## Adding a prompt

Drop a `.txt` in `prompts/`. `v0_production.txt` is the deployed prompt, extracted
from `funcs.PROMPT`; re-extract it after changing `funcs.py` so the baseline stays
honest:

```bash
../../venv/bin/python -c "import sys; sys.path.insert(0,'../../backend'); import funcs; \
open('prompts/v0_production.txt','w').write(funcs.PROMPT)"
```

## Reading the table

`itemF1` is macro-averaged over receipts, so the 22-row Bali receipt and the
1-row Starbucks one count equally — the short one is where a payment line listed
as an item does the most damage.

A row counts as correct only when its name matches a truth row (60% similarity,
loose on purpose) **and** its price matches exactly. `price✗` is the count that
matched on name and missed on price: that column is the line-total rule failing.

Treat differences under about 0.02 as noise. Six receipts is enough to catch a
prompt that breaks a rule outright, not enough to rank two prompts that both work.
