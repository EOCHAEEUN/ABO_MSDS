import { useState } from "react";
import { FIELD_DEFS, NO_OWNER, TEAM } from "./data.js";
import { count, effective, filteredDocuments } from "./model.js";
import { useWorkspace } from "./WorkspaceContext.jsx";
import { Badge, Button, FieldValue, Icon, Options } from "./ui.jsx";

const OPTIONAL_COLUMN_WIDTH = { submission: 130, language: 80, pages: 72, owner: 118 };

function OwnerSelect({ doc, className = "" }) {
  const { setOwner } = useWorkspace();
  const value = doc.owner || NO_OWNER;
  const options = [NO_OWNER, ...TEAM, ...(TEAM.includes(value) || value === NO_OWNER ? [] : [value])];
  return <select className={"owner-select " + className} aria-label={doc.file_name + " 담당자"} value={value} disabled={Boolean(doc.local_upload)}
    onClick={event => event.stopPropagation()} onChange={event => setOwner(doc.id, event.target.value)}>
    {options.map(name => <option key={name} value={name}>{name}</option>)}
  </select>;
}

function DocumentDetail({ doc, onClose }) {
  const data = effective(doc);
  return <aside className="document-list-detail panel" aria-label="선택한 문서 정보">
    <div className="document-list-detail-heading"><div><span>선택한 문서</span><h2>문서 정보</h2></div><button type="button" className="icon-button" aria-label="문서 정보 닫기" onClick={onClose}><Icon name="close" /></button></div>
    <div className="document-list-detail-body">
      <strong className="document-list-detail-name">{doc.file_name}</strong>
      <p className="document-list-detail-product">{data.product_name.value || "제품명 미확인"}</p>
      <dl>
        <div><dt>공급자</dt><dd>{data.supplier.company_name || "—"}</dd></div>
        <div><dt>상태</dt><dd><Badge doc={doc} /></dd></div>
        <div><dt>검토 진행</dt><dd>{count(doc)} / 5</dd></div>
        <div><dt>최근 수정</dt><dd>{doc.updated_at || "—"}</dd></div>
        <div><dt>담당자</dt><dd><OwnerSelect doc={doc} /></dd></div>
      </dl>
      <section className="document-list-summary" aria-labelledby="document-list-summary-title">
        <h3 id="document-list-summary-title">주요 정보 요약</h3>
        <dl>{FIELD_DEFS.filter(field => field.key !== "product_name").map(field => <div key={field.key}><dt>{field.key === "ingredients" ? "CAS 번호" : field.label}</dt><dd><FieldValue doc={doc} field={field.key} /></dd></div>)}<div><dt>권고 용도</dt><dd>{data.recommended_use.value || "자료없음"}</dd></div></dl>
      </section>
    </div>
    <div className="document-list-detail-footer"><Button action="open-review" data-id={doc.id} className="primary">검토하기 <Icon name="right" /></Button></div>
  </aside>;
}

