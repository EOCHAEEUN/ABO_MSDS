import { FIELD_DEFS } from "./data.js";
import { API_MODE } from "./api.js";
import { effective, unverifiedHazard } from "./model.js";
import { useWorkspace } from "./WorkspaceContext.jsx";
import { Button, DocumentHeader, FieldValue, Icon, Multiline } from "./ui.jsx";
import PreviewPanel from "./PreviewPanel.jsx";

function ReviewTable({ doc }) {
  const { state, toggleConfirm } = useWorkspace();
  const fields = FIELD_DEFS.filter(field => !state.onlyPending || !doc.confirmed_fields.includes(field.key));
  if (!fields.length) return <div className="empty-state"><Icon name="check" /><h3>모든 필드의 검토가 완료되었습니다.</h3><Button action="show-all">전체 필드 보기</Button></div>;
  return <div className="table-scroll"><table className="review-table">
    <colgroup><col className="field-col" /><col /><col className="evidence-col" /><col className="match-col" /><col className="confirm-col" /><col className="edit-col" /></colgroup>
    <thead><tr><th>필드</th><th>추출값</th><th>근거</th><th>원문 대조</th><th>담당자 확정</th><th><span className="sr-only">수정</span></th></tr></thead>
    <tbody>{fields.map(field => {
      const confirmed = doc.confirmed_fields.includes(field.key);
      const rule = doc.rule_results?.[field.key];
      const reviewed = Boolean(doc.reviews[field.key]);
      const hazards = field.key === "hazard_statements" ? effective(doc).hazard_statements : [];
      const warning = hazards.some(item => unverifiedHazard(doc, item));
      return <tr key={field.key} className={`field-row ${state.field === field.key ? "selected" : ""}`} data-field={field.key}>
        <th scope="row"><Button action="field" className="field-button" data-field={field.key}>{field.label}</Button></th>
        <td className="field-value">{hazards.length ? hazards.map((item, index) => <div key={index} className={`hazard-value ${unverifiedHazard(doc, item) ? "unverified" : ""}`}>
          <div><b>{item.code || "코드 없음"}</b><span>{item.text}</span></div>
          {unverifiedHazard(doc, item) && <div className="hazard-actions"><Button action="delete-hazard" className="small-button warning-outline" data-index={index} disabled={state.busy}>삭제</Button><Button action="keep-hazard" className="small-button" disabled={state.busy}>유지</Button><span className="badge warning-outline">원문 확인 필요</span></div>}
        </div>) : <FieldValue doc={doc} field={field.key} />}</td>
        <td>{rule?.page ? `${rule.page}쪽` : "—"}</td>
        <td>{reviewed ? <span className="reviewed-text">수정됨</span> : !rule ? <span className="muted">대기</span> : rule.review_status === "OK" ? <span className="match-ok"><Icon name="check" /> 일치</span> : <span className="text-warning">{rule.review_status === "SOURCE_CHECK_REQUIRED" ? "원문 확인" : "검토 필요"}</span>}</td>
        <td><label className={`confirm-label ${confirmed ? "confirmed" : ""}`}><input type="checkbox" data-confirm={field.key} checked={confirmed} disabled={warning || doc.pending_extraction || state.busy} aria-label={`${field.label} 확정`} onChange={event => toggleConfirm(field.key, event.target.checked)} /><span>{confirmed ? "확정" : "미확정"}</span></label></td>
        <td><Button action="edit-field" className="link-button" data-field={field.key} disabled={doc.pending_extraction || state.busy}>수정</Button></td>
      </tr>;
    })}</tbody>
  </table></div>;
}

