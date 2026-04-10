# RoboTwin 2.0 数据飞轮代码架构梳理报告

> 目标：面向“具身智能数据飞轮”实现，不做泛导览，而是识别已具备流程、缺口与最优补流程插入点。

## 0. 分析边界与方法

- 本报告仅基于仓库代码路径、脚本入口、I/O 逻辑与调用链梳理。
- 重点检查了：`collect_data.sh`、`script/`、`envs/`、`task_config/`、`description/utils/`、`policy/*` 中的数据处理/训练/评测入口。
- 对“是否存在自动化飞轮能力（回流、调度、补数、版本关联）”采用“代码证据优先”判断；若无法闭环确认，标记为“待进一步验证”。

---

## 1. 仓库现有主链路总览（现状）

### 1.1 如何采集

1. 统一采集入口是根目录 `collect_data.sh`，内部调用 `script/collect_data.py`。  
2. `script/collect_data.py` 先读任务配置 `task_config/*.yml`，再动态加载任务环境 `envs.<task_name>`。  
3. 采集分两段：
   - **Seed/预规划阶段**：`need_plan=True`，执行 `TASK_ENV.play_once()`，仅在 `plan_success && check_success()` 时记录 seed 到 `seed.txt`，并缓存轨迹规划结果到 `_traj_data/episode*.pkl`。
   - **正式数据落盘阶段**：`need_plan=False`，按 seed 重放，执行 `_take_picture()` 逐帧缓存 `.cache/episode*/{frame}.pkl`，然后 `merge_pkl_to_hdf5_video()` 合并为 `data/episode*.hdf5` + `video/episode*.mp4`。
4. 每个 episode 的场景参数写入 `scene_info.json`，随后调用 `description/gen_episode_instructions.sh` 生成语言指令 `instructions/episode*.json`。

### 1.2 如何落盘

默认落盘根路径来自 task config 的 `save_path`（通常 `./data`），组织为：

- `data/<task>/<task_config>/seed.txt`：成功 seed 列表。
- `data/<task>/<task_config>/_traj_data/episode*.pkl`：规划轨迹缓存（左右臂 path）。
- `data/<task>/<task_config>/data/episode*.hdf5`：训练主数据。
- `data/<task>/<task_config>/video/episode*.mp4`：可视化回放。
- `data/<task>/<task_config>/scene_info.json`：场景信息与模板占位符参数。
- `data/<task>/<task_config>/instructions/episode*.json`：seen/unseen 语言描述。

### 1.3 如何进入训练

- 各策略采用**各自独立的 process_data + train** 两段式：
  - ACT：`policy/ACT/process_data.py` -> `policy/ACT/train.sh`。
  - DP：`policy/DP/process_data.py`（转 zarr）-> `policy/DP/train.sh`。
  - DP3：`policy/DP3/scripts/process_data.py`（点云 zarr）-> `policy/DP3/train.sh`。
  - RDT：`policy/RDT/scripts/process_data.py`（每 episode 独立目录 + 语言编码）-> `policy/RDT/finetune.sh`。
- 输入统一来自 RoboTwin 采集的 HDF5，但中间格式不统一（HDF5/压缩JPEG/HWC图像/zarr/多目录结构并存）。

### 1.4 如何统一评测

- 统一评测入口是 `script/eval_policy.py`：
  - 加载 `policy/<name>/deploy_policy.yml`。
  - 通过统一接口反射调用策略模块的 `get_model / eval / reset_model`。
  - 固定在环境中执行 100 次有效种子评测（带 expert seed 筛选），输出成功率。
- 评测输出目录：`eval_result/<task>/<policy>/<task_config>/<ckpt_setting>/<timestamp>/`。
- 结果文件当前仅 `_result.txt`（文本），若开启评测录像则写 mp4。

---

## 2. 数据飞轮七环节映射表

