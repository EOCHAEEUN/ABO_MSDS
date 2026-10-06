import { useRef, useState } from "react";
import { api } from "./api.js";
import { Icon } from "./ui.jsx";
import "./question-page.css";

const EXAMPLES = [
  "등록된 제품 중 인화점이 가장 낮은 제품은?",
  "Kixx PAO 1 SN 0W-30을 취급할 때 필요한 개인보호구는?",
  "Acetone이 눈에 들어갔을 때 응급조치는 어떻게 해야 해?",
  "LOCTITE 648이 누출되면 어떻게 처리해야 해?",
];

const PATH_LABELS = {
  classify: "질문 분류",
  retrieve: "문서 검색",
  grade: "근거 판정",
  rewrite: "검색어 보정",
  generate: "답변 생성",
  fallback: "답변 제한",
};

function cells(line) {
  return line.trim().replace(/^\||\|$/g, "").split("|").map(value => value.trim());
}

function InlineText({ text }) {
  return text.split(/(\*\*[^*]+\*\*)/).map((part, index) => part.startsWith("**") && part.endsWith("**") ? <strong key={index}>{part.slice(2, -2)}</strong> : <span key={index}>{part}</span>);
}

function AnswerContent({ text }) {
  const lines = text.split("\n");
  const blocks = [];
  let index = 0;
  while (index < lines.length) {
    if (!lines[index].trim()) { index += 1; continue; }
    const isTable = lines[index].includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1]);
    if (isTable) {
      const header = cells(lines[index]);
      index += 2;
      const rows = [];
      while (index < lines.length && lines[index].includes("|") && lines[index].trim()) rows.push(cells(lines[index++]));
      blocks.push(<div className="question-table-scroll" key={`table-${index}`}><table><thead><tr>{header.map((value, cell) => <th key={cell}><InlineText text={value} /></th>)}</tr></thead><tbody>{rows.map((row, rowIndex) => <tr key={rowIndex}>{row.map((value, cell) => <td key={cell}><InlineText text={value} /></td>)}</tr>)}</tbody></table></div>);
      continue;
    }
    if (/^\s*[-*]\s+/.test(lines[index])) {
      const items = [];
      while (index < lines.length && /^\s*[-*]\s+/.test(lines[index])) items.push(lines[index++].replace(/^\s*[-*]\s+/, ""));
      blocks.push(<ul key={`list-${index}`}>{items.map((item, itemIndex) => <li key={itemIndex}><InlineText text={item} /></li>)}</ul>);
      continue;
    }
    const paragraph = [];
    while (index < lines.length && lines[index].trim() && !(lines[index].includes("|") && index + 1 < lines.length && /^\s*\|?\s*:?-{3,}/.test(lines[index + 1]))) paragraph.push(lines[index++]);
    blocks.push(<p key={`paragraph-${index}`}>{paragraph.map((line, lineIndex) => <span key={lineIndex}><InlineText text={line} />{lineIndex < paragraph.length - 1 && <br />}</span>)}</p>);
  }
  return <div className="question-answer-copy">{blocks}</div>;
}

export default function QuestionPage() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const input = useRef(null);

  async function submit(event) {
    event?.preventDefault();
    const value = question.trim();
    if (!value || busy) return;
    setBusy(true);
    setError("");
    try {
      setResult(await api.ask(value));
    } catch (issue) {
      setError(issue.message);
    } finally {
      setBusy(false);
    }
  }

  function chooseExample(value) {
    setQuestion(value);
    setError("");
    input.current?.focus();
  }

  return <main id="main" className="question-page">
    <header className="workspace-page-header question-heading">
      <div className="workspace-page-heading"><span className="workspace-page-eyebrow"><Icon name="sparkle" />근거 기반 안전 질의</span><h1 className="workspace-page-title">MSDS 질의</h1><p className="workspace-page-support">등록된 MSDS 1~16항에서 근거를 검색해 답변합니다. 근거가 없으면 추측하지 않습니다.</p></div>
      <span className="question-model-badge"><span className="question-live-dot" />Ollama · LangGraph</span>
    </header>

    <div className="question-content">
      <section className="question-compose panel" aria-labelledby="question-label">
        <form onSubmit={submit}>
          <label id="question-label" htmlFor="msds-question">MSDS에 대해 질문하세요</label>
          <div className="question-input-row">
            <textarea ref={input} id="msds-question" value={question} maxLength={1000} onChange={event => setQuestion(event.target.value)} onKeyDown={event => { if (event.key === "Enter" && !event.shiftKey) { event.preventDefault(); submit(); } }} placeholder="예: 이 제품이 눈에 들어갔을 때 어떻게 해야 하나요?" aria-describedby="question-hint" />
            <button type="submit" className="primary question-submit" disabled={busy || !question.trim()}>{busy ? <span className="spinner" /> : <Icon name="message" />}{busy ? "근거 검색 중" : "질문하기"}</button>
          </div>
          <p id="question-hint">Enter로 질문 · Shift+Enter로 줄바꿈</p>
        </form>
        <div className="question-examples" aria-label="예시 질문"><span>예시 질문</span><div>{EXAMPLES.map(example => <button type="button" key={example} onClick={() => chooseExample(example)} disabled={busy}>{example}</button>)}</div></div>
      </section>

      {error && <div className="question-error" role="alert"><Icon name="info" /><div><strong>답변을 만들지 못했습니다.</strong><p>{error}</p></div></div>}

      <section className={`question-result ${result ? "has-result" : ""}`} aria-live="polite" aria-busy={busy}>
        {!result && !busy ? <div className="question-empty"><span><Icon name="message" /></span><h2>문서에 근거한 답변을 확인하세요</h2><p>답변과 함께 검색한 MSDS 항목, 실행 경로를 표시합니다.</p></div> : busy ? <div className="question-loading"><span className="spinner" /><strong>관련 제품과 항목을 찾고 있습니다.</strong><p>질문 분류 → 문서 검색 → 근거 판정 → 답변 생성을 진행합니다.</p></div> : <>
          <article className="question-answer panel">
            <div className="question-panel-title"><span><Icon name="sparkle" /></span><div><h2>답변</h2><p>아래 내용은 표시된 MSDS 근거만 사용했습니다.</p></div></div>
            <AnswerContent text={result.answer} />
          </article>

          <aside className="question-trace panel">
            <div className="question-panel-title"><span><Icon name="target" /></span><div><h2>실행 경로</h2><p>LangGraph가 거친 단계</p></div></div>
            <ol>{result.path.map((step, index) => <li key={`${step}-${index}`}><span>{index + 1}</span><strong>{PATH_LABELS[step] || step}</strong></li>)}</ol>
          </aside>

          <section className="question-evidence panel">
            <div className="question-panel-title"><span><Icon name="document" /></span><div><h2>검색된 근거</h2><p>{result.evidence.length}개 문서 조각</p></div></div>
            {result.evidence.length ? <div className="question-evidence-list">{result.evidence.map((item, index) => <details key={`${item.doc_id}-${item.section}-${index}`} open={index === 0}>
              <summary><span className="question-evidence-number">{index + 1}</span><span><strong>{item.product_name}</strong><small>{item.section ? `${item.section}. ${item.section_title}` : item.section_title}{item.doc_id ? ` · ${item.doc_id}` : ""}</small></span><Icon name="chevron" /></summary>
              <p>{item.content}</p>
            </details>)}</div> : <p className="question-no-evidence">검색된 근거 없이 제한 안내가 생성되었습니다.</p>}
          </section>
        </>}
      </section>
    </div>
  </main>;
}
