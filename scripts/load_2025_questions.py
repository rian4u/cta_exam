from __future__ import annotations

import argparse
import json
import re
import sqlite3
from dataclasses import dataclass
from html import escape
from pathlib import Path
from statistics import median
from typing import Dict, Iterable, List, Tuple

import pdfplumber


QUESTION_START_RE = re.compile(r"^(\d{1,2})\.(?:\s|$)")
FOOTER_RE = re.compile(
    r"^\d{4}년도\s*제\d+회\s*세무사\s*1차\s*[12]교시\s*A형\s*\(\s*\d+\s*-\s*\d+\s*\)\s*$"
)

SUBJECTS = ("재정학", "세법학개론", "회계학개론", "상법", "민법", "행정소송법")
CIRCLED_TO_DIGIT = str.maketrans({"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5"})
OPTION_TO_DIGIT = {"①": "1", "②": "2", "③": "3", "④": "4", "⑤": "5"}
OPTION_TOKEN_RE = re.compile(r"[①②③④⑤]")
PUA_RE = re.compile(r"[\ue000-\uf8ff]")
PUA_TRANSLATION = str.maketrans(
    {
        "\ue000": "A",
        "\ue001": "B",
        "\ue002": "C",
        "\ue003": "D",
        "\ue00c": "M",
        "\ue00f": "P",
        "\ue010": "Q",
        "\ue012": "S",
        "\ue014": "U",
        "\ue016": "W",
        "\ue017": "X",
        "\ue034": "1",
        "\ue035": "2",
        "\ue036": "3",
        "\ue037": "4",
        "\ue038": "5",
        "\ue039": "9",
        "\ue03b": "8",
        "\ue03d": "0",
        "\ue044": "x",
        "\ue045": "",
        "\ue046": "-",
        "\ue047": "=",
        "\ue048": "+",
        "\ue04b": "{",
        "\ue04c": "}",
        "\ue052": ",",
        "\ue056": "Σ",
        "\ue05c": "√",
        "\ue06d": "",
        "\ue0ed": "i",
    }
)


@dataclass
class QuestionRow:
    출제연도: int
    과목: str
    문제번호: int
    문제지문: str
    보기_1: str
    보기_2: str
    보기_3: str
    보기_4: str
    보기_5: str
    답: str
    답_배포: str
    해설: str
    렌더_마크업: str


@dataclass
class ParsedLine:
    page_no: int
    x0: float
    x1: float
    top: float
    bottom: float
    text: str


@dataclass
class ParsedTable:
    page_no: int
    x0: float
    x1: float
    top: float
    bottom: float
    rows: int
    cols: int
    text_lines: List[str]
    html: str


def normalize_line(text: str) -> str:
    text = text.replace("\xa0", " ").replace("\u200b", "")
    text = text.replace("\t", " ").replace("\r", "")
    text = text.translate(PUA_TRANSLATION)
    text = PUA_RE.sub("", text)
    return text.strip()


def normalize_answer(raw: str) -> str:
    if not raw:
        return ""

    text = raw.translate(CIRCLED_TO_DIGIT)
    text = text.replace(" ", "")

    if "모두" in text:
        return "1,2,3,4,5"

    digits = re.findall(r"[1-5]", text)
    if not digits:
        return text

    ordered_unique: List[str] = []
    for digit in digits:
        if digit not in ordered_unique:
            ordered_unique.append(digit)

    return ",".join(ordered_unique)


def normalize_table_cell(text: str) -> str:
    if not text:
        return ""
    return normalize_line(text).replace("\n", " ").strip()


def table_to_text_lines(table_data: List[List[str]]) -> List[str]:
    rows: List[List[str]] = []
    for raw_row in table_data:
        cleaned_row = [normalize_table_cell(cell) for cell in raw_row]
        if any(cleaned_row):
            rows.append(cleaned_row)

    if not rows:
        return []

    if max(len(row) for row in rows) <= 1:
        return [row[0] for row in rows if row and row[0]]

    return [" | ".join(cell for cell in row if cell) for row in rows]


def render_table_html(table_data: List[List[str]]) -> tuple[str, int, int, List[str]]:
    normalized_rows: List[List[str]] = []
    max_cols = 0
    for raw_row in table_data:
        row = [normalize_table_cell(cell) for cell in raw_row]
        if any(row):
            normalized_rows.append(row)
            max_cols = max(max_cols, len(row))

    if not normalized_rows:
        return "", 0, 0, []

    text_lines = table_to_text_lines(normalized_rows)
    rows = len(normalized_rows)
    cols = max_cols

    if cols <= 1:
        lines_html = "".join(
            f'<div class="rich-box-line">{escape(line)}</div>' for line in text_lines if line
        )
        html = f'<div class="rich-box">{lines_html}</div>'
        return html, rows, cols, text_lines

    body_parts: List[str] = ['<div class="rich-table-wrap"><table class="rich-table">']
    for row_index, row in enumerate(normalized_rows):
        body_parts.append("<tr>")
        cell_tag = "th" if row_index == 0 else "td"
        for column_index in range(cols):
            cell_text = row[column_index] if column_index < len(row) else ""
            body_parts.append(f"<{cell_tag}>{escape(cell_text)}</{cell_tag}>")
        body_parts.append("</tr>")
    body_parts.append("</table></div>")
    html = "".join(body_parts)
    return html, rows, cols, text_lines


