import {useEffect, useRef, useState} from "react";
import {backend} from "../services/backend";
import type {PdfCellRequest} from "../services/research";

interface PageLayout {
  paper_id:string;
  page:number;
  source_version:string;
  items:{kind:string;table_id:number;row:number;column:number;quote:string;locator:string}[];
  table_continuations?:{number:number;headers:string[];previous:{page:number;table_locator:string};current:{page:number;table_locator:string}}[];
  figure_caption_links?:{number:number;figure_locator:string;caption_locator:string}[];
  figure_legends?:{number:number;figure_locator:string;rgb_sha256:string;entries:{
    text:string;color:string;confidence:number;label_pdf_bbox:number[];text_sha256:string;
  }[]}[];
  chart_reading_status?:string;
  formula_evidence?:{
    equations:{number:string;source:{locator:string;quote:string};definitions:{symbol:string;source:{locator:string;quote:string}}[]}[];
    mentions:{number:string;source:{locator:string;quote:string;start:number};equation_locator:string|null}[];
  };
  chart_readings?:{number:number;figure_locator:string;rgb_sha256:string;calibration_id:string;
    x_axis:{label:string;min:number;max:number;at:number};y_axis:{label:string;min:number;max:number};
    panels:{dataset:string;points:{series:string;estimate:number;interval:number[];pdf_bbox:number[]}[]}[];
  }[];
}

