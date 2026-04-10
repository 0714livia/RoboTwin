import argparse
from pathlib import Path

if __package__ in (None, ""):
    import sys
    sys.path.append(str(Path(__file__).resolve().parent))
    from utils import read_json, read_jsonl, write_json, utc_now_iso
else:
    from .utils import read_json, read_jsonl, write_json, utc_now_iso


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute lightweight flywheel automation stats")
    parser.add_argument("--asset_index", default="flywheel_state/asset_index.jsonl")
    parser.add_argument("--eval_index", default="flywheel_state/eval_index.jsonl")
    parser.add_argument("--recollect_plan", default="flywheel_state/recollect_plan.json")
    parser.add_argument("--output", default="flywheel_state/automation_stats.json")
    args = parser.parse_args()

    assets = read_jsonl(Path(args.asset_index))
    eval_rows = read_jsonl(Path(args.eval_index))
    plan = read_json(Path(args.recollect_plan), default={})

    collection_runs = len([a for a in assets if a.get("record_type") == "collection"])
    eval_runs = len(eval_rows)
    model_runs = len([a for a in assets if a.get("record_type") == "model"])

    success_rates = [r.get("success_rate") for r in eval_rows if r.get("success_rate") is not None]
    avg_success = None if not success_rates else sum(success_rates) / len(success_rates)

    payload = {
        "generated_at": utc_now_iso(),
        "collection_runs": collection_runs,
        "model_runs": model_runs,
        "eval_runs": eval_runs,
        "avg_success_rate": avg_success,
        "has_recollect_plan": bool(plan.get("tasks")),
        "planned_recollect_tasks": len(plan.get("tasks", [])),
    }
    write_json(Path(args.output), payload)
    print(f"[automation_stat] wrote stats to {args.output}")


if __name__ == "__main__":
    main()
