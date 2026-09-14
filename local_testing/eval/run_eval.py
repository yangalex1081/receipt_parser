#!/usr/bin/env python
"""Sweep every prompt in prompts/ over every labelled receipt and rank them.

    python local_testing/eval/run_eval.py                    # all prompts, all photos
    python local_testing/eval/run_eval.py -p v0_production   # one prompt
    python local_testing/eval/run_eval.py -c bar sample21    # one or more photos
    python local_testing/eval/run_eval.py -m qwen3-vl:8b     # a different local model
    python local_testing/eval/run_eval.py --modal            # score the live deployment

Needs `ollama serve` running and the model pulled, except under --modal.

--modal scores the deployed transcript_receipt over the same labelled set. It
costs real GPU time and it cannot sweep prompts — the deployed function takes
only image bytes, so the prompt is whatever was baked in at deploy time. Use it
to confirm a winner after deploying it, not to pick one.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone

from harness import (
    DEFAULT_MODEL,
    EVAL_DIR,
    call_modal,
    call_ollama,
    load_cases,
    load_prompts,
    run,
)


def summarise(scores):
    """Aggregate a prompt's per-photo scores.

    Item F1 is macro-averaged over receipts rather than pooled over rows, so the
    22-row Bali receipt and the 1-row Starbucks one count equally. Pooling would
    let a prompt look good by nailing the two long receipts while dropping the
    single-item one, and the single-item one is the case that catches a model
    listing the payment line as a purchase.
    """
    n = len(scores) or 1
    return {
        "f1": sum(s.f1 for s in scores) / n,
        "recall": sum(s.recall for s in scores) / n,
        "precision": sum(s.precision for s in scores) / n,
        "rows_correct": sum(s.correct for s in scores),
        "rows_total": sum(s.n_truth for s in scores),
        "price_wrong": sum(s.name_only for s in scores),
        "junk": sum(s.junk for s in scores),
        "totals_ok": sum(1 for s in scores if s.total_ok),
        "totals_scored": sum(1 for s in scores if s.total_ok is not None),
        "dates_ok": sum(1 for s in scores if s.date_ok),
        "dates_scored": sum(1 for s in scores if s.date_ok is not None),
        "unparsed": sum(1 for s in scores if not s.parsed),
        "truncated": sum(1 for s in scores if s.truncated),
        "seconds": sum(s.seconds for s in scores) / n,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-p", "--prompts", nargs="*", help="prompt stems to run")
    ap.add_argument("-c", "--cases", nargs="*", help="photo stems to run")
    ap.add_argument("-m", "--model", default=DEFAULT_MODEL)
    ap.add_argument("-q", "--quiet", action="store_true", help="skip per-photo lines")
    ap.add_argument(
        "--modal",
        action="store_true",
        help="score the deployed transcript_receipt instead of Ollama (costs GPU)",
    )
    args = ap.parse_args()

    cases = load_cases(args.cases)
    if not cases:
        raise SystemExit("no labelled photos matched")

    caller = call_modal if args.modal else call_ollama

    if args.modal:
        # The deployed function has no prompt parameter, so there is exactly one
        # thing to score and -p cannot change it. Say so rather than silently
        # running the sweep and reporting the same number under five names.
        if args.prompts:
            print("note: --modal ignores -p; the deployed prompt is the only one\n")
        import funcs  # noqa: PLC0415 - harness has already put backend/ on the path
        from harness import MODAL_APP

        prompts = {"deployed": funcs.PROMPT}
        label = f"{MODAL_APP} on Modal ({funcs.MODEL_NAME})"
    else:
        prompts = load_prompts(args.prompts)
        if not prompts:
            raise SystemExit("no prompts matched")
        label = args.model

    print(f"model {label} | {len(prompts)} prompt(s) x {len(cases)} receipt(s)\n")

    results, started = {}, time.monotonic()
    for name, text in prompts.items():
        print(f"[{name}]")
        scores = run(
            name, text, cases, args.model, verbose=not args.quiet, caller=caller
        )
        results[name] = (scores, summarise(scores))
        print()

    header = (
        f"{'prompt':<22}{'itemF1':>8}{'rows':>10}{'price✗':>8}"
        f"{'junk':>7}{'total':>8}{'date':>7}{'fail':>6}{'cut':>5}{'sec':>7}"
    )
    print(header)
    print("-" * len(header))
    for name, (_, agg) in sorted(results.items(), key=lambda kv: -kv[1][1]["f1"]):
        rows = "{}/{}".format(agg["rows_correct"], agg["rows_total"])
        totals = "{}/{}".format(agg["totals_ok"], agg["totals_scored"])
        dates = "{}/{}".format(agg["dates_ok"], agg["dates_scored"])
        print(
            f"{name:<22}{agg['f1']:>8.3f}{rows:>10}"
            f"{agg['price_wrong']:>8}{agg['junk']:>7}"
            f"{totals:>8}{dates:>7}"
            f"{agg['unparsed']:>6}{agg['truncated']:>5}{agg['seconds']:>7.0f}"
        )

    print(
        "\nitemF1: macro-avg over receipts of rows matched by name AND exact price."
        "\nprice✗: rows whose name matched but price did not — the line-total rule failing."
        "\njunk:   subtotal/tax/payment rows wrongly listed as purchases."
        "\nfail:   replies that produced no usable JSON."
        "\ncut:    replies that hit the token cap mid-JSON (raise MAX_NEW_TOKENS, not the prompt)."
    )

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = EVAL_DIR / "results" / f"{stamp}.json"
    out.write_text(
        json.dumps(
            {
                "model": label,
                "backend": "modal" if args.modal else "ollama",
                "elapsed_seconds": round(time.monotonic() - started),
                "prompts": {
                    name: {
                        "summary": agg,
                        "photos": [
                            {
                                "photo": s.photo,
                                "f1": round(s.f1, 3),
                                "correct": s.correct,
                                "n_truth": s.n_truth,
                                "n_pred": s.n_pred,
                                "price_wrong": s.name_only,
                                "qty_ok": s.qty_ok,
                                "junk": s.junk,
                                "total_ok": s.total_ok,
                                "store_ok": s.store_ok,
                                "date_ok": s.date_ok,
                                "seconds": round(s.seconds, 1),
                                "truncated": s.truncated,
                                "output_tokens": s.output_tokens,
                                "missed": s.misses,
                                "raw": s.raw,
                            }
                            for s in scores
                        ],
                    }
                    for name, (scores, agg) in results.items()
                },
            },
            indent=2,
        )
    )
    print(f"\nfull output (incl. raw replies) -> {out.relative_to(EVAL_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
