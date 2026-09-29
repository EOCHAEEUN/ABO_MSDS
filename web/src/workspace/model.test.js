import test from 'node:test';
import assert from 'node:assert/strict';
import { canConfirmMatched, reviewBadge } from './model.js';

test('근거 없는 OK는 대조 완료로 표시하거나 일괄 확정하지 않는다', () => {
  const rule = { review_status: 'OK', source_text: '  ' };
  const doc = { rule_results: { product_name: rule }, confirmed_fields: [], reviews: {} };
  assert.equal(canConfirmMatched(doc, 'product_name'), false);
  assert.deepEqual(reviewBadge(rule), { label: '근거 확인 필요', tone: 'pending' });
});

test('근거가 있는 OK 항목은 원문일치로 표시하고 일괄 확정할 수 있다', () => {
  const rule = { review_status: 'OK', source_text: '제품명: 테스트' };
  const doc = { rule_results: { product_name: rule }, confirmed_fields: [], reviews: {} };
  assert.equal(canConfirmMatched(doc, 'product_name'), true);
  assert.equal(reviewBadge(rule).label, '원문일치');
  assert.equal(canConfirmMatched({ ...doc, pending_extraction: true }, 'product_name'), false);
  assert.equal(canConfirmMatched({ ...doc, confirmed_fields: ['product_name'] }, 'product_name'), false);
});

test('검토 필요 항목은 원문 근거가 있어도 일괄 확정하지 않는다', () => {
  for (const status of ['REVIEW_REQUIRED', 'SOURCE_CHECK_REQUIRED', 'SCHEMA_ERROR']) {
    const rule = { review_status: status, source_text: '일부 근거' };
    assert.equal(canConfirmMatched({ rule_results: { ingredients: rule }, confirmed_fields: [] }, 'ingredients'), false);
    assert.equal(reviewBadge(rule).tone, 'warning');
  }
});

test('항목 제목 줄만 있는 근거(값 없음)는 통과로 표시하거나 일괄 확정하지 않는다', () => {
  const rule = { review_status: 'OK', source_text: '가. 유해성·위험성 분류\n나. 예방조치 문구', source_kind: 'section' };
  const doc = { rule_results: { ghs_classification: rule }, confirmed_fields: [], reviews: {} };
  assert.equal(canConfirmMatched(doc, 'ghs_classification'), false);
  assert.equal(reviewBadge(rule).label, '근거 확인 필요');
});

test('검사 결과 없음과 담당자 확정을 구분한다', () => {
  assert.equal(reviewBadge(undefined).label, '대조 대기');
  assert.equal(reviewBadge(undefined, true).label, '담당자 확인');
});
