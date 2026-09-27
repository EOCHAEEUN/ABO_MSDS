import { demoDocuments, DEMO_EXPERIMENTS, emptyExtraction } from './data.js';

const params = new URLSearchParams(location.search);
export const API_MODE = params.get('mode') === 'api';
const STORAGE_KEY = 'msds-lab-demo-v1';

async function request(path, options = {}) {
  const response = await fetch(path, { ...options, signal: AbortSignal.timeout(120000) });
  if (!response.ok) {
    let message = `API 요청 실패 (${response.status})`;
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

function readDemo() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
    if (Array.isArray(saved) && saved.length && saved.every(doc => doc.id && doc.extraction && doc.reviews && Array.isArray(doc.confirmed_fields))) return saved.map(prepareDocument);
  } catch { /* Disabled storage or stale demo data; use the original fixtures. */ }
  return demoDocuments();
}

export const api = {
  async documents() {
    if (!API_MODE) return readDemo();
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
  saveDemo(document) {
    if (API_MODE) return;
    // Browser PDF object URLs expire on reload. Store only built-in demo documents.
    if (document.local_upload) return;
    const saved = readDemo().map(doc => doc.id === document.id ? document : doc);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(saved));
  },
  async extract(file, model) {
    if (API_MODE) {
      const data = new FormData(); data.append('file', file); data.append('model', model);
      const result = await request('/extract', { method: 'POST', body: data });
      if (!result.document?.extraction) throw new Error('추출 응답에 document.extraction이 필요합니다.');
      return prepareDocument(result.document);
    }
    return {
      id: `upload-${crypto.randomUUID()}`, file_name: file.name, number: '—', language: '미확인',
      page_count: null, submission_number: '—', revision_date: '—',
      updated_at: new Date().toLocaleString('ko-KR'), extracted_at: '추출 전', owner: '검토 담당자',
      split: '미지정', model_name: '미실행', generation_seconds: null, output_tokens: null,
      extraction: emptyExtraction(), source: null, reviews: {}, confirmed_fields: [], rule_results: {},
      local_upload: true, pdf_url: URL.createObjectURL(file), pending_extraction: true,
    };
  },
  async compare(documentId, split = 'val', subset = 'all') {
    if (!API_MODE) return { experiments: structuredClone(DEMO_EXPERIMENTS), split: '예시', subset: '예시', executed_at: '2025.08.12 10:24' };
    return request('/compare', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_id: documentId, split, subset }),
    });
  },
};