def line_inside_table(line: ParsedLine, table: ParsedTable, tolerance: float = 1.0) -> bool:
    if line.page_no != table.page_no:
        return False
    vertically_inside = line.bottom >= table.top - tolerance and line.top <= table.bottom + tolerance
    horizontally_inside = line.x1 >= table.x0 - tolerance and line.x0 <= table.x1 + tolerance
    return vertically_inside and horizontally_inside


MATH_LINE_RE = re.compile(r"^[A-Za-z0-9\s=+\-*/(),.{}\[\]_\\^%Σ√<>|:]+$")


def normalize_math_tex(text: str) -> str:
    tex = text
    tex = re.sub(r"√\s*([A-Za-z0-9_]+)", r"\\sqrt{\1}", tex)
    tex = tex.replace("Σ", r"\sum")
    return tex


def render_line_html(text: str) -> str:
    stripped = text.strip()
    if stripped:
        has_math_token = any(token in stripped for token in ("=", "_", "√", "Σ", "\\"))
        has_korean = bool(re.search(r"[가-힣]", stripped))
        if has_math_token and not has_korean and MATH_LINE_RE.match(stripped):
            math_text = normalize_math_tex(stripped)
            return f'<div class="rich-line rich-math">\\({escape(math_text)}\\)</div>'
    return f'<div class="rich-line">{escape(text)}</div>'


def render_plain_text_html(text: str) -> str:
    lines = [line for line in text.split("\n") if line.strip()]
    if not lines:
        return ""
    html_lines = "".join(render_line_html(line) for line in lines)
    return f'<div class="rich-content">{html_lines}</div>'


def detect_inset_box_groups(
    lines: List[ParsedLine],
    trailing_anchor: Tuple[int, float] | None = None,
    reference_gap: float | None = None,
) -> List[Tuple[int, int]]:
    if len(lines) < 2:
        return []

    ordered = sorted(lines, key=lambda item: (item.page_no, item.top, item.x0))
    baseline_x = min(line.x0 for line in ordered)
    typical_gap = float(reference_gap) if reference_gap and reference_gap > 0 else estimate_typical_line_gap(ordered)
    inset_threshold = 22.0
    boundary_gap = max(6.0, typical_gap * 1.25)
    max_internal_gap = max(10.0, typical_gap * 1.8)

    candidate_indexes: List[int] = [
        index for index, line in enumerate(ordered) if line.x0 - baseline_x >= inset_threshold
    ]
    if not candidate_indexes:
        return []

    groups: List[Tuple[int, int]] = []
    group_start = candidate_indexes[0]
    previous_index = candidate_indexes[0]

    for index in candidate_indexes[1:]:
        previous_line = ordered[previous_index]
        current_line = ordered[index]
        same_page = previous_line.page_no == current_line.page_no
        gap = current_line.top - previous_line.bottom
        contiguous = same_page and gap <= max_internal_gap and index == previous_index + 1
        if contiguous:
            previous_index = index
            continue
        groups.append((group_start, previous_index))
        group_start = index
        previous_index = index

    groups.append((group_start, previous_index))

    accepted: List[Tuple[int, int]] = []
    for start, end in groups:
        if start == 0:
            continue
        before = ordered[start - 1]
        first = ordered[start]
        last = ordered[end]
        if before.page_no != first.page_no:
            continue
        before_gap = first.top - before.bottom

        if end >= len(ordered) - 1:
            if trailing_anchor is None or trailing_anchor[0] != last.page_no:
                continue
            after_gap = trailing_anchor[1] - last.bottom
        else:
            after = ordered[end + 1]
            if last.page_no != after.page_no:
                continue
            after_gap = after.top - last.bottom

        if before_gap < boundary_gap or after_gap < boundary_gap:
            continue
        accepted.append((start, end))

    return accepted


