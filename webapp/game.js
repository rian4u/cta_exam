const YEAR = 2025;
const SUBJECTS = ["재정학", "회계학개론", "상법", "민법", "행정소송법", "국세기본법", "국세징수법", "소득세법", "법인세법", "부가가치세법", "조세범처벌법"];
const MAX_LIVES = 3;
const SWIPE_THRESHOLD = 56;
const MILESTONES = [
  { score: 20, text: "세무사 1차 합격권 진입!" },
  { score: 50, text: "집중력 최고조! 계속 밀어붙이세요." },
  { score: 100, text: "실전 감각 완성권 진입!" },
];

const arena = document.getElementById("game-arena");
const overlay = document.getElementById("game-overlay");
const overlayTitle = document.getElementById("game-overlay-title");
const overlayText = document.getElementById("game-overlay-text");
const overlayButton = document.getElementById("game-overlay-btn");
const overlayReviewButton = document.getElementById("game-overlay-review-btn");
const statusNode = document.getElementById("game-status");
const emptyNode = document.getElementById("game-empty");
const scoreNode = document.getElementById("game-score");
const comboNode = document.getElementById("game-combo");
const flashNode = document.getElementById("game-flash");
const milestoneNode = document.getElementById("game-milestone");
const subjectSelect = document.getElementById("game-subject");
const toggleButton = document.getElementById("game-toggle-btn");
const resetButton = document.getElementById("game-reset-btn");
const characterNode = document.getElementById("game-character");
const reviewPanel = document.getElementById("game-review-panel");
const reviewCloseButton = document.getElementById("game-review-close-btn");
const reviewSummary = document.getElementById("game-review-summary");
const reviewList = document.getElementById("game-review-list");
const hearts = Array.from(document.querySelectorAll(".game-heart"));

const state = {
  apiBase: "",
  apiReady: false,
  subject: subjectSelect?.value || SUBJECTS[0],
  pool: [],
  xPool: [],
  oPool: [],
  queue: [],
  blocks: [],
  running: false,
  paused: false,
  score: 0,
  combo: 0,
  lives: MAX_LIVES,
  lastFrameAt: 0,
  lastSpawnAt: 0,
  nextBlockId: 1,
  arenaWidth: 0,
  arenaHeight: 0,
  milestonesShown: new Set(),
  flashTimer: 0,
  audioCtx: null,
  nextSpawnTimer: 0,
  reviewHistory: [],
};

function getApiBaseCandidates() {
  const candidates = [];
  const { origin, protocol, hostname } = window.location;
  if (origin && origin !== "null" && protocol.startsWith("http")) {
    candidates.push(origin);
  }
  if (hostname) {
    candidates.push(`http://${hostname}:8000`);
  }
  candidates.push("http://127.0.0.1:8000");
  candidates.push("http://localhost:8000");
  return [...new Set(candidates)];
}

async function verifyApiReady() {
  for (const base of getApiBaseCandidates()) {
    try {
      const response = await fetch(`${base}/api/health`, { mode: "cors" });
      if (!response.ok) {
        continue;
      }
      state.apiBase = base;
      state.apiReady = true;
      return true;
    } catch (_) {}
  }
  state.apiBase = "";
  state.apiReady = false;
  return false;
}

function setStatus(text) {
  if (statusNode) {
    statusNode.textContent = text || "";
  }
}

function formatScore(value) {
  return String(Math.max(0, Number(value) || 0)).padStart(5, "0");
}

function updateHud() {
  if (scoreNode) {
    scoreNode.textContent = formatScore(state.score);
  }
  if (comboNode) {
    comboNode.textContent = String(state.combo);
  }
  hearts.forEach((heart, index) => {
    heart.classList.toggle("is-empty", index >= state.lives);
  });
  if (arena) {
    arena.classList.toggle("combo-on", state.combo >= 5);
  }
}

function updateToggleButton() {
  if (!toggleButton) {
    return;
  }
  const showPause = state.running && !state.paused;
  toggleButton.classList.toggle("is-pause", showPause);
  toggleButton.setAttribute("aria-label", showPause ? "일시정지" : "재생");
  toggleButton.setAttribute("title", showPause ? "일시정지" : "재생");
}

