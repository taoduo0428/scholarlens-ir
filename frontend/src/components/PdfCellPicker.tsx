import {useEffect, useRef, useState} from "react";
import {backend} from "../services/backend";
import type {PdfCellRequest} from "../services/research";

interface PageLayout {
  paper_id:string;
  page:number;
  source_version:string;
  items:{kind:string;table_id:number;row:number;column:number;quote:string}[];
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
      setLayout({...result,items:cells}); setMessage(cells.length?"":"本页没有可定位的表格单元格。");
    } catch(error) {
      if(!controller.signal.aborted) setMessage(error instanceof Error ? error.message : "此页暂不可读。");
    }
  }
  const cell=selection!=="" ? layout?.items[Number(selection)] : null;
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
      {layout && layout.items.length>0 && <label>引用单元格<select value={selection} onChange={e=>setSelection(e.target.value)}>
        <option value="">不引用</option>
        {layout.items.map((item,index)=><option key={index} value={index}>
          表 {item.table_id} · 行 {item.row} · 列 {item.column} · {item.quote.slice(0,100)}
        </option>)}</select></label>}
      {target && <input type="hidden" name="pdf_cell" value={JSON.stringify(target)}/>}
    </>}
  </details>;
}