| 飞轮环节 | 仓库现有实现位置 | 核心脚本/类/函数 | 当前是否完整 | 缺口说明 | 补充建议 |
|---|---|---|---|---|---|
| 数据从哪里来 | 仿真任务环境 + 任务配置 + domain randomization | `collect_data.sh`; `script/collect_data.py`; `envs/<task>.py`; `task_config/*.yml` | 部分完整 | 有采集入口，但来源仅“离线批采集”，缺少由评测失败触发的定向采集 | 在 wrapper 层新增“按失败标签定向采集”入口，复用 `collect_data.py` 参数 |
| 数据长什么样 | 采集 HDF5 + 视频 + scene info + instruction | `envs/_base_task.py`(`_take_picture`,`merge_pkl_to_hdf5_video`); `envs/utils/pkl2hdf5.py`; `description/utils/generate_episode_instructions.py` | 部分完整 | 有事实标准，但未形成正式 schema/version 文档与机器可校验规范 | 增加 `schema.json` + 校验脚本（CI可跑） |
| 数据怎么筛 | 采集阶段 success gate；手工删除坏样本脚本 | `script/collect_data.py` (`plan_success && check_success`); `data/process_stuck.py` | 不完整 | 只有二元成功筛；缺少多维质量分、失败类型标签与批量筛选器 | 新增 `script/filter_dataset.py` 输出结构化筛选报告 |
| 数据怎么进训练 | 各 policy 独立转换+训练 | `policy/*/process_data*.py`; `policy/*/train*.sh` | 部分完整 | pipeline 分裂，数据中间表示不统一，难做跨策略复用与自动编排 | 增加统一 dataset adapter 层（先定义 canonical index，再派生） |
| 数据怎么评 | 统一评测脚本 + policy 统一接口 | `script/eval_policy.py`; `policy/*/deploy_policy.py` | 部分完整 | 输出主要是 `_result.txt`，缺结构化 episode 级失败记录 | 增加 `eval_result.jsonl`（episode_seed/success/fail_reason） |
| 数据怎么回流 | 基本无自动回流，仅人工重采/重训 | 现有仅 `seed.txt`,`scene_info.json`,`process_stuck.py` 可人工操作 | 缺失 | 无自动把失败样本回写到“补数任务队列” | 新增 `build_reflow_queue.py`，从评测失败自动产出补采计划 |
| 怎么触发下一轮 | 基本无统一调度 | 无集中 orchestrator | 缺失 | 无“采集-处理-训练-评测-回流”自动串联与停止条件 | 新增 `script/flywheel_runner.py` 作为最小调度器 |

---

## 3. 关键代码位置清单（按飞轮相关度）

### 3.1 采集入口与采集链路

- `collect_data.sh`：采集总入口，设置 GPU，调用 `script/collect_data.py`，最后清理 `.cache`。  
- `script/collect_data.py`：采集主编排（seed 搜索、重放采集、scene_info 写入、指令生成触发）。  
- `envs/_base_task.py`：采集数据的底层保存/合并逻辑（pkl 缓存、HDF5+视频合并、轨迹缓存、缓存清理）。

### 3.2 采集产物格式与数据组织

- `envs/utils/pkl2hdf5.py`：定义“多帧 pkl -> 单 episode hdf5 + mp4”的转换规则，图像以 JPEG bytes 存储到 `rgb` dataset。  
- `envs/utils/parse_hdf5.py`：读取端将 HDF5 的 `rgb` 字节数组解码回图像。  
- `description/utils/generate_episode_instructions.py`：从 `scene_info.json` + 模板生成 `instructions/episode*.json`（seen/unseen）。

### 3.3 数据预处理与策略数据转换

- ACT：`policy/ACT/process_data.py`（转换为 ACT 训练格式 HDF5，并维护 `SIM_TASK_CONFIGS.json` 索引）。
- DP：`policy/DP/process_data.py`（转换为 zarr，`data/state/action/head_camera + meta/episode_ends`）。
- DP3：`policy/DP3/scripts/process_data.py`（转换点云 zarr）。
- RDT：`policy/RDT/scripts/process_data.py`（按 episode 目录落盘 + 文本 embedding 编码）。

