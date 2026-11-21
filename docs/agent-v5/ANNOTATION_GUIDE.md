# E10 人工评审说明

从仓库根目录运行下列命令。输出目录须为新目录。每份包都带有题目集、原文及运行记录的哈希。完整原文、未脱敏的运行记录和实名评审材料保存在本地。

```sh
python -m tools.research_eval.e10_pack --output output/v5/review-new --include-run
python -m tools.research_eval.e10_score output/v5/review-new --output output/v5/pending-new.json
```

1. 两位评审分别领取 `reviewer-a.json`、`reviewer-b.json`。先依据题面和许可原文独立判断，再对照系统输出中的字段、命题和证据编号填写对应关系。只在实际审阅过的题目中填写判断。未审题保持 `null`。
2. 判断字段遵循 `judgment.schema.json`。每篇许可论文评 0 至 3 分，依次表示无关、略相关、相关、直接相关。证据位置写成 `[paper_id, "abstract:chars:起点-终点"]`，以原文 Unicode 字符计数，起点含、终点不含。判断必须覆盖全部已发布命题和证据，可拒绝任一对应关系并写明理由。
3. 每人使用独立评审身份，记录含时区的实际评审时间并填写 `human_confirmed`。这是评审人自我确认。评分器检查身份字段及数据哈希，身份真实性由组织评审者核实。
4. 两份判断相同可直接计分。存在实质分歧时，由第三人独立填写包内 `adjudication.json`，并写明采信依据。保留两份原判断。尚有争议的题不计入已确认分母。

```sh
python -m tools.research_eval.e10_score output/v5/review-new --reviews output/v5/review-new/reviewer-a.json output/v5/review-new/reviewer-b.json --adjudication output/v5/review-new/adjudication.json --output output/v5/review-scored.json
```

仅在发生裁定并填写裁定人信息后传入 `--adjudication`。`ranking` 按研究阶段实际检索结果中论文首次出现排序，另保留论文发现和段落检索各自的顺序。`claim_support_precision` 统计已发布命题获得原文支持的比例。缺少独立蕴含分类预测时 `entailment_accuracy` 留空。技术执行成功和人类判定任务成功分别计数。`pending-review.json` 列有本批次 102 道 Review 题和 9 道优先复核题。
