const $ = (s) => document.querySelector(s);
function getOrCreateUserId() {
  const key = "tax_exam_user_id";
  const fromStorage = window.localStorage.getItem(key);
  if (fromStorage) return fromStorage;
  const uid = `user_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
  window.localStorage.setItem(key, uid);
  return uid;
}

const CURRENT_USER_ID = getOrCreateUserId();

const SCREENS = ["homeScreen", "setupScreen", "mockScreen", "resultScreen", "notesScreen", "placeholderScreen"];
const DASHBOARD_LABELS = ["재정학", "회계학", "세법학", "선택법"];
const DASHBOARD_DEFAULT_AVG = [72, 68, 70, 66];
const DASHBOARD_DEFAULT_ME = [64, 74, 58, 61];
const MODE_META = {
  mock: { title: "모의고사 설정", desc: "연도/과목 선택 후 문제풀이를 시작합니다." },
  notes: { title: "즐겨찾기", desc: "저장된 즐겨찾기 문제를 확인합니다." },
  ox: { title: "OX모드 설정", desc: "" },
};

const state = {
  options: [],
  oxOptions: [],
  mode: "",
  selection: { year: null, subjectCode: "", subjectName: "" },
  calc: { expr: "" },
  session: {
    type: "mock", // mock | ox
    questions: [],
    answers: {},
    index: 0,
    startedAt: 0,
    timerId: null,
    result: null,
    reviewMode: false,
    autoSubmitting: false,
    selectedResultIndex: 0,
    explanationOpen: false,
    hiddenChoices: {},
    starByKey: {},
    favoriteMemoByKey: {},
    oxStatsById: {},
    mockStatsById: {},
  },
  notes: {
    rows: [],
    subjectFilter: "all",
    colorFilter: "all",
    sourceFilter: "all",
    memoSearch: "",
  },
  nav: { history: [] },
  chart: { labels: DASHBOARD_LABELS, avg: [...DASHBOARD_DEFAULT_AVG], me: [...DASHBOARD_DEFAULT_ME], zones: [] },
};

async function api(path, options = {}) {
  const res = await fetch(path, { headers: { "Content-Type": "application/json" }, ...options });
  if (!res.ok) throw new Error(await res.text());
  return res.json();
}

function currentScreenId() {
  const active = document.querySelector(".screen.active");
  return active ? active.id : null;
}

function showScreen(id, options = {}) {
  const { skipHistory = false } = options;
  const from = currentScreenId();
  if (!skipHistory && from && from !== id) {
    state.nav.history.push(from);
  }
  SCREENS.forEach((sid) => {
    const el = document.getElementById(sid);
    if (el) el.classList.toggle("active", sid === id);
  });
  const bottomBar = $("#bottomBar");
  if (bottomBar) bottomBar.classList.toggle("hidden", id === "homeScreen");

  const backBtn = $("#topBackBtn");
  if (backBtn) backBtn.style.visibility = id === "homeScreen" ? "hidden" : "visible";
}

function noteKey(year, subjectCode, qno) {
  return `${year}|${subjectCode}|${qno}`;
}

function sessionDurationSeconds() {
  if (!state.session.startedAt) return 0;
  return Math.max(0, Math.floor((Date.now() - state.session.startedAt) / 1000));
}

function favoriteTargetFromQuestion(question) {
  if (!question) return null;
  return {
    exam_year: Number(question.exam_year),
    subject_code: String(question.subject_code || ""),
    question_no_exam: Number(question.question_no_exam),
  };
}

function favoriteTargetFromResultDetail(detail) {
  if (!detail || !state.session.result) return null;
  const fallbackYear = Number(state.session.result.exam_year || state.selection.year || 0);
  const fallbackSubject = String(state.session.result.subject_code || state.selection.subjectCode || "");
  return {
    exam_year: Number(detail.exam_year || fallbackYear),
    subject_code: String(detail.subject_code || fallbackSubject),
    question_no_exam: Number(detail.question_no_exam),
  };
}

function currentQuestion() {
  return state.session.questions[state.session.index];
}

function setScoreBadge(text = "") {
  const el = $("#mockScoreBadge");
  if (!el) return;
  el.textContent = text;
  el.style.display = text ? "inline-block" : "none";
}

function setSubmitVisible(visible) {
  const btn = $("#submitMockBtn");
  if (!btn) return;
  btn.style.display = visible ? "block" : "none";
}

function shuffleInPlace(items) {
  for (let i = items.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [items[i], items[j]] = [items[j], items[i]];
  }
}

function computeDday() {
  const examDate = new Date("2026-04-25T00:00:00+09:00");
  const now = new Date();
  const diff = Math.ceil((examDate.getTime() - now.getTime()) / (1000 * 60 * 60 * 24));
  $("#ddayText").textContent = diff >= 0 ? `D-${diff}` : `D+${Math.abs(diff)}`;
}

function drawRadarChart(avg = DASHBOARD_DEFAULT_AVG, me = DASHBOARD_DEFAULT_ME) {
  const canvas = $("#radarChart");
  const ctx = canvas.getContext("2d");
  const w = canvas.width;
  const h = canvas.height;
  const labels = DASHBOARD_LABELS;
  const maxScore = 100;
  const left = 28;
  const right = w - 12;
  const top = 16;
  const bottom = h - 26;
  const chartW = right - left;
  const chartH = bottom - top;
  const groupW = chartW / labels.length;
  const barW = Math.min(16, groupW * 0.26);
  state.chart.labels = [...labels];
  state.chart.avg = [...avg];
  state.chart.me = [...me];
  state.chart.zones = [];

  ctx.clearRect(0, 0, w, h);
  ctx.font = "11px Pretendard";
  ctx.strokeStyle = "#e2eaf7";
  ctx.fillStyle = "#7990b8";

  for (let tick = 0; tick <= 5; tick += 1) {
    const y = top + (chartH * tick) / 5;
    const score = Math.round(maxScore - (maxScore * tick) / 5);
    ctx.beginPath();
    ctx.moveTo(left, y);
    ctx.lineTo(right, y);
    ctx.stroke();
    ctx.fillText(String(score), 4, y + 4);
  }

  for (let i = 0; i < labels.length; i += 1) {
    const gx = left + groupW * i + groupW / 2;
    const avgH = (avg[i] / maxScore) * chartH;
    const meH = (me[i] / maxScore) * chartH;
    ctx.fillStyle = "#7e8ca6";
    ctx.fillRect(gx - barW - 2, bottom - avgH, barW, avgH);
    ctx.fillStyle = "#2f8cff";
    ctx.fillRect(gx + 2, bottom - meH, barW, meH);
    ctx.fillStyle = "#4f6388";
    ctx.textAlign = "center";
    ctx.fillText(labels[i], gx, h - 8);
    state.chart.zones.push({ label: labels[i], idx: i, x: gx, half: groupW / 2, top, bottom });
  }
  ctx.textAlign = "start";
}

function hideChartTooltip() {
  const tooltip = $("#chartTooltip");
  if (!tooltip) return;
  tooltip.classList.add("hidden");
}

function showChartTooltipByX(clientX) {
  const canvas = $("#radarChart");
  const tooltip = $("#chartTooltip");
  if (!canvas || !tooltip) return;
  const rect = canvas.getBoundingClientRect();
  const x = clientX - rect.left;
  const zone = state.chart.zones.find((z) => x >= (z.x - z.half) && x <= (z.x + z.half));
  if (!zone) {
    hideChartTooltip();
    return;
  }
  const avg = state.chart.avg[zone.idx];
  const me = state.chart.me[zone.idx];
  tooltip.textContent = `${zone.label} 평균 ${avg} / 내점수 ${me}`;
  tooltip.classList.remove("hidden");
}

function bindRadarInteractions() {
  const canvas = $("#radarChart");
  if (!canvas) return;
  canvas.addEventListener("mousemove", (e) => showChartTooltipByX(e.clientX));
  canvas.addEventListener("mouseleave", () => hideChartTooltip());
  canvas.addEventListener("touchstart", (e) => {
    if (e.touches && e.touches[0]) showChartTooltipByX(e.touches[0].clientX);
  }, { passive: true });
  canvas.addEventListener("touchmove", (e) => {
    if (e.touches && e.touches[0]) showChartTooltipByX(e.touches[0].clientX);
  }, { passive: true });
  canvas.addEventListener("touchend", () => hideChartTooltip());
}

function _clampScore(v) {
  const n = Number(v);
  if (!Number.isFinite(n)) return null;
  return Math.max(0, Math.min(100, n));
}

async function refreshDashboardChart() {
  try {
    const data = await api(`/api/dashboard/learning-metrics?user_id=${encodeURIComponent(CURRENT_USER_ID)}`);
    const avg = [...DASHBOARD_DEFAULT_AVG];
    const me = [...DASHBOARD_DEFAULT_ME];
    DASHBOARD_LABELS.forEach((label, idx) => {
      const avgVal = _clampScore(data?.overall_avg_scores?.[label]);
      const meVal = _clampScore(data?.my_recent_scores?.[label]);
      if (avgVal !== null) avg[idx] = avgVal;
      if (meVal !== null) me[idx] = meVal;
    });
    drawRadarChart(avg, me);
  } catch {
    drawRadarChart(DASHBOARD_DEFAULT_AVG, DASHBOARD_DEFAULT_ME);
  }
}

function renderSetupYearsAndSubjects() {
  const years = [...new Set(state.options.map((o) => o.exam_year))].sort((a, b) => b - a);
  $("#setupYear").innerHTML = years.map((y) => `<option value="${y}">${y}</option>`).join("");
  state.selection.year = years[0] || null;
  renderSetupSubjectsForYear();
}

function renderSetupSubjectsForYear() {
  const year = Number($("#setupYear").value);
  state.selection.year = year;
  const list = state.options.filter((o) => o.exam_year === year);
  $("#setupSubject").innerHTML = list
    .map((o) => `<option value="${o.subject_code}" data-name="${o.subject_name}">${o.subject_name}</option>`)
    .join("");
  const first = $("#setupSubject").selectedOptions[0];
  state.selection.subjectCode = first ? first.value : "";
  state.selection.subjectName = first ? first.dataset.name || "" : "";
}

function renderSetupSubjectsForOx() {
  $("#setupSubject").innerHTML = state.oxOptions
    .map((o) => `<option value="${o.subject_code}" data-name="${o.subject_name}">${o.subject_name}</option>`)
    .join("");
  const first = $("#setupSubject").selectedOptions[0];
  state.selection.subjectCode = first ? first.value : "";
  state.selection.subjectName = first ? first.dataset.name || "" : "";
}

function syncSetupSelection() {
  const yearFieldHidden = $("#setupYearField").style.display === "none";
  state.selection.year = yearFieldHidden ? null : Number($("#setupYear").value);
  state.selection.subjectCode = $("#setupSubject").value;
  const option = $("#setupSubject").selectedOptions[0];
  state.selection.subjectName = option ? option.dataset.name || "" : "";
}

function openSetup(mode) {
  state.mode = mode;
  const meta = MODE_META[mode] || { title: "설정", desc: "설정을 선택하세요." };
  $("#setupTitle").textContent = meta.title;
  $("#setupDesc").textContent = meta.desc;

  const isOx = mode === "ox";
  $("#setupYearField").style.display = isOx ? "none" : "grid";
  $("#setupContinueBtn").textContent = mode === "mock" || mode === "ox" ? "시작하기" : "다음";

  if (isOx) {
    renderSetupSubjectsForOx();
  } else {
    renderSetupYearsAndSubjects();
  }
  showScreen("setupScreen");
}

function handleModeClick(mode) {
  if (mode === "soon2") {
    $("#placeholderTitle").textContent = "개발중";
    $("#placeholderDesc").textContent = "해당 모드는 순차 구현 예정입니다.";
    showScreen("placeholderScreen");
    return;
  }
  if (mode === "soon1") {
    $("#placeholderTitle").textContent = "회독관리 (개발중)";
    $("#placeholderDesc").textContent = "회독/누적 학습 통계는 다음 단계에서 구현합니다.";
    showScreen("placeholderScreen");
    return;
  }
  if (mode === "notes") {
    state.selection.year = null;
    state.selection.subjectCode = "";
    state.selection.subjectName = "";
    showScreen("notesScreen");
    loadNotes().catch((e) => alert(e.message));
    return;
  }
  openSetup(mode);
}

function stopTimer() {
  if (state.session.timerId) {
    clearInterval(state.session.timerId);
    state.session.timerId = null;
  }
}

function startTimer() {
  stopTimer();
  state.session.startedAt = Date.now();
  state.session.timerId = setInterval(() => {
    // keep startedAt-based duration tracking without rendering a visible stopwatch
  }, 1000);
}

function setCalcDisplay(text) {
  const display = $("#calcDisplay");
  if (display) display.value = text || "0";
}

function evalCalcExpression(expr) {
  const safe = expr.replace(/[^0-9+\-*/.()]/g, "");
  if (!safe) return "0";
  try {
    const result = Function(`"use strict"; return (${safe})`)();
    return Number.isFinite(result) ? String(result) : "Error";
  } catch {
    return "Error";
  }
}

function onCalcKey(key) {
  if (key === "C") {
    state.calc.expr = "";
    setCalcDisplay("0");
    return;
  }
  if (key === "⌫") {
    state.calc.expr = state.calc.expr.slice(0, -1);
    setCalcDisplay(state.calc.expr || "0");
    return;
  }
  if (key === "=") {
    const out = evalCalcExpression(state.calc.expr);
    state.calc.expr = out === "Error" ? "" : out;
    setCalcDisplay(out);
    return;
  }
  state.calc.expr += key;
  setCalcDisplay(state.calc.expr);
}

function bindInlineCalculator() {
  const pad = $("#calcPad");
  if (!pad) return;
  const keys = ["7", "8", "9", "/", "4", "5", "6", "*", "1", "2", "3", "-", "0", ".", "=", "+", "C", "⌫"];
  pad.innerHTML = keys.map((k) => `<button class="calc-key" data-k="${k}">${k}</button>`).join("");
  pad.querySelectorAll(".calc-key").forEach((btn) => btn.addEventListener("click", () => onCalcKey(btn.dataset.k)));
  $("#closeCalcBtn").addEventListener("click", () => toggleInlineCalc(false));
  setCalcDisplay(state.calc.expr || "0");
}

function toggleInlineCalc(open) {
  const sheet = $("#calcInline");
  if (!sheet) return;
  sheet.classList.toggle("hidden", !open);
}

async function loadFavoriteStars() {
  const params = new URLSearchParams({ user_id: CURRENT_USER_ID, subject_code: state.selection.subjectCode });
  if (state.selection.year) params.set("exam_year", String(state.selection.year));
  const rows = await api(`/api/bank-notes?${params.toString()}`);
  const map = {};
  const memoMap = {};
  rows.forEach((row) => {
    const st = String(row.state || "");
    if (st.startsWith("favorite_")) {
      const color = st.replace("favorite_", "");
      if (["red", "yellow", "green"].includes(color)) {
        const key = noteKey(row.exam_year, row.subject_code, row.question_no_exam);
        map[key] = color;
        memoMap[key] = String(row.memo || "");
      }
    }
  });
  state.session.starByKey = map;
  state.session.favoriteMemoByKey = memoMap;
}

async function toggleFavorite(target, color) {
  if (!target) return;
  const year = target.exam_year;
  const subject = target.subject_code;
  const qno = target.question_no_exam;
  const key = noteKey(year, subject, qno);
  const current = state.session.starByKey[key] || "";
  const memo = state.session.favoriteMemoByKey[key] || "";

  if (current === color) {
    await api("/api/favorites/delete", {
      method: "POST",
      body: JSON.stringify({
        exam_year: year,
        subject_code: subject,
        question_no_exam: qno,
        user_id: CURRENT_USER_ID,
      }),
    });
    delete state.session.starByKey[key];
    delete state.session.favoriteMemoByKey[key];
  } else {
    await api("/api/favorites", {
      method: "POST",
      body: JSON.stringify({
        exam_year: year,
        subject_code: subject,
        question_no_exam: qno,
        color,
        memo,
        tags: state.session.type === "ox" ? ["favorite", color, "ox"] : ["favorite", color],
        user_id: CURRENT_USER_ID,
        source: state.session.type,
      }),
    });
    state.session.starByKey[key] = color;
  }
}

async function toggleFavoriteForCurrent(color) {
  const q = currentQuestion();
  const target = favoriteTargetFromQuestion(q);
  await toggleFavorite(target, color);
  renderTopStars();
}

async function toggleFavoriteForResult(color) {
  if (!state.session.result || !state.session.result.details || !state.session.result.details.length) return;
  const idx = Math.max(0, Math.min(state.session.selectedResultIndex, state.session.result.details.length - 1));
  const detail = state.session.result.details[idx];
  const target = favoriteTargetFromResultDetail(detail);
  await toggleFavorite(target, color);
  renderResult();
}

function _targetForMemoEditor(inResult) {
  if (inResult) {
    if (!state.session.result || !state.session.result.details?.length) return null;
    const idx = Math.max(0, Math.min(state.session.selectedResultIndex, state.session.result.details.length - 1));
    return favoriteTargetFromResultDetail(state.session.result.details[idx]);
  }
  return favoriteTargetFromQuestion(currentQuestion());
}

async function openFavoriteMemoEditor(inResult = false) {
  const target = _targetForMemoEditor(inResult);
  if (!target) return;
  const key = noteKey(target.exam_year, target.subject_code, target.question_no_exam);
  const prev = state.session.favoriteMemoByKey[key] || "";
  const next = window.prompt("즐겨찾기 코멘트 입력", prev);
  if (next === null) return;
  const memo = String(next).trim();
  state.session.favoriteMemoByKey[key] = memo;
  if (inResult) renderResult();
  else renderTopStars();

  const currentColor = state.session.starByKey[key] || "";
  if (!currentColor) return;

  await api("/api/favorites", {
    method: "POST",
    body: JSON.stringify({
      exam_year: target.exam_year,
      subject_code: target.subject_code,
      question_no_exam: target.question_no_exam,
      color: currentColor,
      memo,
      tags: state.session.type === "ox" ? ["favorite", currentColor, "ox"] : ["favorite", currentColor],
      user_id: CURRENT_USER_ID,
      source: state.session.type,
    }),
  });
  if (inResult) renderResult();
  else renderTopStars();
}

function renderTopStars() {
  const root = $("#topStarActions");
  if (!root) return;
  const q = currentQuestion();
  if (!q) {
    root.innerHTML = "";
    return;
  }
  const key = noteKey(q.exam_year, q.subject_code, q.question_no_exam);
  const selected = state.session.starByKey[key] || "";
  const hasMemo = Boolean((state.session.favoriteMemoByKey[key] || "").trim());
  root.innerHTML = `
    <button class="star-btn red ${selected === "red" ? "active" : ""}" data-color="red">${selected === "red" ? "✓" : "★"}</button>
    <button class="star-btn yellow ${selected === "yellow" ? "active" : ""}" data-color="yellow">${selected === "yellow" ? "✓" : "★"}</button>
    <button class="star-btn green ${selected === "green" ? "active" : ""}" data-color="green">${selected === "green" ? "✓" : "★"}</button>
    <button class="star-btn memo ${hasMemo ? "filled" : ""}" data-memo="1">📝</button>
  `;
  root.querySelectorAll(".star-btn").forEach((btn) => {
    if (btn.dataset.memo === "1") {
      btn.addEventListener("click", () => openFavoriteMemoEditor(false).catch((e) => alert(e.message)));
      return;
    }
    btn.addEventListener("click", () => toggleFavoriteForCurrent(btn.dataset.color).catch((e) => alert(e.message)));
  });
}

function renderResultStars(detail) {
  const root = $("#resultStarActions");
  if (!root) return;
  const target = favoriteTargetFromResultDetail(detail);
  if (!target) {
    root.innerHTML = "";
    return;
  }
  const key = noteKey(target.exam_year, target.subject_code, target.question_no_exam);
  const selected = state.session.starByKey[key] || "";
  const hasMemo = Boolean((state.session.favoriteMemoByKey[key] || "").trim());
  root.innerHTML = `
    <button class="star-btn red ${selected === "red" ? "active" : ""}" data-color="red">${selected === "red" ? "✓" : "★"}</button>
    <button class="star-btn yellow ${selected === "yellow" ? "active" : ""}" data-color="yellow">${selected === "yellow" ? "✓" : "★"}</button>
    <button class="star-btn green ${selected === "green" ? "active" : ""}" data-color="green">${selected === "green" ? "✓" : "★"}</button>
    <button class="star-btn memo ${hasMemo ? "filled" : ""}" data-memo="1">📝</button>
  `;
  root.querySelectorAll(".star-btn").forEach((btn) => {
    if (btn.dataset.memo === "1") {
      btn.addEventListener("click", () => openFavoriteMemoEditor(true).catch((e) => alert(e.message)));
      return;
    }
    btn.addEventListener("click", () => toggleFavoriteForResult(btn.dataset.color).catch((e) => alert(e.message)));
  });
}

async function toggleChoiceConceal(questionId, idx) {
  const key = String(questionId);
  if (!state.session.hiddenChoices[key]) state.session.hiddenChoices[key] = [];
  const set = new Set(state.session.hiddenChoices[key]);
  let hidden = true;
  if (set.has(idx)) {
    set.delete(idx);
    hidden = false;
  } else {
    set.add(idx);
    hidden = true;
  }
  state.session.hiddenChoices[key] = [...set];

  const q = currentQuestion();
  if (q) {
    await api("/api/choice-visibility", {
      method: "POST",
      body: JSON.stringify({
        user_id: CURRENT_USER_ID,
        exam_year: q.exam_year,
        subject_code: q.subject_code,
        question_no_exam: q.question_no_exam,
        choice_no: idx,
        hidden,
      }),
    });
  }
  renderQuestion();
}

async function loadChoiceVisibilityForMock(questions) {
  if (!state.selection.year || !state.selection.subjectCode || !questions.length) {
    state.session.hiddenChoices = {};
    return;
  }
  const params = new URLSearchParams({
    user_id: CURRENT_USER_ID,
    exam_year: String(state.selection.year),
    subject_code: state.selection.subjectCode,
  });
  const rows = await api(`/api/choice-visibility?${params.toString()}`);
  const byQno = {};
  rows.forEach((r) => {
    if (!r.hidden) return;
    const qno = Number(r.question_no_exam);
    const cno = Number(r.choice_no);
    if (!byQno[qno]) byQno[qno] = [];
    byQno[qno].push(cno);
  });
  const byQuestionId = {};
  questions.forEach((q) => {
    const arr = byQno[Number(q.question_no_exam)] || [];
    if (arr.length) byQuestionId[String(q.id)] = arr;
  });
  state.session.hiddenChoices = byQuestionId;
}

async function loadHiddenKeysForOx(subjectCode, years) {
  const hidden = new Set();
  for (const year of years) {
    const params = new URLSearchParams({
      user_id: CURRENT_USER_ID,
      exam_year: String(year),
      subject_code: subjectCode,
    });
    const rows = await api(`/api/choice-visibility?${params.toString()}`);
    rows.forEach((row) => {
      if (!row.hidden) return;
      hidden.add(`${year}|${subjectCode}|${Number(row.question_no_exam)}|${Number(row.choice_no)}`);
    });
  }
  return hidden;
}

async function loadOxStats(subjectCode) {
  const rows = await api(`/api/ox/user-stats?user_id=${encodeURIComponent(CURRENT_USER_ID)}&subject_code=${encodeURIComponent(subjectCode)}`);
  const map = {};
  rows.forEach((row) => {
    map[Number(row.ox_item_id)] = {
      solvedCount: Number(row.solved_count || 0),
      correctCount: Number(row.correct_count || 0),
      accuracy: Number(row.accuracy || 0),
    };
  });
  state.session.oxStatsById = map;
}

async function loadMockStats(examYear, subjectCode) {
  const rows = await api(
    `/api/mock/user-stats?user_id=${encodeURIComponent(CURRENT_USER_ID)}&exam_year=${encodeURIComponent(examYear)}&subject_code=${encodeURIComponent(subjectCode)}`,
  );
  const map = {};
  rows.forEach((row) => {
    map[Number(row.question_id)] = {
      solvedCount: Number(row.solved_count || 0),
      correctCount: Number(row.correct_count || 0),
      accuracy: Number(row.accuracy || 0),
    };
  });
  state.session.mockStatsById = map;
}

function eyeIcon(hidden) {
  if (hidden) {
    return `
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"></path>
        <circle cx="12" cy="12" r="3"></circle>
      </svg>
    `;
  }
  return `
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
      <path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"></path>
      <circle cx="12" cy="12" r="3"></circle>
      <path d="M3 21L21 3"></path>
    </svg>
  `;
}

async function toggleExplanation(questionId) {
  const box = $("#inlineExplanation");
  const btn = $("#explainToggleBtn");
  if (!box || !btn) return;

  if (state.session.explanationOpen) {
    box.style.display = "none";
    box.innerHTML = "";
    btn.textContent = "해설보기";
    state.session.explanationOpen = false;
    return;
  }

  if (state.session.type === "ox") {
    const oxQuestion = currentQuestion();
    const oxExplanation = (oxQuestion?.explanation_text || "").trim();
    box.style.display = "block";
    box.innerHTML = `<div>${oxExplanation || "해설 준비중입니다. 이후 OX 해설 텍스트를 붙여넣을 수 있도록 준비된 영역입니다."}</div>`;
    btn.textContent = "해설가리기";
    state.session.explanationOpen = true;
    return;
  }

  const data = await api(`/api/mock/explanation/${questionId}`);
  box.style.display = "block";
  box.innerHTML = `
    <div><strong>정답 ${data.correct_answer || "-"}</strong></div>
    <div style="margin-top:6px;">${data.explanation_text || "해설이 없습니다."}</div>
  `;
  btn.textContent = "해설가리기";
  state.session.explanationOpen = true;
}

function renderProgressGrid() {
  const wrap = $("#questionProgressGrid");
  if (!wrap) return;
  if (state.session.type === "ox") {
    wrap.innerHTML = "";
    return;
  }
  if (state.session.reviewMode && state.session.result && state.session.result.details) {
    const details = state.session.result.details;
    wrap.innerHTML = details
      .map((d, idx) => {
        const selected = String(d.selected_answer ?? d.selected_ox ?? "").trim();
        const answered = selected !== "";
        const cls = ["progress-cell"];
        let label = "-";
        if (idx === state.session.selectedResultIndex) cls.push("current");
        if (answered && d.is_correct) {
          cls.push("correct");
          label = "○";
        } else if (answered && !d.is_correct) {
          cls.push("wrong");
          label = "X";
        } else {
          cls.push("pending");
        }
        return `<button class="${cls.join(" ")}" data-result-idx="${idx}">${label}</button>`;
      })
      .join("");
    wrap.querySelectorAll("[data-result-idx]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.session.selectedResultIndex = Number(btn.dataset.resultIdx);
        renderQuestion();
      });
    });
    return;
  }

  const total = state.session.questions.length;
  if (!total) {
    wrap.innerHTML = "";
    return;
  }
  wrap.innerHTML = state.session.questions
    .map((q, i) => {
      const isCurrent = i === state.session.index;
      const isDone = Boolean(state.session.answers[q.id]);
      const cls = ["progress-cell", isCurrent ? "current" : "", isDone ? "done" : ""].filter(Boolean).join(" ");
      const label = isDone ? "✓" : String(i + 1);
      return `<button class="${cls}" data-idx="${i}">${label}</button>`;
    })
    .join("");
  wrap.querySelectorAll(".progress-cell").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.session.index = Number(btn.dataset.idx);
      renderQuestion();
    });
  });
}

function renderResultProgressGrid(result) {
  const wrap = $("#resultProgressGrid");
  if (!wrap) return;
  if (!result || !result.details || !result.details.length) {
    wrap.innerHTML = "";
    return;
  }
  wrap.innerHTML = result.details
    .map((d, idx) => {
      const selected = String(d.selected_answer ?? d.selected_ox ?? "").trim();
      const answered = selected !== "";
      let label = String(idx + 1);
      const cls = ["progress-cell"];
      if (idx === state.session.selectedResultIndex) cls.push("current");
      if (answered && d.is_correct) {
        cls.push("correct");
        label = "○";
      } else if (answered && !d.is_correct) {
        cls.push("wrong");
        label = "X";
      } else {
        cls.push("pending");
        label = "-";
      }
      return `<button class="${cls.join(" ")}" data-result-idx="${idx}">${label}</button>`;
    })
    .join("");
  wrap.querySelectorAll("[data-result-idx]").forEach((btn) => {
    btn.addEventListener("click", () => {
      state.session.selectedResultIndex = Number(btn.dataset.resultIdx);
      renderResult();
    });
  });
}

function renderQuestion() {
  const root = $("#mockQuestion");
  const total = state.session.questions.length;
  if (!total) {
    root.textContent = "문제를 불러오는 중입니다.";
    renderProgressGrid();
    return;
  }
  if (state.session.reviewMode && state.session.result && state.session.result.details?.length) {
    const topStars = $("#topStarActions");
    if (topStars) topStars.innerHTML = "";
    const result = state.session.result;
    const idx = Math.max(0, Math.min(state.session.selectedResultIndex, result.details.length - 1));
    state.session.selectedResultIndex = idx;
    const d = result.details[idx];

    if (state.session.type === "mock") {
      const selected = String(d.selected_answer || "");
      const correctAnswer = String(d.correct_answer || "");
      const explanation = String(d.explanation_text || "").trim();
      const choicesHtml = (d.choices || [])
        .map((choice, i) => {
          const no = String(i + 1);
          const isCorrect = no === correctAnswer;
          const isSelectedWrong = no === selected && selected !== correctAnswer;
          const classes = ["result-choice"];
          if (isCorrect) classes.push("correct");
          if (isSelectedWrong) classes.push("wrong");
          return `<div class="${classes.join(" ")}">${no}) ${choice}</div>`;
        })
        .join("");

      root.innerHTML = `
        <div class="result-question">
          <div class="row-between">
            <div><strong>${d.question_no_exam}번</strong></div>
            <div id="resultStarActions" class="top-star-actions"></div>
          </div>
          <div style="margin-top:6px;">${d.question_text || ""}</div>
          <div>${choicesHtml}</div>
          <div class="item" style="margin-top:10px;">
            <div><strong>해설</strong></div>
            <div style="margin-top:6px;">${explanation || "해설이 없습니다."}</div>
          </div>
        </div>
      `;
      renderResultStars(d);
    } else {
      const selectedOx = String(d.selected_ox || "");
      const expectedOx = String(d.expected_ox || "");
      const oxOClass = ["result-choice"];
      const oxXClass = ["result-choice"];
      if (selectedOx && expectedOx) {
        if (selectedOx === expectedOx) {
          if (selectedOx === "O") oxOClass.push("correct");
          if (selectedOx === "X") oxXClass.push("correct");
        } else {
          if (expectedOx === "O") oxOClass.push("correct");
          if (expectedOx === "X") oxXClass.push("correct");
          if (selectedOx === "O") oxOClass.push("wrong");
          if (selectedOx === "X") oxXClass.push("wrong");
        }
      }
      const oxExplanation = String(d.choice_explanation_text || d.judge_reason || "").trim();
      root.innerHTML = `
        <div class="result-question">
          <div class="row-between">
            <div><strong>문장 판정 결과</strong></div>
            <div id="resultStarActions" class="top-star-actions"></div>
          </div>
          <div style="margin-top:6px;">${d.choice_text || ""}</div>
          <div style="margin-top:8px;">
            <div class="${oxOClass.join(" ")}">O</div>
            <div class="${oxXClass.join(" ")}">X</div>
          </div>
          <div class="item" style="margin-top:10px;">
            <div><strong>해설</strong></div>
            <div style="margin-top:6px;">${oxExplanation || "해설이 없습니다."}</div>
          </div>
        </div>
      `;
      renderResultStars(d);
    }
    renderProgressGrid();
    return;
  }
  if (state.session.index >= total) {
    if (state.session.type === "ox" && !state.session.reviewMode) {
      if (!state.session.autoSubmitting) {
        state.session.autoSubmitting = true;
        root.textContent = "채점 중입니다...";
        submitOx().catch((e) => {
          state.session.autoSubmitting = false;
          alert(e.message);
        });
      } else {
        root.textContent = "채점 중입니다...";
      }
      renderProgressGrid();
      return;
    }
    root.textContent = $("#submitMockBtn")?.style.display === "none"
      ? "모든 문항을 풀었습니다."
      : "모든 문항을 풀었습니다. 아래 '채점하기' 버튼을 눌러 결과를 확인하세요.";
    renderProgressGrid();
    return;
  }

  const q = currentQuestion();

  if (state.session.type === "mock") {
    const mstats = state.session.mockStatsById[Number(q.id)] || { solvedCount: 0, correctCount: 0, accuracy: 0 };
    const hiddenSet = new Set(state.session.hiddenChoices[String(q.id)] || []);
    const choices = q.choices
      .map((c, i) => {
        const idx = i + 1;
        const hidden = hiddenSet.has(idx);
        return `
          <div class="choice-row">
            <button class="choice-btn" data-answer="${idx}">
              <span class="choice-no">${idx})</span>
              <span class="choice-text ${hidden ? "concealed" : ""}">${c}</span>
            </button>
            <button class="choice-toggle" data-hide="${idx}" aria-label="${hidden ? "보기" : "가리기"}">${eyeIcon(hidden)}</button>
          </div>
        `;
      })
      .join("");

    root.innerHTML = `
      <div><strong>${state.session.index + 1}/${total}</strong> · ${q.question_no_exam}번</div>
      <div style="margin-top:8px;">${q.question_text}</div>
      <div class="subtle" style="margin-top:8px;">풀이 ${mstats.solvedCount}회 · 정답 ${mstats.correctCount}회 · 정답률 ${mstats.accuracy}%</div>
      <div class="choice-list">${choices}</div>
      <div class="question-actions">
        <button class="action-btn" id="explainToggleBtn">해설보기</button>
        <button class="action-btn" id="calcBtn">계산기</button>
      </div>
      <div id="inlineExplanation" style="display:none;margin-top:8px;" class="item"></div>
      <div id="calcInline" class="calc-inline hidden">
        <div class="calc-head">
          <strong>계산기</strong>
          <button id="closeCalcBtn" class="mini-btn">닫기</button>
        </div>
        <input id="calcDisplay" class="calc-display" value="0" readonly />
        <div id="calcPad" class="calc-pad"></div>
      </div>
    `;

    root.querySelectorAll(".choice-btn").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.session.answers[q.id] = String(btn.dataset.answer);
        state.session.index += 1;
        state.calc.expr = "";
        state.session.explanationOpen = false;
        renderQuestion();
      });
    });
    root.querySelectorAll(".choice-toggle").forEach((btn) => {
      btn.addEventListener("click", () => toggleChoiceConceal(q.id, Number(btn.dataset.hide)).catch((e) => alert(e.message)));
    });
  } else {
    const stats = state.session.oxStatsById[Number(q.id)] || { solvedCount: 0, correctCount: 0, accuracy: 0 };
    const disablePrev = state.session.index <= 0 ? "disabled" : "";
    const disableNext = state.session.index >= (total - 1) ? "disabled" : "";
    const selectedOx = String(state.session.answers[q.id] || "");
    const expectedOx = String(q.expected_ox || "");
    const showExplanation = Boolean(selectedOx) || state.session.explanationOpen;
    const oClass = ["action-btn"];
    const xClass = ["action-btn"];
    let oxStatusText = "아직 답을 선택하지 않았습니다.";
    let oxStatusClass = "subtle";
    if (selectedOx && expectedOx) {
      if (selectedOx === expectedOx) {
        oxStatusText = "정답입니다.";
        oxStatusClass = "ox-status-correct";
        if (selectedOx === "O") oClass.push("correct");
        if (selectedOx === "X") xClass.push("correct");
      } else {
        oxStatusText = "오답입니다.";
        oxStatusClass = "ox-status-wrong";
        if (expectedOx === "O") oClass.push("correct");
        if (expectedOx === "X") xClass.push("correct");
        if (selectedOx === "O") oClass.push("wrong");
        if (selectedOx === "X") xClass.push("wrong");
      }
    }
    const oxExplanation = q.choice_explanation_text || q.judge_reason || q.explanation_text || "해설 준비중입니다.";
    root.innerHTML = `
      <div><strong>OX 문제</strong></div>
      <div style="margin-top:8px;">${q.choice_text}</div>
      <div class="subtle" style="margin-top:8px;">풀이 ${stats.solvedCount}회 · 정답 ${stats.correctCount}회 · 정답률 ${stats.accuracy}%</div>
      <div class="question-actions" style="grid-template-columns:1fr 1fr;">
        <button class="${oClass.join(" ")}" data-ox="O">O</button>
        <button class="${xClass.join(" ")}" data-ox="X">X</button>
      </div>
      <div class="question-actions" style="grid-template-columns:1fr 1fr 1fr;">
        <button class="action-btn" id="oxPrevBtn" ${disablePrev}>이전</button>
        <button class="action-btn" id="explainToggleBtn">${showExplanation ? "해설가리기" : "해설보기"}</button>
        <button class="action-btn" id="oxNextBtn" ${disableNext}>다음</button>
      </div>
      <div id="inlineExplanation" style="display:${showExplanation ? "block" : "none"};margin-top:8px;" class="item">
        <div class="${oxStatusClass}"><strong>${oxStatusText}</strong></div>
        <div>${oxExplanation}</div>
      </div>
    `;

    root.querySelectorAll("[data-ox]").forEach((btn) => {
      btn.addEventListener("click", () => {
        state.session.answers[q.id] = btn.dataset.ox;
        state.calc.expr = "";
        state.session.explanationOpen = true;
        renderQuestion();
      });
    });

    const prevBtn = $("#oxPrevBtn");
    if (prevBtn) {
      prevBtn.addEventListener("click", () => {
        if (state.session.index <= 0) return;
        state.session.index -= 1;
        renderQuestion();
      });
    }
    const nextBtn = $("#oxNextBtn");
    if (nextBtn) {
      nextBtn.addEventListener("click", () => {
        if (state.session.index >= (total - 1)) {
          const answeredCount = Object.keys(state.session.answers).length;
          if (answeredCount >= total) submitOx().catch((e) => alert(e.message));
          return;
        }
        state.session.index += 1;
        state.session.explanationOpen = false;
        renderQuestion();
      });
    }
  }

  $("#explainToggleBtn").addEventListener("click", () => toggleExplanation(q.id).catch((e) => alert(e.message)));
  const calcBtn = $("#calcBtn");
  if (calcBtn) {
    calcBtn.addEventListener("click", () => toggleInlineCalc(true));
    bindInlineCalculator();
  }
  renderTopStars();
  renderProgressGrid();
}

async function startMock() {
  syncSetupSelection();
  const list = await api(`/api/mock/questions?exam_year=${state.selection.year}&subject_code=${state.selection.subjectCode}`);
  state.session.type = "mock";
  state.session.questions = list;
  state.session.answers = {};
  state.session.index = 0;
  state.session.result = null;
  state.session.reviewMode = false;
  state.session.autoSubmitting = false;
  state.session.mockStatsById = {};
  state.calc.expr = "";
  state.session.oxStatsById = {};
  await loadChoiceVisibilityForMock(list);
  await loadMockStats(state.selection.year, state.selection.subjectCode);
  await loadFavoriteStars();
  setScoreBadge("");
  setSubmitVisible(true);
  $("#mockMeta").textContent = `${state.selection.year} ${state.selection.subjectName}`;
  showScreen("mockScreen");
  startTimer();
  renderQuestion();
}

async function startOx() {
  syncSetupSelection();
  const rawList = await api(`/api/ox/questions/v2?subject_code=${state.selection.subjectCode}`);
  const years = [...new Set(rawList.map((q) => Number(q.exam_year)).filter((y) => Number.isFinite(y)))];
  const hiddenKeys = await loadHiddenKeysForOx(state.selection.subjectCode, years);
  const list = rawList.filter((q) => !hiddenKeys.has(`${q.exam_year}|${q.subject_code}|${q.question_no_exam}|${q.choice_no}`));
  shuffleInPlace(list);
  state.session.type = "ox";
  state.session.questions = list;
  state.session.answers = {};
  state.session.index = 0;
  state.session.result = null;
  state.session.reviewMode = false;
  state.session.autoSubmitting = false;
  state.calc.expr = "";
  await loadOxStats(state.selection.subjectCode);
  await loadFavoriteStars();
  setScoreBadge("");
  setSubmitVisible(false);
  $("#mockMeta").textContent = `${state.selection.subjectName}`;
  showScreen("mockScreen");
  startTimer();
  renderQuestion();
}

async function submitMock() {
  if (!state.session.questions.length) return;
  stopTimer();
  syncSetupSelection();
  const result = await api("/api/mock/submit", {
    method: "POST",
    body: JSON.stringify({
      exam_year: state.selection.year,
      subject_code: state.selection.subjectCode,
      answers: state.session.answers,
      user_id: CURRENT_USER_ID,
      started_at: state.session.startedAt ? new Date(state.session.startedAt).toISOString() : null,
      duration_seconds: sessionDurationSeconds(),
    }),
  });
  state.session.result = result;
  state.session.reviewMode = true;
  state.session.selectedResultIndex = 0;
  const total = Number(result.total_questions || 0);
  const correct = Number(result.correct_count || 0);
  const score100 = total ? Math.round((correct / total) * 1000) / 10 : 0;
  setScoreBadge(`${score100}점/100점`);
  setSubmitVisible(false);
  state.session.autoSubmitting = false;
  renderQuestion();
  refreshDashboardChart().catch(() => {});
}

async function submitOx() {
  if (!state.session.questions.length) return;
  stopTimer();
  const result = await api("/api/ox/submit", {
    method: "POST",
    body: JSON.stringify({
      subject_code: state.selection.subjectCode,
      answers: state.session.answers,
      user_id: CURRENT_USER_ID,
      started_at: state.session.startedAt ? new Date(state.session.startedAt).toISOString() : null,
      duration_seconds: sessionDurationSeconds(),
    }),
  });
  state.session.result = result;
  state.session.reviewMode = true;
  state.session.selectedResultIndex = 0;
  const total = Number(result.total_questions || 0);
  const correct = Number(result.correct_count || 0);
  const score100 = total ? Math.round((correct / total) * 1000) / 10 : 0;
  setScoreBadge(`${score100}점/100점`);
  setSubmitVisible(false);
  state.session.autoSubmitting = false;
  renderQuestion();
  refreshDashboardChart().catch(() => {});
}

function renderResult() {
  const result = state.session.result;
  if (!result) return;
  const total = Number(result.total_questions || 0);
  const correct = Number(result.correct_count || 0);
  const score100 = total ? Math.round((correct / total) * 1000) / 10 : 0;

  $("#resultSummary").innerHTML = `
    <div><strong>${result.correct_count}/${result.total_questions} 정답 : ${score100}점 / 100점</strong></div>
    <div class="meta">문제를 눌러서 확인하세요.</div>
  `;
  renderResultProgressGrid(result);
  const idx = Math.max(0, Math.min(state.session.selectedResultIndex, result.details.length - 1));
  state.session.selectedResultIndex = idx;
  const d = result.details[idx];
  if (!d) {
    $("#resultBody").innerHTML = "<div class='item'>결과가 없습니다.</div>";
    return;
  }

  if (state.session.type === "mock") {
    const selected = String(d.selected_answer || "");
    const correctAnswer = String(d.correct_answer || "");
    const choicesHtml = (d.choices || [])
      .map((choice, i) => {
        const no = String(i + 1);
        const isCorrect = no === correctAnswer;
        const isSelected = no === selected;
        const classes = ["result-choice"];
        if (isCorrect) classes.push("correct");
        if (isSelected && !isCorrect) classes.push("wrong");
        return `<div class="${classes.join(" ")}">${no}) ${choice}</div>`;
      })
      .join("");

    $("#resultBody").innerHTML = `
      <div class="result-question">
        <div class="row-between">
          <div><strong>${d.question_no_exam}번</strong></div>
          <div id="resultStarActions" class="top-star-actions"></div>
        </div>
        <div style="margin-top:6px;">${d.question_text || ""}</div>
        <div>${choicesHtml}</div>
      </div>
    `;
    renderResultStars(d);
    return;
  }

  const selectedOx = String(d.selected_ox || "");
  const expectedOx = String(d.expected_ox || "");
  const oxOClass = ["result-choice"];
  const oxXClass = ["result-choice"];
  if (selectedOx && expectedOx) {
    if (selectedOx === expectedOx) {
      if (selectedOx === "O") oxOClass.push("correct");
      if (selectedOx === "X") oxXClass.push("correct");
    } else {
      if (expectedOx === "O") oxOClass.push("correct");
      if (expectedOx === "X") oxXClass.push("correct");
      if (selectedOx === "O") oxOClass.push("wrong");
      if (selectedOx === "X") oxXClass.push("wrong");
    }
  }
  const oxExplanation = String(d.choice_explanation_text || d.judge_reason || "").trim();

  $("#resultBody").innerHTML = `
    <div class="result-question">
      <div class="row-between">
        <div><strong>문장 판정 결과</strong></div>
        <div id="resultStarActions" class="top-star-actions"></div>
      </div>
      <div style="margin-top:6px;">${d.choice_text || ""}</div>
      <div style="margin-top:8px;">
        <div class="${oxOClass.join(" ")}">O</div>
        <div class="${oxXClass.join(" ")}">X</div>
      </div>
      <div class="item" style="margin-top:10px;">
        <div><strong>해설</strong></div>
        <div style="margin-top:6px;">${oxExplanation || "해설이 없습니다."}</div>
      </div>
    </div>
  `;
  renderResultStars(d);
}

function colorFromState(stateText) {
  const s = String(stateText || "");
  if (s.startsWith("favorite_")) return s.replace("favorite_", "");
  return "";
}

async function openQuestionFromNote(note) {
  if (String(note.source || "") === "ox" || (note.tags || []).includes("ox")) {
    state.selection.subjectCode = note.subject_code;
    state.selection.subjectName = note.subject_name || note.subject_code;
    const rawList = await api(`/api/ox/questions/v2?subject_code=${note.subject_code}`);
    const years = [...new Set(rawList.map((q) => Number(q.exam_year)).filter((y) => Number.isFinite(y)))];
    const hiddenKeys = await loadHiddenKeysForOx(note.subject_code, years);
    const list = rawList.filter((q) => !hiddenKeys.has(`${q.exam_year}|${q.subject_code}|${q.question_no_exam}|${q.choice_no}`));
    shuffleInPlace(list);
    state.session.type = "ox";
    state.session.questions = list;
    state.session.answers = {};
    state.session.index = Math.max(
      0,
      list.findIndex((q) => q.exam_year === note.exam_year && q.question_no_exam === note.question_no_exam),
    );
    state.session.result = null;
    state.session.reviewMode = false;
    state.session.autoSubmitting = false;
    setSubmitVisible(false);
    setScoreBadge("");
    await loadOxStats(note.subject_code);
    await loadFavoriteStars();
    $("#mockMeta").textContent = `${state.selection.subjectName}`;
    showScreen("mockScreen");
    stopTimer();
    renderQuestion();
    return;
  }

  state.selection.year = note.exam_year;
  state.selection.subjectCode = note.subject_code;
  state.selection.subjectName = note.subject_name || note.subject_code;
  const list = await api(`/api/mock/questions?exam_year=${note.exam_year}&subject_code=${note.subject_code}`);
  state.session.type = "mock";
  state.session.questions = list;
  state.session.answers = {};
  state.session.index = Math.max(0, list.findIndex((q) => q.question_no_exam === note.question_no_exam));
  state.session.result = null;
  state.session.reviewMode = false;
  state.session.autoSubmitting = false;
  state.session.mockStatsById = {};
  state.session.oxStatsById = {};
  setSubmitVisible(true);
  setScoreBadge("");
  await loadChoiceVisibilityForMock(list);
  await loadMockStats(note.exam_year, note.subject_code);
  await loadFavoriteStars();
  setSubmitVisible(false);
  $("#mockMeta").textContent = `${note.exam_year} ${state.selection.subjectName}`;
  showScreen("mockScreen");
  stopTimer();
  renderQuestion();
}

async function loadNotes() {
  const notes = await api(`/api/bank-notes?user_id=${encodeURIComponent(CURRENT_USER_ID)}`);
  const favorites = notes.filter((n) => String(n.state || "").startsWith("favorite_"));
  const deduped = [];
  const seen = new Set();
  favorites.forEach((n) => {
    const source = String(n.source || "mock").toLowerCase();
    const key = `${n.exam_year}|${n.subject_code}|${n.question_no_exam}|${source}`;
    if (seen.has(key)) return;
    seen.add(key);
    deduped.push(n);
  });
  state.notes.rows = deduped;
  state.notes.subjectFilter = "all";
  state.notes.colorFilter = "all";
  state.notes.sourceFilter = "all";
  state.notes.memoSearch = "";
  if ($("#notesMemoSearch")) $("#notesMemoSearch").value = "";

  const subjectMap = new Map();
  deduped.forEach((n) => {
    subjectMap.set(String(n.subject_code), String(n.subject_name || n.subject_code));
  });
  const subjectOptions = [`<option value="all">전체</option>`].concat(
    [...subjectMap.entries()]
      .sort((a, b) => a[1].localeCompare(b[1], "ko"))
      .map(([code, name]) => `<option value="${code}">${name}</option>`),
  );
  $("#notesSubjectFilter").innerHTML = subjectOptions.join("");
  $("#notesColorFilter").innerHTML = `
    <option value="all">전체</option>
    <option value="red">빨강</option>
    <option value="yellow">노랑</option>
    <option value="green">초록</option>
  `;
  $("#notesSourceFilter").innerHTML = `
    <option value="all">전체</option>
    <option value="mock">5지선다</option>
    <option value="ox">OX</option>
  `;

  $("#notesMeta").textContent = `총 ${deduped.length}건`;
  if (!deduped.length) {
    $("#notesList").innerHTML = "<div class='item'>저장된 즐겨찾기가 없습니다.</div>";
    return;
  }

  renderNotesList();
}

function renderNotesList() {
  const subject = $("#notesSubjectFilter") ? $("#notesSubjectFilter").value : "all";
  const color = $("#notesColorFilter") ? $("#notesColorFilter").value : "all";
  const source = $("#notesSourceFilter") ? $("#notesSourceFilter").value : "all";
  const memoSearch = ($("#notesMemoSearch")?.value || "").trim().toLowerCase();
  state.notes.subjectFilter = subject;
  state.notes.colorFilter = color;
  state.notes.sourceFilter = source;
  state.notes.memoSearch = memoSearch;

  const filtered = state.notes.rows.filter((n) => {
    const bySubject = subject === "all" || String(n.subject_code) === subject;
    const byColor = color === "all" || colorFromState(n.state) === color;
    const bySource = source === "all" || String(n.source || "").toLowerCase() === source;
    const memo = String(n.memo || "").toLowerCase();
    const byMemo = !memoSearch || memo.includes(memoSearch);
    return bySubject && byColor && bySource && byMemo;
  });
  $("#notesMeta").textContent = `총 ${filtered.length}건`;
  if (!filtered.length) {
    $("#notesList").innerHTML = "<div class='item'>필터 조건의 즐겨찾기가 없습니다.</div>";
    return;
  }

  $("#notesList").innerHTML = filtered
    .map((n, idx) => {
      const colorName = colorFromState(n.state);
      const colorClass = colorName ? `favorite-card ${colorName}` : "favorite-card";
      const modeLabel = String(n.source || "").toLowerCase() === "ox" ? "OX" : "5지선다";
      return `
        <div class="item note-open ${colorClass}" data-idx="${idx}">
          <div><strong>[${modeLabel}] ${n.exam_year} / ${n.subject_name || n.subject_code} / ${n.question_no_exam}번</strong></div>
        </div>
      `;
    })
    .join("");

  $("#notesList").querySelectorAll(".note-open").forEach((el) => {
    el.addEventListener("click", () => {
      const idx = Number(el.dataset.idx);
      openQuestionFromNote(filtered[idx]).catch((e) => alert(e.message));
    });
  });
}

function handleSetupContinue() {
  syncSetupSelection();

  if (state.mode === "mock") {
    if (!state.selection.year || !state.selection.subjectCode) {
      alert("연도/과목을 선택하세요.");
      return;
    }
    startMock().catch((e) => alert(e.message));
    return;
  }

  if (state.mode === "ox") {
    if (!state.selection.subjectCode) {
      alert("과목을 선택하세요.");
      return;
    }
    startOx().catch((e) => alert(e.message));
    return;
  }

}

function bindEvents() {
  document.querySelectorAll(".mode-btn").forEach((btn) => {
    btn.addEventListener("click", () => handleModeClick(btn.dataset.mode));
  });

  $("#setupYear").addEventListener("change", renderSetupSubjectsForYear);
  $("#setupSubject").addEventListener("change", syncSetupSelection);
  $("#setupContinueBtn").addEventListener("click", handleSetupContinue);
  $("#submitMockBtn").addEventListener("click", () => {
    if (state.session.type === "ox") submitOx().catch((e) => alert(e.message));
    else submitMock().catch((e) => alert(e.message));
  });
  $("#topBackBtn").addEventListener("click", () => {
    stopTimer();
    const target = state.nav.history.pop() || "homeScreen";
    showScreen(target, { skipHistory: true });
  });
  $("#notesSubjectFilter").addEventListener("change", renderNotesList);
  $("#notesColorFilter").addEventListener("change", renderNotesList);
  $("#notesSourceFilter").addEventListener("change", renderNotesList);
  $("#notesMemoSearch").addEventListener("input", renderNotesList);

  $("#topHomeBtn").addEventListener("click", () => {
    stopTimer();
    state.nav.history = [];
    showScreen("homeScreen", { skipHistory: true });
  });
}

async function init() {
  computeDday();
  bindEvents();
  bindRadarInteractions();
  showScreen("homeScreen", { skipHistory: true });

  await api("/api/users/upsert", {
    method: "POST",
    body: JSON.stringify({ user_id: CURRENT_USER_ID, display_name: "로컬 사용자" }),
  });

  state.options = await api("/api/mock/options");
  state.oxOptions = await api("/api/ox/options");
  await refreshDashboardChart();
}

init().catch((err) => {
  console.error(err);
  alert(`초기화 실패: ${err.message}`);
});