def render_rich_section_html(
    lines: List[ParsedLine],
    tables: List[ParsedTable],
    trailing_anchor: Tuple[int, float] | None = None,
    reference_gap: float | None = None,
) -> str:
    elements: List[Tuple[int, float, int, str]] = []

    filtered_lines: List[ParsedLine] = []
    for line in lines:
        if any(line_inside_table(line, table) for table in tables):
            continue
        if not line.text.strip():
            continue
        filtered_lines.append(line)

    box_groups = detect_inset_box_groups(
        filtered_lines,
        trailing_anchor=trailing_anchor,
        reference_gap=reference_gap,
    )
    box_lookup: Dict[int, Tuple[int, int]] = {start: (start, end) for start, end in box_groups}
    skip_indexes: set[int] = set()

    for start, end in box_groups:
        skip_indexes.update(range(start + 1, end + 1))

    for index, line in enumerate(filtered_lines):
        if index in skip_indexes:
            continue
        if index in box_lookup:
            start, end = box_lookup[index]
            box_lines: List[str] = []
            for item in range(start, end + 1):
                box_lines.extend(split_box_list_segments(filtered_lines[item].text))
            lines_html = "".join(render_line_html(line) for line in box_lines)
            box_html = f'<div class="rich-box">{lines_html}</div>'
            elements.append((line.page_no, line.top, 0, box_html))
            continue
        elements.append((line.page_no, line.top, 0, render_line_html(line.text)))

    for table in tables:
        if not table.html:
            continue
        elements.append((table.page_no, table.top, 1, table.html))

    if not elements:
        return ""

    elements.sort(key=lambda item: (item[0], item[1], item[2]))
    content = "".join(item[3] for item in elements)
    return f'<div class="rich-content">{content}</div>'


def extract_pdf_lines_and_tables(
    pdf_path: Path,
    footer_cutoff: float = 60.0,
) -> tuple[List[ParsedLine], List[ParsedTable]]:
    lines: List[ParsedLine] = []
    tables: List[ParsedTable] = []

    with pdfplumber.open(pdf_path) as doc:
        for page_no, page in enumerate(doc.pages, start=1):
            page_height = float(page.height)
            try:
                page_lines = page.extract_text_lines(layout=False, strip=True, return_chars=False)
            except TypeError:
                page_lines = page.extract_text_lines(layout=False, strip=True)

            for line in page_lines:
                text = normalize_line(line.get("text", ""))
                if not text or FOOTER_RE.match(text):
                    continue

                x0 = float(line.get("x0", 0.0))
                x1 = float(line.get("x1", x0))
                y0 = float(line.get("top", 0.0))
                y1 = float(line.get("bottom", y0))
                if y0 >= page_height - footer_cutoff:
                    continue

                lines.append(
                    ParsedLine(
                        page_no=page_no,
                        x0=x0,
                        x1=x1,
                        top=y0,
                        bottom=y1,
                        text=text,
                    )
                )

            for table in page.find_tables():
                x0, top, x1, bottom = (float(v) for v in table.bbox)
                if top >= page_height - footer_cutoff:
                    continue
                table_data = table.extract()
                table_html, rows, cols, text_lines = render_table_html(table_data)
                if not table_html and not text_lines:
                    continue
                tables.append(
                    ParsedTable(
                        page_no=page_no,
                        x0=x0,
                        x1=x1,
                        top=top,
                        bottom=bottom,
                        rows=rows,
                        cols=cols,
                        text_lines=text_lines,
                        html=table_html,
                    )
                )

    lines.sort(key=lambda item: (item.page_no, item.top, item.x0))
    tables.sort(key=lambda item: (item.page_no, item.top, item.x0))
    return lines, tables


def split_option_segments(line: str) -> List[Tuple[str, str]]:
    matches = list(OPTION_TOKEN_RE.finditer(line))
    if not matches or matches[0].start() != 0:
        return []

    segments: List[Tuple[str, str]] = []
    for index, match in enumerate(matches):
        marker = match.group(0)
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(line)
        option_no = OPTION_TO_DIGIT[marker]
        option_text = line[start:end].strip()
        segments.append((option_no, option_text))
    return segments


def detect_question_boundaries(
    lines: Iterable[ParsedLine],
    x_threshold: float = 65.0,
) -> List[Tuple[int, int]]:
    boundaries: List[Tuple[int, int]] = []
    seen_numbers: set[int] = set()

    for index, line in enumerate(lines):
        if line.x0 > x_threshold:
            continue
        match = QUESTION_START_RE.match(line.text)
        if not match:
            continue

        number = int(match.group(1))
        if number < 1 or number > 80 or number in seen_numbers:
            continue

        seen_numbers.add(number)
        boundaries.append((index, number))

    if len(boundaries) != 80:
        found = sorted(seen_numbers)
        raise ValueError(
            f"문항 경계 검출 실패: {len(boundaries)}개 검출, 번호={found[:5]}...{found[-5:] if found else found}"
        )

    return boundaries


def compare_position(left: Tuple[int, float], right: Tuple[int, float]) -> int:
    if left[0] < right[0]:
        return -1
    if left[0] > right[0]:
        return 1
    if left[1] < right[1]:
        return -1
    if left[1] > right[1]:
        return 1
    return 0


