import argparse
import subprocess
from pathlib import Path
from datetime import datetime

if __package__ in (None, ""):
    import sys
    sys.path.append(str(Path(__file__).resolve().parent))
    from utils import write_json
else:
    from .utils import write_json


def run_cmd(cmd: str, cwd: str | None = None) -> None:
    print(f"[flywheel_runner] RUN: {cmd} (cwd={cwd or '.'})")
    subprocess.run(cmd, shell=True, check=True, cwd=cwd)


def main() -> None:
    parser = argparse.ArgumentParser(description="Minimal runnable flywheel MVP runner")
    parser.add_argument("--task_name", required=True)
    parser.add_argument("--task_config", required=True)
    parser.add_argument("--gpu_id", type=int, default=0)
    parser.add_argument("--expert_data_num", type=int, default=50)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--ckpt_setting", default="demo_randomized")
    parser.add_argument("--iteration_id", default=None)
    parser.add_argument("--skip_collect", action="store_true")
    parser.add_argument("--skip_train", action="store_true")
    parser.add_argument("--skip_eval", action="store_true")
    parser.add_argument("--auto_trigger_next_collect", action="store_true")
    parser.add_argument("--main_tasks", default="")
    args = parser.parse_args()

    iteration_id = args.iteration_id or datetime.utcnow().strftime("iter_%Y%m%d_%H%M%S")
    state_file = Path(f"flywheel_state/iterations/{iteration_id}.json")

    state = {
        "iteration_id": iteration_id,
        "task_name": args.task_name,
        "task_config": args.task_config,
        "steps": [],
    }

    if not args.skip_collect:
        run_cmd(f"bash collect_data.sh {args.task_name} {args.task_config} {args.gpu_id}")
        run_cmd(
            "python -m script.flywheel.asset_index "
            f"--mode collection --iteration_id {iteration_id} --task_name {args.task_name} --task_config {args.task_config}"
        )
        state["steps"].append("collect")

    if not args.skip_train:
        run_cmd(f"bash process_data.sh {args.task_name} {args.task_config} {args.expert_data_num}", cwd="policy/ACT")
        run_cmd(
            f"bash train.sh {args.task_name} {args.task_config} {args.expert_data_num} {args.seed} {args.gpu_id}",
            cwd="policy/ACT",
        )
        run_cmd(
            "python -m script.flywheel.asset_index "
            f"--mode model --iteration_id {iteration_id} --task_name {args.task_name} --task_config {args.task_config} "
            f"--model_version {args.ckpt_setting} --model_path policy/ACT/act_ckpt/act-{args.task_name}/{args.ckpt_setting}-{args.expert_data_num}"
        )
        state["steps"].append("train")

    if not args.skip_eval:
        run_cmd(
            f"bash eval.sh {args.task_name} {args.task_config} {args.ckpt_setting} {args.expert_data_num} {args.seed} {args.gpu_id}",
            cwd="policy/ACT",
        )
        run_cmd(
            "python -m script.flywheel.asset_index "
            f"--mode evaluation --iteration_id {iteration_id} --task_name {args.task_name} --task_config {args.task_config} "
            f"--policy_name ACT --ckpt_setting {args.ckpt_setting} --model_version {args.ckpt_setting}"
        )
        run_cmd(
            "python -m script.flywheel.collect_eval_index "
            f"--iteration_id {iteration_id} --task_name {args.task_name} --task_config {args.task_config} "
            f"--policy_name ACT --ckpt_setting {args.ckpt_setting}"
        )
        run_cmd("python -m script.flywheel.failure_bucket")
        run_cmd(
            "python -m script.flywheel.recollect_plan "
            f"--iteration_id {iteration_id} --main_tasks \"{args.main_tasks}\" --base_episode {args.expert_data_num}"
        )
        run_cmd("python -m script.flywheel.automation_stat")
        state["steps"].append("eval_and_reflow")

    if args.auto_trigger_next_collect:
        run_cmd(
            "python - <<'PY'\n"
            "import json\n"
            "from pathlib import Path\n"
            "plan = json.loads(Path('flywheel_state/recollect_plan.json').read_text(encoding='utf-8'))\n"
            "if not plan.get('tasks'):\n"
            "    print('[flywheel_runner] no recollect tasks, skip auto trigger')\n"
            "else:\n"
            "    top = plan['tasks'][0]\n"
            "    print('[flywheel_runner] top recollect suggestion:', top)\n"
            "PY"
        )
        state["steps"].append("next_round_hint")

    write_json(state_file, state)
    print(f"[flywheel_runner] iteration done: {iteration_id}")


if __name__ == "__main__":
    main()
