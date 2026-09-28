import { Fragment } from "react";
import { API_MODE, source } from "./api.js";
import { METRICS } from "./data.js";
import { useWorkspace } from "./WorkspaceContext.jsx";
import { Button, DocumentHeader, Icon } from "./ui.jsx";

// 명세의 기본 지표 + 값이 모든 실험에 있을 때만 쓰는 추가 지표(GHS F1 · 문서 완전 정답)
function availableMetrics(experiments) {
  return METRICS.filter(metric => !metric.optional || (experiments.length && experiments.every(item => Number.isFinite(item[metric.key]))));
}

function MetricCards() {
  const { state } = useWorkspace();
  const selected = state.experiments.find(item => item.id === state.selectedExperiment) || state.experiments.at(-1);
  const base = state.experiments[0];
  if (!selected || !base) return null;
  const average = row => (row.cas + row.pair + row.hcode) / 3;
  const cards = [
    ["document", "JSON 파싱률", selected.parsing, "%", selected.parsing - base.parsing, "유효한 JSON 형태로 파싱된 비율"],
    ["checklist", "스키마 준수율", selected.schema, "%", selected.schema - base.schema, "사전 정의된 스키마를 준수한 비율"],
    ["target", "필드 정확도 (평균 F1)", average(selected), "%", average(selected) - average(base), "CAS · pair · H-code F1의 평균"],
    ["clock", "평균 생성 시간", selected.seconds, "초", base.seconds ? (selected.seconds / base.seconds - 1) * 100 : 0, "문서 1건당 평균 생성 시간"],
  ];
  return <div className="metric-cards">{cards.map(([symbol, title, value, unit, delta, description]) => <section className="panel metric-card" key={symbol}><div className="metric-icon"><Icon name={symbol} /></div><div><h2>{title}</h2><div className="metric-value">{Number(value).toFixed(1)}{unit}<span className={`metric-change ${(symbol === "clock" ? delta <= 0 : delta >= 0) ? "positive" : "negative"}`}>{delta >= 0 ? "▲ +" : "▼ "}{delta.toFixed(1)}{symbol === "clock" ? "%" : "p"}</span></div><p>{description}</p></div></section>)}</div>;
}

function BarChart() {
  const { state } = useWorkspace();
  const metric = METRICS.find(item => item.key === state.metric);
  const max = metric.key === "seconds" ? Math.max(5, Math.ceil(Math.max(...state.experiments.map(item => item.seconds)) / 5) * 5) : 100;
  return <div className="bar-chart" role="img" aria-label={`${metric.label} 실험별 비교. 수치는 옆 비교표에서 확인할 수 있습니다.`}>
    <div className="bar-grid">{state.experiments.map((item, i) => <div className="bar-row" key={item.id}><span className={`bar-label ${item.id === state.selectedExperiment ? "selected" : ""}`}>{item.short || item.name}{item.id === state.selectedExperiment ? " (선택)" : ""}</span><div className="bar-track"><div className={`bar-fill bar-${i % 4}`} style={{ width: `${Math.max(0, Math.min(100, item[metric.key] / max * 100))}%` }}><span>{Number(item[metric.key]).toFixed(1)}{metric.unit}</span></div></div></div>)}
      <div className="chart-axis"><span /><div>{Array.from({ length: 6 }, (_, i) => <span key={i}>{(max * i / 5).toFixed(0)}</span>)}</div></div>
    </div><div className="axis-caption">{metric.label} ({metric.unit})</div>
  </div>;
}

function LineChart() {
  const { state } = useWorkspace();
  const metric = METRICS.find(item => item.key === state.trend);
  const data = state.experiments;
  const point = (value, index) => [76 + index * 630 / Math.max(1, data.length - 1), 156 - value * 1.35];
  return <svg className="line-chart" viewBox="0 0 780 205" role="img" aria-label={`${metric.label} 추이. ${data.map(item => `${item.name} ${item[state.trend]}%`).join(", ")}`}>
    {Array.from({ length: 6 }, (_, i) => { const y = 156 - i * 27; return <Fragment key={i}><line x1="48" y1={y} x2="750" y2={y} className="grid-line" /><text x="32" y={y + 4} textAnchor="end">{i * 20}</text></Fragment>; })}
    <path d="M48 21V156H750" className="axis-line" /><polyline points={data.map((item, i) => point(item[state.trend], i).join(",")).join(" ")} className="trend-line" />
    {data.map((item, i) => { const [x, y] = point(item[state.trend], i); return <Fragment key={item.id}><circle cx={x} cy={y} r="3.8" /><text x={x} y={y - 9} textAnchor="middle" className="point-label">{item[state.trend]}</text><text x={x} y="184" textAnchor="middle">{item.short || item.name}</text></Fragment>; })}
  </svg>;
}

