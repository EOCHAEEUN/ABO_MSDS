import { useEffect, useRef } from "react";
import { API_MODE, source } from "./api.js";
import { FIELD_DEFS, sourceText } from "./data.js";
import { canConfirmMatched, count, effective, reviewBadge, unverifiedHazard } from "./model.js";
import { useWorkspace } from "./WorkspaceContext.jsx";
import { Button, FieldValue, Icon, Multiline, Progress } from "./ui.jsx";
import PreviewPanel from "./PreviewPanel.jsx";

// 추출 텍스트(모델이 읽은 1~3항 원문)는 필드 검토의 "원문 텍스트"에서만 본다. 왼쪽 패널은 원본 PDF 전용
function SourceText({ doc }) {
  const { state } = useWorkspace();
  const body = useRef(null);
  const field = FIELD_DEFS.find(item => item.key === state.field);
  const rule = doc.rule_results?.[state.field];
  const snippet = doc.reviews?.[state.field]?.evidence?.source_text || rule?.source_text;
  useEffect(() => { if (body.current) body.current.scrollTop = 0; }, [doc.id]);
  return <div className="source-text-view review-source-text" ref={body}>
    <div className="source-reading-note"><Icon name="document" /><div><strong>추출된 원문 · 1~3항</strong><p>모델이 읽은 텍스트입니다. 필드를 고르면 그 근거가 위에 표시되고, 왼쪽 PDF는 근거 쪽으로 이동합니다.</p></div></div>
    {snippet && <section className="source-focus" data-source={state.field}><div><span>선택한 필드의 근거</span><b>{field?.label} · {rule?.page ? `원문 ${rule.page}쪽` : rule?.section || "위치 미제공"}</b></div><pre>{snippet}</pre></section>}
    {doc.source_text?.trim() ? <article className="source-transcript"><header><h3>원문 전체</h3><span>추출 결과와 대조해 주세요</span></header><pre>{doc.source_text}</pre></article> : <div className="extracted-text">{FIELD_DEFS.map(item => <section data-source={item.key} key={item.key} className={`text-section ${item.key === state.field ? "highlighted" : ""}`}><h3>{item.section} · {item.label}</h3><p>{doc.rule_results?.[item.key]?.source_text || (doc.source ? sourceText(doc.source, item.key) : "원문 텍스트가 제공되지 않았습니다.")}</p></section>)}</div>}
  </div>;
}


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
  return <header className="review-document-header workspace-page-header">
    <div className="review-document-heading workspace-page-heading">
      <div className="review-context-label workspace-page-eyebrow"><span>문서 검토</span>{source.mode === "results" && <b>저장된 실험 결과</b>}{!API_MODE && source.mode !== "results" && <b>예시 문서</b>}{doc.model_name && <b>{doc.model_name}</b>}</div>
      <div className="review-title-row"><h1 className="workspace-page-title">{values.product_name.value || doc.file_name}</h1><span className="pdf-badge">{doc.pdf_url || doc.source ? "PDF" : "TEXT"}</span></div>
      <div className="review-document-meta workspace-page-support">{meta.map((item, index) => <span key={index}>{index === 0 && <Icon name="document" />}{item}</span>)}</div>
    </div>
    <div className="review-header-tools workspace-page-actions">
      <div className="review-search-row">
        <form className="review-search" role="search" onSubmit={search}><Icon name="search" /><input name="query" type="search" defaultValue={state.query} aria-label="문서 검색" placeholder="문서명, 공급자, CAS 번호 검색" /></form>
        <Button action="upload" className="review-upload-button" aria-label="새 PDF 문서 업로드" disabled={state.busy}><span className="review-upload-mark"><Icon name="plus" /></span><span>새 문서</span></Button>
      </div>
      <div className="review-progress"><span>검토 완료율</span><Progress doc={doc} /><strong>{count(doc) * 20}%</strong></div>
    </div>
  </header>;
}

function MatchBadge({ rule, reviewed = false, warning = false }) {
  const badge = reviewBadge(rule, reviewed, warning);
  return <span className={`review-match-badge is-${badge.tone}`}>{badge.label}</span>;
}

