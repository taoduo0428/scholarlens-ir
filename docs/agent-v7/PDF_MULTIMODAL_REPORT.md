# PDF 版面核验

核验样本是 Pan 等人发表的 *Online Community Detection for Large Complex Networks*，出版社采用 CC BY 4.0。读取同篇论文的 PDF 和 JATS XML，共 12 页，6 张表、6 幅标注图。[出版社原文](https://doi.org/10.1371/journal.pone.0102799)

用 pdfplumber 0.11.11 提取页内区域，对全部返回项检查边界框、坐标系、文档哈希及引文哈希。表格比较只归一化 Unicode、空白和全空分隔行，保留列序、行序、数字、符号及表头。6 张表的 219 个单元格与出版社逐格一致，位于第 6、7、8、10 页。7 个候选中，第 1 页装饰框为误检。单篇命中率不能外推到扫描论文或复杂跨页表格。

公式、图像区域和题注各有类型。该样本返回 7 个图像区域。页级 API 现在按位置匹配编号题注。同页图像和题注须水平重叠、垂直相邻，并且能唯一配对。工作台展示题注原行和双方位置。该论文的 6 幅编号图分别位于第 3、4、5、6、9、10 页。各题注首行均包含对应 JATS 图标题。将 PDF 嵌入位图与出版社另行分发的 6 张大图解码为 RGB 后，6 组尺寸和逐像素 SHA-256 均一致。第 1 页的第七个图像区域保留为无题注区域。图表轴数值、图例、OCR、跨页表连接及公式语义都保留未核验状态。工作台可在限定论文范围内读取指定页，选择原表单元格。生成报告时，服务在当前账户和任务预算内重新读取单元格，并核对文档版本与引文哈希。报告和 Markdown 保留页、表、物理行列及坐标。

图像复核使用 `python -m tools.research_eval.v7_pdf_figures <PDF> <JATS XML> <图片目录> <新结果文件>`。图片目录使用 `publisher-g001.img` 至 `publisher-g006.img` 六个文件，来源为 PLOS 文章图页的 large 版本。逐图记录包含页码、区域、题注哈希、发布文件哈希和解码后的像素哈希。[逐图复核结果](figure-results.json) · [出版社图 1](https://journals.plos.org/plosone/article/figure/image?size=large&id=10.1371/journal.pone.0102799.g001)

真实样本复核选择第 6 页表 1 的物理第 3 行第 2 列，结果为 `23,133`。出版社 JATS 原表的行名为 `ca-CondMat`，列名为 `Number of nodes`。复核程序还从 SQLite 读回报告比对内容。命令为 `python -m tools.research_eval.v7_pdf_publication <publisher.pdf> <publisher.xml>`。这个结果覆盖指定单元格的引用；跨页表和自动推断仍待验证。

复核命令为 `python -m tools.research_eval.v7_pdf <publisher.pdf> <publisher.xml> --output <result.json>`。脚本先验证论文的两份输入哈希，再调用产品页级提取入口。提交 `6e2a78f` 实现访问接口，`b4c6927` 加入出版社对照，`99bc99c` 升级解析器。[逐表页码与哈希](pdf-results.json)