def collect_tables_for_block(block: List[ParsedLine], tables: List[ParsedTable]) -> List[ParsedTable]:
    if not block:
        return []

    ranges: Dict[int, Tuple[float, float]] = {}
    for line in block:
        page_range = ranges.get(line.page_no)
        if page_range is None:
            ranges[line.page_no] = (line.top, line.bottom)
        else:
            ranges[line.page_no] = (min(page_range[0], line.top), max(page_range[1], line.bottom))

    selected: List[ParsedTable] = []
    for table in tables:
        page_range = ranges.get(table.page_no)
        if page_range is None:
            continue
        start_y, end_y = page_range
        if table.bottom < start_y - 2.0 or table.top > end_y + 2.0:
            continue
        selected.append(table)

    selected.sort(key=lambda item: (item.page_no, item.top, item.x0))
    return selected


PARAGRAPH_START_RE = re.compile(r"^\((?:단|참고|주)\s*,?|^※|^<[^>]+>|^다음\s")
FORMULA_ONLY_RE = re.compile(r"^[A-Za-z0-9\s=+\-*/(),.{}\[\]_\\^%Σ√<>|:]+$")
BOX_LIST_MARKER_RE = re.compile(r"(?:○|[ㄱ-ㅎ][\.\)]|[①②③④⑤⑥⑦⑧⑨⑩])")
ANNOTATION_ONLY_RE = re.compile(r"^(?:[A-Za-z]|[ivIV])(?:\s+(?:[A-Za-z]|[ivIV])){1,8}$")
SECTION_HEADER_RE = re.compile(r"^[0-9]{1,2}\.")


def is_hangul_char(char: str) -> bool:
    return bool(char) and ("\uac00" <= char <= "\ud7a3")


