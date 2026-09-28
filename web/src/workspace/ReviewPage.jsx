import { API_MODE } from "./api.js";
import { FIELD_DEFS } from "./data.js";
import { count, effective, unverifiedHazard } from "./model.js";
import { useWorkspace } from "./WorkspaceContext.jsx";
import { Button, FieldValue, Icon, Multiline, Progress } from "./ui.jsx";
import PreviewPanel from "./PreviewPanel.jsx";

const displayName = { ingredients: "CAS 번호", ghs_classification: "GHS 분류", hazard_statements: "유해 · 위험 문구" };
const fieldName = field => displayName[field.key] || field.label;

function ReviewDocumentHeader({ doc }) {
  const { state, patch, navigate } = useWorkspace();
  const values = effective(doc);
  const meta = [doc.file_name, values.supplier.company_name || "공급자 미기재", doc.revision_date || "개정일 미기재", doc.page_count ? `${doc.page_count}쪽` : "페이지 미확인", doc.language || "언어 미확인"];
  function search(event) {
    event.preventDefault();
    patch({ query: new FormData(event.currentTarget).get("query")?.trim() || "", page: 1 });
    navigate("documents");
  }
  return <header className="review-document-header">
    <div className="review-document-heading">
      <div className="review-title-row"><h1>{values.product_name.value || doc.file_name}</h1><span className="pdf-badge">PDF</span></div>
      <div className="review-document-meta">{meta.map((item, index) => <span key={index}>{index === 0 && <Icon name="document" />}{item}</span>)}</div>
    </div>
    <div className="review-header-tools">
      <form className="review-search" role="search" onSubmit={search}><Icon name="search" /><input name="query" type="search" defaultValue={state.query} aria-label="문서 검색" placeholder="문서명, 공급자, CAS 번호 검색" /></form>
      <div className="review-progress"><span>검토 완료율</span><Progress doc={doc} /><strong>{count(doc) * 20}%</strong></div>
    </div>
  </header>;
}

function MatchBadge({ rule, reviewed = false, warning = false }) {
  const status = warning ? "원문에서 확인되지 않음" : reviewed ? "담당자 확인" : rule?.review_status === "OK" ? "원문과 일치" : rule?.review_status ? "원문 확인 필요" : "대조 대기";
  return <span className={`review-match-badge ${warning || (rule?.review_status && rule.review_status !== "OK" && !reviewed) ? "is-warning" : ""}`}>{status}</span>;
}

function ReviewField({ doc, field }) {
  const { state, toggleConfirm } = useWorkspace();
  const key = field.key;
  const selected = state.field === key;
  const confirmed = doc.confirmed_fields.includes(key);
  const rule = doc.rule_results?.[key];
  const evidence = doc.reviews?.[key]?.evidence;
  const page = evidence?.page || rule?.page;
  return <article className={`review-field-card ${selected ? "is-selected" : ""}`}>
    <Button action="field" data-field={key} className="review-field-open" aria-label={`${fieldName(field)} 근거 보기`} aria-expanded={selected}><Icon name="right" /></Button>
    <div className="review-field-label">{fieldName(field)}</div>
    <div className="review-field-content"><div className="review-field-value">{key === "ingredients" ? (effective(doc).ingredients.map(item => item.cas_number || (item.is_substitute_data ? "영업비밀" : "CAS 미기재")).join(", ") || effective(doc).list_status.ingredients) : <FieldValue doc={doc} field={key} />}</div><div className="review-field-meta"><span>{page ? `원문 ${page}쪽` : "근거 미제공"}</span><span aria-hidden="true">·</span><MatchBadge rule={rule} reviewed={Boolean(doc.reviews?.[key])} /></div></div>
    <Button action="edit-field" data-field={key} className="review-edit-button" disabled={doc.pending_extraction || state.busy}>수정</Button>
    <label className="review-field-confirm"><input type="checkbox" checked={confirmed} disabled={doc.pending_extraction || state.busy} onChange={event => toggleConfirm(key, event.target.checked)} /><span className="sr-only">{fieldName(field)} 담당자 확정</span></label>
    {selected && <div className="review-field-evidence"><b>원문 근거</b><Multiline>{evidence?.source_text || rule?.source_text || "원문 근거가 아직 제공되지 않았습니다."}</Multiline></div>}
  </article>;
}

