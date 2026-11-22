# 彩色图例读取

## 接口契约

工作台读取已授权论文页面时，后端可返回 `figure_legends`。需在服务环境的 `SCHOLARLENS_TESSERACT` 设置 Tesseract 可执行文件的绝对路径，并安装 PDF 版面依赖。输入为带唯一题注的内嵌 RGB 位图。算法从图像中定位纵向排列的实心色块，使用右侧文字识别图例名称。每项保留色块颜色、图号、原 PDF 哈希、页码、图像 RGB 哈希、标签文字哈希、图内像素位置和 PDF 坐标。

验收覆盖两幅出版社原图、未支持的线型图、相同颜色的独立条块、缺失文字、错误文字位置和依赖未配置。识别结果供工作台复核，置信度来自 OCR 引擎。图例与具体数据点的映射另行核验。负责人为 ScholarLens 后端维护者。

## 出版社原图验证

测试读取同一篇开放论文的 6 幅图。页号按 PDF 文件从 1 起算。图号、页码、原图 SHA-256 和题注定位以出版社版本为准。图 4 至 6 的文字参考来自既有的 AI 看图转录，坐标参考来自此前在选定图例区域运行的 OCR。此次产品从完整位图自行定位色块。[论文原文](https://doi.org/10.1371/journal.pone.0102799) · [图像与题注记录](figure-results.json) · [参考转录与 OCR 词框](legend-ocr-results.json)

| 图与页码 | 产品输出 | 核对结果 |
| --- | --- | --- |
| 图 1–3，第 3–5 页 | 各 0 行 | 图 1 有其他样式的图例。这三幅图没有逐词转录参考。 |
| 图 4，第 6 页 | 0 行 | 线型图例的两个参考标签为 OLEM、OLTM，此版尚未识别。 |
| 图 5，第 9 页 | 6 行 | New、Split、Join、Move、Keep、Dense，按出版社图中的顺序逐项匹配。 |
| 图 6，第 10 页 | 6 行 | 同上六项，文字框按本图单独核验。 |

在两幅受支持的色块图上恢复了 12/12 项。在有参考转录的三幅图上恢复了 12/14 项，多余标签为 0。逐项核对了文字 SHA-256、色块中心像素、图例与题注的对应关系、原图 RGB SHA-256，以及从像素框换算出的 PDF 页内坐标。Tesseract v5.4.0.20240606 使用英文模型。对六幅源图的独立复算用时 13.094 秒。[机器记录](figure-legend-semantics-results.json)

另对图 5、图 6 分别做了两种变换。只将文字框涂白，两幅图均仍有 6 个可定位色块，输出标签均为 0。将原图中的色块与文字一起平移到同尺寸白色画布，两幅图均恢复全部 6 行，框相对预期移动位置的最大误差为 1 像素。这些变换复用同两幅原图。

## 工作台与回归

本地 Chrome 157 通过正式路由 `GET /api/papers/figure-eval-paper/pdf/layout/{page}` 访问授权 PDF，测试目录提供一条论文元数据。第 9、10 页各显示 6 行，可逐行核对文字、色值、页内坐标与原图哈希。切换到第 6 页时显示“本页未识别出可核对的彩色图例”。访问文件中不存在的第 499 页，接口返回 HTTP 422，工作台显示“无法在本页定位可读证据”。两次切页的旧图例行均已清除。此次浏览器运行有 0 个页面脚本错误，0 个 HTTP 5xx。后端 29 项专项与回归测试通过，前端类型检查和 API 模式生产构建通过。[浏览器记录](figure-legend-browser-results.json)

在仓库根目录运行以下命令。先安装项目锁定的 PDF、图像和测试依赖，设置 `SCHOLARLENS_TESSERACT` 为含英文模型的 Tesseract 可执行文件绝对路径。使用此前核对过的同版 PDF 和六张出版社位图。输出路径应为新文件。

```powershell
python -m pytest -q backend/tests/research/test_figure_legend.py backend/tests/research/test_pdf_layout.py backend/tests/research/test_figure_captions.py backend/tests/research/test_table_continuation.py
python -m tools.research_eval.v7_figure_legend_semantics output/v7/licensed-pdf/journal.pone.0102799.pdf output/v7/figure-verification-01 --tesseract $env:SCHOLARLENS_TESSERACT --output output/v7/recheck-legend.json
$env:VITE_DATA_SOURCE = 'api'
$env:VITE_API_BASE_URL = '/api'
$env:VITE_RESEARCH_ENABLED = 'true'
npm --prefix frontend run build -- --outDir ../output/v7/legend-ui-dist
python -m tools.research_eval.v7_figure_legend_browser output/v7/licensed-pdf/journal.pone.0102799.pdf output/v7/legend-ui-dist --tesseract $env:SCHOLARLENS_TESSERACT --output output/v7/recheck-legend-ui.json
```

浏览器复算需要可用的 Node.js Playwright 及 Chromium。也可通过 `SCHOLARLENS_PLAYWRIGHT` 与 `SCHOLARLENS_CHROME` 分别指定已安装的 Playwright 模块和浏览器可执行文件。测试使用随机回环端口和临时账号库。线上 OCR 是否启用取决于服务上的 Tesseract 配置。
