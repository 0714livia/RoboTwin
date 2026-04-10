import argparse
from pathlib import Path
from typing import Dict, List

from .utils import append_jsonl, read_json, read_jsonl, utc_now_iso


def _latest_eval_dir(eval_root: Path, task_name: str, policy_name: str, task_config: str, ckpt_setting: str) -> Path | None:
    base = eval_root / task_name / policy_name / task_config / ckpt_setting
    if not base.exists():
        return None
    candidates = [p for p in base.iterdir() if p.is_dir()]
    if not candidates:
        return None
    return sorted(candidates, key=lambda p: p.name)[-1]


def index_collection(iteration_id: str, task_name: str, task_config: str, data_root: Path, source_type: str = "collect") -> Dict:
    task_dir = data_root / task_name / task_config
    data_dir = task_dir / "data"
    episodes = sorted(data_dir.glob("episode*.hdf5")) if data_dir.exists() else []
    scene_info = task_dir / "scene_info.json"
    return {
        "record_type": "collection",
        "timestamp": utc_now_iso(),
        "iteration_id": iteration_id,
        "task_name": task_name,
        "task_config": task_config,
        "source_type": source_type,
        "success": len(episodes) > 0,
        "episode_count": len(episodes),
        "data_path": str(task_dir),
        "scene_info_path": str(scene_info) if scene_info.exists() else None,
        "eval_result": None,
        "model_version": None,
        "episode_id": None,
    }


def index_eval(iteration_id: str, task_name: str, task_config: str, policy_name: str, ckpt_setting: str,
               eval_root: Path, model_version: str | None = None) -> Dict:
    latest_dir = _latest_eval_dir(eval_root, task_name, policy_name, task_config, ckpt_setting)
    result_path = None
    success_rate = None
    fail_count = None
    if latest_dir:
        result_path = latest_dir / "_result.txt"
        if result_path.exists():
            text = result_path.read_text(encoding="utf-8", errors="ignore").strip().splitlines()
            values = []
            for line in text:
                line = line.strip()
                if not line:
                    continue
                try:
                    values.append(float(line))
                except ValueError:
                    pass
            if values:
                success_rate = values[-1]
                fail_count = max(0, int(round((1 - success_rate) * 100)))

    return {
        "record_type": "evaluation",
        "timestamp": utc_now_iso(),
        "iteration_id": iteration_id,
        "task_name": task_name,
        "task_config": task_config,
        "source_type": "eval",
        "success": (success_rate is not None and success_rate >= 0.95),
        "episode_count": 100,
        "data_path": str(latest_dir) if latest_dir else None,
        "scene_info_path": None,
        "eval_result": {
            "success_rate": success_rate,
            "estimated_failure_count": fail_count,
            "result_path": str(result_path) if result_path else None,
        },
        "model_version": model_version or ckpt_setting,
        "episode_id": None,
    }


def index_model(iteration_id: str, task_name: str, task_config: str, model_version: str, model_path: str | None) -> Dict:
    return {
        "record_type": "model",
        "timestamp": utc_now_iso(),
        "iteration_id": iteration_id,
        "task_name": task_name,
        "task_config": task_config,
        "source_type": "train",
        "success": model_path is not None,
        "episode_count": None,
        "data_path": model_path,
        "scene_info_path": None,
        "eval_result": None,
        "model_version": model_version,
        "episode_id": None,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Append collection/model/eval records into flywheel asset index (JSONL)")
    parser.add_argument("--mode", choices=["collection", "evaluation", "model"], required=True)
    parser.add_argument("--iteration_id", required=True)
    parser.add_argument("--task_name", required=True)
    parser.add_argument("--task_config", required=True)
    parser.add_argument("--policy_name", default="ACT")
    parser.add_argument("--ckpt_setting", default="")
    parser.add_argument("--model_version", default=None)
    parser.add_argument("--model_path", default=None)
    parser.add_argument("--data_root", default="data")
    parser.add_argument("--eval_root", default="eval_result")
    parser.add_argument("--output", default="flywheel_state/asset_index.jsonl")
    args = parser.parse_args()

    output = Path(args.output)

    if args.mode == "collection":
        row = index_collection(args.iteration_id, args.task_name, args.task_config, Path(args.data_root))
    elif args.mode == "evaluation":
        row = index_eval(args.iteration_id, args.task_name, args.task_config, args.policy_name,
                         args.ckpt_setting, Path(args.eval_root), args.model_version)
    else:
        if not args.model_version:
            raise ValueError("--model_version is required in model mode")
        row = index_model(args.iteration_id, args.task_name, args.task_config, args.model_version, args.model_path)

    append_jsonl(output, [row])
    print(f"[asset_index] appended 1 row to {output}")


if __name__ == "__main__":
    main()
