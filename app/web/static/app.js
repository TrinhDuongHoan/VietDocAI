const fileInput = document.querySelector("#fileInput");
const fileLabel = document.querySelector("#fileLabel");
const form = document.querySelector("#uploadForm");
const message = document.querySelector("#message");
const documentList = document.querySelector("#documentList");
const documentDetail = document.querySelector("#documentDetail");
const emptyState = document.querySelector("#emptyState");
const refreshButton = document.querySelector("#refreshButton");
const healthStatus = document.querySelector("#healthStatus");

let selectedDocumentId = null;
let pollTimer = null;

fileInput.addEventListener("change", () => {
  fileLabel.textContent = fileInput.files[0]?.name || "Chọn file hoặc kéo thả";
});

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  if (!fileInput.files.length) {
    setMessage("Chọn một file trước khi gửi OCR.", "bad");
    return;
  }

  const submitButton = form.querySelector("button");
  submitButton.disabled = true;
  setMessage("Đang tải file và tạo job OCR...", "");

  try {
    const body = new FormData();
    body.append("file", fileInput.files[0]);

    const response = await fetch("/api/v1/documents", {
      method: "POST",
      body,
    });
    const payload = await parseResponse(response);

    selectedDocumentId = payload.document_id;
    setMessage(`Đã tạo job OCR ${shortId(payload.document_id)}.`, "ok");
    form.reset();
    fileLabel.textContent = "Chọn file hoặc kéo thả";
    await refreshDocuments();
    await selectDocument(selectedDocumentId);
  } catch (error) {
    setMessage(error.message, "bad");
  } finally {
    submitButton.disabled = false;
  }
});

refreshButton.addEventListener("click", refreshDocuments);