def is_formula_like(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    if re.search(r"[가-힣]", stripped):
        return False
    has_symbol = any(token in stripped for token in ("=", "+", "-", "/", "*", "_", "^", "√", "Σ"))
    return has_symbol and FORMULA_ONLY_RE.match(stripped) is not None


def is_annotation_line(text: str) -> bool:
    stripped = text.strip()
    if not stripped:
        return False
    return ANNOTATION_ONLY_RE.match(stripped) is not None


def estimate_typical_line_gap(lines: List[ParsedLine]) -> float:
    gaps: List[float] = []
    for idx in range(1, len(lines)):
        previous = lines[idx - 1]
        current = lines[idx]
        if previous.page_no != current.page_no:
            continue
        gap = current.top - previous.bottom
        if 0.0 <= gap <= 40.0:
            gaps.append(gap)
    if not gaps:
        return 7.0
    return float(median(gaps))


def join_inline_separator(previous_text: str, current_text: str) -> str:
    prev = previous_text.rstrip()
    curr = current_text.lstrip()
    if not prev or not curr:
        return ""

    prev_last = prev[-1]
    curr_first = curr[0]

    if prev_last in "([{\u201c\"'" or curr_first in ".,;:!?)]}%":
        return ""
    if prev_last in "+-/*=|<>" or curr_first in "+-/*=|<>":
        return " "
    if is_hangul_char(prev_last) and is_hangul_char(curr_first):
        last_token = prev.split()[-1] if prev.split() else prev
        if len(last_token) <= 1:
            return ""
        return " "
    if (
        prev_last.isalnum() and curr_first.isalnum()
    ):
        return ""
    return " "


def should_keep_paragraph_break(previous: ParsedLine, current: ParsedLine, typical_gap: float) -> bool:
    if previous.page_no != current.page_no:
        return True

    vertical_gap = current.top - previous.bottom
    if vertical_gap > max(4.0, typical_gap * 1.45):
        return True

    previous_text = previous.text.strip()
    current_text = current.text.strip()
    if not previous_text or not current_text:
        return True

    if SECTION_HEADER_RE.match(current_text):
        return True
    if PARAGRAPH_START_RE.match(current_text):
        return True
    if is_formula_like(previous_text) or is_formula_like(current_text):
        return True
    if is_annotation_line(previous_text) or is_annotation_line(current_text):
        return True
    if previous_text.endswith("?") or previous_text.endswith("!"):
        return True
    if previous_text.endswith(".") and PARAGRAPH_START_RE.match(current_text):
        return True

    return False


def collapse_wrapped_lines(lines: List[ParsedLine]) -> List[ParsedLine]:
    if not lines:
        return []

    ordered = sorted(lines, key=lambda item: (item.page_no, item.top, item.x0))
    typical_gap = estimate_typical_line_gap(ordered)
    merged: List[ParsedLine] = [
        ParsedLine(
            page_no=ordered[0].page_no,
            x0=ordered[0].x0,
            x1=ordered[0].x1,
            top=ordered[0].top,
            bottom=ordered[0].bottom,
            text=ordered[0].text.strip(),
        )
    ]

    for line in ordered[1:]:
        current = ParsedLine(
            page_no=line.page_no,
            x0=line.x0,
            x1=line.x1,
            top=line.top,
            bottom=line.bottom,
            text=line.text.strip(),
        )
        previous = merged[-1]

        if should_keep_paragraph_break(previous, current, typical_gap):
            merged.append(current)
            continue

        separator = join_inline_separator(previous.text, current.text)
        previous.text = f"{previous.text.rstrip()}{separator}{current.text.lstrip()}".strip()
        previous.bottom = max(previous.bottom, current.bottom)
        previous.x1 = max(previous.x1, current.x1)

    return merged


def split_box_list_segments(text: str) -> List[str]:
    stripped = text.strip()
    if not stripped:
        return []

    positions: List[int] = []
    for match in BOX_LIST_MARKER_RE.finditer(stripped):
        marker_start = match.start()
        marker_token = match.group(0)
        if marker_start > 0 and marker_token.startswith("○"):
            prev = stripped[marker_start - 1]
            if prev in {"○", "ㆍ"}:
                continue
        positions.append(marker_start)

    if len(positions) <= 1:
        return [stripped]

    segments: List[str] = []
    for index, start in enumerate(positions):
        end = positions[index + 1] if index + 1 < len(positions) else len(stripped)
        segment = stripped[start:end].strip()
        if segment:
            segments.append(segment)
    return segments if segments else [stripped]


def parse_question_block(
    question_no: int,
    block: List[ParsedLine],
    block_tables: List[ParsedTable],
) -> Tuple[str, Dict[str, str], str, Dict[str, str]]:
    stem_lines: List[ParsedLine] = []
    options: Dict[str, List[ParsedLine]] = {str(i): [] for i in range(1, 6)}
    option_anchors: Dict[str, Tuple[int, float]] = {}
    current_option: str | None = None
    first_option_anchor: Tuple[int, float] | None = None

    for idx, raw_line in enumerate(block):
        text = raw_line.text
        if idx == 0:
            text = QUESTION_START_RE.sub("", text, count=1).strip()
            if not text:
                continue

        option_segments = split_option_segments(text)
        if option_segments:
            for option_no, option_text in option_segments:
                current_option = option_no
                if option_no not in option_anchors:
                    option_anchors[option_no] = (raw_line.page_no, raw_line.top)
                if first_option_anchor is None:
                    first_option_anchor = (raw_line.page_no, raw_line.top)
                if option_text:
                    options[current_option].append(
                        ParsedLine(
                            page_no=raw_line.page_no,
                            x0=raw_line.x0,
                            x1=raw_line.x1,
                            top=raw_line.top,
                            bottom=raw_line.bottom,
                            text=option_text,
                        )
                    )
            continue

        line = ParsedLine(
            page_no=raw_line.page_no,
            x0=raw_line.x0,
            x1=raw_line.x1,
            top=raw_line.top,
            bottom=raw_line.bottom,
            text=text,
        )

        if current_option:
            options[current_option].append(line)
        else:
            stem_lines.append(line)

    stem_tables: List[ParsedTable] = []
    option_tables: Dict[str, List[ParsedTable]] = {str(i): [] for i in range(1, 6)}

    for table in block_tables:
        table_pos = (table.page_no, table.top)
        if first_option_anchor is None or compare_position(table_pos, first_option_anchor) < 0:
            stem_tables.append(table)
            continue

        matched_option = None
        for option_no in ("1", "2", "3", "4", "5"):
            anchor = option_anchors.get(option_no)
            if anchor is None:
                continue
            if compare_position(anchor, table_pos) <= 0:
                matched_option = option_no

        if matched_option is None:
            stem_tables.append(table)
        else:
            option_tables[matched_option].append(table)

    raw_stem_lines_for_gap = list(stem_lines)
    stem_lines = collapse_wrapped_lines(stem_lines)
    for key in ("1", "2", "3", "4", "5"):
        options[key] = collapse_wrapped_lines(options[key])

    stem = "\n".join(line.text for line in stem_lines if line.text).strip()
    normalized_options = {
        key: "\n".join(line.text for line in value if line.text).strip() for key, value in options.items()
    }

    if not stem:
        raise ValueError(f"{question_no}번 문제지문 파싱 실패")

    stem_html = render_rich_section_html(
        stem_lines,
        stem_tables,
        trailing_anchor=first_option_anchor,
        reference_gap=estimate_typical_line_gap(raw_stem_lines_for_gap),
    )
    options_html = {
        key: render_rich_section_html(options[key], option_tables[key]) for key in ("1", "2", "3", "4", "5")
    }
    return stem, normalized_options, stem_html, options_html


def parse_exam_pdf(pdf_path: Path) -> Dict[int, Dict[str, object]]:
    lines, tables = extract_pdf_lines_and_tables(pdf_path)
    boundaries = detect_question_boundaries(lines)
    parsed: Dict[int, Dict[str, object]] = {}

    for index, (start_idx, question_no) in enumerate(boundaries):
        end_idx = boundaries[index + 1][0] if index + 1 < len(boundaries) else len(lines)
        block = lines[start_idx:end_idx]

        block_tables = collect_tables_for_block(block, tables)
        stem, options, stem_html, options_html = parse_question_block(question_no, block, block_tables)
        parsed[question_no] = {
            "stem": stem,
            "options": options,
            "stem_html": stem_html,
            "options_html": options_html,
        }

    return parsed


def repair_parsed_question_text(
    year: int,
    subject: str,
    number: int,
    stem: str,
    options: Dict[str, str],
    stem_html: str,
    options_html: Dict[str, str],
) -> Tuple[str, Dict[str, str], str, Dict[str, str]]:
    if year == 2025 and subject == "재정학" and number == 5:
        options["1"] = re.sub(r"(조세수입은\s*600이다\.?)\s*3\s*$", r"\1", options["1"]).strip()
        options["2"] = re.sub(
            r"비효율성계수는\s*이다\.?\s*4\s*$",
            "비효율성계수는 3/4이다.",
            options["2"],
            flags=re.DOTALL,
        )

    if year == 2025 and subject == "재정학" and number == 24:
        stem = (
            "개인 A와 B로 구성된 경제에 X재가 1000단위 존재하며, 이 재화에 대한 효용함수는 각각 "
            "U_A = 3√X_A, U_B = √X_B 이다.\n"
            "이 사회의 사회후생함수를 W = min{U_A, U_B}로 가정한다. 다음 중 옳지 않은 것은?\n"
            "(단, X ≥ 0, Σ_{i=A,B} X_i = X 는 개인 i의 X재 소비량이다.)"
        )
        stem_html = (
            '<div class="rich-content">'
            '<div class="rich-line">개인 A와 B로 구성된 경제에 X재가 1000단위 존재하며, '
            '이 재화에 대한 효용함수는 각각 \\(U_A = 3\\sqrt{X_A},\\; U_B = \\sqrt{X_B}\\) 이다.</div>'
            '<div class="rich-line">이 사회의 사회후생함수를 \\(W=\\min\\{U_A, U_B\\}\\)로 가정한다. '
            "다음 중 옳지 않은 것은?</div>"
            '<div class="rich-line">(단, \\(X \\ge 0,\\; \\sum_{i=A,B} X_i = X\\)는 개인 '
            "\\(i\\)의 \\(X\\)재 소비량이다.)</div>"
            "</div>"
        )

    if year == 2025 and subject == "재정학" and number == 26:
        stem = (
            "A와 B 두 명으로 구성된 사회에서 개인의 효용을 각각 U_A와 U_B, 사회후생을 W라고 할 때, "
            "다음 중 옳지 않은 것은?"
        )
        options["3"] = "롤즈적 사회후생함수는 W = min{U_A, U_B}로 나타낼 수 있다."
        options["4"] = "사회후생함수가 W = U_A + 2U_B 일 경우, B의 효용을 A의 효용보다 2배 더 중요시 한다."
        stem_html = (
            '<div class="rich-content"><div class="rich-line">A와 B 두 명으로 구성된 사회에서 개인의 효용을 각각 '
            "\\(U_A\\)와 \\(U_B\\), 사회후생을 \\(W\\)라고 할 때, 다음 중 옳지 않은 것은?</div></div>"
        )
        options_html["3"] = (
            '<div class="rich-content"><div class="rich-line">롤즈적 사회후생함수는 '
            "\\(W = \\min\\{U_A, U_B\\}\\)로 나타낼 수 있다.</div></div>"
        )
        options_html["4"] = (
            '<div class="rich-content"><div class="rich-line">사회후생함수가 '
            "\\(W = U_A + 2U_B\\)일 경우, B의 효용을 A의 효용보다 2배 더 중요시 한다.</div></div>"
        )

    if not stem_html:
        stem_html = render_plain_text_html(stem)

    normalized_options_html: Dict[str, str] = {}
    for key in ("1", "2", "3", "4", "5"):
        html = (options_html.get(key) or "").strip()
        if html and ("rich-table" in html or "rich-box" in html or "\\(" in html):
            normalized_options_html[key] = html
        else:
            normalized_options_html[key] = render_plain_text_html(options[key])

    return stem, options, stem_html, normalized_options_html


def parse_solution_file(path: Path) -> Dict[int, Tuple[str, str]]:
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        r"^\s*(?:\*\*)?(\d{1,2})\.\s*.*?\(\s*정답\s*:\s*(.*?)\)\s*(?:\*\*)?\s*$",
        re.MULTILINE,
    )
    matches = list(pattern.finditer(text))
    result: Dict[int, Tuple[str, str]] = {}

    for index, match in enumerate(matches):
        question_no = int(match.group(1))
        answer = normalize_answer(match.group(2))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        explanation = text[start:end].strip()
        result[question_no] = (answer, explanation)

    return result