function ReviewField({ doc, field }) {
  const { state, toggleConfirm } = useWorkspace();
  const key = field.key;
  const selected = state.field === key && state.expandedField === key;
  const confirmed = doc.confirmed_fields.includes(key);
  const rule = doc.rule_results?.[key];
  const evidence = doc.reviews?.[key]?.evidence;
  const page = evidence?.page || rule?.page;
  return <article className={`review-field-card ${selected ? "is-selected" : ""}`}>
    <Button action="field" data-field={key} className="review-field-open" aria-label={`${fieldName(field)} ${selected ? "접기" : "펼치기"}`} aria-expanded={selected} title={selected ? "접기" : "펼치기"}><Icon name="chevron" /></Button>
    <div className="review-field-label">{fieldName(field)}</div>
    <div className="review-field-content"><div className="review-field-value">{key === "ingredients" ? <div className="review-ingredients">{effective(doc).ingredients.length ? effective(doc).ingredients.map((item, i) => <div className="review-ingredient" key={i}><span>{item.chemical_name || `성분 ${i + 1}`}</span><code>{item.cas_number || (item.is_substitute_data ? "영업비밀" : "CAS 미기재")}</code><span>{item.content || "함유량 미기재"}</span></div>) : effective(doc).list_status.ingredients}</div> : <FieldValue doc={doc} field={key} />}</div><div className="review-field-meta"><span>{page ? `원문 ${page}쪽` : rule?.section || "위치 미제공"}</span><span aria-hidden="true">·</span><MatchBadge rule={rule} reviewed={confirmed} /></div></div>
    <div className="review-field-actions">
      <Button action="edit-field" data-field={key} className="review-edit-button" aria-label={`${fieldName(field)} 수정`} title="수정" disabled={doc.pending_extraction || state.busy}><Icon name="edit" /></Button>
      <label className="review-field-confirm"><input type="checkbox" checked={confirmed} disabled={doc.pending_extraction || state.busy} onChange={event => toggleConfirm(key, event.target.checked)} /><span className="sr-only">{fieldName(field)} 담당자 확정</span></label>
    </div>
    {selected && <div className="review-field-evidence"><b>원문 근거</b>{rule?.messages?.length > 0 && <ul className="review-rule-messages">{rule.messages.map((message, i) => <li key={i}>{message}</li>)}</ul>}<Multiline>{evidence?.source_text || rule?.source_text || "원문 근거가 아직 제공되지 않았습니다."}</Multiline></div>}
  </article>;
}

function HazardReview({ doc }) {
  const { state, toggleConfirm } = useWorkspace();
  const key = "hazard_statements";
  const selected = state.field === key && state.expandedField === key;
  const confirmed = doc.confirmed_fields.includes(key);
  const values = effective(doc).hazard_statements;
  const rule = doc.rule_results?.[key];
  const evidence = doc.reviews?.[key]?.evidence;
  const sourceText = evidence?.source_text || rule?.source_text || "";
  const unresolved = values.filter(item => unverifiedHazard(doc, item));
  const page = evidence?.page || rule?.page;
  return <article className={`hazard-review-card ${selected ? "is-open" : ""} ${unresolved.length ? "needs-review" : ""}`}>
    <header className="hazard-card-header">
      <Button action="field" data-field={key} className="hazard-card-title" aria-label={`유해·위험 문구 ${selected ? "접기" : "펼치기"}`} aria-expanded={selected} title={selected ? "접기" : "펼치기"}><Icon name="chevron" /><strong>유해 · 위험 문구</strong></Button>
      <div className="hazard-card-status">{unresolved.length ? <span className="hazard-warning-count">{unresolved.length}건 확인 필요</span> : <MatchBadge rule={rule} reviewed={confirmed} />}
        <Button action="edit-field" data-field={key} className="review-edit-button" aria-label="유해·위험 문구 수정" title="수정" disabled={doc.pending_extraction || state.busy}><Icon name="edit" /></Button>
        <label className="hazard-confirm"><input type="checkbox" checked={confirmed} disabled={Boolean(unresolved.length) || doc.pending_extraction || state.busy} onChange={event => toggleConfirm(key, event.target.checked)} /><span>확정</span></label>
      </div>
    </header>
    {selected && <>
      <div className="hazard-table-scroll"><table className="hazard-table"><thead><tr><th>코드</th><th>유해 · 위험 문구</th><th>근거 위치</th><th>확인 결과</th><th>작업</th></tr></thead><tbody>
        {values.map((item, index) => { const warning = unverifiedHazard(doc, item); return <tr key={`${item.code || "none"}-${index}`} className={warning ? "hazard-warning-row" : ""}><td className="hazard-code">{item.code || "—"}</td><td>{item.text}</td><td>{warning ? "—" : page ? `원문 ${page}쪽` : rule?.section || "위치 미제공"}</td><td><MatchBadge rule={rule} warning={warning} reviewed={confirmed && !warning} /></td><td><div className="hazard-row-actions">{warning ? <><Button action="delete-hazard" data-index={index} className="hazard-action" disabled={state.busy}>삭제</Button><Button action="keep-hazard" className="hazard-action" disabled={state.busy}>다른 페이지에서 찾기</Button></> : <Button action="edit-field" data-field={key} className="hazard-action hazard-edit-button" aria-label={`유해·위험 문구 수정 (${item.code || "코드 없음"})`} title="수정" disabled={state.busy}><Icon name="edit" /></Button>}</div></td></tr>; })}
        {!values.length && <tr><td colSpan={5} className="hazard-empty">유해 · 위험 문구: {effective(doc).list_status.hazard_statements}</td></tr>}
      </tbody></table></div>
      <div className="hazard-evidence-grid">
        <div><h3>원문 근거 {page ? `(${page}쪽)` : ""}</h3><div className="hazard-source"><Multiline>{sourceText || "원문 근거가 아직 제공되지 않았습니다."}</Multiline></div></div>
        <div className="hazard-result"><h3><Icon name="info" /> 확인 결과</h3><p>{unresolved.length ? <>{unresolved.map(item => item.code || "코드 없는 문구").join(", ")}은 제공된 원문 근거에서 일치하는 문구를 찾지 못했습니다.<br /><span>원문에 없으면 삭제하고, 다른 페이지에 있으면 근거 위치를 지정하세요.</span></> : confirmed ? "담당자가 원문과 문구를 검토했습니다." : rule?.review_status === "OK" ? "사전 점검에서 경고가 발견되지 않았습니다. 원문의 누락·오입력 여부를 확인한 뒤 확정하세요." : "원문과 문구를 확인해 주세요."}</p></div>
      </div>
    </>}
  </article>;
}

