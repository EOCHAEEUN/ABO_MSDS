import { demoDocuments, DEMO_EXPERIMENTS } from './data.js';

const params = new URLSearchParams(location.search);
export const API_MODE = params.get('mode') === 'api';
const STORAGE_KEY = 'msds-lab-demo-v1';
const RESULTS_KEY = 'msds-lab-results-v1';
const RESULTS_URL = './results/';

// 데이터 출처: api(서버) · results(저장된 val 실험 결과, python3 -m app.web_results로 생성) · demo(가상 예시)
export const source = { mode: API_MODE ? 'api' : 'demo', skipped: [], note: '', stamp: '', docs: [] };

async function readJson(name) {
  const response = await fetch(`${RESULTS_URL}${name}`, { cache: 'no-store' });
  const type = response.headers.get('content-type') || '';
  if (!response.ok || !type.includes('json')) return null;  // 결과 파일이 없으면 예시 데이터로
  return response.json();
}

async function request(path, options = {}, timeoutMs = 120000) {
  let response;
  try {
    response = await fetch(path, { ...options, signal: AbortSignal.timeout(timeoutMs) });
  } catch (issue) {
    if (path === '/extract') throw new Error(issue.name === 'TimeoutError' ? '추출 시간이 초과되었습니다. 서버 상태를 확인해 주세요.' : '추출 서버에 연결할 수 없습니다. 서버 실행 상태를 확인해 주세요.');
    if (path === '/ask') throw new Error(issue.name === 'TimeoutError' ? '답변 생성 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.' : '질의응답 서버에 연결할 수 없습니다. FastAPI 서버 상태를 확인해 주세요.');
    throw issue;
  }
  if (!response.ok) {
    let message = path === '/extract' ? `추출 서버 오류 (${response.status}). 서버 실행 상태를 확인해 주세요.` : `API 요청 실패 (${response.status})`;
    try { const body = await response.json(); if (typeof body.detail === 'string') message = body.detail; } catch { /* Non-JSON server error. */ }
    throw new Error(message);
  }
  if (response.status === 204) return null;
  const type = response.headers.get('content-type') || '';
  if (!type.includes('application/json')) throw new Error('API가 JSON 응답을 반환하지 않았습니다. 서버 연결을 확인해 주세요.');
  return response.json();
}

function prepareDocument(document) {
  const data = document?.extraction;
  if (document?.id == null || !document.file_name || !data?.product_name || !data?.signal_word || !data?.supplier || !data?.list_status || !data?.recommended_use || !data?.use_restrictions || !['ingredients', 'ghs_classification', 'hazard_statements'].every(key => Array.isArray(data[key]))) {
    throw new Error('문서 응답 구조가 올바르지 않습니다. web/README.md의 Document 계약을 확인해 주세요.');
  }
  return { ...document, id: String(document.id), number: document.number ?? document.id, reviews: document.reviews || {}, confirmed_fields: document.confirmed_fields || [], rule_results: document.rule_results || {}, source: document.source || null };
}

async function readResults() {
  let data;
  try { data = await readJson('documents.json'); } catch { return null; }
  if (!Array.isArray(data?.documents) || !data.documents.length) return null;
  const docs = data.documents.map(prepareDocument);
  source.mode = 'results';
  source.skipped = data.skipped || [];
  // 브라우저에 저장한 검토값은 같은 결과 파일에서 만든 것일 때만 다시 쓴다
  source.stamp = data.stamp || docs.map(doc => doc.id).join('|');  // 결과 파일 내용이 바뀌면 저장본을 버림
  source.docs = docs;
  try {
    const saved = JSON.parse(localStorage.getItem(RESULTS_KEY));
    if (saved?.stamp === source.stamp && Array.isArray(saved.documents)) source.docs = saved.documents.map(prepareDocument);
  } catch { /* 저장소를 쓸 수 없으면 결과 파일 그대로 */ }
  return source.docs;
}

function readDemo() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (Array.isArray(saved) && saved.length && saved.every(doc => doc.id && doc.extraction && doc.reviews && Array.isArray(doc.confirmed_fields))) return saved.map(prepareDocument);
  } catch { /* Disabled storage or stale demo data; use the original fixtures. */ }
  return demoDocuments();
}

export const api = {
  database(table = 'msds_documents', offset = 0, limit = 25) {
    const query = new URLSearchParams({ table, offset: String(offset), limit: String(limit) });
    return request(`/data?${query}`);
  },
  async documents() {
    if (!API_MODE) {
      const results = await readResults();
      if (results) return results;
      source.mode = 'demo';
      return readDemo();
    }
    const result = await request('/documents');
    if (!Array.isArray(result.documents)) throw new Error('문서 목록 응답에 documents 배열이 필요합니다. web/README.md의 연동 명세를 확인해 주세요.');
    return result.documents.map(prepareDocument);
  },
  async confirm(document, reviews, confirmedFields) {
    if (!API_MODE) return;
    return request('/confirm', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_id: document.id, reviews, confirmed_fields: confirmedFields }),
    });
  },
  async setOwner(document, owner) {
    if (API_MODE) {
      return request('/owner', {
        method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ document_id: document.id, owner }),
      });
    }
    // 서버가 없으면 이 브라우저에만 저장한다. 담당자만 바꿔 저장해 확정하지 않은 검토값은 섞지 않는다.
    if (document.local_upload) return;
    const apply = docs => docs.map(doc => doc.id === document.id ? { ...doc, owner } : doc);
    try {
      if (source.mode === 'results') {
        source.docs = apply(source.docs);
        localStorage.setItem(RESULTS_KEY, JSON.stringify({ stamp: source.stamp, documents: source.docs }));
      } else {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(apply(readDemo())));
      }
    } catch { /* 저장소를 쓸 수 없으면 화면에서만 바뀜 */ }
  },
  saveDemo(document) {
    if (API_MODE) return;
    // Browser PDF object URLs expire on reload. Store only built-in demo documents.
    if (document.local_upload) return;
    if (source.mode === 'results') {
      source.docs = source.docs.map(doc => doc.id === document.id ? document : doc);
      try { localStorage.setItem(RESULTS_KEY, JSON.stringify({ stamp: source.stamp, documents: source.docs })); } catch { /* 저장 실패는 화면 동작에 영향 없음 */ }
      return;
    }
    const saved = readDemo().map(doc => doc.id === document.id ? document : doc);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
  },
  async extract(file, model) {
    const data = new FormData(); data.append('file', file); data.append('model', model);
    const result = await request('/extract', { method: 'POST', body: data }, 600000);
    if (!result.document?.extraction) throw new Error('추출 응답에 document.extraction이 필요합니다.');
    return prepareDocument(result.document);
  },
  async compare(documentId, split = 'val', subset = 'all') {
    if (!API_MODE) {
      let result = null;
      try { result = await readJson('compare.json'); } catch { /* 결과 파일 없음 → 예시 */ }
      if (Array.isArray(result?.experiments) && result.experiments.length) { source.note = result.note || ''; return result; }
      return { experiments: structuredClone(DEMO_EXPERIMENTS), split: '예시', subset: '예시', executed_at: '2025.08.12 10:24' };
    }
    const result = await request('/compare', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_id: documentId, split, subset }),
    });
    source.note = result?.note || '';
    return result;
  },
  async ask(question) {
    const result = await request('/ask', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ question }),
    }, 180000);
    if (typeof result?.answer !== 'string' || !Array.isArray(result.path) || !Array.isArray(result.evidence)) {
      throw new Error('질의응답 결과 형식이 올바르지 않습니다.');
    }
    return result;
  },
};
