# RoboTwin Flywheel MVP (wrapper-first)

This folder provides a minimal runnable data-flywheel wrapper layer without changing core env/policy logic.

## Scripts

- `asset_index.py`: append collection/model/eval records into `flywheel_state/asset_index.jsonl`.
- `collect_eval_index.py`: convert latest eval run (`_result.txt`, videos, task config tags) into structured `flywheel_state/eval_index.jsonl`.
- `failure_bucket.py`: aggregate failures by `task_name/task_config/scene_tag/fail_stage`.
- `recollect_plan.py`: generate next-round recollect plan from buckets + historical eval records.
- `automation_stat.py`: output lightweight automation KPIs.
- `flywheel_runner.py`: orchestrate collect -> ACT process/train -> eval -> index -> bucket -> recollect-plan.

## Example

```bash
python -m script.flywheel.flywheel_runner \
  --task_name beat_block_hammer \
  --task_config demo_randomized \
  --gpu_id 0 \
  --expert_data_num 50 \
  --seed 0 \
  --ckpt_setting demo_randomized
```

## State outputs

- `flywheel_state/asset_index.jsonl`
- `flywheel_state/eval_index.jsonl`
- `flywheel_state/failure_buckets.json`
- `flywheel_state/recollect_plan.json`
- `flywheel_state/automation_stats.json`
- `flywheel_state/iterations/<iteration_id>.json`

