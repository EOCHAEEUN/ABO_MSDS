import { WorkspaceContext } from "./WorkspaceContext.jsx";
import { useWorkspaceController } from "./useWorkspaceController.js";
import { Button, Icon } from "./ui.jsx";
import ReviewPage from "./ReviewPage.jsx";
import DocumentsPage from "./DocumentsPage.jsx";
import ComparePage from "./ComparePage.jsx";
import WorkspaceDialogs from "./WorkspaceDialogs.jsx";
import capybaraMsds from "./capybara-msds.png";
import msdsLabMark from "./msds-lab-mark.svg";
import "./workspace.css";
import "./review-refresh.css";

const menu = [
  { id: "review", label: "문서 검토", icon: "document" },
  { id: "documents", label: "문서 목록", icon: "list" },
  { id: "compare", label: "실험 비교", icon: "chart" },
];

function Sidebar({ view }) {
  return <aside className="workspace-sidebar">
    <div className="sidebar-primary">
      <a className="sidebar-brand" href="./index.html" aria-label="MSDS Lab 홈"><span className="sidebar-brand-line"><img className="sidebar-logo" src={msdsLabMark} alt="" /><strong>MSDS Lab</strong></span><span className="sidebar-tagline">Materials for a safer tomorrow</span></a>
      <nav className="sidebar-nav" aria-label="작업공간 메뉴">
        {menu.map(item => <a key={item.id} href={`#${item.id}`} className={`sidebar-item ${view === item.id ? "is-active" : ""}`} aria-current={view === item.id ? "page" : undefined}><Icon name={item.icon} /><span>{item.label}</span></a>)}
      </nav>
    </div>
    <div className="sidebar-help-row"><Button action="help" className="sidebar-help"><Icon name="help" />도움말</Button><img className="sidebar-capybara" src={capybaraMsds} alt="" aria-hidden="true" /></div>
  </aside>;
}

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
    <div id="app" className={`app-shell view-${state.view}`}><Sidebar view={state.view} /><div className="workspace-main">{content}</div></div>
    <div id="toast" className={`toast ${state.notice ? "visible" : ""} ${state.notice?.error ? "error" : ""}`} role="status" aria-live="polite">{state.notice?.message || ""}</div>
    <WorkspaceDialogs />
  </WorkspaceContext.Provider>;
}