export function PdfCellPicker({papers}:{papers:string[]}) {
  const [paper,setPaper]=useState(papers[0] || "");
  const [page,setPage]=useState("1"), [selection,setSelection]=useState("");
  const [layout,setLayout]=useState<PageLayout|null>(null), [message,setMessage]=useState("");
  const request=useRef<AbortController|null>(null);
  useEffect(()=>()=>request.current?.abort(),[]);
  function clear() {
    request.current?.abort();
    setLayout(null); setSelection(""); setMessage("");
  }
  async function read() {
    clear();
    const controller=new AbortController();
    request.current=controller;
    setMessage("正在读取 PDF 页面…");
    try {
      const result=await backend<PageLayout>("/papers/"+encodeURIComponent(paper)+"/pdf/layout/"+Number(page),
        {signal:controller.signal});
      if(controller.signal.aborted) return;
      if(result.paper_id!==paper || result.page!==Number(page)) throw new Error("返回的论文或页码不匹配。");
      const cells=result.items.filter(item=>item.kind==="cell" && item.quote.trim());
      setLayout(result); setMessage(cells.length?"":"本页没有可定位的表格单元格。");
    } catch(error) {
      if(!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "此页暂不可读。");
    }
  }
  const cells=layout?.items.filter(item=>item.kind==="cell" && item.quote.trim()) ?? [];
  const cell=selection!=="" ? cells[Number(selection)] : null;
  const target:PdfCellRequest | null=layout && cell ? {
    paper_id:paper, source_version:layout.source_version, page:layout.page,
    table_id:cell.table_id, row:cell.row, column:cell.column
  } : null;
  return <details><summary>引用 PDF 表格单元格（可选）</summary>
    {!papers.length ? <p>先在论文范围中填入论文 ID。</p> : <>
      <label>表格所属论文<select value={paper} onChange={e=>{clear();setPaper(e.target.value);}}>
        {papers.map(id=><option key={id}>{id}</option>)}</select></label>
      <label>PDF 页码<input type="number" value={page} onChange={e=>{clear();setPage(e.target.value);}}/></label>
      <button className="button button-secondary" type="button" onClick={()=>void read()}
        disabled={!Number.isInteger(Number(page)) || Number(page)<1 || Number(page)>500}>读取本页表格</button>
      {message && <p role="status">{message}</p>}
      {layout && cells.length>0 && <label>引用单元格<select value={selection} onChange={e=>setSelection(e.target.value)}>
        <option value="">不引用</option>
        {cells.map((item,index)=><option key={index} value={index}>
          表 {item.table_id} · 行 {item.row} · 列 {item.column} · {item.quote.slice(0,100)}
        </option>)}</select></label>}
      {layout?.table_continuations?.map(link=><details key={link.current.table_locator}>
        <summary>表 {link.number} 续表 · 第 {link.previous.page}–{link.current.page} 页</summary>
        <p>表头 {link.headers.join(" · ")}</p>
        <p>上一页 <code>{link.previous.table_locator}</code></p>
        <p>本页 <code>{link.current.table_locator}</code></p>
      </details>)}
      {layout?.figure_caption_links?.map(link=><details key={link.figure_locator}>
        <summary>图 {link.number} · 第 {layout.page} 页题注</summary>
        <p>{layout.items.find(item=>item.locator===link.caption_locator)?.quote}</p>
        <p>图像位置 <code>{link.figure_locator}</code></p>
        <p>题注位置 <code>{link.caption_locator}</code></p>
      </details>)}
      {layout?.formula_evidence?.equations.map(eq=><details key={eq.source.locator}>
        <summary>公式 ({eq.number}) · 第 {layout.page} 页</summary>
        <p><code>{eq.source.quote}</code></p>
        <p>原文位置 <code>{eq.source.locator}</code></p>
        {eq.definitions.map(def=><p key={def.source.locator}>变量 {def.symbol} 的原文定义：{def.source.quote}</p>)}
      </details>)}
      {layout?.formula_evidence?.mentions.map(ref=><details key={ref.source.locator+"-"+ref.source.start}>
        <summary>第 {layout.page} 页正文引用 {ref.source.quote}</summary>
        <p>引用位置 <code>{ref.source.locator}</code></p>
        {ref.equation_locator && <p>本页公式位置 <code>{ref.equation_locator}</code></p>}
      </details>)}
      {target && <input type="hidden" name="pdf_cell" value={JSON.stringify(target)}/>}
      {layout && !!layout.figure_caption_links?.length && layout.figure_legends?.length === 0 &&
        <p>本页未识别出可核对的彩色图例。</p>}
      {layout?.chart_reading_status==="unregistered" && <p>此图未登记坐标轴校准，暂无折线读数。</p>}
      {layout?.chart_reading_status==="registry_unavailable" && <p>坐标轴校准文件不可用，暂无折线读数。</p>}
      {layout?.chart_reading_status==="raster_unavailable_or_mismatch" && <p>原图与校准信息未能核对，暂无折线读数。</p>}
      {layout?.chart_readings?.map(chart=><details key={chart.figure_locator+"-endpoints"}>
        <summary>图 {chart.number} · 折线终点读数</summary>
        <p>横轴 {chart.x_axis.label} 从 {chart.x_axis.min} 到 {chart.x_axis.max}，
          读数位置 {chart.x_axis.at}。纵轴 {chart.y_axis.label} 从 {chart.y_axis.min} 到 {chart.y_axis.max}。</p>
        <p>坐标轴校准 <code>{chart.calibration_id}</code></p>
        <p>原图 RGB SHA-256 <code>{chart.rgb_sha256}</code></p>
        {chart.panels.map(panel=><details key={panel.dataset}>
          <summary>{panel.dataset} · {panel.points.length ? "查看读数" : "终点不可分辨"}</summary>
          {panel.points.map(point=><p key={point.series}>
            {point.series} ≈ {point.estimate}（图像读数区间 {point.interval.join(" 至 ")}）<br/>
            第 {layout.page} 页位置 <code>{point.pdf_bbox.join(", ")}</code>
          </p>)}
        </details>)}
      </details>)}
      {layout?.figure_legends?.map(legend=><details key={legend.figure_locator}>
        <summary>图 {legend.number} · 图例文字（OCR）</summary>
        <p>原图 RGB SHA-256 <code>{legend.rgb_sha256}</code></p>
        <ul>{legend.entries.map(entry=><li key={entry.text_sha256}>
          <strong>{entry.text}</strong> · 色值 <code>{entry.color}</code>
          <p>第 {layout.page} 页位置 <code>{entry.label_pdf_bbox.join(", ")}</code></p>
        </li>)}</ul>
      </details>)}
    </>}
  </details>;
}
