import { useEffect, useState } from "react";
import { API_MODE } from "./api.js";
import { useWorkspace } from "./WorkspaceContext.jsx";
import { ROUTES, count, effective, status } from "./model.js";
import { iconPaths } from "./icons.jsx";

export function Icon({ name, className = "" }) {
  return <svg className={`icon ${className}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.65" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{iconPaths[name] || iconPaths.document}</svg>;
}

export function Button({ action, children, type = "button", onClick, ...props }) {
  const { onAction } = useWorkspace();
  return <button type={type} {...props} data-action={action} onClick={onClick || (() => onAction(action, props))}>{children}</button>;
}

export function Options({ values, placeholder }) {
  return <>{placeholder && <option value="">{placeholder}</option>}{values.map(value => <option value={value} key={value}>{value}</option>)}</>;
}

export function Badge({ doc }) {
  const text = status(doc);
  return <span className={`badge ${text === "확정" ? "success" : text === "검토 필요" ? "warning" : "neutral"}`}>{text}</span>;
}

export function Progress({ doc }) {
  return <span className="progress-track" role="progressbar" aria-label="담당자 확정" aria-valuemin={0} aria-valuemax={5} aria-valuenow={count(doc)}><span style={{ width: `${count(doc) * 20}%` }} /></span>;
}

export function Multiline({ children }) {
  return <span className="multiline">{children}</span>;
}

export function FieldValue({ doc, field }) {
  const data = effective(doc);
  if (field === "ingredients") return data.ingredients.length ? data.ingredients.map((item, i) => <div key={i}>{item.cas_number || (item.is_substitute_data ? "영업비밀" : "CAS 미기재")}<small className="ingredient-detail">{item.chemical_name}{item.content ? ` · ${item.content}%` : ""}</small></div>) : data.list_status.ingredients;
  if (field === "ghs_classification") return data.ghs_classification.length ? data.ghs_classification.map((item, i) => <div key={i}>{item.hazard_class} : {item.category || "—"}</div>) : data.list_status.ghs_classification;
  if (field === "hazard_statements") return data.hazard_statements.length ? data.hazard_statements.map((item, i) => <div key={i}><b>{item.code || "코드 없음"}</b>　{item.text}</div>) : data.list_status.hazard_statements;
  return data[field].value || data[field].source_status;
}

export function Header() {
  const { state, patch, navigate } = useWorkspace();
  const [query, setQuery] = useState(state.query);
  useEffect(() => setQuery(state.query), [state.query]);
  function search(event) {
    event.preventDefault();
    patch({ query, page: 1 });
    navigate("documents");
  }
  return <header className="topbar">
    <a className="brand" href="./index.html" aria-label="MSDS Lab 홈">MSDS Lab <span>MSDS 구조화 추출·검토</span></a>
    <nav className="main-nav" aria-label="주 메뉴">{Object.entries(ROUTES).map(([key, label]) => <a href={`#${key}`} className={state.view === key ? "active" : ""} aria-current={state.view === key ? "page" : undefined} key={key}>{label}</a>)}</nav>
    <div className="topbar-right">
      <span className={`mode-badge ${API_MODE ? "live" : ""}`}>{API_MODE ? "API 연결" : "예시 모드"}</span>
      <form id="global-search" className="global-search" onSubmit={search}><Icon name="search" /><input name="query" aria-label="전체 문서 검색" placeholder="문서명, 공급자, CAS 번호 검색" value={query} onChange={event => setQuery(event.target.value)} /></form>
      <Button action="help" className="text-button">도움말</Button><Button action="profile" className="text-button user-button">검토 담당자 <Icon name="chevron" /></Button>
    </div>
  </header>;
}

export function DocumentHeader({ doc }) {
  const values = effective(doc);
  const metadata = [["파일명", doc.file_name], ["공급자", values.supplier.company_name || "—"], ["제출번호", doc.submission_number || "—"], ["개정일", doc.revision_date || "—"], ["페이지", doc.page_count ? `${doc.page_count}쪽` : "—"], ["언어", doc.language]];
  return <section className="document-header" aria-label="현재 문서 정보">
    <div className="document-heading"><h1>{values.product_name.value || doc.file_name}</h1><div className="metadata">{metadata.map(([label, value]) => <span key={label}>{label} <b>{value}</b></span>)}</div></div>
    <div className="document-stats"><div className="model-info"><span>모델 <b>{doc.model_name}</b></span><span>생성 <b>{doc.generation_seconds ?? "—"}{doc.generation_seconds == null ? "" : "초"}</b></span><span>출력 <b>{doc.output_tokens ?? "—"}</b> 토큰</span></div>
      <div className="confirmation-info"><span>담당자 확정</span><Progress doc={doc} /><span><b>{count(doc)}</b> / 5 필드</span><strong>{count(doc) * 20}%</strong></div>
    </div>
  </section>;
}