function setOverlay(title, text, buttonLabel = "다시 시작", visible = true, { showReview = false } = {}) {
  if (overlayTitle) overlayTitle.textContent = title;
  if (overlayText) overlayText.textContent = text;
  if (overlayButton) overlayButton.textContent = buttonLabel;
  if (overlayReviewButton) {
    overlayReviewButton.classList.toggle("is-hidden", !showReview);
    if (!showReview) {
      overlayReviewButton.textContent = "해설보기";
    }
  }
  if (overlay) {
    overlay.classList.toggle("is-hidden", !visible);
  }
}

function shuffle(items) {
  const copy = [...items];
  for (let i = copy.length - 1; i > 0; i -= 1) {
    const j = Math.floor(Math.random() * (i + 1));
    [copy[i], copy[j]] = [copy[j], copy[i]];
  }
  return copy;
}

function trimQuestion(text) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  if (value.length <= 58) {
    return value;
  }
  return `${value.slice(0, 58).trim()}...`;
}

function hideReviewPanel({ clear = true } = {}) {
  if (reviewPanel) {
    reviewPanel.classList.add("is-hidden");
  }
  if (clear && reviewList) {
    reviewList.innerHTML = "";
  }
  if (clear && reviewSummary) {
    reviewSummary.textContent = "";
  }
}

function showReviewPanel() {
  if (reviewPanel) {
    reviewPanel.classList.remove("is-hidden");
  }
}

function recordReview(block, outcome) {
  state.reviewHistory.push({
    question: String(block?.question || "").trim(),
    answer: String(block?.answer || "").trim().toUpperCase(),
    explanation: String(block?.explanation || "").trim(),
    outcome: String(outcome || ""),
  });
}

function renderReviewPanel() {
  if (!reviewPanel || !reviewList || !reviewSummary) {
    return;
  }
  reviewList.innerHTML = "";
  const items = state.reviewHistory.filter((item) => item.question);
  const wrongCount = items.filter((item) => item.outcome !== "correct").length;
  reviewSummary.textContent = `총 ${items.length}문제 | 오답/실수 ${wrongCount}문제`;
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "qa-empty";
    empty.textContent = "복습할 문제가 없습니다.";
    reviewList.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "game-review-item";

    const head = document.createElement("div");
    head.className = "game-review-item-head";

    const title = document.createElement("div");
    title.className = "game-review-title";
    title.textContent = item.question;

    const meta = document.createElement("div");
    meta.className = "game-review-meta";
    meta.textContent =
      item.outcome === "correct" ? `정답 ${item.answer}` : `놓침/오답 | 정답 ${item.answer}`;
    if (item.outcome !== "correct") {
      meta.classList.add("is-wrong");
    }

    const body = document.createElement("div");
    body.className = "game-review-body";
    body.textContent = item.explanation || "해설 정보가 없습니다.";

    head.append(title);
    card.append(head, meta, body);
    reviewList.appendChild(card);
  });
}


function clearBlocks() {
  state.blocks.forEach((block) => {
    block.el?.remove();
  });
  state.blocks = [];
}

function ensureAudio() {
  if (state.audioCtx || !window.AudioContext) {
    return state.audioCtx;
  }
  state.audioCtx = new AudioContext();
  return state.audioCtx;
}

function playTone(type) {
  const audioCtx = ensureAudio();
  if (!audioCtx) {
    return;
  }
  if (audioCtx.state === "suspended") {
    audioCtx.resume().catch(() => {});
  }
  const now = audioCtx.currentTime;
  const gain = audioCtx.createGain();
  gain.connect(audioCtx.destination);
  gain.gain.setValueAtTime(0.0001, now);

  if (type === "good") {
    const osc1 = audioCtx.createOscillator();
    const osc2 = audioCtx.createOscillator();
    osc1.type = "triangle";
    osc2.type = "square";
    osc1.frequency.setValueAtTime(740, now);
    osc2.frequency.setValueAtTime(1110, now);
    osc1.connect(gain);
    osc2.connect(gain);
    gain.gain.exponentialRampToValueAtTime(0.06, now + 0.02);
    gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.18);
    osc1.start(now);
    osc2.start(now);
    osc1.stop(now + 0.18);
    osc2.stop(now + 0.18);
    return;
  }

  const osc = audioCtx.createOscillator();
  osc.type = "sawtooth";
  osc.frequency.setValueAtTime(240, now);
  osc.frequency.exponentialRampToValueAtTime(140, now + 0.24);
  osc.connect(gain);
  gain.gain.exponentialRampToValueAtTime(0.08, now + 0.02);
  gain.gain.exponentialRampToValueAtTime(0.0001, now + 0.28);
  osc.start(now);
  osc.stop(now + 0.28);
}