export default function ComparePage({ doc }) {
  const { state, patch } = useWorkspace();
  const selected = state.experiments.find(item => item.id === state.selectedExperiment);
  const isDemo = !API_MODE && state.compareSplit === "예시";
  const metrics = availableMetrics(state.experiments);
  const extraCols = metrics.filter(metric => metric.optional);
  const cols = ["parsing", "schema", "cas", "pair", "hcode", ...extraCols.map(metric => metric.key), "seconds", "tokens"];
  return <><DocumentHeader doc={doc} /><main id="main" className="comparison-content">
    <section className="comparison-heading"><div><h1>모델 비교 결과</h1><p>Base Zero-shot, Base Few-shot(k=2), QLoRA 모델의 추출 성능을 비교합니다.</p></div><div><span className="comparison-date">{isDemo ? "예시 실행일" : "평가 실행일"} &nbsp;{state.compareAt || "—"}</span><Button action="compare-options" disabled={state.busy}><Icon name="refresh" /> {state.busy ? "비교 중…" : "다른 실험 비교하기"}</Button></div></section>
    <div className="comparison-notice">{isDemo ? "예시 데이터 · 아래 수치는 첨부 화면을 재현한 값이며 실제 평가 결과가 아닙니다." : `평가셋: ${state.compareSplit} · ${state.compareSubset}${state.experiments[0]?.n_docs ? ` (${state.experiments[0].n_docs}건)` : ""} · 평가셋별 결과를 분리하여 표시합니다.${source.note ? ` ${source.note}` : ""}`}</div>
    {!state.experiments.length ? <section className="panel empty-state"><h2>{state.busy ? "실험 결과를 불러오는 중입니다." : "표시할 실험 결과가 없습니다."}</h2><Button action="load-compare" disabled={state.busy}>실험 결과 불러오기</Button></section> : <>
      <MetricCards />
      <div className="comparison-top-grid">
        <section className="panel experiment-panel"><h2>실험별 비교 결과</h2><div className="table-scroll"><table className="experiment-table">
          <thead><tr><th>실험명</th><th>조건</th><th>파싱률<br />(%)</th><th>스키마<br />(%)</th><th>CAS F1<br />(%)</th><th>pair F1<br />(%)</th><th>H-code F1<br />(%)</th>{extraCols.map(metric => <th key={metric.key}>{metric.label}<br />(%)</th>)}<th>생성 시간<br />(초)</th><th>출력 토큰<br />(개)</th></tr></thead>
          <tbody>{state.experiments.map(item => <tr key={item.id} className={item.id === state.selectedExperiment ? "selected" : ""}><th><Button action="select-experiment" className="experiment-button" data-id={item.id}>{item.name} {item.id === state.selectedExperiment && <span className="selected-chip">선택</span>}</Button></th><td>{item.condition}</td>{cols.map(key => <td key={key}>{item[key]}</td>)}</tr>)}</tbody>
        </table></div></section>
        <section className="panel bar-panel"><div className="chart-toolbar"><h2>주요 지표 비교</h2><label>지표 선택 <select id="chart-metric" aria-label="막대그래프 지표" value={state.metric} onChange={event => patch({ metric: event.target.value })}>{metrics.map(metric => <option key={metric.key} value={metric.key}>{metric.label} ({metric.unit})</option>)}</select></label></div><BarChart /></section>
      </div>
      <div className="comparison-bottom-grid">
        <section className="panel trend-panel"><div className="trend-heading"><h2>주요 지표 추이</h2><div className="tabs" role="tablist" aria-label="추이 지표">{metrics.filter(metric => metric.key !== "seconds").map(metric => <Button action="trend" data-metric={metric.key} key={metric.key} className={`tab ${metric.key === state.trend ? "active" : ""}`} role="tab" aria-selected={metric.key === state.trend}>{metric.label}</Button>)}</div></div><LineChart /></section>
        <section className="panel conclusion-panel"><h2>결론 및 검토 의견</h2><div className="conclusion-box"><div className="conclusion-icon"><Icon name="check" /></div><div><h3>{selected?.name || ""} 모델의 결과를 검토합니다.</h3><p>{selected?.id === "qlora_r2" && isDemo ? "예시 비교에서 파싱률과 스키마 준수율이 모두 95% 이상입니다." : "선택한 실험의 형식 준수율, 필드 정확도와 생성 시간을 함께 확인하세요."}<br />최종 모델 선정은 실제 Validation 결과와 프로젝트 판정 기준에 따라 진행합니다.</p></div></div>
          <div className="conclusion-bottom"><div><b>추가 검토 사항</b><ul><li>H-code 항목의 원문 근거와 오탐을 추가 확인하세요.</li><li>평가셋별 수치를 합산하지 않고 분리해 검토하세요.</li><li>{isDemo ? "예시 모델 선택은 실제 서버 모델을 변경하지 않습니다." : "val은 조건 선택용입니다. 최종 판정은 test 평가로 합니다."}</li></ul></div><Button action="go-review" className="blue-outline"><Icon name="document" /> 문서 검토하기</Button></div>
        </section>
      </div>
    </>}
  </main></>;
}
