import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const WEB_ROOT = fileURLToPath(new URL(".", import.meta.url));
const RAW_DIR = path.resolve(WEB_ROOT, "../data/raw");
const RESULTS = path.resolve(WEB_ROOT, "public/results/documents.json");
const PDF_PATH = /^\/pdfs\/((?:KR|EN)-[A-Z0-9]+-\d{3})\.pdf$/;

// 원본 PDF 미리보기(개발 · 미리보기 서버 전용).
// PDF는 저작권 때문에 저장소에 넣지 않으므로(data/raw/, git 제외) 복사하지 않고 이 컴퓨터의 data/raw/에서 읽어 보낸다.
// 결과 파일(public/results/documents.json)에 있는 문서만 보낸다 — data/raw/에는 test 문서 PDF도 있으므로 목록 밖 요청은 거부한다.
function localPdfs() {
  const handler = (req, res, next) => {
    const match = PDF_PATH.exec((req.url || "").split("?")[0]);
    if (!match) return next();
    let fileName;
    try {
      fileName = JSON.parse(fs.readFileSync(RESULTS, "utf8")).documents.find(doc => doc.doc_id === match[1])?.file_name;
    } catch { /* 결과 파일이 없으면 아래에서 404 */ }
    const file = fileName ? path.join(RAW_DIR, path.basename(fileName)) : null;
    if (!file || !fs.existsSync(file)) {
      res.statusCode = 404;
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      res.end(`<p style="font:14px sans-serif;color:#555;padding:24px">${fileName ? `이 컴퓨터에 원본 PDF가 없습니다: data/raw/${path.basename(fileName)}` : "결과 목록에 없는 문서입니다."}<br>원본 PDF는 저장소에 없고 팀 드라이브로 공유합니다. "추출 텍스트" 탭에서 원문을 볼 수 있습니다.</p>`);
      return;
    }
    res.setHeader("Content-Type", "application/pdf");
    res.setHeader("Content-Disposition", "inline");
    res.setHeader("Cache-Control", "no-store");
    fs.createReadStream(file).pipe(res);
  };
  return {
    name: "local-pdfs",
    configureServer(server) { server.middlewares.use(handler); },
    configurePreviewServer(server) { server.middlewares.use(handler); },
  };
}

export default defineConfig({
  base: "./",
  appType: "mpa",
  plugins: [react(), localPdfs()],
  server: { port: 5173, strictPort: true },
  preview: { port: 4173, strictPort: true },
  build: {
    rolldownOptions: {
      input: {
        landing: fileURLToPath(new URL("./index.html", import.meta.url)),
        workspace: fileURLToPath(new URL("./workspace.html", import.meta.url)),
      },
    },
  },
});
