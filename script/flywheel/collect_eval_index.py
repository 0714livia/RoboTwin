import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional
import yaml

if __package__ in (None, ""):
    import sys
    sys.path.append(str(Path(__file__).resolve().parent))
    from utils import append_jsonl, read_jsonl, utc_now_iso
else:
    from .utils import append_jsonl, read_jsonl, utc_now_iso


def _parse_result_txt(path: Path) -> Optional[float]:
    if not path.exists():
        return None
    scores: List[float] = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        try:
            scores.append(float(line.strip()))
        except Exception:
            continue
    return scores[-1] if scores else None


def _scene_label(task_name: str, task_config: str, data_root: Path) -> str:
    cfg_file = Path("task_config") / f"{task_config}.yml"
    tags = []
    if cfg_file.exists():
        cfg = yaml.safe_load(cfg_file.read_text(encoding="utf-8"))
        dr = (cfg or {}).get("domain_randomization", {}) or {}
        if dr.get("cluttered_table"):
            tags.append("cluttered")
        if dr.get("random_background"):
            tags.append("random_bg")
        if dr.get("random_light"):
            tags.append("random_light")
    scene_info_path = data_root / task_name / task_config / "scene_info.json"
    if scene_info_path.exists() and not tags:
        tags.append("scene_info_present")
    return "+".join(tags) if tags else "default"


def build_eval_record(iteration_id: str, task_name: str, task_config: str, policy_name: str,
                      ckpt_setting: str, eval_dir: Path, data_root: Path, test_num: int = 100) -> Dict:
    result_path = eval_dir / "_result.txt"
    success_rate = _parse_result_txt(result_path)
    fail_count = None if success_rate is None else max(0, int(round((1.0 - success_rate) * test_num)))
    videos = sorted(eval_dir.glob("episode*.mp4"))

    return {
        "timestamp": utc_now_iso(),
        "iteration_id": iteration_id,
        "task_name": task_name,
        "task_config": task_config,
        "policy_name": policy_name,
        "model_version": ckpt_setting,
        "eval_dir": str(eval_dir),
        "result_path": str(result_path) if result_path.exists() else None,
        "test_num": test_num,
        "success_rate": success_rate,
        "failure_count": fail_count,
        "success_count": None if fail_count is None else test_num - fail_count,
        "scene_tag": _scene_label(task_name, task_config, data_root),
        "fail_stage": "unknown",  # MVP: no stage signal in current eval flow
        "video_count": len(videos),
        "videos": [str(v) for v in videos[:20]],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build structured eval JSONL records from eval_result/*/_result.txt")
    parser.add_argument("--iteration_id", required=True)
    parser.add_argument("--task_name", required=True)
    parser.add_argument("--task_config", required=True)
    parser.add_argument("--policy_name", default="ACT")
    parser.add_argument("--ckpt_setting", required=True)
    parser.add_argument("--eval_root", default="eval_result")
    parser.add_argument("--data_root", default="data")
    parser.add_argument("--output", default="flywheel_state/eval_index.jsonl")
    parser.add_argument("--test_num", type=int, default=100)
    args = parser.parse_args()

    target = Path(args.eval_root) / args.task_name / args.policy_name / args.task_config / args.ckpt_setting
    if not target.exists():
        raise FileNotFoundError(f"eval target not found: {target}")

    timestamp_dirs = sorted([p for p in target.iterdir() if p.is_dir()], key=lambda p: p.name)
    if not timestamp_dirs:
        raise FileNotFoundError(f"no eval run dirs in: {target}")

    latest = timestamp_dirs[-1]
    row = build_eval_record(
        iteration_id=args.iteration_id,
        task_name=args.task_name,
        task_config=args.task_config,
        policy_name=args.policy_name,
        ckpt_setting=args.ckpt_setting,
        eval_dir=latest,
        data_root=Path(args.data_root),
        test_num=args.test_num,
    )

    append_jsonl(Path(args.output), [row])
    print(f"[collect_eval_index] appended 1 row to {args.output}")


if __name__ == "__main__":
    main()
