(function () {
  const DEVICE_KEY = "taxexam:device-id";
  const NOTES_KEY = "taxexam:user-notes:v1";
  const NOTES_BACKUP_KEY = "taxexam:user-notes:v1:backup";
  const IMPORTANCE_LEVELS = new Set(["red", "yellow", "green", "gray"]);

  function normalizeText(value, maxLength = 0) {
    const text = String(value ?? "").trim();
    if (!maxLength || text.length <= maxLength) {
      return text;
    }
    return text.slice(0, maxLength);
  }

  function normalizeImportance(value) {
    const normalized = String(value || "")
      .trim()
      .toLowerCase();
    return IMPORTANCE_LEVELS.has(normalized) ? normalized : "";
  }

  function normalizeSource(value) {
    const normalized = String(value || "")
      .trim()
      .toLowerCase();
    return normalized === "ox" ? "ox" : "question";
  }

  function normalizeYear(value) {
    const year = Number(value || 0);
    return Number.isFinite(year) ? year : 0;
  }

  function normalizeQuestionNo(value) {
    const questionNo = Number(value || 0);
    return Number.isFinite(questionNo) ? questionNo : 0;
  }

  function normalizeQuestionKey(value) {
    return normalizeText(value, 160);
  }

  function makeNoteKey({ source, year, subject, question_no, question_key }) {
    const normalizedSource = normalizeSource(source);
    const normalizedQuestionKey = normalizeQuestionKey(question_key);
    if (normalizedSource === "ox" && normalizedQuestionKey) {
      return [
        normalizedSource,
        String(normalizeYear(year)),
        normalizeText(subject, 100),
        normalizedQuestionKey,
      ].join("|");
    }
    return [
      normalizedSource,
      String(normalizeYear(year)),
      normalizeText(subject, 100),
      String(normalizeQuestionNo(question_no)),
    ].join("|");
  }

  function generateDeviceId() {
    try {
      if (window.crypto && typeof window.crypto.randomUUID === "function") {
        return `device-${window.crypto.randomUUID()}`;
      }
    } catch (_) {}
    return `device-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
  }

  function getDeviceId() {
    let value = "";
    try {
      value = normalizeText(localStorage.getItem(DEVICE_KEY), 96);
    } catch (_) {
      value = "";
    }
    if (!value) {
      value = generateDeviceId();
      try {
        localStorage.setItem(DEVICE_KEY, value);
      } catch (_) {}
    }
    return value;
  }

  function parseStore(raw) {
    if (!raw) {
      return null;
    }
    const parsed = JSON.parse(raw);
    if (!parsed || typeof parsed !== "object") {
      return null;
    }
    return parsed.notes && typeof parsed.notes === "object" ? parsed.notes : {};
  }

  function readStore() {
    try {
      const primary = parseStore(localStorage.getItem(NOTES_KEY));
      if (primary) {
        return primary;
      }
      const backup = parseStore(localStorage.getItem(NOTES_BACKUP_KEY));
      if (backup) {
        localStorage.setItem(
          NOTES_KEY,
          JSON.stringify({
            version: 1,
            restored_at: new Date().toISOString(),
            notes: backup,
          })
        );
        return backup;
      }
      return {};
    } catch (_) {
      return {};
    }
  }

  function writeStore(notes) {
    const payload = JSON.stringify({
      version: 1,
      updated_at: new Date().toISOString(),
      notes,
    });
    try {
      localStorage.setItem(NOTES_KEY, payload);
      localStorage.setItem(NOTES_BACKUP_KEY, payload);
    } catch (_) {}
  }

  function sanitizeEntry(entry) {
    if (!entry || typeof entry !== "object") {
      return null;
    }
    const next = {
      source: normalizeSource(entry.source),
      year: normalizeYear(entry.year),
      subject: normalizeText(entry.subject, 100),
      question_key: normalizeQuestionKey(entry.question_key),
      question_no: normalizeQuestionNo(entry.question_no),
      importance: normalizeImportance(entry.importance),
      comment: normalizeText(entry.comment, 4000),
      updated_at: normalizeText(entry.updated_at || new Date().toISOString(), 40),
      question_preview: normalizeText(entry.question_preview, 1000),
      answer: normalizeText(entry.answer, 64),
      explanation: normalizeText(entry.explanation, 8000),
    };
    if (!next.subject || next.question_no <= 0) {
      return null;
    }
    if (!next.importance && !next.comment) {
      return null;
    }
    return next;
  }

  function upsertNote(entry) {
    const key = makeNoteKey(entry);
    const notes = readStore();
    const sanitized = sanitizeEntry(entry);
    if (!sanitized) {
      delete notes[key];
      writeStore(notes);
      return null;
    }
    notes[key] = sanitized;
    writeStore(notes);
    return sanitized;
  }

  function getNote(query) {
    const notes = readStore();
    const key = makeNoteKey(query);
    const entry = notes[key];
    const direct = sanitizeEntry(entry);
    if (direct) {
      return direct;
    }

    const normalizedSource = normalizeSource(query?.source);
    const normalizedQuestionKey = normalizeQuestionKey(query?.question_key);
    const normalizedQuestionNo = normalizeQuestionNo(query?.question_no);
    if (normalizedSource === "ox" && normalizedQuestionKey && normalizedQuestionNo > 0) {
      const legacyKey = [
        normalizedSource,
        String(normalizeYear(query?.year)),
        normalizeText(query?.subject, 100),
        String(normalizedQuestionNo),
      ].join("|");
      const legacyEntry = sanitizeEntry(notes[legacyKey]);
      if (legacyEntry) {
        const migrated = {
          ...legacyEntry,
          question_key: normalizedQuestionKey,
          question_no: normalizedQuestionNo,
        };
        delete notes[legacyKey];
        notes[key] = migrated;
        writeStore(notes);
        return migrated;
      }
    }
    return null;
  }

  function getNotesMap(filters) {
    const source = normalizeSource(filters?.source);
    const year = normalizeYear(filters?.year);
    const subject = normalizeText(filters?.subject, 100);
    const notes = readStore();
    const result = {};
    Object.values(notes).forEach((entry) => {
      const sanitized = sanitizeEntry(entry);
      if (!sanitized) {
        return;
      }
      if (sanitized.source !== source) {
        return;
      }
      if (year && sanitized.year !== year) {
        return;
      }
      if (subject && sanitized.subject !== subject) {
        return;
      }
      const resultKey =
        sanitized.source === "ox" && sanitized.question_key
          ? sanitized.question_key
          : String(sanitized.question_no);
      result[resultKey] = sanitized;
    });
    return result;
  }

  function listNotes(filters = {}) {
    const subject = normalizeText(filters.subject, 100);
    const source = filters.source ? normalizeSource(filters.source) : "";
    const notes = readStore();
    const items = [];
    Object.values(notes).forEach((entry) => {
      const sanitized = sanitizeEntry(entry);
      if (!sanitized) {
        return;
      }
      if (subject && sanitized.subject !== subject) {
        return;
      }
      if (source && sanitized.source !== source) {
        return;
      }
      items.push(sanitized);
    });
    items.sort((a, b) => String(b.updated_at).localeCompare(String(a.updated_at)));
    return items;
  }

  window.TaxExamLocalData = {
    getDeviceId,
    normalizeImportance,
    makeNoteKey,
    upsertNote,
    getNote,
    getNotesMap,
    listNotes,
  };
})();
