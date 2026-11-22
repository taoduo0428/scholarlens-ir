import {useState} from "react";
import {jaegerMountPath, validTraceIds} from "../services/traceViewer";

const base = jaegerMountPath(import.meta.env.VITE_JAEGER_UI_PATH);

function TraceRow({id}: {id: string}) {
  const [feedback, setFeedback] = useState("");
  async function copy() {
    try {
      await navigator.clipboard.writeText(id);
      setFeedback("已复制追踪 ID");
    } catch {
      setFeedback("请选中上方追踪 ID，手动复制。");
    }
  }
  return <li>
    <code>{id}</code>{" "}
    <button type="button" onClick={copy}>复制追踪 ID</button>{" "}
    {base && <a href={`${base}/trace/${id}`} target="_blank" rel="noopener noreferrer"
      referrerPolicy="no-referrer">在 Jaeger 查看</a>}
    {feedback && <p role="status">{feedback}</p>}
  </li>;
}

export function TaskTraceViewer({taskId, traces}: {taskId: string; traces: string[]}) {
  const ids = validTraceIds(traces);
  return <details>
    <summary>任务追踪</summary>
    <p>任务 ID {taskId}</p>
    {ids.length ? <>
      <ul>{ids.map(id => <TraceRow id={id} key={id}/>)}</ul>
      <p>{base ? "查看链路需要 Jaeger 网关授权。" : "当前环境未配置 Jaeger 查看地址。"}</p>
    </> : <p>运行环境尚无追踪记录</p>}
  </details>;
}
