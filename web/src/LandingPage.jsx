import "./landing-page.css";

const rows = [
  ["제품명", "PGMEA", "일치", ""],
  ["CAS 번호", "108-65-6", "일치", ""],
  ["GHS 분류", "인화성 액체 · 구분 3", "일치", ""],
  ["신호어", "경고", "일치", ""],
  ["H-code", "H335", "확인", "warn"],
];

function Logo() {
  return (
    <svg className="logo" viewBox="0 0 32 32" fill="none" aria-hidden="true">
      <line x1="16" y1="16" x2="6" y2="7" />
      <line x1="16" y1="16" x2="25" y2="7" />
      <line x1="16" y1="16" x2="27" y2="19" />
      <line x1="16" y1="16" x2="8" y2="25" />
      <line x1="16" y1="16" x2="16" y2="3" />
      <circle cx="16" cy="16" r="3.2" />
      <circle cx="6" cy="7" r="2.5" />
      <circle cx="25" cy="7" r="2.5" />
      <circle cx="27" cy="19" r="2.5" />
      <circle cx="8" cy="25" r="2.5" className="accent" />
      <circle cx="16" cy="3" r="2.5" />
    </svg>
  );
}

function DocumentVisual() {
  return (
    <div className="hero-visual" role="img" aria-label="검토 예시: PGMEA 문서와 추출 결과를 대조합니다. 제품명·CAS·GHS·신호어는 일치하고 원문에 없는 H335는 확인이 필요합니다.">
      <div className="visual-stage" aria-hidden="true">
        <div className="doc-back"></div>
        <div className="doc">
          <h3>물질안전보건자료</h3><div className="sub">Material Safety Data Sheet</div>
          <div className="rule"></div>
          <div className="sec">1. 화학제품과 회사에 관한 정보</div>
          <div className="doc-copy"><b>가. 제품명</b><br /><span className="highlight">프로필렌글리콜 모노메틸에테르 아세테이트 (PGMEA)</span></div>
          <div className="sec">2. 유해성·위험성</div>
          <div className="hazards">
            <div className="diamond"><span><svg viewBox="0 0 24 28" fill="currentColor"><path d="M13 1c2 7-5 8-2 13 2-1 3-3 3-5 5 4 8 8 6 13-2 6-14 7-17 0C0 16 5 11 7 8c-1 5 0 7 2 8C7 9 12 7 13 1Z" /></svg></span></div>
            <div className="diamond"><span className="hazard-exclamation">!</span></div>
          </div>
          <div className="doc-copy"><b>신호어</b> 경고<br /><b>유해·위험 문구</b><br />H226 &nbsp; 인화성 액체 및 증기<br />H336 &nbsp; 졸음 또는 현기증을 일으킬 수 있음</div>
          <div className="sec">3. 구성성분의 명칭 및 함유량</div>
          <table className="doc-table"><tbody><tr><td>화학물질명</td><td>CAS 번호</td><td>함유량(%)</td></tr><tr><td>PGMEA</td><td>108-65-6</td><td>99~100</td></tr></tbody></table>
        </div>
        <div className="connector c1"></div><div className="connector c2"></div>
        <div className="extract-panel">
          <div className="extract-head">추출 결과 <span>원문 근거</span></div>
          {rows.map(([name, value, state, cls]) => (
            <div className={`extract-row ${cls}`} key={name}>
              <div className="name">{name}</div>
              <div>{value}</div>
              <div className="state">{state}</div>
            </div>
          ))}
        </div>
        <span className="visual-caption">원문 대조 · 검토 예시</span>
      </div>
    </div>
  );
}