function showFlash(text, tone) {
  if (!flashNode) {
    return;
  }
  flashNode.textContent = text;
  flashNode.className = `game-flash is-visible ${tone === "good" ? "is-good" : "is-bad"}`;
  window.clearTimeout(state.flashTimer);
  state.flashTimer = window.setTimeout(() => {
    if (flashNode) {
      flashNode.className = "game-flash";
      flashNode.textContent = "";
    }
  }, 420);
}

function showMilestone(text) {
  if (!milestoneNode) {
    return;
  }
  milestoneNode.textContent = text;
  milestoneNode.classList.add("is-visible");
  window.setTimeout(() => {
    milestoneNode.classList.remove("is-visible");
  }, 1900);
}

function clearNextSpawnTimer() {
  if (state.nextSpawnTimer) {
    window.clearTimeout(state.nextSpawnTimer);
    state.nextSpawnTimer = 0;
  }
}

function scheduleNextSpawn(delayMs = 120) {
  clearNextSpawnTimer();
  if (!state.running) {
    return;
  }
  state.nextSpawnTimer = window.setTimeout(() => {
    state.nextSpawnTimer = 0;
    if (!state.running || state.paused || state.blocks.length > 0) {
      return;
    }
    spawnBlock();
    state.lastSpawnAt = performance.now();
  }, delayMs);
}

function updateCharacter(mode) {
  if (!characterNode) {
    return;
  }
  characterNode.classList.remove("is-panic", "is-cheer", "is-down");
  if (mode) {
    characterNode.classList.add(mode);
    if (mode !== "is-down") {
      window.setTimeout(() => {
        characterNode.classList.remove(mode);
      }, mode === "is-cheer" ? 500 : 700);
    }
  }
}

function applyMilestones() {
  for (const item of MILESTONES) {
    if (state.score >= item.score && !state.milestonesShown.has(item.score)) {
      state.milestonesShown.add(item.score);
      showMilestone(item.text);
      updateCharacter("is-cheer");
    }
  }
}

function loseLife(reason) {
  state.combo = 0;
  state.lives = Math.max(0, state.lives - 1);
  updateHud();
  playTone("bad");
  showFlash("X", "bad");
  updateCharacter("is-panic");
  if (reason) {
    setStatus(reason);
  }
  if (state.lives <= 0) {
    endGame();
  }
}

function removeBlock(block, withBurst = false) {
  const target = state.blocks.find((item) => item.id === block.id);
  if (!target) {
    return;
  }
  target.removing = true;
  target.dragging = false;
  if (withBurst) {
    target.el.classList.add("is-burst");
  }
  window.setTimeout(() => {
    target.el?.remove();
  }, withBurst ? 260 : 0);
  state.blocks = state.blocks.filter((item) => item.id !== block.id);
}

function handleCorrect(block) {
  recordReview(block, "correct");
  state.combo += 1;
  const scoreDelta = state.combo >= 5 ? 2 : 1;
  state.score += scoreDelta;
  updateHud();
  applyMilestones();
  showFlash("O", "good");
  playTone("good");
  updateCharacter(state.combo >= 5 ? "is-cheer" : "");
  setStatus(state.combo >= 5 ? `콤보 ${state.combo}. 점수 2배 적용 중입니다.` : "정답입니다.");
  removeBlock(block, true);
  scheduleNextSpawn(180);
}