### 3.4 训练主线脚本与入口

- ACT：`policy/ACT/train.sh` -> `imitate_episodes.py`。
- DP：`policy/DP/train.sh` -> `train.py`（hydra 配置）。
- DP3：`policy/DP3/train.sh` -> `scripts/train_policy.sh`。
- RDT：`policy/RDT/finetune.sh` -> `main.py`（accelerate/deepspeed）。

### 3.5 统一评测入口与输出

- `script/eval_policy.py`：跨策略统一评测入口。
- `policy/*/deploy_policy.py`：统一接口适配层，需提供 `get_model/eval/reset_model`。
- 输出目录：`eval_result/...`，核心结果文件 `_result.txt`，可选视频。

### 3.6 失败反馈、补数与回流相关

- `data/process_stuck.py`：仅支持手动删除指定坏 episode 并替换 seed（偏手工修复，不是飞轮回流）。
- 未发现：失败样本池、失败标签分桶、自动补数计划生成脚本、跨轮次版本索引、全链路调度器。

### 3.7 调度器/runner

- 存在**评测模型服务 runner**：`script/policy_model_server.py` + `script/eval_policy_client.py`（用于模型服务化推理）。
- 不等价于飞轮调度器：它不负责编排采集/处理/训练/回流轮次。

---

## 4. RoboTwin 2.0 飞轮成熟度判断

### 判定：**“已具备飞轮底座但缺少调度与回流”**

### 证据（代码级）

- 已有底座：
  - 稳定采集链（seed 搜索 + 重放 + HDF5落盘）。
  - 多策略训练入口（虽然分裂）。
  - 统一评测入口（策略接口统一）。
- 核心缺口：
  - 评测结果缺少结构化失败样本输出（主要是文本成功率）。
  - 无自动失败样本池/分桶。
  - 无自动补数计划生成与执行。
  - 无跨轮次 dataset/model/eval 版本关联（manifest/index）。
  - 无统一 flywheel orchestrator。

因此不是“仅有采训评流水线”（因为已有较完整底座），也远未达到“已接近完整飞轮”。

---

## 5. 数据飞轮缺口清单

### 5.1 已经有

- 数据采集入口与可配置随机化。
- 采集落盘到 HDF5 + video + scene_info + instruction。
- 多策略数据转换与训练入口。
- 统一评测入口与统一策略推理接口（deploy_policy 适配）。

### 5.2 部分有

- 数据筛选：仅成功/失败 gate + 手工修复脚本。
- 评测结果：有成功率输出，但结构化粒度不足。
- runner：有模型服务 runner，但不是飞轮调度器。

### 5.3 完全没有（当前仓库未见）

- 数据资产索引层（dataset manifest/index + lineage）。
- 失败样本池。
- 高价值失败样本分桶。
- 自动补数计划生成。
- 飞轮调度器（多阶段自动编排）。
- 训练/数据/评测版本关联闭环。
- 自动化率统计（飞轮 KPI）。

### 5.4 指定能力逐项判断

- 数据资产索引层：**缺失**。
- 失败样本池：**缺失**。
- 高价值失败样本分桶：**缺失**。
- 结构化评测结果输出：**缺失（仅文本结果）**。
- 自动补数计划生成：**缺失**。
- 飞轮调度器：**缺失**。
- 训练/数据/评测版本关联：**缺失**。
- 自动化率统计：**缺失**。

---

## 6. MVP 实现建议（最小增量，优先 wrapper 层）

> 原则：尽量不改 `envs/`、`policy` 核心训练逻辑，先在 `script/` 增量封装。

### 6.1 最值得先新增的脚本（建议顺序）