async function parseResponse(response) {
  const text = await response.text();
  const payload = text ? JSON.parse(text) : {};

  if (!response.ok) {
    const detail = payload.detail || `HTTP ${response.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return payload;
}

function setMessage(text, tone) {
  message.textContent = text;
  message.className = `message ${tone || ""}`;
}

function statusClass(status) {
  return `status ${status}`;
}

function statusLabel(status) {
  const labels = {
    queued: "Đang chờ",
    processing: "Đang OCR",
    retrying: "Đang thử lại",
    completed: "Hoàn tất",
    failed: "Thất bại",
  };
  return labels[status] || status;
}

function formatDate(value) {
  if (!value) return "Chưa có";
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "short",
    timeStyle: "medium",
  }).format(new Date(value));
}

function formatBytes(value) {
  if (!Number.isFinite(value)) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let size = value;
  let unitIndex = 0;

  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }

  return `${new Intl.NumberFormat("vi-VN", {
    maximumFractionDigits: unitIndex === 0 ? 0 : 1,
  }).format(size)} ${units[unitIndex]}`;
}

function shortId(value) {
  return value ? value.slice(0, 8) : "";
}

async function checkHealth() {
  try {
    const response = await fetch("/health/ready");
    if (!response.ok) throw new Error("not ready");
    healthStatus.textContent = "Sẵn sàng";
    healthStatus.className = "health ok";
  } catch {
    healthStatus.textContent = "Chưa sẵn sàng";
    healthStatus.className = "health bad";
  }
}

async function refreshDocuments() {
  documentList.innerHTML = `<p class="state-text">Đang tải danh sách...</p>`;

  try {
    const response = await fetch("/api/v1/documents?limit=50");
    const documents = await parseResponse(response);
    renderDocumentList(documents);
  } catch (error) {
    documentList.innerHTML = `<p class="state-text">${escapeHtml(error.message)}</p>`;
  }
}

function renderDocumentList(documents) {
  if (!documents.length) {
    documentList.innerHTML = `<p class="state-text">Chưa có document nào.</p>`;
    return;
  }

  documentList.innerHTML = documents
    .map((doc) => {
      const active = doc.id === selectedDocumentId ? " active" : "";
      const ocr = normalizeOcrResult(doc.result);
      return `
        <button class="doc-item${active}" type="button" data-document-id="${doc.id}">
          <span class="doc-row">
            <span class="doc-title">${escapeHtml(doc.original_filename)}</span>
            <span class="${statusClass(doc.status)}">${statusLabel(doc.status)}</span>
          </span>
          <span class="doc-meta">${formatBytes(doc.file_size)} · ${ocr.lineCount} dòng · ${shortId(doc.id)}</span>
        </button>
      `;
    })
    .join("");

  documentList.querySelectorAll("[data-document-id]").forEach((item) => {
    item.addEventListener("click", () => selectDocument(item.dataset.documentId));
  });
}

async function selectDocument(documentId) {
  selectedDocumentId = documentId;
  emptyState.classList.add("hidden");
  documentDetail.classList.remove("hidden");
  documentDetail.innerHTML = `<p class="state-text">Đang tải chi tiết...</p>`;

  try {
    const response = await fetch(`/api/v1/documents/${documentId}`);
    const doc = await parseResponse(response);
    renderDocumentDetail(doc);
    schedulePolling(doc);
    await refreshDocuments();
  } catch (error) {
    documentDetail.innerHTML = `<p class="state-text">${escapeHtml(error.message)}</p>`;
  }
}

function renderDocumentDetail(doc) {
  const ocr = normalizeOcrResult(doc.result);
  const elapsed = formatElapsed(doc.processing_started_at, doc.completed_at || doc.failed_at);
  const overlay = buildOverlayModel(ocr.lines);

  documentDetail.innerHTML = `
    <header class="detail-head">
      <div>
        <p class="eyebrow">Chi tiết document</p>
        <h2>${escapeHtml(doc.original_filename)}</h2>
      </div>
      <span class="${statusClass(doc.status)}">${statusLabel(doc.status)}</span>
    </header>

    <dl class="job-meta">
      ${metaItem("Mã job", shortId(doc.id))}
      ${metaItem("Dung lượng", formatBytes(doc.file_size))}
      ${metaItem("Loại file", doc.content_type)}
      ${metaItem("Số dòng", String(ocr.lineCount))}
      ${metaItem("Confidence", ocr.averageConfidenceLabel)}
      ${metaItem("Thời gian xử lý", elapsed)}
    </dl>

    ${
      doc.error_message
        ? `<p class="message bad">${escapeHtml(doc.error_message)}</p>`
        : ""
    }

    <section class="result-layout">
      <article class="result-card preview-card">
        <div class="result-card-head">
          <h3>File & vùng nhận diện</h3>
          <span>${overlay.modeLabel}</span>
        </div>
        ${renderOcrPreview(doc, overlay)}
      </article>

      <article class="result-card primary">
        <div class="result-card-head">
          <h3>Văn bản đã nhận dạng</h3>
          <span>${ocr.lineCount} dòng</span>
        </div>
        <div class="plain-text">${escapeHtml(ocr.plainText || "Chưa có kết quả OCR.")}</div>
      </article>

      <article class="result-card">
        <div class="result-card-head">
          <h3>Dòng OCR</h3>
          <span>${ocr.averageConfidenceLabel}</span>
        </div>
        ${renderLines(ocr.lines, overlay)}
      </article>

      <details class="result-card raw-json">
        <summary>JSON gốc</summary>
        <pre>${escapeHtml(JSON.stringify(doc.result || {}, null, 2))}</pre>
      </details>
    </section>
  `;

  bindPreviewInteractions();
}

function metaItem(label, value) {
  return `
    <div>
      <dt>${escapeHtml(label)}</dt>
      <dd>${escapeHtml(value || "Chưa có")}</dd>
    </div>
  `;
}

function renderOcrPreview(doc, overlay) {
  if (!overlay.regions.length) {
    return `
      <div class="preview-empty">
        Chưa có vùng OCR để hiển thị.
      </div>
    `;
  }

  const fileUrl = `/api/v1/documents/${encodeURIComponent(doc.id)}/file`;
  const previewUrl = `/api/v1/documents/${encodeURIComponent(doc.id)}/preview`;

  return `
    <div class="document-preview" aria-label="File gốc và các vùng OCR">
      <div class="file-preview-stage">
        ${renderSourceFile(doc, previewUrl, fileUrl)}
        <div class="preview-overlay" aria-hidden="true">
        ${overlay.regions
          .map(
            (region) => `
              <button
                class="ocr-region ${region.synthetic ? "synthetic" : ""}"
                type="button"
                data-line-index="${region.index}"
                data-source-left="${region.sourceLeft ?? ""}"
                data-source-top="${region.sourceTop ?? ""}"
                data-source-right="${region.sourceRight ?? ""}"
                data-source-bottom="${region.sourceBottom ?? ""}"
                style="left:${region.left}%;top:${region.top}%;width:${region.width}%;height:${region.height}%;"
                title="${escapeHtml(region.text)}"
                aria-label="Vùng OCR dòng ${region.index + 1}"
              >
                <span>${region.index + 1}</span>
              </button>
            `,
          )
          .join("")}
        </div>
      </div>
      <p class="preview-note">
        ${overlay.hasRealBoxes
          ? "Đang hiển thị file gốc và vùng được dựng từ tọa độ OCR thật."
          : "Đang hiển thị file gốc, nhưng document này chưa có tọa độ OCR nên vùng được mô phỏng theo thứ tự dòng."}
      </p>
    </div>
  `;
}

function renderSourceFile(doc, previewUrl, originalUrl) {
  return `
    <img
      class="source-file source-image"
      src="${previewUrl}"
      alt="${escapeHtml(doc.original_filename)}"
      data-original-url="${originalUrl}"
    />
  `;
}

function renderLines(lines, overlay) {
  if (!lines.length) {
    return `<p class="state-text compact">Chưa có dòng OCR để hiển thị.</p>`;
  }

  return `
    <ol class="line-list">
      ${lines
        .map((line, index) => {
          const confidence = formatConfidence(line.confidence);
          const hasRegion = overlay.regions.some((region) => region.index === index);
          return `
            <li class="ocr-line ${hasRegion ? "has-region" : ""}" data-line-index="${index}">
              <span class="line-number">${index + 1}</span>
              <span class="line-text">${escapeHtml(line.text)}</span>
              <span class="confidence ${confidence.className}">${confidence.label}</span>
            </li>
          `;
        })
        .join("")}
    </ol>
  `;
}

function normalizeOcrResult(result) {
  const lines = collectLines(result);
  const confidenceValues = lines
    .map((line) => line.confidence)
    .filter((value) => typeof value === "number" && Number.isFinite(value));
  const averageConfidence = confidenceValues.length
    ? confidenceValues.reduce((sum, value) => sum + value, 0) / confidenceValues.length
    : null;

  return {
    lines,
    lineCount: lines.length,
    plainText: lines.map((line) => line.text).join("\n"),
    averageConfidence,
    averageConfidenceLabel:
      averageConfidence === null
        ? "Chưa có"
        : `${Math.round(averageConfidence * 100)}%`,
  };
}

function collectLines(result) {
  if (!result) return [];

  if (Array.isArray(result.pages)) {
    return result.pages.flatMap((page, pageIndex) =>
      collectLines({ ...page, pageIndex: page.page_index ?? pageIndex + 1 }),
    );
  }

  if (Array.isArray(result.lines)) {
    return result.lines
      .map((line, index) => normalizeLine(line, index, result.pageIndex))
      .filter(Boolean);
  }

  const texts = firstArray(result.rec_texts, result.texts);
  const scores = firstArray(result.rec_scores, result.scores, result.confidences);
  const boxes = firstArray(result.rec_boxes, result.rec_polys, result.boxes, result.polys);

  if (texts.length) {
    return texts.map((text, index) => ({
      text: String(text),
      confidence: numberOrNull(scores[index]),
      box: boxes[index] || null,
      pageIndex: result.pageIndex || null,
    }));
  }

  if (typeof result.text === "string") {
    return result.text
      .split(/\r?\n/)
      .filter(Boolean)
      .map((text, index) => ({
        text,
        confidence: numberOrNull(result.confidence),
        box: null,
        pageIndex: result.pageIndex || null,
        index,
      }));
  }

  return [];
}

function normalizeLine(line, index, pageIndex) {
  if (typeof line === "string") {
    return {
      text: line,
      confidence: null,
      box: null,
      pageIndex: pageIndex || null,
      index,
    };
  }

  if (!line || typeof line !== "object") return null;

  const text = line.text ?? line.rec_text ?? line.value ?? "";
  if (!String(text).trim()) return null;

  return {
    text: String(text),
    confidence: numberOrNull(line.confidence ?? line.score ?? line.rec_score),
    box: line.box ?? line.bbox ?? line.polygon ?? line.poly ?? null,
    pageIndex: line.page_index ?? line.pageIndex ?? pageIndex ?? null,
    index,
  };
}

function firstArray(...values) {
  return values.find((value) => Array.isArray(value)) || [];
}

function buildOverlayModel(lines) {
  const realBoxes = lines
    .map((line, index) => ({ ...boxToRect(line.box), index, text: line.text }))
    .filter((region) => region !== null && isUsableRect(region));

  if (realBoxes.length) {
    return {
      regions: normalizeRegions(realBoxes, false),
      hasRealBoxes: true,
      modeLabel: `${realBoxes.length} vùng thật`,
    };
  }

  const syntheticRegions = lines
    .slice(0, 40)
    .map((line, index) => syntheticRegion(line, index))
    .filter(Boolean);

  return {
    regions: syntheticRegions,
    hasRealBoxes: false,
    modeLabel: syntheticRegions.length ? `${syntheticRegions.length} vùng mô phỏng` : "Chưa có vùng",
  };
}

function boxToRect(box) {
  if (!box) return null;

  if (
    Array.isArray(box) &&
    box.length === 4 &&
    box.every((value) => typeof value === "number" || typeof value === "string")
  ) {
    const [x1, y1, x2, y2] = box.map(Number);
    return {
      left: Math.min(x1, x2),
      top: Math.min(y1, y2),
      right: Math.max(x1, x2),
      bottom: Math.max(y1, y2),
    };
  }

  const points = Array.isArray(box)
    ? box
        .map((point) => {
          if (Array.isArray(point) && point.length >= 2) {
            return { x: Number(point[0]), y: Number(point[1]) };
          }

          if (point && typeof point === "object") {
            return { x: Number(point.x), y: Number(point.y) };
          }

          return null;
        })
        .filter((point) => point && Number.isFinite(point.x) && Number.isFinite(point.y))
    : [];

  if (!points.length) return null;

  const xs = points.map((point) => point.x);
  const ys = points.map((point) => point.y);

  return {
    left: Math.min(...xs),
    top: Math.min(...ys),
    right: Math.max(...xs),
    bottom: Math.max(...ys),
  };
}

function isUsableRect(rect) {
  return (
    rect &&
    Number.isFinite(rect.left) &&
    Number.isFinite(rect.top) &&
    Number.isFinite(rect.right) &&
    Number.isFinite(rect.bottom) &&
    rect.right > rect.left &&
    rect.bottom > rect.top
  );
}

function normalizeRegions(regions, synthetic) {
  const bounds = regions.reduce(
    (acc, region) => ({
      left: Math.min(acc.left, region.left),
      top: Math.min(acc.top, region.top),
      right: Math.max(acc.right, region.right),
      bottom: Math.max(acc.bottom, region.bottom),
    }),
    { left: Infinity, top: Infinity, right: -Infinity, bottom: -Infinity },
  );

  const width = Math.max(1, bounds.right - bounds.left);
  const height = Math.max(1, bounds.bottom - bounds.top);
  const padding = 5;

  return regions.map((region) => {
    const left = padding + ((region.left - bounds.left) / width) * (100 - padding * 2);
    const top = padding + ((region.top - bounds.top) / height) * (100 - padding * 2);
    const right = padding + ((region.right - bounds.left) / width) * (100 - padding * 2);
    const bottom = padding + ((region.bottom - bounds.top) / height) * (100 - padding * 2);

    return {
      index: region.index,
      text: region.text,
      sourceLeft: region.left,
      sourceTop: region.top,
      sourceRight: region.right,
      sourceBottom: region.bottom,
      left: clampPercent(left),
      top: clampPercent(top),
      width: clampPercent(Math.max(3, right - left)),
      height: clampPercent(Math.max(2.4, bottom - top)),
      synthetic,
    };
  });
}

function syntheticRegion(line, index) {
  const row = index % 18;
  const columnOffset = Math.floor(index / 18) % 2;
  const left = 7 + columnOffset * 3 + (index % 3) * 1.4;
  const top = 7 + row * 4.8;
  const width = Math.min(78, Math.max(28, String(line.text).length * 1.35));

  if (top > 91) return null;

  return {
    index,
    text: line.text,
    left,
    top,
    width,
    height: 3.2,
    synthetic: true,
  };
}

function clampPercent(value) {
  return Math.max(0, Math.min(100, Number(value.toFixed(3))));
}

function bindPreviewInteractions() {
  const detail = documentDetail;
  const targets = detail.querySelectorAll("[data-line-index]");
  const sourceImage = detail.querySelector(".source-image");

  if (sourceImage) {
    if (sourceImage.complete) {
      fitRegionsToImage(sourceImage);
    } else {
      sourceImage.addEventListener("load", () => fitRegionsToImage(sourceImage), {
        once: true,
      });
    }
  }

  targets.forEach((target) => {
    const lineIndex = target.dataset.lineIndex;
    target.addEventListener("mouseenter", () => setActiveRegion(lineIndex));
    target.addEventListener("focus", () => setActiveRegion(lineIndex));
    target.addEventListener("mouseleave", clearActiveRegion);
    target.addEventListener("blur", clearActiveRegion);
    target.addEventListener("click", () => setActiveRegion(lineIndex));
  });
}

function fitRegionsToImage(image) {
  const naturalWidth = image.naturalWidth;
  const naturalHeight = image.naturalHeight;

  if (!naturalWidth || !naturalHeight) return;

  documentDetail.querySelectorAll(".ocr-region").forEach((region) => {
    const left = Number(region.dataset.sourceLeft);
    const top = Number(region.dataset.sourceTop);
    const right = Number(region.dataset.sourceRight);
    const bottom = Number(region.dataset.sourceBottom);

    if (![left, top, right, bottom].every(Number.isFinite)) return;

    region.style.left = `${clampPercent((left / naturalWidth) * 100)}%`;
    region.style.top = `${clampPercent((top / naturalHeight) * 100)}%`;
    region.style.width = `${clampPercent(((right - left) / naturalWidth) * 100)}%`;
    region.style.height = `${clampPercent(((bottom - top) / naturalHeight) * 100)}%`;
  });
}

function setActiveRegion(lineIndex) {
  documentDetail.querySelectorAll("[data-line-index]").forEach((element) => {
    element.classList.toggle("is-linked", element.dataset.lineIndex === lineIndex);
  });
}

function clearActiveRegion() {
  documentDetail.querySelectorAll(".is-linked").forEach((element) => {
    element.classList.remove("is-linked");
  });
}

function numberOrNull(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatConfidence(value) {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    return { label: "N/A", className: "unknown" };
  }

  const percentage = Math.round(value * 100);
  const className = percentage >= 90 ? "high" : percentage >= 70 ? "medium" : "low";
  return { label: `${percentage}%`, className };
}

function formatElapsed(startedAt, finishedAt) {
  if (!startedAt || !finishedAt) return "Chưa có";
  const seconds = Math.max(0, Math.round((new Date(finishedAt) - new Date(startedAt)) / 1000));
  return `${seconds}s`;
}

function schedulePolling(doc) {
  clearTimeout(pollTimer);

  if (["queued", "processing", "retrying"].includes(doc.status)) {
    pollTimer = setTimeout(() => selectDocument(doc.id), 3000);
  }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

checkHealth();
refreshDocuments();
setInterval(checkHealth, 10000);
