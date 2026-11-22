# PDF 中的公式与正文引用

论文布局接口在 `formula_evidence` 中返回本页可辨认的单行编号等式、正文显式引用和紧邻等式的变量定义。输入是已获准读取的 PDF 版本和页码。每条转录保留源行位置、字符区间及哈希。正文提到的编号可以来自另一页，此时只呈现原文提及。维护者以独立 PDF 样本核对编号匹配、变量名和拒绝歧义的情况，并与出版社正文对照。

当前范围为 PDF 自带的文字层。扫描公式、损坏字体映射和跨行分式需要其他解析证据。源文件没有提供的 LaTeX 和推导保持为空。

## 2026-11-22 出版社原文核验

PLOS ONE 论文 *Online Community Detection for Complex Networks* 第 8 页的 Results 段落分别提到时间模块度和期望模块度。出版社 JATS 正文保留这两个编号的字面引用，公式本体以图片提供。[出版社论文](https://doi.org/10.1371/journal.pone.0102799)

| PDF 正文提及 | 出版社段落中的术语 | 研究工具返回的行内字符区间 | PDFium 独立读出的页内字符区间 | JATS 公式图 ID |
| --- | --- | --- | --- | --- |
| Eq.(4) | temporal modularity | [77, 83) | [2678, 2684) | pone.0102799.e084 |
| Eq.(6) | expected modularity | [94, 100) | [2732, 2738) | pone.0102799.e109 |

验收从固定哈希的 PDF 和 XML 重跑。两处行内切片都能还原原文，两份切片哈希和原行哈希均吻合。PDFium 独立定位的六个字符都在相应源行的包围框内。第 4、5 页的两个复杂陈列公式在产品中的表达式均为缺失，已验证的完整转录为 0/2。第 8 页正文引用保留原行位置。[逐条核验记录](formula-source-results.json)

Chrome 157 的本地独立会话使用真实账号、工作台生产构建及正常 PDF 布局路由，用一条隔离目录记录定位该论文。打开第 8 页后，浏览器显示两个式号，展开后均能看到与核验记录相符的源行位置。改读第 499 页时接口返回 422，界面清除了两条旧引用，页面脚本错误为 0。[浏览器记录](formula-browser-results.json)

以下命令从仓库根目录执行。使用已安装项目 PDF 依赖的 Python，把 `$Pdf`、`$Xml` 指向已获准读取的两份出版社原件。浏览器复跑需要启用研究功能且连接同源 API 的前端构建、安装 Playwright 的 Python，以及本机 Chrome。

```powershell
python -m tools.research_eval.v7_formula $Pdf $Xml --output output/formula-check.json
python -m tools.research_eval.v7_formula_browser $Pdf $Dist output/formula-check.json --browser-python $BrowserPython --chrome $Chrome --output output/formula-browser-check.json
```
