# 研究任务人工盲评

本地候选包包含 102 道工程研究题，覆盖 17 个专题和 34 篇公开论文。每个专题有事实核对、方法比较、多步综合、指标提取、可比性判断和证据不足六道题，分别提供 8 篇候选论文。题包保存论文 ID、数据行号、摘要哈希和可核对的字符区间。当前已签核的真实任务数为 0，人工指标为 `null`。

## 准备材料

在项目根目录运行下列 PowerShell 命令。第一条以本机 Git LFS 对象重新生成题包，核对锁定的源文件与保存的 JSON。第二条从原件导出一道题所需的八份摘要。输出目录使用本机现有的 `output`，输出文件名须是新名称。

```powershell
.venv/Scripts/python.exe -m tools.research_eval.review_pack verify
.venv/Scripts/python.exe -m tools.research_eval.review_pack --out output/review-materials.json materials --task review-01-comparison
```

每次正式评分先冻结该次运行，保存题包规范化 SHA-256、实际作答的题目 ID、按检索顺序排列的论文 ID，以及系统输出的每条结论和所引论文。运行记录可以只包含部分题目，评分结果会同时显示运行题数和题包总数。以下字段说明提供录入格式。

```json
{
  "pack_sha256": "<verify 输出的 pack_sha256>",
  "tasks": [{
    "task_id": "review-01-comparison",
    "ranking": ["<实际排第 1 的论文 ID>", "<实际排第 2 的论文 ID>"],
    "claims": [
      {"claim_id": "C1", "text": "<系统输出的原文>", "cited_paper_ids": ["<实际所引论文 ID>"]}
    ]
  }]
}
```

把实际运行保存为 `output/review-run.json`，由协调人生成空表。分发时隐去系统名称、原始排序和其他评审员的选择。两位评审员分别获得同一份空表与相应题目的材料，独立填写。摘要中的导航区间仅用于定位，评审员应通读八份摘要后再确认相关性。

```powershell
.venv/Scripts/python.exe -m tools.research_eval.review_pack --out output/review-sheet.json template --run output/review-run.json
```

## 填写与签核

逐题给八篇候选论文填写 `qrels`。0 表示无关，1 表示相关背景，2 表示直接支持一个必要回答点，3 表示足以回答核心问题。尚未审阅的论文保留 `null`。对于要求判断缺乏证据的题目，能够直接说明适用边界的摘要可获相关分。

逐条核对结论、所引论文和适用条件，在 `judgment` 填入 `supported`、`contradicted` 或 `insufficient`。在 `reason` 写明论文 ID、依据所在句及其与结论的关系。对于数值比较，同时核对指标定义、单位、数据集与协议。只有这些条件足以支持原结论时才选 `supported`。证据范围为题包的摘要。

评审员填入项目内唯一的 `reviewer_id`、带时区的 ISO 时间 `signed_at`，并将 `human_attestation` 设为 `true`。协调人保管被授权评审员与代号的对应记录。程序校验签核声明、评审员代号以及题包和输出的哈希，身份授权由协调人核对。

## 导入与评分

```powershell
.venv/Scripts/python.exe -m tools.research_eval.review_pack --out output/review-scores.json score --run output/review-run.json --review output/reviewer-A.json --review output/reviewer-B.json
```

允许单人签核的项目在上述命令中提供一份 `--review` 并加 `--allow-single-reviewer`。查看待评状态时省略 `--review`。双人模式下，两人对同一组标签的结论须完全一致。协调人可把分歧退回评审员复核，各自另存一份修订后的签核表再导入。

同一题的八个相关分齐全后，调用已有评分实现计算 P@5、Recall@10、nDCG@10 和 MRR。P@5 的分母固定为 5。全部相关分为零时，Recall、nDCG 和 MRR 均保留 `null`。本次运行的每道题都具有有效指标时才输出相应的算术平均值。人工结论支持率取整次运行中 `supported` 的条数除以系统输出的结论总数。每条结论都需完成相应的人工作答和签核，空结论集合保留 `null`。结果中的 `disagreement` 或 `pending` 可以定位仍需复核的题目。