def parse_published_answers(path: Path) -> Dict[Tuple[str, int], str]:
    text = path.read_text(encoding="utf-8")
    results: Dict[Tuple[str, int], str] = {}
    current_subject = ""

    pair_pattern = re.compile(r"\*\*(\d{1,2})\*\*:(.*?)(?=,\s*\*\*\d{1,2}\*\*:|$)")

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue

        for subject in SUBJECTS:
            if f"**{subject}**" in stripped:
                current_subject = subject
                break

        if not current_subject:
            continue

        for match in pair_pattern.finditer(stripped):
            question_no = int(match.group(1))
            answer = normalize_answer(match.group(2))
            results[(current_subject, question_no)] = answer

    return results


def find_single_pdf(base_dir: Path, token: str) -> Path:
    files = [path for path in base_dir.glob("*.pdf") if token in path.name and "시험지 원본" in path.name]
    if len(files) != 1:
        names = [path.name for path in files]
        raise FileNotFoundError(f"'{token}' PDF를 단일하게 찾지 못했습니다: {names}")
    return files[0]


def find_second_session_pdfs(base_dir: Path) -> List[Path]:
    files = [path for path in base_dir.glob("*.pdf") if "2교시" in path.name and "시험지 원본" in path.name]
    if len(files) < 1:
        raise FileNotFoundError("2교시 시험지 원본 PDF를 찾지 못했습니다.")
    return sorted(files)


