import {useEffect, useRef, useState} from "react";
import {BackendError} from "../services/backend";
import {research} from "../services/research";

type Props = {
  taskId: string;
  revision: number;
  terminal: boolean;
  onDeleted: () => void;
  onConflict: () => void;
};

export function TaskDataActions({taskId, revision, terminal, onDeleted, onConflict}: Props) {
  const [confirmAt, setConfirmAt] = useState<number | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const current = useRef<AbortController | null>(null);
  useEffect(() => () => current.current?.abort(), []);

  async function act(kind: "export" | "erase") {
    if (current.current || (kind === "erase" && confirmAt === null)) return;
    const ctl = new AbortController();
    current.current = ctl;
    setBusy(true);
    setError("");
    try {
      if (kind === "export") {
        const blob = await research.exportZip(taskId, ctl.signal);
        if (ctl.signal.aborted) return;
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = "research-" + taskId + ".zip";
        document.body.append(link);
        link.click();
        link.remove();
        window.setTimeout(() => URL.revokeObjectURL(url), 1000);
      } else if (confirmAt !== null) {
        await research.erase(taskId, confirmAt, ctl.signal);
        if (!ctl.signal.aborted) onDeleted();
      }
    } catch (cause) {
      if (ctl.signal.aborted) return;
      setError(cause instanceof Error ? cause.message : "操作失败，请重试。");
      if (kind === "erase") {
        setConfirmAt(null);
        if (cause instanceof BackendError && cause.status === 409) onConflict();
      }
    } finally {
      current.current = null;
      if (!ctl.signal.aborted) setBusy(false);
    }
  }

  return <div>
    <div className="research-buttons">
      <button type="button" className="button button-secondary" disabled={busy}
        onClick={() => void act("export")}>导出任务 ZIP</button>
      {terminal && confirmAt === null && <button type="button" className="button button-secondary" disabled={busy}
        onClick={() => {setError(""); setConfirmAt(revision);}}>删除任务</button>}
    </div>
    {confirmAt !== null && <div role="group" aria-label="确认删除研究任务">
      <p>删除后，本任务的证据、报告和项目记忆将从工作台移除。需要保留时请先导出。</p>
      <div className="research-buttons">
        <button type="button" className="button button-secondary" disabled={busy}
          onClick={() => setConfirmAt(null)}>保留任务</button>
        <button type="button" className="button button-secondary" disabled={busy}
          onClick={() => void act("erase")}>确认永久删除</button>
      </div>
    </div>}
    {error && <p role="alert">{error}</p>}
  </div>;
}
