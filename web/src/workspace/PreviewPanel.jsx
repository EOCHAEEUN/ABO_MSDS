import { useEffect, useRef } from "react";
import { FIELD_DEFS, sourceText } from "./data.js";
import { safePdfUrl } from "./model.js";
import { useWorkspace } from "./WorkspaceContext.jsx";
import { Button, Icon, Multiline } from "./ui.jsx";

function Paper({ doc }) {
  const { state } = useWorkspace();
  if (!doc.source) return <div className="empty-state">원문 미리보기가 없습니다.</div>;
  const source = doc.source;
  const highlight = key => state.field === key && state.view === "review" ? " highlighted" : "";
  const scale = state.zoom === "fit" ? 1 : state.zoom / 100;
  if (state.page > 1) return <article className="paper placeholder-page" style={{ "--zoom": scale }}>
    <span className="paper-demo">예시 문서 · 원본 PDF 아님</span><h2>물 질 안 전 보 건 자 료</h2>
    <div className="unavailable-page"><Icon name="document" /><h3>{state.page}쪽 원문 미제공</h3><p>첨부 화면의 1쪽만 재현한 예시입니다.<br />PDF를 업로드하면 실제 원문을 볼 수 있습니다.</p><Button action="first-page">1쪽으로 돌아가기</Button></div>
    <footer>- {state.page} / {doc.page_count} -</footer>
  </article>;
  return <article className="paper" style={{ "--zoom": scale }}>
    <span className="paper-demo">예시 문서 · 원본 PDF 아님</span>
    <h2>물 질 안 전 보 건 자 료</h2><div className="paper-meta"><span>제출번호 : {doc.submission_number}</span><span>개정일자 : {doc.revision_date} (개정번호 3)</span></div>
    <h3>1. 화학제품과 회사에 관한 정보</h3>
    <table className="paper-table"><tbody>
      <tr data-source="product_name"><td>가. 제품명</td><td className={highlight("product_name")}>{source.product_name.value || "자료없음"}</td></tr>
      <tr><td>나. 제품의 권고 용도와<br />　 사용상의 제한</td><td>권고 용도 : {source.recommended_use.value || "자료없음"}<br />사용상의 제한 : {source.use_restrictions.value || "자료없음"}</td></tr>
      <tr><td>다. 공급자 정보</td><td>회사명 : {source.supplier.company_name || "자료없음"}<br />주소 : {source.supplier.address || "자료없음"}<br />긴급전화번호 : {source.supplier.emergency_phone || "자료없음"}</td></tr>
    </tbody></table>
    <h3>2. 유해성·위험성</h3>
    <table className="paper-table"><tbody>
      <tr data-source="ghs_classification"><td>가. 유해성·위험성 분류</td><td className={highlight("ghs_classification")}><Multiline>{sourceText(source, "ghs_classification")}</Multiline></td></tr>
      <tr><td rowSpan={3} className="paper-label">나. 예방조치문구를<br />　 포함한 경고표지 항목</td><td data-source="signal_word" className={highlight("signal_word")}><div className="hazard-symbols">그림문자 {source.signal_word.value ? <><span className="hazard-diamond"><Icon name="flame" /></span><span className="hazard-diamond"><b>!</b></span></> : "자료없음"}<span>신호어 : <b>{source.signal_word.value || "자료없음"}</b></span></div></td></tr>
      <tr><td className="paper-hazards"><div className="paper-subtitle">유해·위험 문구 {state.field === "hazard_statements" && state.view === "review" && <span>유해·위험 문구</span>}</div><div data-source="hazard_statements" className={`source-lines${highlight("hazard_statements")}`}><Multiline>{sourceText(source, "hazard_statements")}</Multiline></div></td></tr>
      <tr><td className="paper-note">예방조치 문구<br /><span>1~3항 핵심 필드 추출 범위에서 제외됩니다.</span></td></tr>
      <tr><td>다. 기타 유해성·위험성</td><td>자료없음</td></tr>
    </tbody></table>
    <h3>3. 구성성분의 명칭 및 함유량</h3>
    <table className="paper-table ingredient-paper"><thead><tr><th>화학물질명</th><th>관용명 및 이명</th><th>CAS 번호 또는 식별번호</th><th>함유량(%)</th></tr></thead><tbody data-source="ingredients" className={highlight("ingredients")}>{source.ingredients.map((item, i) => <tr key={i}><td>{item.chemical_name}</td><td>{doc.id === "demo-1" ? "PGMEA" : "—"}</td><td>{item.cas_number || "—"}</td><td>{item.content || "—"}</td></tr>)}</tbody></table>
    <footer>- 1 / {doc.page_count} -</footer>
  </article>;
}