function handleIncorrect(block, reason = "오답입니다. 다시 확인하세요.") {
  if (block.removing) {
    return;
  }
  recordReview(block, "wrong");
  block.removing = true;
  block.dragging = false;
  block.el.classList.add("is-wrong");
  state.blocks = state.blocks.filter((item) => item.id !== block.id);
  window.setTimeout(() => {
    block.el?.remove();
  }, 180);
  loseLife(reason);
  if (state.running) {
    scheduleNextSpawn(180);
  }
}

function updateBlockTransform(block) {
  const offsetX = block.dragOffsetX || 0;
  block.el.style.transform = `translate(${block.x + offsetX}px, ${block.y}px)`;
}

function resolveSwipe(block, direction) {
  if (!state.running || state.paused || block.removing) {
    return;
  }
  const selectedAnswer = direction === "left" ? "O" : direction === "right" ? "X" : "";
  if (!selectedAnswer) {
    return;
  }
  if (String(block.answer).toUpperCase() === selectedAnswer) {
    handleCorrect(block);
  } else {
    handleIncorrect(block);
  }
}

function onBlockPointerDown(block, event) {
  if (!state.running || state.paused || block.removing || block.dragging) {
    return;
  }
  block.dragging = true;
  block.pointerId = event.pointerId;
  block.dragStartX = event.clientX;
  block.dragOffsetX = 0;
  block.el.classList.add("is-dragging");
  if (typeof block.el.setPointerCapture === "function") {
    try {
      block.el.setPointerCapture(event.pointerId);
    } catch (_) {}
  }
}

function onBlockPointerMove(block, event) {
  if (!block.dragging || block.pointerId !== event.pointerId || block.removing) {
    return;
  }
  block.dragOffsetX = Math.max(-96, Math.min(96, event.clientX - block.dragStartX));
  updateBlockTransform(block);
}

function finishBlockPointer(block, event, cancelled = false) {
  if (!block.dragging || (event && block.pointerId !== event.pointerId)) {
    return;
  }
  const deltaX = cancelled || !event ? 0 : event.clientX - block.dragStartX;
  block.dragging = false;
  block.pointerId = null;
  block.dragStartX = 0;
  block.dragOffsetX = 0;
  block.el.classList.remove("is-dragging");
  if (event && typeof block.el.releasePointerCapture === "function") {
    try {
      block.el.releasePointerCapture(event.pointerId);
    } catch (_) {}
  }
  updateBlockTransform(block);
  if (cancelled || block.removing) {
    return;
  }
  if (deltaX <= -SWIPE_THRESHOLD) {
    resolveSwipe(block, "left");
    return;
  }
  if (deltaX >= SWIPE_THRESHOLD) {
    resolveSwipe(block, "right");
    return;
  }
  setStatus("O는 왼쪽, X는 오른쪽으로 밀어주세요.");
}

function computeSpawnInterval() {
  return 10800;
}

function createBlock(item) {
  if (!arena) {
    return;
  }
  const el = document.createElement("button");
  el.type = "button";
  el.className = "falling-block";
  el.setAttribute("aria-label", "문제 블록");

  const text = document.createElement("span");
  text.className = "falling-block-text";
  text.textContent = trimQuestion(item.question);

  el.append(text);

  const width = 176;
  const horizontalPadding = 10;
  const maxX = Math.max(horizontalPadding, state.arenaWidth - width - horizontalPadding);
  const x = horizontalPadding + Math.floor(Math.random() * Math.max(1, maxX - horizontalPadding + 1));
  const travelDistance = Math.max(1, state.arenaHeight + 96 - 120);
  const speed = travelDistance / 10;
  const block = {
    id: state.nextBlockId += 1,
    answer: String(item.answer || "").toUpperCase(),
    question: item.question || "",
    explanation: item.explanation || "",
    x,
    y: -96,
    width,
    speed,
    el,
    removing: false,
    pointerId: null,
    dragStartX: 0,
    dragOffsetX: 0,
    dragging: false,
  };

  el.style.width = `${width}px`;
  updateBlockTransform(block);
  el.addEventListener("pointerdown", (event) => onBlockPointerDown(block, event));
  el.addEventListener("pointermove", (event) => onBlockPointerMove(block, event));
  el.addEventListener("pointerup", (event) => finishBlockPointer(block, event));
  el.addEventListener("pointercancel", (event) => finishBlockPointer(block, event, true));
  el.addEventListener("lostpointercapture", () => finishBlockPointer(block, null, true));

  arena.appendChild(el);
  state.blocks.push(block);
}

