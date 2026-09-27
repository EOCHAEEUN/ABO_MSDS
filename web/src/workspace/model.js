export const ROUTES = { review: "문서 검토", documents: "문서 목록", compare: "실험 비교" };
export const current = state => state.documents.find(doc => doc.id === state.selectedId) || state.documents[0];
export const count = doc => doc.confirmed_fields.length;
export const status = doc => doc.pending_extraction ? "추출 대기" : count(doc) === 5 ? "확정" : count(doc) > 1 ? "검토 필요" : "미확정";

export function effective(doc) {
  const extraction = structuredClone(doc.extraction);
  for (const [key, review] of Object.entries(doc.reviews || {})) {
    extraction[key] = structuredClone(review.confirmed_value);
    if (review.list_status) extraction.list_status[key] = review.list_status;
  }
  return extraction;
}

export function filteredDocuments(state) {
  const query = state.query.trim().toLocaleLowerCase();
  return state.documents.filter(doc => {
    const data = effective(doc);
    return (!query || [doc.file_name, data.product_name.value, data.supplier.company_name, ...data.ingredients.map(item => item.cas_number)].join(" ").toLocaleLowerCase().includes(query)) &&
      (!state.filters.supplier || data.supplier.company_name === state.filters.supplier) &&
      (!state.filters.language || doc.language === state.filters.language) &&
      (!state.filters.status || status(doc) === state.filters.status) &&
      (!state.filters.split || doc.split === state.filters.split);
  });
}

export function unverifiedHazard(doc, item) {
  if (doc.reviews.hazard_statements?.resolved && doc.reviews.hazard_statements.confirmed_value.some(value => value.code === item.code && value.text === item.text)) return false;
  if (doc.rule_results?.hazard_statements?.review_status !== "SOURCE_CHECK_REQUIRED") return false;
  const text = doc.rule_results.hazard_statements.source_text || "";
  return !text.includes(item.text) || Boolean(item.code && !text.includes(item.code));
}

export function applyReview(state, id, key, value, extras = {}) {
  const doc = state.documents.find(item => item.id === id);
  if (!doc) return;
  doc.reviews[key] = { confirmed_value: structuredClone(value), confirmed_at: new Date().toISOString(), ...extras };
  if (!doc.confirmed_fields.includes(key)) doc.confirmed_fields.push(key);
  state.dirtyDocuments.add(id);
}

export function safePdfUrl(value) {
  try {
    const url = new URL(value, location.href);
    return ["http:", "https:", "blob:"].includes(url.protocol) ? url.href : "";
  } catch { return ""; }
}

export function download(content, name, type) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const link = document.createElement("a");
  link.href = url;
  link.download = name;
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function downloadDocuments(documents) {
  const cell = value => {
    let text = String(value ?? "");
    if (/^[=+@\-\t\r]/.test(text)) text = "'" + text;
    return '"' + text.replaceAll('"', '""') + '"';
  };
  const rows = [["문서명", "제품명", "공급자", "CAS 번호", "언어", "상태", "검토 진행", "최근 수정일", "담당자"],
    ...documents.map(doc => {
      const data = effective(doc);
      return [doc.file_name, data.product_name.value, data.supplier.company_name, data.ingredients.map(item => item.cas_number).join("; "), doc.language, status(doc), count(doc) + " / 5", doc.updated_at, doc.owner];
    })];
  download("\uFEFF" + rows.map(row => row.map(cell).join(",")).join("\r\n"), "msds-documents.csv", "text/csv;charset=utf-8");
}

export function validateList(key, value, sourceStatus) {
  if (!Array.isArray(value)) throw new Error('JSON 배열 형태로 입력해 주세요.');
  if ((sourceStatus === '기재') !== (value.length > 0)) throw new Error('기재 상태에는 항목이 필요하며, 자료없음·해당없음은 빈 배열이어야 합니다.');
  const schemas = { ingredients: ['chemical_name', 'cas_number', 'ke_number', 'content', 'is_substitute_data'], ghs_classification: ['hazard_class', 'category'], hazard_statements: ['code', 'text'] };
  for (const item of value) {
    const keys = schemas[key];
    if (!item || typeof item !== 'object' || Array.isArray(item) || Object.keys(item).length !== keys.length || keys.some(field => !(field in item))) throw new Error(`각 항목에 ${keys.join(', ')} 키를 정확히 유지해 주세요.`);
    for (const [field, value] of Object.entries(item)) {
      if (field === 'is_substitute_data') { if (typeof value !== 'boolean') throw new Error('is_substitute_data는 true 또는 false여야 합니다.'); }
      else if (value !== null && typeof value !== 'string') throw new Error(`${field}는 문자열 또는 null이어야 합니다.`);
    }
    const required = key === 'ingredients' ? 'chemical_name' : key === 'ghs_classification' ? 'hazard_class' : 'text';
    if (typeof item[required] !== 'string' || !item[required].trim()) throw new Error(`${required}를 입력해 주세요.`);
    if (item.cas_number !== undefined && item.cas_number !== null) {
      const match = /^(\d{2,7})-(\d{2})-(\d)$/.exec(item.cas_number);
      if (!match || [...(match[1] + match[2])].reverse().reduce((sum, digit, i) => sum + Number(digit) * (i + 1), 0) % 10 !== Number(match[3])) throw new Error('CAS 번호의 형식 또는 검증숫자가 올바르지 않습니다.');
    }
    if (item.is_substitute_data && item.cas_number !== null) throw new Error('영업비밀 성분의 CAS 번호는 null이어야 합니다.');
    if (item.ke_number != null && !/^KE-\d{5}$/.test(item.ke_number)) throw new Error('KE 번호는 KE-00000 형식이어야 합니다.');
    if (item.code != null && !/^H\d{3}[A-Za-z]{0,2}(\+H\d{3}[A-Za-z]{0,2})*$/.test(item.code)) throw new Error('H코드 형식을 확인해 주세요.');
    if (item.category != null && !/^구분 \d[A-C]?$/.test(item.category) && !['액화가스', '압축가스', '냉동액화가스', '용해가스'].includes(item.category)) throw new Error('구분은 구분 3, 구분 1A 또는 가스 상태명으로 입력해 주세요.');
  }
}