function ReviewPanel({ doc }) {
  const { state, patch } = useWorkspace();
  return <section className="review-panel-refresh" aria-label="필드 검토">
    <div className="review-panel-heading"><div className="review-panel-heading-copy"><h2>필드 검토</h2><span aria-hidden="true">›</span><p>1~3항의 핵심 정보를 확인하고 필요 시 수정하세요.</p></div><div className="review-panel-actions"><Button action="result-tab" data-tab={state.resultTab === "text" ? "fields" : "text"} className="review-utility-button" aria-pressed={state.resultTab === "text"}>{state.resultTab === "text" ? "필드 보기" : "원문 텍스트"}</Button><Button action="result-tab" data-tab={state.resultTab === "json" ? "fields" : "json"} className="review-utility-button" aria-pressed={state.resultTab === "json"}>{state.resultTab === "json" ? "필드 보기" : "JSON 보기"}</Button><button type="button" className="review-utility-button" aria-pressed={state.onlyPending} onClick={() => patch({ onlyPending: !state.onlyPending })}>{state.onlyPending ? "전체 보기" : "미확정만"}</button><Button action="confirm-matched" className="review-confirm-all" disabled={state.busy || !FIELD_DEFS.some(field => canConfirmMatched(doc, field.key))}><Icon name="check" /> 사전 점검 항목 확정</Button></div></div>
    {doc.pending_extraction && <div className="inline-notice">업로드한 PDF의 로컬 미리보기입니다. 실제 추출에는 API 연결이 필요합니다.</div>}
    {state.resultTab === "text" ? <SourceText doc={doc} /> : state.resultTab === "json" ? <div className="review-json-panel"><div><span>담당자 수정값을 반영한 JSON</span><Button action="download-raw" className="review-utility-button">모델 원본 다운로드</Button></div><pre>{JSON.stringify(effective(doc), null, 2)}</pre></div> : <div className="review-cards">{FIELD_DEFS.filter(field => field.key !== "hazard_statements" && (!state.onlyPending || !doc.confirmed_fields.includes(field.key))).map(field => <ReviewField key={field.key} doc={doc} field={field} />)}{(!state.onlyPending || !doc.confirmed_fields.includes("hazard_statements")) && <HazardReview doc={doc} />}{state.onlyPending && count(doc) === 5 && <div className="review-all-done">모든 핵심 필드의 검토가 완료되었습니다.</div>}</div>}
  </section>;
}

export default function ReviewPage({ doc }) {
  const { state } = useWorkspace();
  const index = FIELD_DEFS.findIndex(field => field.key === state.field);
  return <div className="review-screen"><ReviewDocumentHeader doc={doc} /><main id="main" className="review-layout"><PreviewPanel doc={doc} /><ReviewPanel doc={doc} /></main><footer className="review-footer"><div className="review-footer-left"><Button action="prev-field" className="review-nav-button review-prev" disabled={index <= 0}><Icon name="left" /> 이전</Button>{state.dirtyDocuments.has(doc.id) && <span className="unsaved-indicator">저장하지 않은 변경사항</span>}</div><div className="review-step"><strong>{index + 1} / {FIELD_DEFS.length}</strong><div className="review-step-track" aria-hidden="true">{FIELD_DEFS.map((field, step) => <i key={field.key} className={`${doc.confirmed_fields.includes(field.key) ? "is-confirmed" : ""} ${step === index ? "is-active" : ""}`} />)}</div><span className="review-step-label">{fieldName(FIELD_DEFS[index])} 검토 중</span></div><div className="review-footer-actions"><Button action="next-field" className="review-nav-button review-next" disabled={index >= FIELD_DEFS.length - 1}>다음 <Icon name="right" /></Button><div className="review-commit-actions"><Button action="download-json" className="review-download" disabled={doc.pending_extraction || state.busy}><Icon name="download" /> JSON 다운로드</Button><Button action="save" className="primary review-complete" disabled={state.busy || doc.pending_extraction}><Icon name="check" /> {state.busy ? "저장 중…" : "검토 완료"}</Button></div></div></footer><p className="sr-only">{API_MODE ? "실제 문서 검토 화면" : "예시 데이터 화면"}</p></div>;
}
