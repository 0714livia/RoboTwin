import argparse
from pathlib import Path
from typing import Dict, List, Set

if __package__ in (None, ""):
    import sys
    sys.path.append(str(Path(__file__).resolve().parent))
    from utils import read_json, read_jsonl, write_json, utc_now_iso
else:
    from .utils import read_json, read_jsonl, write_json, utc_now_iso


def _recent_repeat_count(eval_rows: List[Dict], task_name: str, task_config: str, lookback: int = 3) -> int:
    matched = [r for r in eval_rows if r.get("task_name") == task_name and r.get("task_config") == task_config]
    matched = sorted(matched, key=lambda x: x.get("timestamp", ""), reverse=True)
    repeats = 0
    for row in matched[:lookback]:
        if (row.get("failure_count") or 0) > 0:
            repeats += 1
    return repeats


def build_plan(
    failure_buckets: Dict,
    eval_rows: List[Dict],
    iteration_id: str,
    main_tasks: Set[str],
    base_episode: int,
) -> Dict:
    tasks = []
    for bucket in failure_buckets.get("buckets", []):
        task_name = bucket.get("task_name")
        task_config = bucket.get("task_config")
        total_fail = int(bucket.get("total_failure_count", 0))

        related = [r for r in bucket.get("records", []) if r.get("failure_count") is not None]
        avg_fail_rate = 0.0
        if related:
            avg_fail_rate = sum(float(r.get("failure_count", 0)) / 100.0 for r in related) / len(related)

        main_bonus = 1.5 if task_name in main_tasks else 1.0
        repeat = _recent_repeat_count(eval_rows, task_name, task_config, lookback=3)
        repeat_bonus = 1.0 + 0.15 * repeat

        impact = avg_fail_rate if avg_fail_rate > 0 else min(1.0, total_fail / 100.0)
        score = (total_fail * 0.6 + impact * 100 * 0.3) * main_bonus * repeat_bonus

        recollect_episodes = max(5, int(base_episode * (0.2 + min(0.8, impact)) * main_bonus))

        tasks.append({
            "task_name": task_name,
            "task_config": task_config,
            "scene_tag": bucket.get("scene_tag", "default"),
            "fail_stage": bucket.get("fail_stage", "unknown"),
            "priority_score": round(score, 3),
            "estimated_failure_count": total_fail,
            "avg_fail_rate": round(avg_fail_rate, 4),
            "is_main_task": task_name in main_tasks,
            "recent_repeat_fail_rounds": repeat,
            "recommended_episode_num": recollect_episodes,
            "strategy": {
                "collect_mode": "targeted_recollect",
                "suggest_use_seed": False,
                "suggest_increase_domain_randomization": bucket.get("scene_tag") != "default",
            },
        })

    tasks = sorted(tasks, key=lambda x: x["priority_score"], reverse=True)

    return {
        "generated_at": utc_now_iso(),
        "iteration_id": iteration_id,
        "plan_type": "next_round_recollect",
        "task_count": len(tasks),
        "tasks": tasks,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate recollection plan from failure buckets")
    parser.add_argument("--iteration_id", required=True)
    parser.add_argument("--failure_input", default="flywheel_state/failure_buckets.json")
    parser.add_argument("--eval_input", default="flywheel_state/eval_index.jsonl")
    parser.add_argument("--output", default="flywheel_state/recollect_plan.json")
    parser.add_argument("--main_tasks", default="")
    parser.add_argument("--base_episode", type=int, default=50)
    args = parser.parse_args()

    failure_payload = read_json(Path(args.failure_input), default={})
    eval_rows = read_jsonl(Path(args.eval_input))
    main_tasks = {x.strip() for x in args.main_tasks.split(",") if x.strip()}

    plan = build_plan(
        failure_buckets=failure_payload,
        eval_rows=eval_rows,
        iteration_id=args.iteration_id,
        main_tasks=main_tasks,
        base_episode=args.base_episode,
    )

    write_json(Path(args.output), plan)
    print(f"[recollect_plan] wrote {plan['task_count']} plan items to {args.output}")


if __name__ == "__main__":
    main()
