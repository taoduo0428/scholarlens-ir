# PDF 版面核验

核验样本是 Pan 等人发表的 *Online Community Detection for Large Complex Networks*，出版社采用 CC BY 4.0。读取同篇论文的 PDF 和 JATS XML，共 12 页，6 张表、6 幅标注图。[出版社原文](https://doi.org/10.1371/journal.pone.0102799)

用 pdfplumber 0.11.11 提取页内区域，对全部返回项检查边界框、坐标系、文档哈希及引文哈希。表格比较只归一化 Unicode、空白和全空分隔行，保留列序、行序、数字、符号及表头。6 张表的 219 个单元格与出版社逐格一致，位于第 6、7、8、10 页。7 个候选中，第 1 页装饰框为误检。单篇命中率不能外推到扫描论文或复杂跨页表格。

公式、图像区域和题注各有类型。该样本返回 7 个图像区域。图像区域与出版社的 6 幅图还缺内容级匹配。图表轴数值、图例、OCR、跨页表连接及公式语义都保留未核验状态。工作台可在限定论文范围内读取指定页，选择原表单元格。生成报告时，服务在当前账户和任务预算内重新读取单元格，并核对文档版本与引文哈希。报告和 Markdown 保留页、表、物理行列及坐标。

真实样本复核选择第 6 页表 1 的物理第 3 行第 2 列，结果为 `23,133`。出版社 JATS 原表的行名为 `ca-CondMat`，列名为 `Number of nodes`。复核程序还从 SQLite 读回报告比对内容。命令为 `python -m tools.research_eval.v7_pdf_publication <publisher.pdf> <publisher.xml>`。这个结果覆盖指定单元格的引用；跨页表和自动推断仍待验证。

复核命令为 `python -m tools.research_eval.v7_pdf <publisher.pdf> <publisher.xml> --output <result.json>`。脚本先验证论文的两份输入哈希，再调用产品页级提取入口。提交 `6e2a78f` 实现访问接口，`b4c6927` 加入出版社对照，`99bc99c` 升级解析器。[逐表页码与哈希](pdf-results.json)
