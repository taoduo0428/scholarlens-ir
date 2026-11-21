# PDF 版面核验

核验样本是 Pan 等人发表的 *Online Community Detection for Large Complex Networks*，出版社采用 CC BY 4.0。读取同篇论文的 PDF 和 JATS XML，共 12 页，6 张表、6 幅标注图。[出版社原文](https://doi.org/10.1371/journal.pone.0102799)

用 pdfplumber 0.11.11 提取页内区域，对全部返回项检查边界框、坐标系、文档哈希及引文哈希。表格比较只归一化 Unicode、空白和全空分隔行，保留列序、行序、数字、符号及表头。6 张表的 219 个单元格与出版社逐格一致，位于第 6、7、8、10 页。7 个候选中，第 1 页装饰框为误检。单篇命中率不能外推到扫描论文或复杂跨页表格。

公式、图像区域和题注各有类型。该样本返回 7 个图像区域。图像区域与出版社的 6 幅图还缺内容级匹配。图表轴数值、图例、OCR、跨页表连接及公式语义都保留未核验状态。研究任务中用表格回答问题仍需要把布局位置接入字段绑定及发布核验。

复核命令为 `python -m tools.research_eval.v7_pdf <publisher.pdf> <publisher.xml> --output <result.json>`。脚本先验证论文的两份输入哈希，再调用产品页级提取入口。提交 `6e2a78f` 实现访问接口，`b4c6927` 加入出版社对照，`99bc99c` 升级解析器。[逐表页码与哈希](pdf-results.json)