def extract_optional_subject_from_filename(pdf_path: Path) -> str:
    match = re.search(r"\(([^)]+)\)", pdf_path.stem)
    if not match:
        raise ValueError(f"선택법 과목명을 파일명에서 찾을 수 없습니다: {pdf_path.name}")
    subject = match.group(1).strip()
    if subject not in {"상법", "민법", "행정소송법"}:
        raise ValueError(f"알 수 없는 선택법 과목명: {subject}")
    return subject


def build_question_rows(data_dir: Path, year: int) -> List[QuestionRow]:
    records: Dict[Tuple[int, str, int], QuestionRow] = {}

    first_pdf = find_single_pdf(data_dir, "1교시")
    first_questions = parse_exam_pdf(first_pdf)
    for number, parsed in first_questions.items():
        stem = str(parsed["stem"])
        options = dict(parsed["options"])
        stem_html = str(parsed.get("stem_html") or "")
        options_html = dict(parsed.get("options_html") or {})
        subject = "재정학" if number <= 40 else "세법학개론"
        stem, options, stem_html, options_html = repair_parsed_question_text(
            year, subject, number, stem, options, stem_html, options_html
        )
        render_payload = json.dumps(
            {
                "stem_html": stem_html,
                "options_html": [options_html["1"], options_html["2"], options_html["3"], options_html["4"], options_html["5"]],
            },
            ensure_ascii=False,
        )
        key = (year, subject, number)
        records[key] = QuestionRow(
            출제연도=year,
            과목=subject,
            문제번호=number,
            문제지문=stem,
            보기_1=options["1"],
            보기_2=options["2"],
            보기_3=options["3"],
            보기_4=options["4"],
            보기_5=options["5"],
            답="",
            답_배포="",
            해설="",
            렌더_마크업=render_payload,
        )

    for second_pdf in find_second_session_pdfs(data_dir):
        optional_subject = extract_optional_subject_from_filename(second_pdf)
        second_questions = parse_exam_pdf(second_pdf)

        for number, parsed in second_questions.items():
            stem = str(parsed["stem"])
            options = dict(parsed["options"])
            stem_html = str(parsed.get("stem_html") or "")
            options_html = dict(parsed.get("options_html") or {})
            subject = "회계학개론" if number <= 40 else optional_subject
            stem, options, stem_html, options_html = repair_parsed_question_text(
                year, subject, number, stem, options, stem_html, options_html
            )
            render_payload = json.dumps(
                {
                    "stem_html": stem_html,
                    "options_html": [options_html["1"], options_html["2"], options_html["3"], options_html["4"], options_html["5"]],
                },
                ensure_ascii=False,
            )
            key = (year, subject, number)

            if subject == "회계학개론" and key in records:
                continue

            records[key] = QuestionRow(
                출제연도=year,
                과목=subject,
                문제번호=number,
                문제지문=stem,
                보기_1=options["1"],
                보기_2=options["2"],
                보기_3=options["3"],
                보기_4=options["4"],
                보기_5=options["5"],
                답="",
                답_배포="",
                해설="",
                렌더_마크업=render_payload,
            )

    solution_files = {
        "재정학": data_dir / "재정학풀이.txt",
        "세법학개론": data_dir / "세법학개론풀이.txt",
        "회계학개론": data_dir / "회계학개론풀이.txt",
        "상법": data_dir / "상법풀이.txt",
        "민법": data_dir / "민법풀이.txt",
        "행정소송법": data_dir / "행정소송법풀이.txt",
    }
    solution_map: Dict[str, Dict[int, Tuple[str, str]]] = {
        subject: parse_solution_file(path) for subject, path in solution_files.items()
    }

    published_map = parse_published_answers(data_dir / "실제정답.txt")

    for key, row in records.items():
        _, subject, number = key
        answer, explanation = solution_map.get(subject, {}).get(number, ("", ""))
        row.답 = answer
        row.해설 = explanation
        row.답_배포 = published_map.get((subject, number), "")

    return sorted(records.values(), key=lambda row: (row.출제연도, row.과목, row.문제번호))


