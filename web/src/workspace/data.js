// UI demonstration fixtures, transcribed from the supplied mockup.
// Never read training labels, sealed test data, or report scores here.
export const FIELD_DEFS = [
  { key: 'product_name', label: '제품명', section: '1항 가.' },
  { key: 'ingredients', label: '구성성분 · CAS 번호', section: '3항' },
  { key: 'ghs_classification', label: 'GHS 분류', section: '2항 가.' },
  { key: 'signal_word', label: '신호어', section: '2항 나.' },
  { key: 'hazard_statements', label: '유해·위험 문구', section: '2항 나.' },
];

const products = [
  ['pgmea_msds_kr.pdf', '프로필렌글리콜 모노메틸에테르 아세테이트', '○○케미칼(주)', '108-65-6', '한국어', 16, 4, '김민수'],
  ['acetonitrile_msds.pdf', '아세토니트릴', '△△화학(주)', '75-05-8', '한국어', 12, 2, '이영희'],
  ['methanol_msds_en.pdf', '메탄올', 'Sample Chemicals', '67-56-1', '영어', 14, 5, '박지훈'],
  ['toluene_msds_kr.pdf', '톨루엔', '○○케미칼(주)', '108-88-3', '한국어', 11, 1, '최수진'],
  ['sulfuricacid_msds_kr.pdf', '황산', '□□산업(주)', '7664-93-9', '한국어', 18, 5, '김민수'],
  ['n-hexane_msds_en.pdf', 'n-헥산', 'Example Supplier', '110-54-3', '영어', 13, 3, '이영희'],
  ['ipa_msds_kr.pdf', '이소프로필 알코올', '△△화학(주)', '67-63-0', '한국어', 15, 0, '박지훈'],
  ['hydrochloricacid_msds.pdf', '염화수소 (수용액)', '□□산업(주)', '7647-01-0', '한국어', 20, 5, '최수진'],
];

const stated = value => ({ value, source_status: '기재' });
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
  return products.map(([file, product, supplier, cas, language, pages, confirmed, owner], index) => {
    // Only the first fixture has hazard data supplied by the user's screen.
    // Do not infer chemical classifications for the other document-list fixtures.
    const extraction = {
      ...emptyExtraction(), product_name: stated(product),
      recommended_use: index === 0 ? stated('반도체 공정용 세정제, 희석 용제') : missing(),
      use_restrictions: index === 0 ? stated('권고 용도 외 사용 금지') : missing(),
      supplier: { company_name: supplier, address: index === 0 ? '경기도 ○○시 ○○구 ○○로 123' : null, emergency_phone: index === 0 ? '031-000-0000' : null },
      ingredients: [{ chemical_name: product, cas_number: cas, ke_number: null, content: index === 0 ? '≥99.0' : null, is_substitute_data: false }],
      ghs_classification: index === 0 ? [{ hazard_class: '인화성 액체', category: '구분 3' }, { hazard_class: '특정표적장기 독성(1회 노출)', category: '구분 3' }] : [],
      signal_word: index === 0 ? stated('경고') : missing(),
      hazard_statements: index === 0 ? [
        { code: 'H226', text: '인화성 액체 및 증기' },
        { code: 'H336', text: '졸음 또는 현기증을 일으킬 수 있음' },
        { code: 'H335', text: '호흡기계 자극을 일으킬 수 있음' },
      ] : [],
      list_status: { ingredients: '기재', ghs_classification: index === 0 ? '기재' : '자료없음', hazard_statements: index === 0 ? '기재' : '자료없음' },
    };
    const source = structuredClone(extraction);
    if (index === 0) source.hazard_statements.pop();
    return {
      id: `demo-${index + 1}`, number: 128 - index, file_name: file, language, page_count: pages,
      submission_number: index === 0 ? '○○○○-○○○○○○○○' : `DEMO-2025-00${index + 1}`,
      revision_date: `2025.08.${String(12 - index).padStart(2, '0')}`,
      updated_at: `2025.08.${String(12 - index).padStart(2, '0')} 14:37`,
      extracted_at: '2025.08.12 10:24', owner, split: '예시', model_name: 'QLoRA v1',
      generation_seconds: 7.2, output_tokens: 412, extraction, source, reviews: {},
      confirmed_fields: FIELD_DEFS.slice(0, confirmed).map(field => field.key),
      rule_results: Object.fromEntries(FIELD_DEFS.map(field => [field.key, {
        review_status: index === 0 && field.key === 'hazard_statements' ? 'SOURCE_CHECK_REQUIRED' : 'OK',
        reason_code: null, page: 1, section: field.section,
        source_text: sourceText(source, field.key),
      }])),
    };
  });
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
  { key: 'seconds', label: '생성 시간', unit: '초' },
];
