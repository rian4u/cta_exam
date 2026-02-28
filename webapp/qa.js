const message = document.getElementById("qa-message");
const list = document.getElementById("qa-list");
const nicknameInput = document.getElementById("qa-nickname");
const titleInput = document.getElementById("qa-title");
const subjectInput = document.getElementById("qa-subject");
const yearInput = document.getElementById("qa-year");
const questionNoInput = document.getElementById("qa-question-no");
const bodyInput = document.getElementById("qa-body");
const submitButton = document.getElementById("qa-submit");
const refreshButton = document.getElementById("qa-refresh");

const state = {
  apiReady: false,
  apiBase: "",
};

const STORAGE_KEY = "qa:nickname";

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
      state.apiReady = true;
      state.apiBase = base;
      return true;
    } catch (_) {}
  }
  state.apiReady = false;
  state.apiBase = "";
  return false;
}

function setMessage(text) {
  if (message) {
    message.textContent = text || "";
  }
}

function saveNickname() {
  const nickname = String(nicknameInput?.value || "").trim();
  if (!nickname) {
    localStorage.removeItem(STORAGE_KEY);
    return;
  }
  localStorage.setItem(STORAGE_KEY, nickname);
}

function restoreNickname() {
  const nickname = localStorage.getItem(STORAGE_KEY) || "";
  if (nicknameInput && nickname) {
    nicknameInput.value = nickname;
  }
}

function createAnswerForm(postId) {
  const wrap = document.createElement("div");
  wrap.className = "qa-answer-form";

  const input = document.createElement("textarea");
  input.className = "wrong-input qa-answer-input";
  input.rows = 3;
  input.placeholder = "이 질문에 대한 답변을 남기세요.";

  const button = document.createElement("button");
  button.type = "button";
  button.className = "exam-back";
  button.textContent = "답변 등록";

  button.addEventListener("click", async () => {
    const nickname = String(nicknameInput?.value || "").trim();
    const body = input.value.trim();
    saveNickname();
    if (!nickname || !body) {
      setMessage("답변 등록에는 닉네임과 내용이 필요합니다.");
      return;
    }
    if (!state.apiReady && !(await verifyApiReady())) {
      setMessage("QA API에 연결할 수 없습니다.");
      return;
    }
    button.disabled = true;
    try {
      const response = await fetch(`${state.apiBase}/api/qa/answers`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          post_id: postId,
          nickname,
          body,
        }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) {
        setMessage(payload.error || "답변 등록에 실패했습니다.");
        return;
      }
      input.value = "";
      setMessage("답변이 등록되었습니다.");
      await loadPosts();
    } catch (_) {
      setMessage("답변 등록 중 오류가 발생했습니다.");
    } finally {
      button.disabled = false;
    }
  });

  wrap.append(input, button);
  return wrap;
}

function renderPosts(items) {
  if (!list) {
    return;
  }
  list.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("div");
    empty.className = "qa-empty";
    empty.textContent = "?? ??? ??? ????.";
    list.appendChild(empty);
    return;
  }

  items.forEach((item) => {
    const card = document.createElement("article");
    card.className = "qa-item";

    const details = document.createElement("details");
    details.className = "qa-disclosure";

    const summary = document.createElement("summary");
    summary.className = "qa-summary";

    const title = document.createElement("div");
    title.className = "qa-title";
    title.textContent = item.title || "(?? ??)";

    const meta = document.createElement("div");
    meta.className = "qa-meta";
    const parts = [item.nickname || "??", item.updated_at || item.created_at || "-"];
    if (item.subject) {
      let questionRef = item.subject;
      if (Number(item.year) > 0) {
        questionRef += ` ${item.year}`;
      }
      if (Number(item.question_no) > 0) {
        questionRef += `-${item.question_no}?`;
      }
      parts.push(questionRef);
    }
    meta.textContent = parts.join(" ? ");

    const content = document.createElement("div");
    content.className = "qa-content";

    const body = document.createElement("div");
    body.className = "qa-body";
    body.textContent = item.body || "";

    const answerList = document.createElement("div");
    answerList.className = "qa-answer-list";
    const answers = Array.isArray(item.answers) ? item.answers : [];
    if (!answers.length) {
      const empty = document.createElement("div");
      empty.className = "qa-answer-empty";
      empty.textContent = "?? ??? ????.";
      answerList.appendChild(empty);
    } else {
      answers.forEach((answer) => {
        const answerCard = document.createElement("div");
        answerCard.className = "qa-answer-item";

        const answerMeta = document.createElement("div");
        answerMeta.className = "qa-answer-meta";
        answerMeta.textContent = `${answer.nickname || "??"} ? ${answer.updated_at || answer.created_at || "-"}`;

        const answerBody = document.createElement("div");
        answerBody.className = "qa-answer-body";
        answerBody.textContent = answer.body || "";

        answerCard.append(answerMeta, answerBody);
        answerList.appendChild(answerCard);
      });
    }

    summary.append(title, meta);
    content.append(body, answerList, createAnswerForm(item.id));
    details.append(summary, content);
    card.append(details);
    list.appendChild(card);
  });
}

async function loadPosts() {
  if (!state.apiReady && !(await verifyApiReady())) {
    setMessage("QA API에 연결할 수 없습니다.");
    renderPosts([]);
    return;
  }
  try {
    const response = await fetch(`${state.apiBase}/api/qa/posts?limit=60`, { mode: "cors" });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMessage(payload.error || "질문 목록을 불러오지 못했습니다.");
      renderPosts([]);
      return;
    }
    setMessage("");
    renderPosts(Array.isArray(payload.items) ? payload.items : []);
  } catch (_) {
    setMessage("질문 목록을 불러오는 중 오류가 발생했습니다.");
    renderPosts([]);
  }
}

async function submitPost() {
  saveNickname();
  const nickname = String(nicknameInput?.value || "").trim();
  const title = String(titleInput?.value || "").trim();
  const body = String(bodyInput?.value || "").trim();
  const subject = String(subjectInput?.value || "").trim();
  const year = Number(yearInput?.value || 0);
  const questionNo = Number(questionNoInput?.value || 0);

  if (!nickname || !title || !body) {
    setMessage("닉네임, 제목, 내용은 필수입니다.");
    return;
  }
  if (!state.apiReady && !(await verifyApiReady())) {
    setMessage("QA API에 연결할 수 없습니다.");
    return;
  }

  submitButton.disabled = true;
  try {
    const response = await fetch(`${state.apiBase}/api/qa/posts`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        nickname,
        title,
        body,
        subject,
        year,
        question_no: questionNo,
      }),
    });
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      setMessage(payload.error || "질문 등록에 실패했습니다.");
      return;
    }
    if (titleInput) titleInput.value = "";
    if (bodyInput) bodyInput.value = "";
    if (yearInput) yearInput.value = "";
    if (questionNoInput) questionNoInput.value = "";
    if (subjectInput) subjectInput.value = "";
    setMessage("질문이 등록되었습니다.");
    await loadPosts();
  } catch (_) {
    setMessage("질문 등록 중 오류가 발생했습니다.");
  } finally {
    submitButton.disabled = false;
  }
}

restoreNickname();
submitButton?.addEventListener("click", submitPost);
refreshButton?.addEventListener("click", () => {
  loadPosts();
});
nicknameInput?.addEventListener("change", saveNickname);
loadPosts();
