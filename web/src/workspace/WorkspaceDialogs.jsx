import { useEffect, useRef, useState } from "react";
import { API_MODE } from "./api.js";
import { FIELD_DEFS } from "./data.js";
import { effective, unverifiedHazard, validateList } from "./model.js";
import { useWorkspace } from "./WorkspaceContext.jsx";
import { Button, Icon, Options } from "./ui.jsx";

function EditForm({ doc, fieldKey }) {
  const { state, commitReview, closeModal, notify } = useWorkspace();
  const data = effective(doc);
  const isList = Array.isArray(data[fieldKey]);
  const [value, setValue] = useState(() => isList ? JSON.stringify(data[fieldKey], null, 2) : data[fieldKey].value || "");
  const [sourceStatus, setStatus] = useState(() => isList ? data.list_status[fieldKey] : data[fieldKey].source_status);
  const [error, setError] = useState("");
  function submit(event) {
    event.preventDefault();
    try {
      const parsed = isList ? JSON.parse(value) : { value: sourceStatus === "기재" ? value.trim() : null, source_status: sourceStatus };
      if (isList) validateList(fieldKey, parsed, sourceStatus);
      else if (sourceStatus === "기재" && !parsed.value) throw new Error("기재 상태에는 값이 필요합니다.");
      const extras = isList ? { list_status: sourceStatus } : {};
      if (fieldKey === "hazard_statements") {
        if (parsed.some(item => unverifiedHazard(doc, item))) throw new Error("원문에 없는 문구는 삭제하거나, 필드의 유지 버튼에서 원문 근거를 먼저 지정해 주세요.");
        extras.resolved = true;
      }
      commitReview(doc.id, fieldKey, parsed, extras);
      closeModal();
      notify("수정값을 반영했습니다. 검토 완료 후 저장해 주세요.");
    } catch (issue) { setError(issue instanceof SyntaxError ? "JSON 문법을 확인해 주세요. 쉼표와 따옴표가 필요합니다." : issue.message); }
  }
  return <form id="edit-form" data-field={fieldKey} onSubmit={submit}>
    <p className="modal-description">수정값은 모델 원본과 분리하여 보관합니다.</p>
    <label className="form-label" htmlFor="edit-value">{isList ? "추출값 (JSON 배열)" : fieldKey === "signal_word" ? "신호어" : "제품명"}</label>
    {isList ? <><textarea id="edit-value" name="value" className="code-input" rows={11} spellCheck={false} value={value} onChange={event => setValue(event.target.value)} /><p className="form-hint">원문에 적힌 값만 입력하세요. 빈 목록은 []로 입력합니다.</p></> : fieldKey === "signal_word" ? <select id="edit-value" name="value" value={value} onChange={event => setValue(event.target.value)}><Options values={["위험", "경고"]} placeholder="값 없음" /></select> : <input id="edit-value" name="value" value={value} onChange={event => setValue(event.target.value)} />}
    <label className="form-label" htmlFor="edit-status">원문 상태</label><select id="edit-status" name="source_status" value={sourceStatus} onChange={event => setStatus(event.target.value)}><Options values={["기재", "자료없음", "해당없음"]} /></select>
    <p id="edit-error" className="form-error" role="alert">{error}</p>
    <div className="modal-footer"><Button action="close-modal">취소</Button><button className="primary" type="submit" disabled={state.busy}>수정하고 확정</button></div>
  </form>;
}

function EvidenceForm({ doc }) {
  const { commitReview, closeModal, notify } = useWorkspace();
  const [page, setPage] = useState("1");
  const [source, setSource] = useState("");
  const [error, setError] = useState("");
  function submit(event) {
    event.preventDefault();
    const values = effective(doc);
    const unresolved = values.hazard_statements.filter(item => unverifiedHazard(doc, item));
    const normalize = value => value.replace(/\s/g, "");
    if (!source.trim() || unresolved.some(item => !normalize(source).includes(normalize(item.text)))) {
      setError("확인할 문구가 포함된 원문 근거를 입력해 주세요."); return;
    }
    commitReview(doc.id, "hazard_statements", values.hazard_statements, { list_status: values.list_status.hazard_statements, resolved: true, evidence: { page: Number(page), source_text: source.trim() } });
    closeModal();
    notify("담당자 원문 근거를 기록했습니다. 검토 완료 후 저장해 주세요.");
  }
  return <form id="evidence-form" onSubmit={submit}>
    <p className="modal-description">문구가 실제로 기재된 페이지와 원문을 입력해 주세요.</p>
    <label className="form-label" htmlFor="evidence-page">원문 페이지</label><input id="evidence-page" name="page" type="number" min={1} max={doc.page_count || 9999} required value={page} onChange={event => setPage(event.target.value)} />
    <label className="form-label" htmlFor="evidence-source">원문 근거</label><textarea id="evidence-source" name="source" rows={4} required placeholder="해당 문구를 원문 그대로 입력하세요" value={source} onChange={event => setSource(event.target.value)} />
    <p className="form-hint">담당자가 확인한 근거로 저장되며 자동 일치 판정으로 바뀌지 않습니다.</p><p id="evidence-error" className="form-error" role="alert">{error}</p>
    <div className="modal-footer"><Button action="close-modal">취소</Button><button type="submit" className="primary">근거 지정 후 유지</button></div>
  </form>;
}

