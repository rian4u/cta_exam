-- ============================================================
-- tax_exam3 Supabase Schema
-- Run this in Supabase Dashboard > SQL Editor
-- ============================================================

-- 1. 기출문제 (5지선다)
CREATE TABLE IF NOT EXISTS questions (
  id                 BIGSERIAL PRIMARY KEY,
  year               INTEGER NOT NULL,
  subject            TEXT    NOT NULL,
  original_no        INTEGER NOT NULL,
  stem               TEXT    NOT NULL DEFAULT '',
  stem_html          TEXT    NOT NULL DEFAULT '',
  options            JSONB   NOT NULL DEFAULT '[]',
  options_html       JSONB   NOT NULL DEFAULT '[]',
  answer             TEXT    NOT NULL DEFAULT '',
  distributed_answer TEXT    NOT NULL DEFAULT '',
  explanation        TEXT    NOT NULL DEFAULT '',
  UNIQUE (year, subject, original_no)
);

CREATE INDEX IF NOT EXISTS idx_questions_year_subject ON questions (year, subject);

-- 2. OX 문제
CREATE TABLE IF NOT EXISTS ox_questions (
  id          BIGSERIAL PRIMARY KEY,
  year        INTEGER NOT NULL,
  subject     TEXT    NOT NULL,
  original_no INTEGER NOT NULL,
  source_no   INTEGER NOT NULL DEFAULT 0,
  stable_id   TEXT    NOT NULL DEFAULT '',
  question    TEXT    NOT NULL DEFAULT '',
  answer      TEXT    NOT NULL DEFAULT '',
  explanation TEXT    NOT NULL DEFAULT '',
  UNIQUE (year, subject, original_no)
);

CREATE INDEX IF NOT EXISTS idx_ox_questions_year_subject ON ox_questions (year, subject);

-- 3. 공지게시판
CREATE TABLE IF NOT EXISTS notices (
  id           BIGSERIAL    PRIMARY KEY,
  title        TEXT         NOT NULL,
  body         TEXT         NOT NULL,
  author       TEXT         NOT NULL DEFAULT '관리자',
  is_published BOOLEAN      NOT NULL DEFAULT TRUE,
  created_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at   TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_notices_created ON notices (created_at DESC);

-- Initial notice
INSERT INTO notices (title, body, author, is_published)
VALUES (
  '공지',
  '문제/해설 데이터는 순차적으로 오픈됩니다.' || CHR(10) || '현재 모의고사 연도 선택은 2025년만 활성화되어 있습니다.',
  '관리자',
  TRUE
) ON CONFLICT DO NOTHING;

-- 4. 사용자 오답노트
CREATE TABLE IF NOT EXISTS user_notes (
  id          BIGSERIAL    PRIMARY KEY,
  user_id     TEXT         NOT NULL,
  source      TEXT         NOT NULL DEFAULT 'question',
  year        INTEGER      NOT NULL,
  subject     TEXT         NOT NULL,
  question_no INTEGER      NOT NULL,
  importance  TEXT         NOT NULL DEFAULT '',
  comment     TEXT         NOT NULL DEFAULT '',
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  UNIQUE (user_id, source, year, subject, question_no)
);

CREATE INDEX IF NOT EXISTS idx_user_notes_user ON user_notes (user_id, source, year, subject);

-- 5. 문의 게시판 (문의글)
CREATE TABLE IF NOT EXISTS inquiries (
  id          BIGSERIAL    PRIMARY KEY,
  nickname    TEXT         NOT NULL CHECK (char_length(nickname) BETWEEN 1 AND 40),
  title       TEXT         NOT NULL CHECK (char_length(title) BETWEEN 1 AND 160),
  body        TEXT         NOT NULL CHECK (char_length(body) BETWEEN 1 AND 3000),
  subject     TEXT         NOT NULL DEFAULT '',
  year        INTEGER      NOT NULL DEFAULT 0,
  question_no INTEGER      NOT NULL DEFAULT 0,
  is_closed   BOOLEAN      NOT NULL DEFAULT FALSE,
  created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW(),
  updated_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inquiries_created ON inquiries (created_at DESC);

-- 6. 문의 답변
CREATE TABLE IF NOT EXISTS inquiry_replies (
  id         BIGSERIAL    PRIMARY KEY,
  inquiry_id BIGINT       NOT NULL REFERENCES inquiries(id) ON DELETE CASCADE,
  is_admin   BOOLEAN      NOT NULL DEFAULT FALSE,
  nickname   TEXT         NOT NULL CHECK (char_length(nickname) BETWEEN 1 AND 40),
  body       TEXT         NOT NULL CHECK (char_length(body) BETWEEN 1 AND 3000),
  created_at TIMESTAMPTZ  NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_inquiry_replies_inquiry ON inquiry_replies (inquiry_id);

-- ============================================================
-- Row Level Security
-- ============================================================

ALTER TABLE questions        ENABLE ROW LEVEL SECURITY;
ALTER TABLE ox_questions     ENABLE ROW LEVEL SECURITY;
ALTER TABLE notices          ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_notes       ENABLE ROW LEVEL SECURITY;
ALTER TABLE inquiries        ENABLE ROW LEVEL SECURITY;
ALTER TABLE inquiry_replies  ENABLE ROW LEVEL SECURITY;

-- questions: anyone can read
CREATE POLICY "anon read questions" ON questions
  FOR SELECT USING (true);

-- ox_questions: anyone can read
CREATE POLICY "anon read ox_questions" ON ox_questions
  FOR SELECT USING (true);

-- notices: anyone can read published; service_role manages all
CREATE POLICY "anon read published notices" ON notices
  FOR SELECT USING (is_published = true);

-- user_notes: anyone can read/write (keyed by random device_id)
CREATE POLICY "anon all user_notes" ON user_notes
  FOR ALL USING (true) WITH CHECK (true);

-- inquiries: anyone can read/insert
CREATE POLICY "anon read inquiries" ON inquiries
  FOR SELECT USING (true);
CREATE POLICY "anon insert inquiries" ON inquiries
  FOR INSERT WITH CHECK (true);

-- inquiry_replies: anyone can read/insert (is_admin enforced by Worker)
CREATE POLICY "anon read replies" ON inquiry_replies
  FOR SELECT USING (true);
CREATE POLICY "anon insert replies" ON inquiry_replies
  FOR INSERT WITH CHECK (true);
