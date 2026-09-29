// 예시 모드 데이터: data/labels(train·val 정답 라벨) + data/text(원문 1~3항 텍스트)로
// scripts/build_demo_documents.py가 만든 실제 문서 45건. 재생성하려면 그 스크립트를 다시
// 돌리고 demo-documents.json을 갱신한다. source(종이 모양 mock)는 없고 대신 source_text에
// 원문 전체가 들어 있어 PreviewPanel이 "원문 전체 / 추출 결과와 대조" 화면으로 보여준다.
import demoDocumentsData from './demo-documents.json';

export const FIELD_DEFS = [
  { key: 'product_name', label: '제품명', section: '1항 가.' },
  { key: 'ingredients', label: '구성성분 · CAS 번호', section: '3항' },
  { key: 'ghs_classification', label: 'GHS 분류', section: '2항 가.' },
  { key: 'signal_word', label: '신호어', section: '2항 나.' },
  { key: 'hazard_statements', label: '유해·위험 문구', section: '2항 나.' },
];

const missing = () => ({ value: null, source_status: '자료없음' });

export function emptyExtraction() {
  return {
    product_name: missing(), recommended_use: missing(), use_restrictions: missing(),
    supplier: { company_name: null, address: null, emergency_phone: null },
    ingredients: [], ghs_classification: [], signal_word: missing(), hazard_statements: [],
    list_status: { ingredients: '자료없음', ghs_classification: '자료없음', hazard_statements: '자료없음' },
  };
}

export function demoDocuments() {
  return demoDocumentsData.map(doc => structuredClone(doc));
}

export function sourceText(extraction, field) {
  if (field === 'ingredients') return extraction.ingredients.map(item => `${item.chemical_name}  ${item.cas_number || 'CAS 미기재'}  ${item.content || ''}`).join('\n');
  if (field === 'ghs_classification') return extraction.ghs_classification.map(item => `${item.hazard_class} : ${item.category || ''}`).join('\n') || '자료없음';
  if (field === 'hazard_statements') return extraction.hazard_statements.map(item => `${item.code || ''}  ${item.text}`).join('\n') || '자료없음';
  return extraction[field]?.value || extraction[field]?.source_status || '자료없음';
}

export const DEMO_EXPERIMENTS = [
  { id: 'base_zs', name: 'Base Zero-shot', short: 'Base Zero-shot', condition: '기본 프롬프트', parsing: 74.2, schema: 68.1, cas: 71.4, pair: 62.7, hcode: 58.3, seconds: 12.5, tokens: 298 },
  { id: 'base_fs', name: 'Base Few-shot (k=2)', short: 'Base Few-shot (k=2)', condition: '예시 2건 포함', parsing: 86.1, schema: 82.3, cas: 85.6, pair: 78.4, hcode: 72.1, seconds: 9.1, tokens: 356 },
  { id: 'qlora_r1', name: 'QLoRA r16 1epoch', short: 'QLoRA r16 1epoch', condition: 'r=16, 1 epoch', parsing: 94.7, schema: 91.8, cas: 92.1, pair: 88.9, hcode: 84.6, seconds: 7.4, tokens: 401 },
  { id: 'qlora_r2', name: 'QLoRA r16 2epoch', short: 'QLoRA r16 2epoch', condition: 'r=16, 2 epoch', parsing: 97.8, schema: 95.3, cas: 96.4, pair: 93.1, hcode: 89.7, seconds: 6.8, tokens: 412 },
];

export const METRICS = [
  { key: 'parsing', label: '파싱률', unit: '%' },
  { key: 'schema', label: '스키마 준수율', unit: '%' },
  { key: 'cas', label: 'CAS F1', unit: '%' },
  { key: 'pair', label: 'pair F1', unit: '%' },
  { key: 'hcode', label: 'H-code F1', unit: '%' },
  { key: 'ghs', label: 'GHS 분류 F1', unit: '%', optional: true },
  { key: 'exact', label: '문서 완전 정답', unit: '%', optional: true },
  { key: 'seconds', label: '생성 시간', unit: '초' },
];