function UploadForm() {
  const { state, uploadFile } = useWorkspace();
  const [file, setFile] = useState(null);
  const [model, setModel] = useState("qlora");
  const [error, setError] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [previewUrl, setPreviewUrl] = useState(null);
  const previewUrlRef = useRef(null);
  useEffect(() => () => { if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current); }, []);

  function selectFile(nextFile) {
    if (previewUrlRef.current) URL.revokeObjectURL(previewUrlRef.current);
    previewUrlRef.current = null;
    setPreviewUrl(null);
    setFile(nextFile);
    setError("");
  }
  function handleDrop(event) {
    event.preventDefault();
    setDragging(false);
    selectFile(event.dataTransfer.files[0] || null);
  }
  async function submit(event) {
    event.preventDefault();
    if (!file || submitting) return;
    setError("");
    try {
      if (!/\.pdf$/i.test(file.name)) throw new Error("PDF 파일을 선택해 주세요.");
      if (file.size > 30 * 1024 * 1024) throw new Error("30MB 이하의 PDF 파일을 선택해 주세요.");
      if (new TextDecoder().decode(await file.slice(0, 5).arrayBuffer()) !== "%PDF-") throw new Error("유효한 PDF 파일이 아닙니다. 파일 내용을 확인해 주세요.");
      const url = URL.createObjectURL(file);
      previewUrlRef.current = url;
      setPreviewUrl(url);
    } catch (issue) { setError(issue.message); }
  }
  async function extract() {
    if (submitting) return;
    setSubmitting(true);
    setError("");
    try { await uploadFile(file, model); }
    catch (issue) { setError(issue.message); }
    finally { setSubmitting(false); }
  }
  return <form id="upload-form" className={previewUrl ? "is-previewing" : ""} onSubmit={submit}>
    {previewUrl ? <div className="upload-preview"><div className="upload-preview-heading"><strong>{file.name}</strong><button type="button" onClick={() => selectFile(file)}>다른 파일 선택</button></div><iframe src={previewUrl + "#view=FitH"} title={file.name + " PDF 미리보기"} /></div> : <>
      <p className="modal-description">PDF 파일을 선택하거나 아래에 끌어다 놓으세요.</p>
      <label className={"upload-dropzone" + (dragging ? " is-dragging" : "")} htmlFor="pdf-file" onDragEnter={event => { event.preventDefault(); setDragging(true); }} onDragOver={event => { event.preventDefault(); event.dataTransfer.dropEffect = "copy"; }} onDragLeave={event => { if (!event.currentTarget.contains(event.relatedTarget)) setDragging(false); }} onDrop={handleDrop}>
        <Icon name="upload" /><b>{file ? file.name : "PDF 파일 선택"}</b><span>{file ? (file.size / 1024 / 1024).toFixed(1) + " MB · 다른 파일을 선택하려면 클릭" : "클릭하거나 PDF를 여기에 놓으세요"}</span><small>PDF 1개 · 최대 30MB</small><input id="pdf-file" name="file" type="file" accept=".pdf,application/pdf" onChange={event => selectFile(event.target.files[0] || null)} />
      </label>
    </>}
    {file && <><label className="form-label" htmlFor="upload-model">추출 모델</label><select id="upload-model" name="model" value={model} onChange={event => setModel(event.target.value)}><option value="qlora">QLoRA</option><option value="base">Base</option></select></>}
    <p id="upload-error" className="form-error" role="alert">{error}</p>
    <div className="modal-footer"><Button action="close-modal" disabled={state.busy || submitting}>{previewUrl ? "닫기" : "취소"}</Button>{!previewUrl && <button type="submit" disabled={state.busy || submitting || !file}>PDF 미리보기</button>}<button type="button" className="primary" onClick={extract} disabled={state.busy || submitting || !file}>{submitting ? "추출 중…" : "업로드하고 추출"}</button></div>
  </form>;
}