export default function LandingPage() {
  return (
    <>
      <a className="skip-link" href="#intro">본문 바로가기</a>
      <nav className="nav" aria-label="주 메뉴">
        <div className="wrap nav-inner">
          <a className="brand" href="#top" aria-label="MSDS Lab 홈">
            <Logo />
            MSDS Lab <small>analyze · build · operate</small>
          </a>
          <div className="nav-links"><a href="#intro">프로젝트 소개</a><a href="#review">문서 검토</a><a href="#experiment">실험 비교</a></div>
          <a className="top-cta" href="./workspace.html#review">검토 화면 보기 <span aria-hidden="true">→</span></a>
        </div>
      </nav>

      <header className="hero" id="top">
        <div className="wrap">
          <div className="hero-grid">
            <div className="hero-copy">
              <div className="kicker">MSDS DOCUMENT ANALYSIS</div>
              <h1>MSDS를 읽는 데서<br />끝내지 않습니다.<br /><span>원문과 함께 검토 가능한<br />데이터로 만듭니다.</span></h1>
              <p>제조사마다 다른 형식의 MSDS 1~3항에서 핵심 정보를 구조화하고, 추출값의 원문 근거와 검토 상태를 함께 제공합니다.</p>
              <div className="actions">
                <a className="btn primary" href="./workspace.html#review">검토 화면 보기 <span aria-hidden="true">→</span></a>
                <a className="btn ghost" href="#intro">프로젝트 자세히 보기 <span aria-hidden="true">↓</span></a>
              </div>
              <div className="hero-meta"><div><b>1~3항</b>핵심 정보 추출</div><div><b>Evidence</b>원문 근거와 함께 대조</div><div><b>Multiple formats</b>현행 · 구서식 · 영문 SDS</div></div>
            </div>

            <DocumentVisual />
          </div>
          <div className="hero-strip">
            <div className="strip-item"><div className="strip-icon" aria-hidden="true">▤</div><div><b>1~3항 전용</b><span>필요한 범위만 정확하게</span></div></div>
            <div className="strip-item"><div className="strip-icon" aria-hidden="true">⌕</div><div><b>원문 근거 제공</b><span>페이지 · 문장 단위 확인</span></div></div>
            <div className="strip-item"><div className="strip-icon" aria-hidden="true">⚙</div><div><b>다양한 서식 대응</b><span>현행 · 구서식 · 영문 SDS</span></div></div>
          </div>
        </div>
      </header>

      <main className="editorial" id="intro">
        <div className="wrap">
          <div className="editorial-grid">
            <section className="panel" aria-labelledby="why-title">
              <div className="num">02 WHY</div><h2 id="why-title">제조사마다 같은 정보도<br />다른 위치와 형태로 존재합니다.</h2>
              <p>MSDS는 제조사, 연도, 국가에 따라 항목 구조와 표기가 달라 자동화된 구조화 검토가 필요합니다.</p>
              <div className="doc-variants" aria-hidden="true">
                <div className="mini-doc"><b>현행 MSDS (국문)</b><small>물질안전보건자료</small><div className="mini-line"></div><div className="mini-line short"></div><div className="mini-line"></div><small>1. 화학제품과 회사에 관한 정보</small></div>
                <div className="mini-doc"><b>구서식 MSDS (국문)</b><small>물질안전보건자료</small><div className="mini-line"></div><div className="mini-line short"></div><div className="mini-line"></div><small>1. 화학제품과 회사에 관한 정보</small></div>
                <div className="mini-doc"><b>SDS (영문)</b><small>Safety Data Sheet</small><div className="mini-line"></div><div className="mini-line short"></div><div className="mini-line"></div><small>1. Identification</small></div>
              </div>
            </section>
            <section className="panel" aria-labelledby="extract-title">
              <div className="num">03 WHAT WE EXTRACT</div><h2 id="extract-title">MSDS 1~3항에서<br />이런 정보를 추출합니다.</h2>
              <p>문서 형식이 달라도 핵심 항목의 의미를 이해하고, 일관된 스키마로 구조화합니다.</p>
              <div className="field-map">
                <div className="map-doc" aria-hidden="true"><b>물질안전보건자료</b><div className="mini-line"></div><small className="highlight">가. 제품명 PGMEA</small><div className="mini-line"></div><small>2. 유해성·위험성</small><div className="mini-line short"></div><small>3. 구성성분</small></div>
                <div className="map-chip">제품명</div><div className="map-chip">CAS 번호</div><div className="map-chip">GHS 분류</div><div className="map-chip">신호어</div><div className="map-chip">유해·위험 문구</div>
              </div>
            </section>
            <section className="panel" id="review" aria-labelledby="review-title">
              <div className="num">04 REVIEW EXPERIENCE</div><h2 id="review-title">원문을 보며, 추출값을 함께 검토합니다.</h2>
              <p>추출한 값이 어디에서 왔는지 원문과 나란히 확인하고, 일치 여부와 예외 항목을 쉽게 검토할 수 있습니다.</p>
              <a className="review-shot" href="./workspace.html#review" aria-label="원문과 추출값을 대조하는 문서 검토 화면 열기">
                <div className="review-doc" aria-hidden="true"><div className="mini-line"></div><div className="mini-line short"></div><div className="yellow"></div></div>
                <div className="review-table" aria-hidden="true">
                  <div className="trow"><span>제품명</span><span className="ok">일치</span></div><div className="trow"><span>CAS</span><span className="ok">일치</span></div>
                  <div className="trow"><span>GHS</span><span className="ok">일치</span></div><div className="trow"><span>H226</span><span className="ok">일치</span></div>
                  <div className="trow warn"><span>H335</span><span>확인 필요</span></div>
                </div>
              </a>
            </section>
            <section className="panel" aria-labelledby="exception-title">
              <div className="num">05 EXCEPTION CASE</div><h2 id="exception-title">예외 항목은 명확하게 표시합니다.</h2>
              <p>원문에 근거가 없는 값, 해석이 필요한 항목은 검토가 필요한 상태로 표시합니다.</p>
              <div className="exception-table" role="table" aria-label="예외 항목 검토 예시">
                <div className="ex-row" role="row"><div role="rowheader">제품명</div><div role="cell">PGMEA</div><div role="cell">일치</div></div>
                <div className="ex-row" role="row"><div role="rowheader">신호어</div><div role="cell">경고</div><div role="cell">일치</div></div>
                <div className="ex-row" role="row"><div role="rowheader">H226</div><div role="cell">인화성 액체 및 증기</div><div role="cell">일치</div></div>
                <div className="ex-row warn" role="row"><div role="rowheader">H335</div><div role="cell">호흡기계 자극을 일으킬 수 있음</div><div role="cell">원문 확인</div></div>
              </div>
            </section>
          </div>

          <div className="lower" id="experiment">
            <section className="panel" aria-labelledby="experiment-title">
              <div className="num">06 EXPERIMENT RESULT</div><h2 className="small-title" id="experiment-title">모델 실험 결과</h2>
              <p>Base zero-shot · Base few-shot · QLoRA를 같은 val 문서로 비교합니다.</p>
              {/* 재시작(2026-09-28): 파일럿 수치는 쓰지 않는다. 재시작 val 채점 뒤 report/scores.csv 값으로 채운다. */}
              <div className="table-scroll" role="region" aria-label="모델 실험 결과 표" tabIndex="0">
                <table className="model-table">
                  <thead><tr><th scope="col">모델</th><th scope="col">GHS F1 ↑</th><th scope="col">문서 정답률 ↑</th><th scope="col">스키마 준수율 ↑</th></tr></thead>
                  <tbody>
                    <tr><th scope="row">Base (Zero-shot)</th><td>—</td><td>—</td><td>—</td></tr>
                    <tr><th scope="row">Base (Few-shot, k=2)</th><td>—</td><td>—</td><td>—</td></tr>
                    <tr><th scope="row">QLoRA</th><td>—</td><td>—</td><td>—</td></tr>
                  </tbody>
                </table>
              </div>
              <p className="result-note">평가 전입니다. 결과가 나오면 갱신합니다.</p>
              <a className="text-link" href="./workspace.html#compare">실험 비교 화면 보기 <span aria-hidden="true">→</span></a>
            </section>
            <section className="panel" aria-labelledby="boundary-title">
              <div className="num">07 BOUNDARY</div><h2 className="small-title" id="boundary-title">모델이 하지 않는 일</h2>
              <p>명확한 한계를 정의하여, 자동화와 검토의 균형을 지켰습니다.</p>
              <div className="boundary-list">
                <div className="boundary-item"><span aria-hidden="true">×</span><div><b>화학적 적정성 판단</b><br />분류의 정답 여부를 대신 판단하지 않습니다.</div></div>
                <div className="boundary-item"><span aria-hidden="true">×</span><div><b>원문에 없는 정보 생성</b><br />문서에 없는 H-code를 추정해 채우지 않도록 설계합니다.</div></div>
                <div className="boundary-item"><span aria-hidden="true">×</span><div><b>최종 승인 대체</b><br />사람의 검토와 확정을 대신하지 않습니다.</div></div>
              </div>
            </section>
            <section className="panel" aria-labelledby="visual-title">
              <div className="num">RESULT VISUAL</div><h2 className="small-title" id="visual-title">비교 지표</h2>
              <p>GHS 분류 F1 · val</p>
              <p className="result-note">평가 전입니다. 결과가 나오면 막대그래프로 표시합니다.</p>
            </section>
          </div>
        </div>
      </main>

      <section className="cta" aria-labelledby="cta-title">
        <div className="wrap cta-inner">
          <div><h2 id="cta-title">MSDS 검토를 더 안전하고 빠르게.</h2><p>원문을 근거로, 신뢰할 수 있는 구조화 데이터를 만듭니다.</p></div>
          <a className="btn" href="./workspace.html#review">문서 검토 화면 보기 <span aria-hidden="true">→</span></a>
        </div>
      </section>
      <footer><div className="wrap foot"><strong>MSDS Lab · ABO</strong><span>Analyze · Build · Operate</span></div></footer>
    </>
  );
}