export default function DocumentsPage() {
  const { state, patch, update, selectDocument } = useWorkspace();
  const [detailOpen, setDetailOpen] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
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
  const activeFilterCount = Object.values(state.filters).filter(Boolean).length;
  // 선택 열 너비(px). 표는 table-layout: fixed라 이름 32% · 공급자 23%가 먼저 자리를 잡고, 나머지 45%에
  // 고정 열(체크 42 + 상태 105 + 검토 진행 105 + 최근 수정 120 = 372)과 선택 열이 들어가야 잘리지 않는다.
  const extraWidth = Object.entries(OPTIONAL_COLUMN_WIDTH).reduce((sum, [key, width]) => sum + (state.columns[key] ? width : 0), 0);
  const tableMinWidth = extraWidth ? Math.ceil((372 + extraWidth) / 0.45) : 710;
  function openDetail(id) {
    selectDocument(id);
    setDetailOpen(true);
  }
  return <main id="main" className={"documents-page" + (filtersOpen ? " filters-expanded" : "")}>
    <header className="list-heading workspace-page-header"><div className="workspace-page-heading"><span className="workspace-page-eyebrow">등록 문서</span><h1 className="workspace-page-title">문서 목록</h1><p className="workspace-page-support">문서를 찾고 검토 상태를 확인하세요.</p></div>
      <div className="list-filters workspace-page-actions"><button type="button" className="filter-toggle" aria-expanded={filtersOpen} aria-controls="list-filter-panel" onClick={() => setFiltersOpen(!filtersOpen)}>필터{activeFilterCount ? " " + activeFilterCount : ""} <Icon name="chevron" /></button>
        <label className="search-input"><Icon name="search" /><input id="list-search" aria-label="문서 목록 검색" placeholder="문서명, 제품명, 공급자, CAS 번호 검색" value={state.query} onChange={event => patch({ query: event.target.value, page: 1 })} /></label>
        <Button action="upload" className="primary" disabled={state.busy}><Icon name="plus" /> 문서 업로드</Button>
      </div>
    </header>
    <div id="list-filter-panel" className="list-filter-panel" hidden={!filtersOpen}>{filters.map(([key, label, values, placeholder]) => <select key={key} data-filter={key} aria-label={label} value={state.filters[key]} onChange={event => { const value = event.target.value; update(next => { next.filters[key] = value; next.page = 1; }); }}><Options values={values} placeholder={placeholder} /></select>)}<button type="button" onClick={() => update(next => { next.filters = { supplier: "", language: "", status: "", split: "" }; next.page = 1; })}>필터 초기화</button></div>
    <div className={"documents-content" + (detailOpen && selected ? " has-detail" : "")}><section className="panel documents-table-panel">
      <div className="panel-toolbar"><div className="panel-title"><h2>문서 목록</h2><span>총 {docs.length}건{state.checked.size ? " · " + state.checked.size + "건 선택" : ""}</span></div><div className="toolbar-actions">
        <Button action="refresh" disabled={state.busy}><Icon name="refresh" /> 새로고침</Button><Button action="download-list"><Icon name="download" /> CSV 다운로드</Button><Button action="columns">열 설정 <Icon name="chevron" /></Button>
      </div></div>
      <div className="table-scroll" role="region" aria-label="문서 목록 표" tabIndex={0}><table className="document-table" style={{ minWidth: tableMinWidth }}>
        <thead><tr><th className="checkbox-cell"><input type="checkbox" id="check-all" aria-label="검색 결과 전체 선택" checked={allChecked} disabled={!docs.length} ref={element => { if (element) element.indeterminate = !allChecked && docs.some(doc => state.checked.has(doc.id)); }} onChange={event => { const checked = event.target.checked; update(next => { docs.forEach(doc => checked ? next.checked.add(doc.id) : next.checked.delete(doc.id)); }); }} /></th>
          <th>문서 / 제품명</th><th>공급자</th><th>상태</th><th>검토 진행</th><th>최근 수정</th>{state.columns.submission && <th className="col-submission">제출번호</th>}{state.columns.language && <th className="col-language">언어</th>}{state.columns.pages && <th className="col-pages">페이지</th>}{state.columns.owner && <th className="col-owner">담당자</th>}
        </tr></thead>
        <tbody>{docs.map(doc => {
          const data = effective(doc);
          return <tr key={doc.id} data-document={doc.id} className={detailOpen && selected?.id === doc.id ? "selected" : ""} tabIndex={0} aria-selected={detailOpen && selected?.id === doc.id} onClick={event => { if (!event.target.closest("input, button, a, select")) openDetail(doc.id); }} onKeyDown={event => { if (event.target === event.currentTarget && (event.key === "Enter" || event.key === " ")) { event.preventDefault(); openDetail(doc.id); } }}>
            <td className="checkbox-cell"><input type="checkbox" data-select={doc.id} aria-label={doc.file_name + " 선택"} checked={state.checked.has(doc.id)} onChange={event => { const checked = event.target.checked; update(next => { checked ? next.checked.add(doc.id) : next.checked.delete(doc.id); }); }} /></td>
            <td className="document-primary-cell"><button type="button" className="document-link" onClick={() => openDetail(doc.id)}>{doc.file_name}</button><span>{data.product_name.value || "제품명 미확인"}</span></td>
            <td title={data.supplier.company_name || ""}>{data.supplier.company_name || "—"}</td>
            <td><Badge doc={doc} /></td><td className="document-progress-cell">{count(doc)} / 5</td><td>{doc.updated_at?.split(" ")[0] || "—"}</td>
            {state.columns.submission && <td className="col-submission">{doc.submission_number || "—"}</td>}{state.columns.language && <td className="col-language">{doc.language}</td>}{state.columns.pages && <td className="numeric col-pages">{doc.page_count || "—"}</td>}{state.columns.owner && <td className="col-owner owner-cell"><OwnerSelect doc={doc} /></td>}
          </tr>;
        })}</tbody>
      </table>{!docs.length && <div className="empty-state"><Icon name="search" /><h3>검색 조건에 맞는 문서가 없습니다.</h3><Button action="reset-filters">검색 조건 초기화</Button></div>}</div>
    </section>
    {detailOpen && selected && <DocumentDetail doc={selected} onClose={() => setDetailOpen(false)} />}
    </div>
  </main>;
}