function refillQueue() {
  if (state.queue.length > 0) {
    return;
  }
  state.queue = shuffle(state.pool);
}

function spawnBlock() {
  refillQueue();
  const item = state.queue.shift();
  if (!item) {
    return;
  }
  createBlock(item);
}

function step(timestamp) {
  if (!state.running) {
    state.lastFrameAt = 0;
    return;
  }
  if (state.paused) {
    state.lastFrameAt = timestamp;
    window.requestAnimationFrame(step);
    return;
  }
  if (!state.lastFrameAt) {
    state.lastFrameAt = timestamp;
  }
  const delta = Math.min(48, timestamp - state.lastFrameAt);
  state.lastFrameAt = timestamp;

  if (!state.lastSpawnAt) {
    state.lastSpawnAt = timestamp;
  }

  const toRemove = [];
  for (const block of state.blocks) {
    if (block.removing) {
      continue;
    }
    block.y += (block.speed * delta) / 1000;
    updateBlockTransform(block);
    if (block.y >= state.arenaHeight - 120) {
      toRemove.push(block);
    }
  }

  for (const block of toRemove) {
    recordReview(block, "missed");
    removeBlock(block, false);
    loseLife("끝까지 내려와서 생명이 차감되었습니다.");
    if (!state.running) {
      break;
    }
    scheduleNextSpawn(120);
  }

  window.requestAnimationFrame(step);
}

function resetStateForRun() {
  clearNextSpawnTimer();
  clearBlocks();
  state.reviewHistory = [];
  state.score = 0;
  state.combo = 0;
  state.lives = MAX_LIVES;
  state.running = false;
  state.paused = false;
  state.lastFrameAt = 0;
  state.lastSpawnAt = 0;
  state.milestonesShown = new Set();
  updateHud();
  updateToggleButton();
  updateCharacter("");
  hideReviewPanel();
  if (overlayReviewButton) {
    overlayReviewButton.textContent = "해설보기";
  }
}

function prepareArenaMetrics() {
  if (!arena) {
    return;
  }
  const rect = arena.getBoundingClientRect();
  state.arenaWidth = rect.width;
  state.arenaHeight = rect.height;
}

function startRun() {
  if (!state.pool.length) {
    setOverlay(
      "출제 불가",
      "해당 과목의 OX 데이터가 없습니다. 다른 과목을 선택하거나 OX 데이터를 먼저 적재해 주세요.",
      "닫기",
      true,
      { showReview: false }
    );
    setStatus("선택한 과목의 OX 데이터가 없습니다.");
    if (emptyNode) {
      emptyNode.classList.remove("is-hidden");
    }
    return;
  }
  ensureAudio();
  prepareArenaMetrics();
  resetStateForRun();
  state.queue = [];
  state.running = true;
  state.paused = false;
  setOverlay("", "", "", false, { showReview: false });
  if (emptyNode) {
    emptyNode.classList.add("is-hidden");
  }
  setStatus(`${state.subject} OX ${state.pool.length}문제로 시작합니다.`);
  updateToggleButton();
  spawnBlock();
  window.requestAnimationFrame(step);
}

function endGame() {
  clearNextSpawnTimer();
  state.running = false;
  state.paused = false;
  updateToggleButton();
  updateCharacter("is-down");
  renderReviewPanel();
  hideReviewPanel({ clear: false });
  setOverlay(
    "불합격(Game Over)",
    `최종 점수 ${formatScore(state.score)}. 다시 시작하거나 해설을 확인하세요.`,
    "다시 시작",
    true,
    { showReview: true }
  );
  setStatus("하트를 모두 잃었습니다.");
}

function togglePause() {
  if (!state.running) {
    startRun();
    return;
  }
  state.paused = !state.paused;
  updateToggleButton();
  setStatus(state.paused ? "일시정지 상태입니다." : "다시 진행합니다.");
}