function HazardReview({ doc }) {
  const { state, toggleConfirm } = useWorkspace();
  const key = "hazard_statements";
  const selected = state.field === key;
  const confirmed = doc.confirmed_fields.includes(key);
  const values = effective(doc).hazard_statements;
  const rule = doc.rule_results?.[key];
  const evidence = doc.reviews?.[key]?.evidence;
  const sourceText = evidence?.source_text || rule?.source_text || "";
  const unresolved = values.filter(item => unverifiedHazard(doc, item));
  const page = evidence?.page || rule?.page;
  return <article className={`hazard-review-card ${selected ? "is-open" : ""} ${unresolved.length ? "needs-review" : ""}`}>
    <header className="hazard-card-header">
      <Button action="field" data-field={key} className="hazard-card-title" aria-expanded={selected}><Icon name="chevron" /><strong>유해 · 위험 문구</strong></Button>
      <div className="hazard-card-status">{unresolved.length ? <span className="hazard-warning-count">{unresolved.length}건 확인 필요</span> : <MatchBadge rule={rule} reviewed={Boolean(doc.reviews?.[key])} />}
        <label className="hazard-confirm"><input type="checkbox" checked={confirmed} disabled={Boolean(unresolved.length) || doc.pending_extraction || state.busy} onChange={event => toggleConfirm(key, event.target.checked)} /><span>확정</span></label>
      </div>
    </header>
    {selected && <>
      <div className="hazard-table-scroll"><table className="hazard-table"><thead><tr><th>코드</th><th>유해 · 위험 문구</th><th>원문 페이지</th><th>확인 결과</th><th>작업</th></tr></thead><tbody>
        {values.map((item, index) => { const warning = unverifiedHazard(doc, item); const matchedInSource = sourceText.includes(item.text) && (!item.code || sourceText.includes(item.code)); return <tr key={`${item.code || "none"}-${index}`} className={warning ? "hazard-warning-row" : ""}><td className="hazard-code">{item.code || "—"}</td><td>{item.text}</td><td>{warning ? "—" : page ? `원문 ${page}쪽` : "—"}</td><td><MatchBadge rule={matchedInSource ? { review_status: "OK" } : rule} warning={warning} reviewed={Boolean(doc.reviews?.[key]) && !warning} /></td><td><div className="hazard-row-actions">{warning ? <><Button action="delete-hazard" data-index={index} className="hazard-action" disabled={state.busy}>삭제</Button><Button action="keep-hazard" className="hazard-action" disabled={state.busy}>다른 페이지에서 찾기</Button></> : <Button action="edit-field" data-field={key} className="hazard-action" disabled={state.busy}>수정</Button>}</div></td></tr>; })}
        {!values.length && <tr><td colSpan={5} className="hazard-empty">유해 · 위험 문구: {effective(doc).list_status.hazard_statements}</td></tr>}
      </tbody></table></div>
      <div className="hazard-evidence-grid">
        <div><h3>원문 근거 {page ? `(${page}쪽)` : ""}</h3><div className="hazard-source"><Multiline>{sourceText || "원문 근거가 아직 제공되지 않았습니다."}</Multiline></div></div>
        <div className="hazard-result"><h3><Icon name="info" /> 확인 결과</h3><p>{unresolved.length ? <>{unresolved.map(item => item.code || "코드 없는 문구").join(", ")}은 제공된 원문 근거에서 일치하는 문구를 찾지 못했습니다.<br /><span>원문에 없으면 삭제하고, 다른 페이지에 있으면 근거 위치를 지정하세요.</span></> : doc.reviews?.[key] ? "담당자가 원문과 문구를 검토했습니다." : rule?.review_status === "OK" ? "제공된 유해 · 위험 문구가 원문과 일치합니다." : "원문과 문구를 확인해 주세요."}</p></div>
      </div>
    </>}
  </article>;
}

function ReviewPanel({ doc }) {
  const { state, patch } = useWorkspace();
  return <section className="review-panel-refresh" aria-label="필드 검토">
    <div className="review-panel-heading"><div className="review-panel-heading-copy"><h2>필드 검토</h2><span aria-hidden="true">›</span><p>1~3항의 핵심 정보를 확인하고 필요 시 수정하세요.</p></div><div className="review-panel-actions"><Button action="result-tab" data-tab={state.resultTab === "fields" ? "json" : "fields"} className="review-utility-button">{state.resultTab === "fields" ? "JSON 보기" : "필드 보기"}</Button><button type="button" className="review-utility-button" aria-pressed={state.onlyPending} onClick={() => patch({ onlyPending: !state.onlyPending })}>{state.onlyPending ? "전체 보기" : "미확정만"}</button><Button action="confirm-matched" className="review-confirm-all" disabled={doc.pending_extraction || state.busy}><Icon name="check" /> 일치하는 항목 모두 확정</Button></div></div>
    {doc.pending_extraction && <div className="inline-notice">업로드한 PDF의 로컬 미리보기입니다. 실제 추출에는 API 연결이 필요합니다.</div>}
    {state.resultTab === "json" ? <div className="review-json-panel"><div><span>담당자 수정값을 반영한 JSON</span><Button action="download-raw" className="review-utility-button">모델 원본 다운로드</Button></div><pre>{JSON.stringify(effective(doc), null, 2)}</pre></div> : <div className="review-cards">{FIELD_DEFS.filter(field => field.key !== "hazard_statements" && (!state.onlyPending || !doc.confirmed_fields.includes(field.key))).map(field => <ReviewField key={field.key} doc={doc} field={field} />)}{(!state.onlyPending || !doc.confirmed_fields.includes("hazard_statements")) && <HazardReview doc={doc} />}{state.onlyPending && count(doc) === 5 && <div className="review-all-done">모든 핵심 필드의 검토가 완료되었습니다.</div>}</div>}
  </section>;
}

export default function ReviewPage({ doc }) {
  const { state } = useWorkspace();
  const index = FIELD_DEFS.findIndex(field => field.key === state.field);
  return <div className="review-screen"><ReviewDocumentHeader doc={doc} /><main id="main" className="review-layout"><PreviewPanel doc={doc} /><ReviewPanel doc={doc} /></main><footer className="review-footer"><div className="review-footer-left"><Button action="prev-field" disabled={index <= 0}><Icon name="left" /> 이전 필드</Button>{state.dirtyDocuments.has(doc.id) && <span className="unsaved-indicator">저장하지 않은 변경사항</span>}</div><div className="review-step"><strong>{index + 1} / {FIELD_DEFS.length}</strong><span>{fieldName(FIELD_DEFS[index])} 검토 중</span></div><div className="review-footer-actions"><Button action="download-json" className="review-download" disabled={doc.pending_extraction || state.busy}><Icon name="download" /> JSON 다운로드</Button><Button action="next-field" disabled={index >= FIELD_DEFS.length - 1}>다음 필드 <Icon name="right" /></Button><Button action="save" className="primary review-complete" disabled={state.busy || doc.pending_extraction}><Icon name="check" /> {state.busy ? "저장 중…" : "검토 완료"}</Button></div></footer><p className="sr-only">{API_MODE ? "실제 문서 검토 화면" : "예시 데이터 화면"}</p></div>;
}
