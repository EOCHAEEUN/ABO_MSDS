import { useCallback, useEffect, useRef, useState } from "react";
import { api, API_MODE, source } from "./api.js";
import { FIELD_DEFS } from "./data.js";
import { ROUTES, applyReview, canConfirmMatched, count, current, download, downloadDocuments, effective, filteredDocuments, unverifiedHazard } from "./model.js";

function initialState() {
  return {
    view: ROUTES[location.hash.slice(1)] ? location.hash.slice(1) : "review",
    documents: [], selectedId: null, field: "hazard_statements", sourceTab: "original", resultTab: "fields",
    page: 1, zoom: "fit", query: new URLSearchParams(location.search).get("search") || "",
    filters: { supplier: "", language: "", status: "", split: "" },
    checked: new Set(), columns: { submission: true, language: true, pages: true, owner: true },
    onlyPending: false, experiments: [], selectedExperiment: "qlora_r2", metric: "parsing", trend: "parsing",
    compareAt: "", compareSplit: API_MODE ? "val" : "예시", compareSubset: "all",
    loading: true, busy: false, error: "", dirtyDocuments: new Set(), modal: null, notice: null, scrollRequest: 0,
  };
}

export function useWorkspaceController() {
  const [state, setState] = useState(initialState);
  const latest = useRef(state);
  const alive = useRef(true);
  const docsRequest = useRef(0);
  const compareRequest = useRef(0);
  const compareAttempt = useRef("");
  const toastTimer = useRef(null);

  const update = useCallback(recipe => {
    if (!alive.current) return;
    const next = structuredClone(latest.current);
    recipe(next);
    latest.current = next;
    setState(next);
  }, []);
  const patch = useCallback(values => update(next => Object.assign(next, values)), [update]);
  const notify = useCallback((message, error = false) => {
    clearTimeout(toastTimer.current);
    patch({ notice: { message, error } });
    toastTimer.current = setTimeout(() => patch({ notice: null }), 4500);
  }, [patch]);
  const navigate = useCallback(view => {
    if (location.hash !== `#${view}`) location.hash = view;
    else patch({ view, page: 1 });
  }, [patch]);
  const closeModal = useCallback(() => patch({ modal: null }), [patch]);

  const selectDocument = useCallback(id => {
    if (latest.current.selectedId !== id) compareAttempt.current = "";
    update(next => {
      if (next.selectedId !== id) { next.experiments = []; next.compareAt = ""; }
      next.selectedId = id;
      // 문서를 바꾸면 지금 보고 있는 필드의 근거 쪽으로 연다
      const doc = next.documents.find(item => item.id === id);
      next.page = doc?.reviews?.[next.field]?.evidence?.page || doc?.rule_results?.[next.field]?.page || 1;
    });
  }, [update]);

  const selectField = useCallback(key => {
    const doc = current(latest.current);
    update(next => {
      next.field = key;
      next.page = doc?.reviews?.[key]?.evidence?.page || doc?.rule_results?.[key]?.page || 1;
      next.scrollRequest += 1;
    });
  }, [update]);

  const loadDocuments = useCallback(async () => {
    const request = ++docsRequest.current;
    patch({ busy: true });
    try {
      const docs = await api.documents();
      if (request !== docsRequest.current || !alive.current) return;
      latest.current.documents.filter(doc => doc.local_upload && !docs.some(item => item.id === doc.id)).forEach(doc => URL.revokeObjectURL(doc.pdf_url));
      compareAttempt.current = "";
      update(next => {
        next.documents = docs;
        const retainedSelection = docs.some(doc => doc.id === next.selectedId);
        next.selectedId = retainedSelection ? next.selectedId : docs[0]?.id;
        if (!retainedSelection && source.mode === "results") next.field = "product_name";
        next.error = "";
        next.dirtyDocuments.clear();
        next.checked = new Set([...next.checked].filter(id => docs.some(doc => doc.id === id)));
        next.experiments = [];
        next.compareAt = "";
        next.page = 1;
      });
      if (source.mode === "results" && source.skipped.length) {
        notify(`파싱 실패 등으로 목록에서 뺀 결과 ${source.skipped.length}건: ${source.skipped.map(item => `${item.condition} · ${item.doc_id}`).join(", ")}`);
      }
    } catch (error) {
      if (request === docsRequest.current && alive.current) { patch({ error: error.message }); notify(error.message, true); }
    } finally {
      if (request === docsRequest.current && alive.current) patch({ loading: false, busy: false });
    }
  }, [patch, update, notify]);

  const loadCompare = useCallback(async () => {
    const snapshot = latest.current;
    const doc = current(snapshot);
    if (!doc || snapshot.busy) return;
    const request = ++compareRequest.current;
    compareAttempt.current = `${doc.id}|${snapshot.compareSplit}|${snapshot.compareSubset}`;
    patch({ busy: true });
    try {
      const result = await api.compare(doc.id, snapshot.compareSplit, snapshot.compareSubset);
      if (request !== compareRequest.current || current(latest.current)?.id !== doc.id || !alive.current) return;
      if (!Array.isArray(result.experiments) || result.experiments.some(item => !item.id || ["parsing", "schema", "cas", "pair", "hcode", "seconds", "tokens"].some(key => !Number.isFinite(item[key])))) throw new Error("실험 결과 형식이 올바르지 않습니다.");
      update(next => {
        next.experiments = result.experiments;
        next.compareAt = result.executed_at || "—";
        next.compareSplit = result.split || next.compareSplit;
        next.compareSubset = result.subset || next.compareSubset;
        if (!result.experiments.some(item => item.id === next.selectedExperiment)) next.selectedExperiment = result.experiments.at(-1)?.id;
      });
      compareAttempt.current = `${doc.id}|${latest.current.compareSplit}|${latest.current.compareSubset}`;
    } catch (error) {
      if (request === compareRequest.current && current(latest.current)?.id === doc.id && alive.current) notify(error.message, true);
    } finally {
      if (request === compareRequest.current && alive.current) patch({ busy: false });
    }
  }, [notify, patch, update]);

  const commitReview = useCallback((id, key, value, extras = {}) => {
    update(next => applyReview(next, id, key, value, extras));
  }, [update]);

  const toggleConfirm = useCallback((key, checked) => {
    const snapshot = latest.current;
    const doc = current(snapshot);
    if (!doc || snapshot.busy || doc.pending_extraction) return;
    const values = effective(doc);
    if (checked) {
      if (key === "hazard_statements" && values[key].some(item => unverifiedHazard(doc, item))) return;
      commitReview(doc.id, key, values[key], { ...(Array.isArray(values[key]) ? { list_status: values.list_status[key] } : {}), ...doc.reviews[key] });
    } else update(next => {
      const target = next.documents.find(item => item.id === doc.id);
      target.confirmed_fields = target.confirmed_fields.filter(field => field !== key);
      next.dirtyDocuments.add(doc.id);
    });
  }, [commitReview, update]);

  const saveReviews = useCallback(async () => {
    const snapshot = latest.current;
    const doc = current(snapshot);
    if (!doc || snapshot.busy || doc.pending_extraction) return;
    if (count(doc) !== 5) {
      selectField(FIELD_DEFS.find(item => !doc.confirmed_fields.includes(item.key)).key);
      notify(`미확정 ${5 - count(doc)}개 필드를 먼저 검토해 주세요.`, true);
      return;
    }
    patch({ busy: true });
    try {
      const saved = structuredClone(doc);
      await api.confirm(saved, saved.reviews, saved.confirmed_fields);
      saved.updated_at = new Date().toLocaleString("sv-SE").replaceAll("-", ".");
      api.saveDemo(saved);
      update(next => {
        const target = next.documents.find(item => item.id === saved.id);
        if (target) target.updated_at = saved.updated_at;
        next.dirtyDocuments.delete(saved.id);
      });
      notify(API_MODE ? "검토 결과를 서버에 저장했습니다." : "검토 결과를 이 브라우저에 저장했습니다.");
    } catch (error) { notify(`저장하지 못했습니다. ${error.message}`, true); }
    finally { patch({ busy: false }); }
  }, [notify, patch, selectField, update]);

  const uploadFile = useCallback(async (file, model) => {
    if (!file?.size || !/\.pdf$/i.test(file.name)) throw new Error("PDF 파일을 선택해 주세요.");
    if (file.size > 30 * 1024 * 1024) throw new Error("30MB 이하의 PDF 파일을 선택해 주세요.");
    const magic = new TextDecoder().decode(await file.slice(0, 5).arrayBuffer());
    if (magic !== "%PDF-") throw new Error("유효한 PDF 파일이 아닙니다. 파일 내용을 확인해 주세요.");
    patch({ busy: true });
    try {
      const doc = await api.extract(file, model);
      if (!alive.current) { if (doc.local_upload) URL.revokeObjectURL(doc.pdf_url); return; }
      compareAttempt.current = "";
      update(next => {
        next.documents.unshift(doc);
        next.selectedId = doc.id;
        next.experiments = [];
        next.compareAt = "";
        next.page = 1;
        next.modal = null;
        next.error = "";
      });
      navigate("review");
      notify(API_MODE ? "문서를 추출했습니다." : "로컬 PDF를 열었습니다. 실제 추출에는 API 연결이 필요합니다.");
    } finally { patch({ busy: false }); }
  }, [navigate, notify, patch, update]);

  const onAction = useCallback(async (action, props = {}) => {
    const snapshot = latest.current;
    const doc = current(snapshot);
    const modal = (type, extras = {}) => patch({ modal: { type, documentId: doc?.id, ...extras } });
    try {
      switch (action) {
        case "help": case "profile": case "columns": modal(action); break;
        case "upload": if (!snapshot.busy) modal("upload"); break;
        case "keep-hazard": modal("evidence"); break;
        case "compare-options": modal("compare"); break;
        case "edit-field": modal("edit", { field: props["data-field"] }); break;
        case "close-modal": closeModal(); break;
        case "source-tab": patch({ sourceTab: props["data-tab"] }); break;
        case "result-tab": patch({ resultTab: props["data-tab"] }); break;
        case "field": selectField(props["data-field"]); break;
        case "prev-field": case "next-field": {
          const index = FIELD_DEFS.findIndex(field => field.key === snapshot.field);
          selectField(FIELD_DEFS[Math.max(0, Math.min(4, index + (action === "prev-field" ? -1 : 1)))].key); break;
        }
        // "fit"은 PDF 폭 맞춤(기본). 확대 · 축소를 누르면 100%에서 10%씩 움직이고, 가운데 버튼은 폭 맞춤으로 되돌린다
        case "zoom-in": patch({ zoom: snapshot.zoom === "fit" ? 110 : Math.min(150, snapshot.zoom + 10) }); break;
        case "zoom-out": patch({ zoom: snapshot.zoom === "fit" ? 90 : Math.max(70, snapshot.zoom - 10) }); break;
        case "zoom-reset": patch({ zoom: "fit" }); break;
        case "first-page": patch({ page: 1 }); break;
        case "page": patch({ page: Number(props["data-page"]) }); break;
        case "prev-page": patch({ page: Math.max(1, snapshot.page - 1) }); break;
        case "next-page": {
          const filtered = filteredDocuments(snapshot);
          const target = snapshot.view === "documents" ? filtered.find(item => item.id === snapshot.selectedId) || filtered[0] : doc;
          patch({ page: Math.min(target?.page_count || 1, snapshot.page + 1) }); break;
        }
        case "show-all": patch({ onlyPending: false }); break;
        case "confirm-matched": {
          if (!doc || snapshot.busy || doc.pending_extraction) break;
          const keys = FIELD_DEFS.filter(field => canConfirmMatched(doc, field.key)).map(field => field.key);
          if (!keys.length) { notify("근거가 제공된 검사 통과 항목이 없습니다."); break; }
          update(next => {
            const target = next.documents.find(item => item.id === doc.id);
            const values = effective(target);
            for (const key of keys) applyReview(next, doc.id, key, values[key], Array.isArray(values[key]) ? { list_status: values.list_status[key] } : {});
          });
          notify(`근거가 제공된 검사 통과 항목 ${keys.length}개를 확정했습니다.`);
          break;
        }
        case "delete-hazard": {
          if (snapshot.busy) break;
          const values = effective(doc).hazard_statements;
          values.splice(Number(props["data-index"]), 1);
          const warning = values.some(item => unverifiedHazard(doc, item));
          update(next => {
            applyReview(next, doc.id, "hazard_statements", values, { resolved: !warning, list_status: values.length ? "기재" : "자료없음" });
            if (warning) next.documents.find(item => item.id === doc.id).confirmed_fields = doc.confirmed_fields.filter(key => key !== "hazard_statements");
          });
          notify("문구를 삭제했습니다. 검토 완료 후 저장해 주세요."); break;
        }
        case "save": await saveReviews(); break;
        case "download-json": case "download-raw":
          if (doc) {
            const raw = action === "download-raw";
            download(JSON.stringify(raw ? doc.extraction : effective(doc), null, 2), doc.file_name.replace(/\.pdf$/i, "") + (raw ? ".model-original.json" : ".json"), "application/json");
            if (!raw) notify("현재 검토값을 JSON으로 다운로드했습니다.");
          }
          break;
        case "select-document": selectDocument(props["data-id"]); break;
        case "open-review": selectDocument(props["data-id"]); navigate("review"); break;
        case "go-review": navigate("review"); break;
        case "reset-filters": patch({ query: "", filters: { supplier: "", language: "", status: "", split: "" }, page: 1 }); break;
        case "refresh":
          if (snapshot.dirtyDocuments.size || snapshot.documents.some(item => item.local_upload)) modal("refresh");
          else await loadDocuments();
          break;
        case "reload-confirmed": closeModal(); await loadDocuments(); break;
        case "download-list": {
          const docs = snapshot.checked.size ? snapshot.documents.filter(item => snapshot.checked.has(item.id)) : filteredDocuments(snapshot);
          if (docs.length) downloadDocuments(docs); else notify("다운로드할 문서가 없습니다.");
          break;
        }
        case "select-experiment": patch({ selectedExperiment: props["data-id"] }); break;
        case "trend": patch({ trend: props["data-metric"] }); break;
        case "load-compare": await loadCompare(); break;
        default: break;
      }
    } catch (error) { notify(error.message, true); }
  }, [patch, closeModal, commitReview, selectDocument, selectField, navigate, update, notify, loadDocuments, loadCompare, saveReviews]);

  useEffect(() => {
    alive.current = true;
    loadDocuments();
    const hashChange = () => patch({ view: ROUTES[location.hash.slice(1)] ? location.hash.slice(1) : "review", page: 1, modal: null });
    const beforeUnload = event => { if (latest.current.dirtyDocuments.size) { event.preventDefault(); event.returnValue = ""; } };
    window.addEventListener("hashchange", hashChange);
    window.addEventListener("beforeunload", beforeUnload);
    return () => {
      alive.current = false;
      docsRequest.current += 1;
      compareRequest.current += 1;
      clearTimeout(toastTimer.current);
      window.removeEventListener("hashchange", hashChange);
      window.removeEventListener("beforeunload", beforeUnload);
      latest.current.documents.filter(doc => doc.local_upload).forEach(doc => URL.revokeObjectURL(doc.pdf_url));
    };
  }, [loadDocuments, patch]);

  useEffect(() => { document.title = `MSDS Lab · ${ROUTES[state.view]}`; }, [state.view]);
  useEffect(() => {
    const doc = current(state);
    const key = doc && `${doc.id}|${state.compareSplit}|${state.compareSubset}`;
    if (state.view === "compare" && !state.loading && !state.busy && doc && !state.experiments.length && compareAttempt.current !== key) loadCompare();
  }, [state.view, state.selectedId, state.loading, state.busy, state.compareSplit, state.compareSubset, state.experiments.length, loadCompare]);
  useEffect(() => {
    if (!state.scrollRequest || state.view !== "review") return;
    const frame = requestAnimationFrame(() => document.querySelector(`[data-source="${state.field}"]`)?.scrollIntoView({ behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth", block: "nearest" }));
    return () => cancelAnimationFrame(frame);
  }, [state.scrollRequest, state.field, state.view]);

  return { state, doc: current(state), update, patch, navigate, notify, closeModal, selectDocument, commitReview, toggleConfirm, uploadFile, loadCompare, onAction };
}