function CompareForm() {
  const { state, patch, closeModal, loadCompare } = useWorkspace();
  const [subset, setSubset] = useState(API_MODE ? state.compareSubset : "all");
  const split = API_MODE ? "val" : "예시";
  async function submit(event) {
    event.preventDefault();
    patch({ compareSplit: split, compareSubset: subset });
    closeModal();
    await loadCompare();
  }
  return <form id="compare-form" onSubmit={submit}><p className="modal-description">동일한 평가셋에서 수행된 실험 결과를 비교합니다.</p>
    <label className="form-label" htmlFor="compare-split">평가 데이터</label><select id="compare-split" name="split" defaultValue={split}><option value={split}>{API_MODE ? "Validation (조건 선택용)" : "첨부 화면 예시 데이터"}</option></select>
    <label className="form-label" htmlFor="compare-subset">문서 유형</label><select id="compare-subset" name="subset" value={subset} onChange={event => setSubset(event.target.value)}><option value="all">전체</option>{API_MODE && <><option value="current_kr">국문 현행</option><option value="legacy_kr">국문 구서식</option><option value="import_kr">수입품 국문판</option></>}</select>
    <p className="form-hint">{API_MODE ? "봉인된 Test 평가를 이 화면에서 실행하지 않습니다." : "화면 확인용 수치를 다시 불러옵니다. 모델 학습·평가는 실행되지 않습니다."}</p>
    <div className="modal-footer"><Button action="close-modal">취소</Button><button type="submit" className="primary" disabled={state.busy}>비교 결과 불러오기</button></div>
  </form>;
}

function ModalFrame({ title, children }) {
  const { state, closeModal } = useWorkspace();
  const ref = useRef(null);
  useEffect(() => {
    const dialog = ref.current;
    const previous = document.activeElement;
    dialog.showModal();
    return () => { dialog.close(); if (previous?.isConnected) previous.focus(); };
  }, []);
  return <dialog ref={ref} id="modal" aria-labelledby="modal-title" onCancel={event => { event.preventDefault(); if (!state.busy) closeModal(); }} onClick={event => {
    if (event.target !== event.currentTarget || state.busy) return;
    const rect = event.currentTarget.getBoundingClientRect();
    if (event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom) closeModal();
  }}>
    <div className="modal-heading"><h2 id="modal-title">{title}</h2><Button action="close-modal" className="icon-button" aria-label="닫기" disabled={state.busy}><Icon name="close" /></Button></div>{children}
  </dialog>;
}

export default function WorkspaceDialogs() {
  const { state, update } = useWorkspace();
  const modal = state.modal;
  if (!modal) return null;
  const doc = state.documents.find(item => item.id === modal.documentId);
  const titles = { help: "MSDS Lab 사용 안내", profile: "검토 담당자", columns: "문서 목록 표시 항목", refresh: "문서 목록 새로고침", evidence: "원문 근거 지정", upload: "MSDS 문서 업로드", compare: "실험 비교 설정", edit: `${FIELD_DEFS.find(field => field.key === modal.field)?.label || ""} 수정` };
  let body;
  switch (modal.type) {
    case "edit": body = doc && <EditForm doc={doc} fieldKey={modal.field} />; break;
    case "evidence": body = doc && <EvidenceForm doc={doc} />; break;
    case "upload": body = <UploadForm />; break;
    case "compare": body = <CompareForm />; break;
    case "columns": body = <><div className="column-options">{Object.entries({ submission: "제출번호", language: "언어", pages: "페이지", owner: "담당자" }).map(([key, label]) => <label key={key}><input type="checkbox" data-column={key} checked={state.columns[key]} onChange={event => { const checked = event.target.checked; update(next => { next.columns[key] = checked; }); }} /> {label}</label>)}</div><div className="modal-footer"><Button action="close-modal" className="primary">적용</Button></div></>; break;
    case "refresh": body = <><p className="modal-description">저장하지 않은 수정값이 초기화됩니다. 새로고침할까요?</p><div className="modal-footer"><Button action="close-modal">취소</Button><Button action="reload-confirmed" className="primary">새로고침</Button></div></>; break;
    case "profile": body = <div className="help-content"><p>현재 문서 담당자: <b>{doc?.owner || "미지정"}</b></p><p>이 화면에는 사용자 인증 기능이 연결되어 있지 않습니다.</p></div>; break;
    case "help": body = <div className="help-content"><p>원문과 추출 결과를 나란히 확인하고 핵심 5개 필드를 검토하는 작업 공간입니다.</p><ol><li><b>문서 목록</b>에서 문서를 선택하고 검토하기를 누릅니다.</li><li>필드를 누르면 해당 원문 근거가 강조됩니다.</li><li>원문 확인이 필요한 문구는 삭제하거나 근거 위치를 지정합니다.</li><li>필드별 담당자 확정을 완료한 뒤 <b>확정하고 저장</b>을 누릅니다.</li><li>확정된 값을 JSON으로 다운로드할 수 있습니다.</li></ol><div className="inline-notice">{API_MODE ? "실제 추출·저장·비교는 연결된 API를 사용합니다." : "현재 예시 모드입니다. PDF를 선택한 뒤 바로 추출하거나 먼저 미리 볼 수 있습니다. 추출이 완료되면 API 모드에서 검토합니다."}</div></div>; break;
    default: return null;
  }
  return <ModalFrame key={`${modal.type}-${modal.documentId}-${modal.field}`} title={titles[modal.type]}>{body}</ModalFrame>;
}