def ensure_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS 문제 (
            문제id INTEGER PRIMARY KEY AUTOINCREMENT,
            출제연도 INTEGER NOT NULL,
            과목 TEXT NOT NULL,
            문제번호 INTEGER NOT NULL,
            문제지문 TEXT NOT NULL,
            보기_1 TEXT,
            보기_2 TEXT,
            보기_3 TEXT,
            보기_4 TEXT,
            보기_5 TEXT,
            답 TEXT,
            답_배포 TEXT,
            해설 TEXT,
            렌더_마크업 TEXT,
            UNIQUE (출제연도, 과목, 문제번호)
        )
        """
    )
    columns = {row[1] for row in conn.execute('PRAGMA table_info("문제")')}
    if "렌더_마크업" not in columns:
        conn.execute('ALTER TABLE "문제" ADD COLUMN "렌더_마크업" TEXT')
    conn.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_문제_출제연도_과목
        ON 문제 (출제연도, 과목)
        """
    )


def upsert_questions(conn: sqlite3.Connection, rows: List[QuestionRow]) -> None:
    sql = """
    INSERT INTO 문제 (
        출제연도, 과목, 문제번호, 문제지문,
        보기_1, 보기_2, 보기_3, 보기_4, 보기_5,
        답, 답_배포, 해설, 렌더_마크업
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(출제연도, 과목, 문제번호) DO UPDATE SET
        문제지문=excluded.문제지문,
        보기_1=excluded.보기_1,
        보기_2=excluded.보기_2,
        보기_3=excluded.보기_3,
        보기_4=excluded.보기_4,
        보기_5=excluded.보기_5,
        답=excluded.답,
        답_배포=excluded.답_배포,
        해설=excluded.해설,
        렌더_마크업=excluded.렌더_마크업
    """

    conn.executemany(
        sql,
        [
            (
                row.출제연도,
                row.과목,
                row.문제번호,
                row.문제지문,
                row.보기_1,
                row.보기_2,
                row.보기_3,
                row.보기_4,
                row.보기_5,
                row.답,
                row.답_배포,
                row.해설,
                row.렌더_마크업,
            )
            for row in rows
        ],
    )


def print_summary(rows: List[QuestionRow]) -> None:
    by_subject: Dict[str, int] = {}
    missing_answer = 0
    missing_published = 0

    for row in rows:
        by_subject[row.과목] = by_subject.get(row.과목, 0) + 1
        if not row.답:
            missing_answer += 1
        if not row.답_배포:
            missing_published += 1

    print(f"총 적재 대상 문항 수: {len(rows)}")
    for subject in SUBJECTS:
        if subject in by_subject:
            print(f"- {subject}: {by_subject[subject]}문항")
    print(f"풀이파일 정답 미매핑: {missing_answer}문항")
    print(f"실제정답 미매핑: {missing_published}문항")


def main() -> None:
    parser = argparse.ArgumentParser(description="2025 세무사 1차 시험 문제 DB 적재 스크립트")
    parser.add_argument("--data-dir", default="data/2025", help="입력 데이터 폴더")
    parser.add_argument("--db-path", default="data/questions.db", help="SQLite DB 파일 경로")
    parser.add_argument("--year", type=int, default=2025, help="출제연도")
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        raise FileNotFoundError(f"데이터 폴더를 찾을 수 없습니다: {data_dir}")

    rows = build_question_rows(data_dir, args.year)

    db_path = Path(args.db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        ensure_schema(conn)
        upsert_questions(conn, rows)
        conn.commit()
    finally:
        conn.close()

    print(f"DB 적재 완료: {db_path}")
    print_summary(rows)


if __name__ == "__main__":
    main()