function EvidencePanel({ doc }) {
  const { state } = useWorkspace();
  const field = FIELD_DEFS.find(item => item.key === state.field);
  const originalRule = doc.rule_results?.[state.field];
  const evidence = doc.reviews[state.field]?.evidence;
  const rule = evidence ? { ...originalRule, ...evidence, section: "담당자 지정 근거" } : originalRule;
  const unresolved = state.field === "hazard_statements" ? effective(doc).hazard_statements.filter(item => unverifiedHazard(doc, item)) : [];
  const codes = unresolved.map(item => item.code || "문구").join(", ");
  return <section className="panel evidence-panel">
    <div className="evidence-heading"><h2>원문 근거 <span>{field.label}</span></h2><span>{rule?.page ? `${rule.page}쪽, ${rule.section || field.section}` : "근거 없음"}</span></div>
    <div className="evidence-box"><blockquote><Multiline>{rule?.source_text || "원문 근거가 아직 제공되지 않았습니다."}</Multiline></blockquote></div>
    <dl className="evidence-details">
      <dt>판정 사유</dt><dd>{codes ? <><strong className="text-warning">{codes}</strong> : 1~3항 원문에서 일치하는 문자열을 찾지 못함 (공백·하이픈 정규화 후)</> : doc.reviews[state.field] ? "담당자가 추출값을 검토했습니다. 모델 원본은 별도로 보존됩니다." : rule?.review_status === "OK" ? "추출값이 원문 근거와 일치합니다." : `원문을 확인해 주세요.${rule?.reason_code ? ` (${rule.reason_code})` : ""}`}</dd>
      <dt>검토 안내</dt><dd>{codes ? "원문에 없는 값이면 삭제하고, 다른 페이지에 근거가 있으면 유지 후 위치를 지정하세요." : "원문과 추출값을 확인한 뒤 담당자 확정을 선택하세요."}</dd>
    </dl>
  </section>;
}

export default function ReviewPage({ doc }) {
  const { state, patch } = useWorkspace();
  return <><DocumentHeader doc={doc} />
    <main id="main" className="review-layout">
      <PreviewPanel doc={doc} />
      <div className="review-right"><section className="panel fields-panel">
        <div className="panel-toolbar"><div className="tabs" role="tablist" aria-label="추출 결과 보기">{["fields", "json"].map((tab, i) => <Button action="result-tab" key={tab} data-tab={tab} className={`tab ${state.resultTab === tab ? "active" : ""}`} role="tab" aria-selected={state.resultTab === tab}>{["필드별 검토", "추출 결과 JSON"][i]}</Button>)}</div>
          <select id="field-filter" aria-label="검토 필드 표시" value={state.onlyPending ? "pending" : "all"} onChange={event => patch({ onlyPending: event.target.value === "pending" })}><option value="all">표시: 전체 필드</option><option value="pending">표시: 미확정 필드</option></select>
        </div>
        {doc.pending_extraction && <div className="inline-notice">업로드한 PDF의 로컬 미리보기입니다. 실제 추출은 API 연결 후 사용할 수 있습니다.</div>}
        {state.resultTab === "fields" ? <ReviewTable doc={doc} /> : <><div className="json-heading"><span>담당자 수정값을 반영한 JSON · 모델 원본 별도 보존</span><Button action="download-raw" className="small-button">모델 원본 다운로드</Button></div><pre className="json-view">{JSON.stringify(effective(doc), null, 2)}</pre></>}
      </section><EvidencePanel doc={doc} /><div className="review-context"><Icon name="info" /> {API_MODE ? "최종 확정값은 담당자가 직접 검토합니다." : "첨부 화면 기반의 예시입니다. 검토 결과는 이 브라우저에 저장됩니다."}</div></div>
    </main>
    <footer className="review-footer"><div className="field-navigation">
      <Button action="prev-field" disabled={state.field === FIELD_DEFS[0].key}>이전 필드</Button>
      <span><strong>{FIELD_DEFS.findIndex(field => field.key === state.field) + 1} / 5</strong> {FIELD_DEFS.find(field => field.key === state.field).label} 검토 중</span>
      <Button action="next-field" disabled={state.field === FIELD_DEFS.at(-1).key}>다음 필드</Button>
    </div><div className="footer-actions">
      {state.dirtyDocuments.has(doc.id) && <span className="unsaved-indicator">저장하지 않은 변경사항</span>}
      <Button action="download-json" disabled={doc.pending_extraction || state.busy}><Icon name="download" /> JSON 다운로드</Button>
      <Button action="save" className="primary" disabled={state.busy || doc.pending_extraction}>{state.busy ? "저장 중…" : "확정하고 저장"}</Button>
    </div></footer>
  </>;
}
