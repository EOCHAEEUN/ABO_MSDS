import { API_MODE } from "./api.js";
import { FIELD_DEFS } from "./data.js";
import { count, effective, filteredDocuments } from "./model.js";
import { useWorkspace } from "./WorkspaceContext.jsx";
import { Badge, Button, FieldValue, Icon, Options, Progress } from "./ui.jsx";
import PreviewPanel from "./PreviewPanel.jsx";

function DocumentInfo({ doc }) {
  const data = effective(doc);
  const pairs = [["문서명", doc.file_name], ["제품명", data.product_name.value || "—"], ["공급자", data.supplier.company_name || "—"], ["제출번호", doc.submission_number || "—"], ["언어", doc.language], ["페이지", doc.page_count ? `${doc.page_count}쪽` : "—"], ["업로드 일시", doc.extracted_at], ["최근 수정일", doc.updated_at]];
  return <section className="panel info-panel"><div className="panel-toolbar"><h2>문서 정보</h2><Button action="open-review" className="link-button" data-id={doc.id}>검토하기 →</Button></div>
    <dl className="info-list">{pairs.map(([key, value]) => <div key={key}><dt>{key}</dt><dd>{value}</dd></div>)}
      <div><dt>상태</dt><dd><Badge doc={doc} /></dd></div>
      <div><dt>검토 진행</dt><dd className="info-progress"><b>{count(doc)} / 5</b><Progress doc={doc} /><b>{count(doc) * 20}%</b></dd></div>
      <div><dt>담당자</dt><dd>{doc.owner}</dd></div><div><dt>비고</dt><dd>{doc.local_upload ? "로컬 PDF · 새로고침 시 제거" : API_MODE ? "—" : "화면 확인용 예시 데이터"}</dd></div>
    </dl>
  </section>;
}

function DocumentSummary({ doc }) {
  return <section className="panel summary-panel"><div className="panel-toolbar"><h2>주요 정보 요약</h2><span className="summary-chip"><Icon name="sparkle" /> 추출 요약</span></div>
    <dl className="summary-list">{FIELD_DEFS.filter(field => field.key !== "product_name").map(field => <div key={field.key}><dt>{field.key === "ingredients" ? "CAS 번호" : field.label}</dt><dd><FieldValue doc={doc} field={field.key} /></dd></div>)}<div><dt>권고 용도</dt><dd>{effective(doc).recommended_use.value || "자료없음"}</dd></div></dl>
    <p className="summary-note">{API_MODE ? "구조화된 추출 결과를 표시합니다." : "예시 데이터 · 실제 모델 추론 결과가 아닙니다."}</p>
  </section>;
}

