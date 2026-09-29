import { useEffect, useState } from "react";
import { api } from "./api.js";
import { Icon } from "./ui.jsx";
import "./data-page.css";

const PAGE_SIZE = 25;
const LABELS = {
  msds_documents: "문서",
  msds_ingredients: "구성성분",
  msds_classifications: "GHS 분류",
  msds_hazard_statements: "유해·위험 문구",
  msds_reviews: "검토 기록",
};

function cellValue(value) {
  if (value == null) return <span className="db-null">NULL</span>;
  if (typeof value === "number") return value.toLocaleString();
  return String(value);
}

function detailValue(value) {
  if (value == null) return "NULL";
  if (typeof value !== "string") return String(value);
  try { return JSON.stringify(JSON.parse(value), null, 2); } catch { return value; }
}

export default function DataPage() {
  const [table, setTable] = useState("msds_documents");
  const [offset, setOffset] = useState(0);
  const [reload, setReload] = useState(0);
  const [result, setResult] = useState(null);
  const [selected, setSelected] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError("");
    api.database(table, offset, PAGE_SIZE).then(data => {
      if (!active) return;
      if (!Array.isArray(data.tables) || !Array.isArray(data.columns) || !Array.isArray(data.rows)) {
        throw new Error("데이터 응답 형식이 올바르지 않습니다.");
      }
      setResult(data);
      setSelected(data.rows[0] || null);
    }).catch(issue => {
      if (active) { setResult(null); setSelected(null); setError(issue.message); }
    }).finally(() => { if (active) setLoading(false); });
    return () => { active = false; };
  }, [table, offset, reload]);

  const tables = result?.tables || Object.keys(LABELS).map(name => ({ name, count: null }));
  const totalRows = result?.tables.reduce((total, item) => total + item.count, 0) ?? 0;
  const rangeStart = result?.total ? offset + 1 : 0;
  const rangeEnd = result ? Math.min(offset + PAGE_SIZE, result.total) : 0;
  const chooseTable = name => { setTable(name); setOffset(0); setSelected(null); };

  return <main id="main" className="db-page">
    <header className="db-heading workspace-page-header">
      <div className="db-heading-copy workspace-page-heading"><span className="db-eyebrow workspace-page-eyebrow">저장된 데이터</span><h1 className="workspace-page-title">데이터</h1><p className="workspace-page-support">문서 추출과 검토 결과가 DB에 적재된 상태를 확인합니다.</p></div>
      <div className="db-heading-actions workspace-page-actions"><span className="db-readonly">읽기 전용 · SQLite</span><button type="button" onClick={() => setReload(value => value + 1)} disabled={loading}><Icon name="refresh" /> 새로고침</button></div>
    </header>
    <div className="db-content">
    {error && <div className="db-error" role="alert"><strong>DB를 불러오지 못했습니다.</strong><span>{error}</span><span>API 서버를 실행한 뒤 새로고침해 주세요.</span></div>}
    <div className="db-stats" aria-label="적재 현황">
      <div><span className="db-stat-icon"><Icon name="document" /></span><div className="db-stat-copy"><span>문서</span><small>msds_documents</small></div><strong>{result?.tables.find(item => item.name === "msds_documents")?.count ?? "—"}</strong></div>
      <div><span className="db-stat-icon"><Icon name="database" /></span><div className="db-stat-copy"><span>연결된 데이터 행</span><small>성분 · 분류 · 문구 · 검토</small></div><strong>{result ? totalRows - (result.tables.find(item => item.name === "msds_documents")?.count || 0) : "—"}</strong></div>
      <div><span className="db-stat-icon"><Icon name="list" /></span><div className="db-stat-copy"><span>테이블</span><small>실제 DB 기준</small></div><strong>{result?.tables.length ?? "—"}</strong></div>
    </div>
    <div className="db-layout">
      <nav className="db-table-nav panel" aria-label="데이터 테이블">
        <div className="db-panel-heading"><span>테이블</span><b>{tables.length}</b></div>
        {tables.map(item => <button key={item.name} type="button" className={`db-table-choice ${table === item.name ? "active" : ""}`} aria-current={table === item.name ? "page" : undefined} onClick={() => chooseTable(item.name)}>
          <Icon name={item.name === "msds_documents" ? "document" : "database"} /><span><strong>{LABELS[item.name] || item.name}</strong><small>{item.name}</small></span><b>{item.count ?? "—"}</b>
        </button>)}
      </nav>
      <section className="db-results panel" aria-label={`${LABELS[table]} 행`}>
        <div className="db-results-heading"><div><span className="db-table-name">{table}</span><h2>{LABELS[table]}</h2><p>저장된 행을 최신 순으로 표시합니다.</p></div><span className="db-row-count">{result?.total ?? "—"} rows</span></div>
        {loading ? <div className="db-message" role="status">DB 행을 불러오는 중…</div> : !result ? <div className="db-message">표시할 데이터가 없습니다.</div> : !result.rows.length ? <div className="db-message">이 테이블에 저장된 행이 없습니다.</div> :
          <div className="db-table-scroll" role="region" aria-label={`${LABELS[table]} 데이터 표`} tabIndex={0}><table className="db-table"><thead><tr><th scope="col">보기</th>{result.columns.map(column => <th scope="col" key={column.name}><span>{column.name}</span><small>{column.type}</small></th>)}</tr></thead><tbody>{result.rows.map(row => <tr key={row.id} className={selected?.id === row.id ? "selected" : ""}><td><button type="button" className="db-view-row" aria-label={`${row.id}번 행 상세 보기`} onClick={() => setSelected(row)}>상세</button></td>{result.columns.map(column => <td key={column.name} title={row[column.name] == null ? "NULL" : String(row[column.name])}><span>{cellValue(row[column.name])}</span></td>)}</tr>)}</tbody></table></div>}
        <div className="db-pagination"><span>{rangeStart}–{rangeEnd} / {result?.total ?? 0}행</span><div><button type="button" onClick={() => setOffset(value => Math.max(0, value - PAGE_SIZE))} disabled={loading || offset === 0} aria-label="이전 행"><Icon name="left" /></button><button type="button" onClick={() => setOffset(value => value + PAGE_SIZE)} disabled={loading || !result || offset + PAGE_SIZE >= result.total} aria-label="다음 행"><Icon name="right" /></button></div></div>
      </section>
      <aside className="db-inspector panel" aria-label="선택한 행 상세">
        <div className="db-panel-heading"><span>행 상세</span>{selected && <b>#{selected.id}</b>}</div>
        {selected && result ? <dl>{result.columns.map(column => <div key={column.name}><dt>{column.name}<small>{column.type}</small></dt><dd><pre>{detailValue(selected[column.name])}</pre></dd></div>)}</dl> : <p className="db-inspector-empty">행을 선택하면 저장된 값을 볼 수 있습니다.</p>}
      </aside>
    </div>
    </div>
  </main>;
}
