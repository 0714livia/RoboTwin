import argparse
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

if __package__ in (None, ""):
    import sys
    sys.path.append(str(Path(__file__).resolve().parent))
    from utils import read_jsonl, write_json, utc_now_iso
else:
    from .utils import read_jsonl, write_json, utc_now_iso


def build_buckets(eval_rows: List[Dict]) -> Dict:
    buckets = defaultdict(lambda: {
        "task_name": None,
        "task_config": None,
        "scene_tag": None,
        "fail_stage": "unknown",
        "total_failure_count": 0,
        "records": [],
        "latest_iteration_id": None,
        "latest_timestamp": None,
    })

    for row in eval_rows:
        failure_count = row.get("failure_count")
        if failure_count is None or failure_count <= 0:
            continue
        key = (
            row.get("task_name"),
            row.get("task_config"),
            row.get("scene_tag", "default"),
            row.get("fail_stage", "unknown"),
        )
        rec = buckets[key]
        rec["task_name"] = key[0]
        rec["task_config"] = key[1]
        rec["scene_tag"] = key[2]
        rec["fail_stage"] = key[3]
        rec["total_failure_count"] += int(failure_count)
        rec["records"].append({
            "iteration_id": row.get("iteration_id"),
            "success_rate": row.get("success_rate"),
            "failure_count": failure_count,
            "model_version": row.get("model_version"),
            "timestamp": row.get("timestamp"),
            "eval_dir": row.get("eval_dir"),
        })
        rec["latest_iteration_id"] = row.get("iteration_id")
        rec["latest_timestamp"] = row.get("timestamp")

    return {
        "generated_at": utc_now_iso(),
        "bucket_count": len(buckets),
        "buckets": list(buckets.values()),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build failure buckets from eval_index.jsonl")
    parser.add_argument("--input", default="flywheel_state/eval_index.jsonl")
    parser.add_argument("--output", default="flywheel_state/failure_buckets.json")
    args = parser.parse_args()

    rows = read_jsonl(Path(args.input))
    payload = build_buckets(rows)
    write_json(Path(args.output), payload)
    print(f"[failure_bucket] wrote {payload['bucket_count']} buckets to {args.output}")


if __name__ == "__main__":
    main()