export default function DocumentsPage() {
  const { state, patch, update, selectDocument } = useWorkspace();
  const docs = filteredDocuments(state);
  const selected = docs.find(doc => doc.id === state.selectedId) || docs[0];
  const suppliers = [...new Set(state.documents.map(doc => effective(doc).supplier.company_name).filter(Boolean))];
  const filters = [
    ["supplier", "제조사 필터", suppliers, "제조사 전체"],
    ["language", "언어 필터", ["한국어", "영어", "미확인"], "언어 전체"],
    ["status", "상태 필터", ["확정", "검토 필요", "미확정", "추출 대기"], "상태 전체"],
    ["split", "데이터 분할 필터", [...new Set(state.documents.map(doc => doc.split).filter(Boolean))], "Split 전체"],
  ];
  const allChecked = Boolean(docs.length && docs.every(doc => state.checked.has(doc.id)));
  return <main id="main">
    <section className="list-heading"><div><h1>문서 목록</h1><p>등록된 MSDS 문서를 조회하고 관리할 수 있습니다.</p></div>
      <div className="list-filters">{filters.map(([key, label, values, placeholder]) => <select key={key} data-filter={key} aria-label={label} value={state.filters[key]} onChange={event => { const value = event.target.value; update(next => { next.filters[key] = value; next.page = 1; }); }}><Options values={values} placeholder={placeholder} /></select>)}
        <label className="search-input"><Icon name="search" /><input id="list-search" aria-label="문서 목록 검색" placeholder="문서명, 제품명, 공급자, CAS 번호 검색" value={state.query} onChange={event => patch({ query: event.target.value, page: 1 })} /></label>
        <Button action="upload" className="primary" disabled={state.busy}><Icon name="plus" /> 문서 업로드</Button>
      </div>
    </section>
    <div className="documents-content"><section className="panel documents-table-panel">
      <div className="panel-toolbar"><div className="panel-title"><h2>문서 목록</h2><span>총 {docs.length}건{state.checked.size ? ` · ${state.checked.size}건 선택` : ""}</span></div><div className="toolbar-actions">
        <Button action="refresh" disabled={state.busy}><Icon name="refresh" /> 새로고침</Button><Button action="download-list"><Icon name="download" /> 목록 다운로드 (CSV)</Button><Button action="columns">표시 항목 설정 <Icon name="chevron" /></Button>
      </div></div>
      <div className="table-scroll"><table className="document-table">
        <thead><tr><th className="checkbox-cell"><input type="checkbox" id="check-all" aria-label="검색 결과 전체 선택" checked={allChecked} disabled={!docs.length} ref={element => { if (element) element.indeterminate = !allChecked && docs.some(doc => state.checked.has(doc.id)); }} onChange={event => { const checked = event.target.checked; update(next => { docs.forEach(doc => checked ? next.checked.add(doc.id) : next.checked.delete(doc.id)); }); }} /></th>
          <th>No.</th><th>문서명</th><th>제품명</th><th>모델</th><th>공급자</th>{state.columns.submission && <th>제출번호</th>}{state.columns.language && <th>언어</th>}{state.columns.pages && <th>페이지</th>}<th>상태</th><th>검토 진행</th><th>최근 수정일</th>{state.columns.owner && <th>담당자</th>}
        </tr></thead>
        <tbody>{docs.map(doc => {
          const data = effective(doc);
          return <tr key={doc.id} data-document={doc.id} className={selected?.id === doc.id ? "selected" : ""} onClick={event => { if (!event.target.closest("input, button, a")) selectDocument(doc.id); }}>
            <td className="checkbox-cell"><input type="checkbox" data-select={doc.id} aria-label={`${doc.file_name} 선택`} checked={state.checked.has(doc.id)} onChange={event => { const checked = event.target.checked; update(next => { checked ? next.checked.add(doc.id) : next.checked.delete(doc.id); }); }} /></td>
            <td>{doc.number ?? "—"}</td><td><Button action="select-document" className="document-link" data-id={doc.id}><span className="tiny-document">{Array.from({ length: 6 }, (_, i) => <i key={i} />)}</span>{doc.file_name}</Button></td>
            <td title={data.product_name.value || ""}>{data.product_name.value || "추출 대기"}</td><td>{doc.model_name || "—"}</td><td>{data.supplier.company_name || "—"}</td>
            {state.columns.submission && <td>{doc.submission_number || "—"}</td>}{state.columns.language && <td>{doc.language}</td>}{state.columns.pages && <td className="numeric">{doc.page_count || "—"}</td>}
            <td className="center"><Badge doc={doc} /></td><td className="numeric"><b>{count(doc)}</b> / 5</td><td>{doc.updated_at?.split(" ")[0] || "—"}</td>{state.columns.owner && <td>{doc.owner}</td>}
          </tr>;
        })}</tbody>
      </table>{!docs.length && <div className="empty-state"><Icon name="search" /><h3>검색 조건에 맞는 문서가 없습니다.</h3><Button action="reset-filters">검색 조건 초기화</Button></div>}</div>
    </section>
    {selected && <div className="document-detail-grid"><PreviewPanel doc={selected} compact /><DocumentInfo doc={selected} /><DocumentSummary doc={selected} /></div>}
    </div>
  </main>;
}