async function fetchOxQuestions(subject) {
  if (!state.apiReady && !(await verifyApiReady())) {
    throw new Error("OX API에 연결할 수 없습니다.");
  }
  const url = `${state.apiBase}/api/ox/questions?year=${YEAR}&subject=${encodeURIComponent(subject)}`;
  const response = await fetch(url, { mode: "cors" });
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload.error || "OX 데이터를 불러오지 못했습니다.");
  }
  const questions = Array.isArray(payload.questions) ? payload.questions : [];
  return questions
    .map((item) => ({
      question: String(item.question || "").trim(),
      answer: String(item.answer || "").trim().toUpperCase(),
      explanation: String(item.explanation || "").trim(),
    }))
    .filter((item) => item.question && (item.answer === "O" || item.answer === "X"));
}

async function loadSubject(subject) {
  state.subject = subject;
  setStatus(`${subject} OX 데이터를 불러오는 중입니다.`);
  resetStateForRun();
  setOverlay("로딩 중", `${subject} OX 데이터를 불러오는 중입니다.`, "대기", true);
  if (overlayButton) {
    overlayButton.disabled = true;
  }
  try {
    const questions = await fetchOxQuestions(subject);
    state.pool = shuffle(questions);
    state.xPool = questions.filter((item) => item.answer === "X");
    state.oPool = questions.filter((item) => item.answer === "O");
    state.queue = [];
    if (!questions.length) {
      if (emptyNode) {
        emptyNode.classList.remove("is-hidden");
      }
      setOverlay("데이터 없음", `${subject} 과목은 아직 OX 데이터가 없습니다. 다른 과목을 선택하세요.`, "닫기", true);
      setStatus(`${subject} 과목은 아직 OX 데이터가 없습니다.`);
      return;
    }
    if (emptyNode) {
      emptyNode.classList.add("is-hidden");
    }
    setOverlay("준비 완료", `${subject} OX ${questions.length}문제를 불러왔습니다. 게임 시작을 누르세요.`, "게임 시작", true);
    setStatus(`${subject} OX ${questions.length}문제를 불러왔습니다.`);
  } catch (error) {
    state.pool = [];
    state.queue = [];
    if (emptyNode) {
      emptyNode.classList.remove("is-hidden");
    }
    setOverlay("연결 실패", error instanceof Error ? error.message : "OX API 연결에 실패했습니다.", "닫기", true);
    setStatus(error instanceof Error ? error.message : "OX API 연결에 실패했습니다.");
  } finally {
    if (overlayButton) {
      overlayButton.disabled = false;
    }
  }
}

function handleSubjectChange() {
  const subject = String(subjectSelect?.value || SUBJECTS[0]).trim();
  if (!SUBJECTS.includes(subject)) {
    return;
  }
  state.subject = subject;
  loadSubject(subject);
}

if (subjectSelect) {
  subjectSelect.addEventListener("change", handleSubjectChange);
}

if (toggleButton) {
  toggleButton.addEventListener("click", togglePause);
}

if (resetButton) {
  resetButton.addEventListener("click", () => {
    loadSubject(state.subject).then(() => {
      if (state.pool.length) {
        startRun();
      }
    });
  });
}

if (overlayButton) {
  overlayButton.addEventListener("click", () => {
    if (state.running) {
      return;
    }
    if (!state.pool.length) {
      loadSubject(state.subject);
      return;
    }
    startRun();
  });
}

if (overlayReviewButton) {
  overlayReviewButton.addEventListener("click", () => {
    if (reviewPanel?.classList.contains("is-hidden")) {
      showReviewPanel();
      overlayReviewButton.textContent = "해설닫기";
    } else {
      hideReviewPanel({ clear: false });
      overlayReviewButton.textContent = "해설보기";
    }
  });
}

if (reviewCloseButton) {
  reviewCloseButton.addEventListener("click", () => {
    hideReviewPanel({ clear: false });
    if (overlayReviewButton) {
      overlayReviewButton.textContent = "해설보기";
    }
  });
}

window.addEventListener("resize", prepareArenaMetrics);

updateHud();
updateToggleButton();
verifyApiReady().finally(() => {
  loadSubject(state.subject);
});
