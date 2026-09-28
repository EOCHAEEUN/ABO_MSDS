import { WorkspaceContext } from "./WorkspaceContext.jsx";
import { useWorkspaceController } from "./useWorkspaceController.js";
import { Button, Header } from "./ui.jsx";
import ReviewPage from "./ReviewPage.jsx";
import DocumentsPage from "./DocumentsPage.jsx";
import ComparePage from "./ComparePage.jsx";
import WorkspaceDialogs from "./WorkspaceDialogs.jsx";
import "./workspace.css";

export default function Workspace() {
  const controller = useWorkspaceController();
  const { state, doc } = controller;
  let content;
  if (state.loading) content = <main id="main" className="loading-state"><span className="spinner" />문서를 불러오고 있습니다.</main>;
  else if (state.error && !doc) content = <main id="main" className="empty-state error-state"><h1>문서를 불러오지 못했습니다.</h1><p>{state.error}</p><Button action="refresh">다시 시도</Button></main>;
  else if (!doc && state.view !== "documents") content = <main id="main" className="empty-state"><h1>등록된 문서가 없습니다.</h1><p>PDF를 업로드하여 문서 검토를 시작하세요.</p><Button action="upload" className="primary">문서 업로드</Button></main>;
  else content = state.view === "review" ? <ReviewPage doc={doc} /> : state.view === "documents" ? <DocumentsPage /> : <ComparePage doc={doc} />;
  return <WorkspaceContext.Provider value={controller}>
    <a className="skip-link" href="#main">본문으로 이동</a>
    <div id="app" className={`app-shell view-${state.view}`}><Header />{content}</div>
    <div id="toast" className={`toast ${state.notice ? "visible" : ""} ${state.notice?.error ? "error" : ""}`} role="status" aria-live="polite">{state.notice?.message || ""}</div>
    <WorkspaceDialogs />
  </WorkspaceContext.Provider>;
}