1. `script/export_eval_jsonl.py`  
   - 输入：`eval_result/...` 当前文本 + 运行日志上下文。  
   - 输出：`eval_result.jsonl`（episode_seed, success, instruction_type, 可选 fail_stage）。  
   - 价值：先把“评测可回流信息”结构化。

2. `script/build_failure_pool.py`  
   - 输入：`eval_result.jsonl`。  
   - 输出：`failure_pool/{task}/{policy}/{ckpt}/failures.parquet(jsonl)`。  
   - 功能：按 task/seed/instruction/fail_type 聚合，可打分（失败频次、跨模型共错）。

3. `script/gen_recollect_plan.py`  
   - 输入：failure pool + task config。  
   - 输出：`plans/recollect_round_<n>.yml`（每任务补采数量、seed策略、randomization策略）。  
   - 功能：自动补数计划生成（先规则法）。

4. `script/flywheel_runner.py`  
   - 仅做编排，不改底层：
     - collect -> process -> train -> eval -> failure_pool -> recollect_plan。
   - 初期支持“单策略单任务单轮/多轮”即可。

5. `script/register_lineage.py`  
   - 维护 `flywheel_registry.json`：记录 run_id、dataset_version、model_ckpt、eval_result、plan_id 的关联。

### 6.2 最适合复用的现有脚本

- 采集复用：`script/collect_data.py`（已有 seed + replay 机制，利于定向补采）。
- 评测复用：`script/eval_policy.py`（已有跨策略统一接口）。
- 转换复用：`policy/*/process_data*.py`（短期先透传，不统一重写）。
- 指令复用：`description/utils/generate_episode_instructions.py`（补采后自动补充语言）。

### 6.3 不建议 MVP 阶段做的事

- 直接统一所有 policy 的训练数据格式（改动大且风险高）。
- 深改 `envs/_base_task.py` 的采集机制（底层耦合重，先包裹再重构）。

---

## 7. 风险点（直接上飞轮时最可能卡住）

1. **数据格式碎片化风险高**：不同 policy process_data 的目标格式差异大（zarr/HDF5/目录结构）。
2. **评测结果非结构化风险高**：缺 episode 级失败原因，回流策略难做精细化。
3. **任务/策略脚本风格不一致**：参数命名、路径组织、ckpt 命名规则不统一。
4. **版本追踪缺失**：无法可靠回答“某次评测使用了哪批数据训练出的哪个模型”。
5. **自动化断点多**：当前大量人工调用 shell，缺少断点恢复与轮次状态机。

---

## 8. 如果要在代码层面实现数据飞轮，最推荐先补的文件/脚本（优先级）

1. `script/flywheel_runner.py`（新）  
   - 原因：先把现有脚本串起来，建立“轮次”概念与最小自动化主干。

2. `script/export_eval_jsonl.py`（新）  
   - 原因：没有结构化评测就没有可编程回流。

3. `script/build_failure_pool.py`（新）  
   - 原因：把失败从“日志文本”变为“可查询资产”。

4. `script/gen_recollect_plan.py`（新）  
   - 原因：实现“失败->补数”闭环关键一跳。

5. `script/register_lineage.py`（新）  
   - 原因：建立数据/模型/评测跨轮关联，支撑复现实验与回滚。

6. `script/collect_data.py`（复用 + 最小改造）  
   - 改造点建议：允许外部计划文件指定 seed list / episode quota / randomization profile。

7. `script/eval_policy.py`（复用 + 最小改造）  
   - 改造点建议：增加 `--jsonl_output` 与 episode 粒度字段。

---

## 9. 待进一步验证项

- 各策略私有训练代码中是否存在独立的实验 tracking（如 wandb artifact 绑定 dataset hash），当前在仓库入口层未见统一约束。  
- 是否有外部平台（非本仓库）承担轮次调度与版本管理；本仓库内未发现对应 orchestrator。  
- 是否存在隐藏的内部数据规范文档（代码内未发现 schema 校验入口）。