function SourceText({ doc }) {
  const { state } = useWorkspace();
  const body = useRef(null);
  const field = FIELD_DEFS.find(item => item.key === state.field);
  const rule = doc.rule_results?.[state.field];
  const snippet = doc.reviews?.[state.field]?.evidence?.source_text || rule?.source_text;
  useEffect(() => { if (body.current) body.current.scrollTop = 0; }, [doc.id]);
  return <div className="source-text-view" ref={body}>
    <div className="source-reading-note"><Icon name="document" /><div><strong>추출된 원문 · 1~3항</strong><p>{doc.pdf_url ? "PDF에서 추출한 텍스트입니다." : "PDF 미연결 · 저장된 원문 텍스트로 검토합니다."} 쪽 위치는 제공되지 않았습니다.</p></div></div>
    {snippet && <section className="source-focus" data-source={state.field}><div><span>선택한 필드의 근거</span><b>{field?.label} · {rule?.section || "위치 미제공"}</b></div><pre>{snippet}</pre></section>}
    {doc.source_text?.trim() ? <article className="source-transcript"><header><h3>원문 전체</h3><span>추출 결과와 대조해 주세요</span></header><pre>{doc.source_text}</pre></article> : <div className="extracted-text">{FIELD_DEFS.map(item => <section data-source={item.key} key={item.key} className={`text-section ${item.key === state.field ? "highlighted" : ""}`}><h3>{item.section} · {item.label}</h3><p>{doc.rule_results?.[item.key]?.source_text || (doc.source ? sourceText(doc.source, item.key) : "원문 텍스트가 제공되지 않았습니다.")}</p></section>)}</div>}
  </div>;
}

export default function PreviewPanel({ doc, compact = false }) {
  const { state } = useWorkspace();
  const panelRef = useRef(null);
  const hasOriginal = Boolean(doc.pdf_url || doc.source);
  const activeTab = hasOriginal ? state.sourceTab : "text";
  const pdf = doc.pdf_url && (compact || activeTab === "original") ? safePdfUrl(doc.pdf_url) : null;
  // 브라우저 PDF 뷰어의 썸네일 · 자체 툴바를 숨기고(쪽 이동 · 확대는 위 툴바로), 기본은 폭 맞춤
  const pdfView = state.zoom === "fit" ? "view=FitH" : `zoom=${state.zoom}`;
  const toggleFullscreen = () => document.fullscreenElement === panelRef.current ? document.exitFullscreen() : panelRef.current?.requestFullscreen?.();
  return <section ref={panelRef} className={`panel preview-panel ${compact ? "compact" : ""}`}>
    <div className="panel-toolbar">
      {compact ? <h2>문서 미리보기</h2> : <div className="tabs" role="tablist" aria-label="원문 보기 방식">{["original", "text"].map((tab, i) => <Button action="source-tab" data-tab={tab} key={tab} role="tab" disabled={tab === "original" && !hasOriginal} title={tab === "original" && !hasOriginal ? "원본 PDF가 연결되지 않았습니다" : undefined} aria-selected={activeTab === tab} className={`tab ${activeTab === tab ? "active" : ""}`}>{["원문 보기", "추출 텍스트"][i]}</Button>)}</div>}
      <div className="preview-controls">
        {hasOriginal && <div className="preview-page-control"><Button action="prev-page" className="icon-button" aria-label="이전 페이지" disabled={state.page <= 1}><Icon name="left" /></Button><span className="page-count">{state.page} / {doc.page_count || "—"}</span><Button action="next-page" className="icon-button" aria-label="다음 페이지" disabled={state.page >= (doc.page_count || 1)}><Icon name="right" /></Button></div>}
        {hasOriginal && <div className="preview-zoom-control"><Button action="zoom-out" className="icon-button" aria-label="축소" disabled={state.zoom !== "fit" && state.zoom <= 70}><Icon name="minus" /></Button><Button action="zoom-reset" className="zoom-label" aria-label="폭 맞춤으로 되돌리기" title="폭 맞춤으로 되돌리기">{state.zoom === "fit" ? "폭 맞춤" : `${state.zoom}%`}</Button><Button action="zoom-in" className="icon-button" aria-label="확대" disabled={state.zoom >= 150}><Icon name="plus" /></Button></div>}
        {pdf && <a className="preview-expand preview-open-tab" href={`${pdf}#page=${state.page}`} target="_blank" rel="noopener" aria-label="PDF를 새 탭에서 열기" title="새 탭에서 열기(다운로드 · 인쇄)"><Icon name="download" /></a>}
        <button type="button" className="preview-expand" aria-label="원문 화면 확대" onClick={toggleFullscreen}><Icon name="expand" /></button>
      </div>
    </div>
    {doc.pdf_url && (compact || activeTab === "original") ? (pdf ? <iframe key={`${doc.id}:${state.page}:${state.zoom}`} className="pdf-frame" src={`${pdf}#page=${state.page}&toolbar=0&navpanes=0&${pdfView}`} title={`${doc.file_name} 원본 PDF ${state.page}쪽`} /> : <div className="empty-state">PDF 주소를 확인해 주세요.</div>) :
      (!hasOriginal || (!compact && activeTab === "text")) ? <SourceText doc={doc} /> :
      <div className="pdf-workspace"><aside className="thumbnails" aria-label="페이지 목록">{Array.from({ length: Math.min(doc.page_count || 1, 4) }, (_, i) => <Button action="page" data-page={i + 1} key={i} className={`thumbnail ${state.page === i + 1 ? "active" : ""}`} aria-label={`${i + 1}쪽 보기`} aria-pressed={state.page === i + 1}><span className="mini-paper">{Array.from({ length: 8 }, (_, j) => <i key={j} />)}</span><span>{i + 1}</span></Button>)}</aside><div className="paper-scroll"><Paper doc={doc} /></div></div>}
  </section>;
}
