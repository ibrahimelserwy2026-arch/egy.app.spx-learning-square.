from __future__ import annotations

import json
import os
import re
import threading
from datetime import datetime, timezone
from typing import Any

import requests
from kivy.app import App
from kivy.clock import Clock
from kivy.core.text import LabelBase
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput
from kivy.uix.gridlayout import GridLayout
from kivy.uix.scrollview import ScrollView


BASE_URL = "https://me-tp.qureo.education"
SECTION_ID_DEFAULT = "106"
DEFAULT_MODEL = "gpt-4.1-mini"
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/157.0.0.0 Safari/537.36"
)
COOKIE_ATTRIBUTES = {
    "path", "domain", "expires", "max-age", "httponly",
    "secure", "samesite", "priority",
}


try:
    import arabic_reshaper
    from bidi.algorithm import get_display
    ARABIC_SHAPING_AVAILABLE = True
except ImportError:
    arabic_reshaper = None
    get_display = None
    ARABIC_SHAPING_AVAILABLE = False


def find_arabic_font() -> str:
    """Find a Windows font with Arabic glyphs; Tahoma is preferred."""
    windows_dir = os.environ.get("WINDIR", r"C:\Windows")
    candidates = (
        os.path.join(windows_dir, "Fonts", "tahoma.ttf"),
        os.path.join(windows_dir, "Fonts", "arial.ttf"),
        os.path.join(windows_dir, "Fonts", "segoeui.ttf"),
    )
    for font_path in candidates:
        if os.path.isfile(font_path):
            try:
                LabelBase.register(name="QureoArabic", fn_regular=font_path)
                return "QureoArabic"
            except Exception:
                continue
    return "Roboto"


ARABIC_FONT_NAME = find_arabic_font()


def display_text(value: Any) -> str:
    """Shape Arabic and apply RTL ordering one line at a time.

    Lines without Arabic (for example Python code) are left untouched.
    """
    text = str(value or "")
    if not ARABIC_SHAPING_AVAILABLE:
        return text
    output: list[str] = []
    for line in text.splitlines(keepends=True):
        ending = ""
        content = line
        if content.endswith("\r\n"):
            content, ending = content[:-2], "\r\n"
        elif content.endswith("\n") or content.endswith("\r"):
            content, ending = content[:-1], content[-1]
        if re.search(r"[\u0600-\u06FF\u0750-\u077F\u08A0-\u08FF]", content):
            try:
                content = get_display(arabic_reshaper.reshape(content), base_dir="R")
            except Exception:
                pass
        output.append(content + ending)
    return "".join(output)


class ArabicLabel(Label):
    def __init__(self, **kwargs):
        kwargs["font_name"] = ARABIC_FONT_NAME
        kwargs["text"] = display_text(kwargs.get("text", ""))
        super().__init__(**kwargs)
        self.bind(text=self._shape_updated_text)

    def _shape_updated_text(self, _instance, value):
        if getattr(self, "_updating_arabic_text", False):
            return
        shaped = display_text(value)
        if shaped != value:
            self._updating_arabic_text = True
            try:
                self.text = shaped
            finally:
                self._updating_arabic_text = False


class ArabicButton(Button):
    def __init__(self, **kwargs):
        kwargs["font_name"] = ARABIC_FONT_NAME
        kwargs["text"] = display_text(kwargs.get("text", ""))
        super().__init__(**kwargs)
        self.bind(text=self._shape_updated_text)

    def _shape_updated_text(self, _instance, value):
        if getattr(self, "_updating_arabic_text", False):
            return
        shaped = display_text(value)
        if shaped != value:
            self._updating_arabic_text = True
            try:
                self.text = shaped
            finally:
                self._updating_arabic_text = False


class ArabicTextInput(TextInput):
    def __init__(self, **kwargs):
        kwargs["font_name"] = ARABIC_FONT_NAME
        if "hint_text" in kwargs:
            kwargs["hint_text"] = display_text(kwargs["hint_text"])
        super().__init__(**kwargs)

def normalize_cookie(raw: str) -> str:
    """Normalize a Cookie header pasted locally by the user."""
    parts: dict[str, str] = {}
    cleaned = (raw or "").replace("\r", "").replace("\n", ";")
    for item in cleaned.split(";"):
        item = item.strip()
        if not item:
            continue
        lowered = item.lower()
        if lowered.startswith("cookie:") or lowered.startswith("set-cookie:"):
            item = item.split(":", 1)[1].strip()
        if "=" not in item:
            continue
        name, value = item.split("=", 1)
        name, value = name.strip(), value.strip()
        if not name or name.lower() in COOKIE_ATTRIBUTES or not value:
            continue
        parts[name] = value
    return "; ".join(f"{name}={value}" for name, value in parts.items())


def parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return datetime.min.replace(tzinfo=timezone.utc)


def get_json(path: str, cookie_header: str, referer: str) -> Any:
    """Read QUREO data with GET only. No answer or completion calls are made."""
    headers = {
        "Accept": "application/json",
        "Cookie": cookie_header,
        "Referer": referer,
        "User-Agent": USER_AGENT,
    }
    response = requests.get(
        f"{BASE_URL}{path}",
        headers=headers,
        timeout=25,
    )
    if response.status_code in (401, 403):
        raise PermissionError(
            "جلسة QUREO غير صالحة أو انتهت. سجّل الدخول من المتصفح "
            "وانسخ Cookie جديدة إلى البرنامج."
        )
    response.raise_for_status()
    try:
        return response.json()
    except ValueError as exc:
        raise ValueError("المنصة لم تُرجع JSON صالحًا.") from exc


def load_chapters(section_id: int, cookie_header: str) -> list[dict[str, Any]]:
    data = get_json(
        f"/api/study/students/sections/{section_id}/chapters",
        cookie_header,
        f"{BASE_URL}/section/{section_id}",
    )
    if not isinstance(data, list):
        raise ValueError("استجابة الفصول ليست قائمة متوقعة.")
    return [item for item in data if isinstance(item, dict) and item.get("chapter_id")]


def load_lectures(chapter_id: int, cookie_header: str) -> list[dict[str, Any]]:
    data = get_json(
        f"/api/study/students/chapters/{chapter_id}/lectures",
        cookie_header,
        f"{BASE_URL}/chapter/{chapter_id}",
    )
    if not isinstance(data, list):
        raise ValueError("استجابة الدروس ليست قائمة متوقعة.")
    return [item for item in data if isinstance(item, dict) and item.get("lecture_id")]


def load_lecture(lecture_id: int, cookie_header: str) -> dict[str, Any]:
    chapter_id = lecture_id // 1000
    data = get_json(
        f"/api/study/lectures/{lecture_id}",
        cookie_header,
        f"{BASE_URL}/chapter/{chapter_id}/lecture/{lecture_id}",
    )
    if not isinstance(data, dict) or not isinstance(data.get("talks"), list):
        raise ValueError("محتوى الدرس لا يحتوي على talks بالشكل المتوقع.")
    return data


def put_json(
    path: str,
    cookie_header: str,
    referer: str,
    payload: dict[str, Any],
) -> tuple[int, Any]:
    """Send one user-approved answer to QUREO and return its HTTP result."""
    headers = {
        "Accept": "application/json",
        "Content-Type": "application/json",
        "Origin": BASE_URL,
        "Cookie": cookie_header,
        "Referer": referer,
        "User-Agent": USER_AGENT,
    }
    response = requests.put(
        f"{BASE_URL}{path}",
        headers=headers,
        json=payload,
        timeout=25,
    )
    if response.status_code in (401, 403):
        raise PermissionError(
            "جلسة QUREO غير صالحة أو انتهت. حدّث Cookie من المتصفح."
        )
    try:
        body: Any = response.json()
    except ValueError:
        body = response.text
    if not response.ok:
        raise requests.HTTPError(
            f"QUREO HTTP {response.status_code}: {str(body)[:1200]}",
            response=response,
        )
    return response.status_code, body


def clean_text(value: Any) -> str:
    text = str(value or "")
    for marker in (
        "[[bdi]]", "[[/bdi]]", "[[code]]", "[[/code]]",
        "[[copy]]", "[[/copy]]",
    ):
        text = text.replace(marker, "")
    return text.strip()


def openai_text(api_key: str, model: str, prompt: str) -> str:
    """Call OpenAI with the question only; QUREO cookies are never sent."""
    if not api_key.strip():
        raise ValueError("أدخل مفتاح OpenAI API لتوليد اقتراح لهذا السؤال.")
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={
            "Authorization": "Bearer " + api_key.strip(),
            "Content-Type": "application/json",
        },
        json={"model": model.strip() or DEFAULT_MODEL, "input": prompt},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    direct = data.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    pieces: list[str] = []
    for item in data.get("output") or []:
        if not isinstance(item, dict):
            continue
        for part in item.get("content") or []:
            if isinstance(part, dict) and part.get("type") == "output_text":
                pieces.append(str(part.get("text") or ""))
    result = "\n".join(pieces).strip()
    if not result:
        raise ValueError("لم يرجع النموذج نص إجابة قابلًا للقراءة.")
    return result


def parse_json_object(text: str) -> dict[str, Any] | None:
    fence = chr(96) * 3
    cleaned = text.strip().replace(fence + "json", "").replace(fence, "").strip()
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(cleaned[start:end + 1])
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        return None


def choice_feedback(choice: dict[str, Any]) -> list[str]:
    feedback: list[str] = []
    for item in choice.get("after_talks") or []:
        if not isinstance(item, dict):
            continue
        body = item.get("body") or {}
        serif = body.get("serif")
        if serif:
            feedback.append(clean_text(serif))
    return feedback


def choice_feedback_is_positive(choice: dict[str, Any]) -> bool:
    text = " ".join(choice_feedback(choice)).lower()
    positive = (
        "correct", "that's right", "that is right", "great job",
        "well done", "perfect", "excellent", "ممتاز", "صحيح",
        "إجابة صحيحة", "اجابة صحيحة", "أحسنت", "احسنت", "رائع",
    )
    negative = (
        "incorrect", "wrong", "try again", "not correct",
        "خطأ", "غير صحيح", "إجابة خاطئة", "اجابة خاطئة",
    )
    return any(word in text for word in positive) and not any(
        word in text for word in negative
    )


def suggest_choice(
    question_text: str,
    choices: list[dict[str, Any]],
    api_key: str,
    model: str,
) -> str:
    options = [
        {
            "label": clean_text(choice.get("label")),
            "value": str(choice.get("value", "")),
        }
        for choice in choices
        if isinstance(choice, dict)
    ]
    prompt = (
        "أنت مساعد تعليمي لأسئلة Python. حل السؤال حسب منطق الكود، "
        "واختر قيمة واحدة من الخيارات المعطاة فقط. لا تعتمد على تخمين "
        "مفتاح إجابة مخفي. أعد JSON فقط بهذا الشكل: "
        '{"value":"القيمة","reason":"سبب مختصر بالعربية"}.\n'
        "السؤال:\n" + clean_text(question_text) +
        "\nالاختيارات:\n" + json.dumps(options, ensure_ascii=False)
    )
    raw = openai_text(api_key, model, prompt)
    parsed = parse_json_object(raw)
    allowed_values = {item["value"] for item in options}
    if not parsed or str(parsed.get("value", "")) not in allowed_values:
        return "لم أستطع التحقق من قيمة الاختيار المقترحة:\n" + raw

    value = str(parsed["value"])
    label = next(
        (item["label"] for item in options if item["value"] == value),
        value,
    )
    return (
        f"الاختيار المقترح: {label} [value={value}]\n"
        f"السبب: {parsed.get('reason', '')}"
    )


def compile_partial_code(code_item: dict[str, Any]) -> str:
    """Fill fitbBlock lines from the per-placeholder model answers."""
    code = str(code_item.get("code") or "")
    for placeholder in code_item.get("placeholders") or []:
        if not isinstance(placeholder, dict):
            continue
        name = str(placeholder.get("name") or "")
        answer = (
            placeholder.get("model_answer")
            or placeholder.get("alternative_code")
            or placeholder.get("default_code")
        )
        if not name or answer is None:
            continue
        pattern = r"(?m)^([ \t]*)" + re.escape(name) + r"[ \t]*$"
        code = re.sub(
            pattern,
            lambda match, replacement=str(answer): match.group(1) + replacement,
            code,
        )
    return code


def suggest_code(
    question_text: str,
    code_item: dict[str, Any],
    hints: list[Any],
    api_key: str,
    model: str,
) -> tuple[str, str]:
    model_answer = code_item.get("model_answer")
    if model_answer:
        return str(model_answer), "الإجابة النموذجية المرفقة في بيانات QUREO."

    if code_item.get("placeholders"):
        completed = compile_partial_code(code_item)
        if completed.strip():
            return completed, "تم ملء الأجزاء من إجابات placeholders الموجودة في الدرس."

    prompt = (
        'حل تمرين Python التالي، وأعد JSON فقط: '
        '{"code":"كود Python كامل","explanation":"شرح عربي مختصر"}.\n'
        "نص السؤال:\n" + clean_text(question_text) +
        "\nالكود الابتدائي:\n" + str(code_item.get("code") or "") +
        "\nالتلميحات:\n" + "\n".join(clean_text(hint) for hint in hints)
    )
    parsed = parse_json_object(openai_text(api_key, model, prompt))
    if not parsed or not isinstance(parsed.get("code"), str):
        raise ValueError("لم أتمكن من تحليل كود الإجابة المقترح.")
    return parsed["code"], str(parsed.get("explanation") or "")


def question_kind(talk: dict[str, Any]) -> str | None:
    talk_type = talk.get("type")
    body = talk.get("body") or {}
    if talk_type == "choice_question":
        return "اختيار من متعدد"
    if talk_type == "try":
        codes = body.get("codes") or []
        has_parts = body.get("editor_type") == "part" or any(
            isinstance(item, dict) and item.get("placeholders")
            for item in codes
        )
        return "إكمال أجزاء الكود" if has_parts else "كتابة كود"
    return None


def format_lecture(
    payload: dict[str, Any],
    api_key: str,
    model: str,
) -> str:
    chapter = payload.get("chapter") or {}
    lecture = payload.get("lecture") or {}
    lines = [
        "=" * 66,
        f"الدرس: {lecture.get('title', 'بدون عنوان')}",
        f"Lecture ID: {lecture.get('id', '—')}",
        f"Chapter: {chapter.get('seq', '—')} | {chapter.get('name', '—')}",
        f"وصف الفصل: {clean_text(chapter.get('description', ''))}",
        "=" * 66,
        "",
    ]

    for summary in payload.get("summaries") or []:
        if isinstance(summary, dict):
            if summary.get("text"):
                lines.append("ملخص: " + clean_text(summary["text"]))
            if summary.get("check_text"):
                lines.append("ملاحظة: " + clean_text(summary["check_text"]))
            lines.append("")

    question_number = 0
    for talk in payload.get("talks") or []:
        if not isinstance(talk, dict):
            continue
        talk_id = talk.get("id", "—")
        talk_type = talk.get("type", "unknown")
        body = talk.get("body") or {}
        kind = question_kind(talk)

        if kind:
            question_number += 1
            question = body.get("question")
            if isinstance(question, dict):
                question_text = question.get("text") or ""
                question_no = question.get("no")
            else:
                question_text = str(question or "")
                question_no = None

            lines.extend([
                "-" * 66,
                f"السؤال {question_number} | النوع: {kind} | Talk ID: {talk_id}",
            ])
            if question_no is not None:
                lines.append(f"رقم السؤال داخل الدرس: {question_no}")
            if question_text:
                lines.append(clean_text(question_text))
            lines.append("")

            if kind == "اختيار من متعدد":
                choices = [
                    item for item in (body.get("choices") or [])
                    if isinstance(item, dict)
                ]
                for choice in choices:
                    label = clean_text(choice.get("label", ""))
                    value = choice.get("value", "")
                    lines.append(f"  • {label}  [value={value}]")
                try:
                    lines.append(
                        suggest_choice(question_text, choices, api_key, model)
                    )
                except Exception as exc:
                    lines.append("لم يتم توليد اقتراح اختيار: " + str(exc))
            else:
                hints = body.get("hints") or []
                codes = body.get("codes") or []
                for code_item in codes:
                    if not isinstance(code_item, dict):
                        continue
                    language = code_item.get("lang") or "python"
                    starter = code_item.get("code")
                    if starter:
                        lines.append("الكود الموجود في المحرر:")
                        lines.append(str(starter))

                    placeholders = code_item.get("placeholders") or []
                    if placeholders:
                        lines.append("الأجزاء المطلوبة:")
                        for part in placeholders:
                            if not isinstance(part, dict):
                                continue
                            position = part.get("position") or {}
                            lines.append(
                                f"  {part.get('name', 'جزء')} "
                                f"(السطر {position.get('line', '?')}): "
                                f"{part.get('model_answer', '')}"
                            )

                    try:
                        answer, explanation = suggest_code(
                            question_text, code_item, hints, api_key, model
                        )
                        lines.append(f"الحل المقترح ({language}):")
                        lines.append(answer)
                        if explanation:
                            lines.append("الشرح: " + explanation)
                    except Exception as exc:
                        lines.append("لم يتم تجهيز كود لهذا السؤال: " + str(exc))

                if hints:
                    lines.append("التلميحات:")
                    for index, hint in enumerate(hints, start=1):
                        lines.append(f"  {index}. {clean_text(hint)}")

                if body.get("guide"):
                    lines.append("إرشاد المنصة: " + clean_text(body["guide"]))

            lines.append("")
        elif talk_type in ("teacher", "student") and body.get("serif"):
            speaker = "المعلم" if talk_type == "teacher" else "الطالب"
            lines.append(f"{speaker}: {clean_text(body['serif'])}")
        elif talk_type == "supplement":
            lines.append(
                "مادة إضافية: "
                + str(body.get("title") or body.get("filename") or "ملف مرفق")
            )

    lines.extend([
        "",
        "=" * 66,
        f"عدد الأسئلة المكتشفة: {question_number}",
        "تم تجهيز الإجابات المقترحة. استخدم زر إرسال السؤال بعد مراجعة الحل.",
        "=" * 66,
    ])
    return "\n".join(lines)


def prepare_submission_questions(
    payload: dict[str, Any],
    api_key: str,
    model: str,
) -> list[dict[str, Any]]:
    """Prepare editable answers from QUREO model answers/placeholders."""
    prepared: list[dict[str, Any]] = []
    for talk in payload.get("talks") or []:
        if not isinstance(talk, dict) or not talk.get("id"):
            continue
        body = talk.get("body") or {}
        talk_type = talk.get("type")
        question = body.get("question")
        question_text = (
            question.get("text", "")
            if isinstance(question, dict)
            else str(question or "")
        )
        base = {
            "talk_id": str(talk["id"]),
            "question_text": clean_text(question_text),
        }

        if talk_type == "choice_question":
            choices = [
                item for item in (body.get("choices") or [])
                if isinstance(item, dict)
            ]
            if not choices:
                continue
            correct = next(
                (
                    item for item in choices
                    if item.get("is_correct") is True
                    or item.get("correct") is True
                    or item.get("isCorrect") is True
                ),
                None,
            )
            source = "إجابة محددة صراحةً في بيانات السؤال"
            if correct is None:
                positive_matches = [
                    item for item in choices if choice_feedback_is_positive(item)
                ]
                if len(positive_matches) == 1:
                    correct = positive_matches[0]
                    source = "تم تحديدها من after_talks الذي يعرض تغذية راجعة إيجابية"
            answer_value = str(correct.get("value", "")) if correct else ""
            if not answer_value and api_key.strip():
                try:
                    suggestion = suggest_choice(
                        question_text, choices, api_key, model
                    )
                    match = re.search(r"\[value=(.*?)\]", suggestion)
                    if match:
                        answer_value = match.group(1).strip()
                        source = "اقتراح تحليلي من OpenAI؛ راجعه قبل الإرسال"
                except Exception:
                    pass
            if not answer_value:
                source = "لم تظهر إجابة صحيحة مؤكدة؛ اختر القيمة بنفسك قبل الإرسال"
            base.update({
                "kind": "choice",
                "lang": "",
                "answer": answer_value,
                "answer_source": source,
                "choices": [
                    {
                        "label": clean_text(item.get("label", "")),
                        "value": str(item.get("value", "")),
                    }
                    for item in choices
                ],
            })
            prepared.append(base)
            continue

        if talk_type != "try":
            continue
        codes = [
            item for item in (body.get("codes") or [])
            if isinstance(item, dict)
        ]
        if not codes:
            continue
        code_item = codes[0]
        language = str(code_item.get("lang") or "python")
        placeholders = [
            item for item in (code_item.get("placeholders") or [])
            if isinstance(item, dict) and item.get("name")
        ]
        is_partial = body.get("editor_type") == "part" or bool(placeholders)

        if is_partial:
            partial_answers = []
            for part in placeholders:
                answer = (
                    part.get("model_answer")
                    or part.get("alternative_code")
                    or part.get("default_code")
                )
                if answer is not None:
                    partial_answers.append({
                        "name": str(part["name"]),
                        "code": str(answer),
                    })
            if not partial_answers:
                continue
            base.update({
                "kind": "try_partial",
                "lang": language,
                "answers": partial_answers,
                "answer_source": "إجابات placeholders المرفقة في بيانات QUREO",
            })
        else:
            answer = code_item.get("model_answer")
            source = "الإجابة النموذجية المرفقة في بيانات QUREO"
            if not answer:
                try:
                    answer, explanation = suggest_code(
                        question_text,
                        code_item,
                        body.get("hints") or [],
                        api_key,
                        model,
                    )
                    source = "اقتراح مولّد؛ راجعه قبل الإرسال"
                except Exception:
                    continue
            base.update({
                "kind": "try",
                "lang": language,
                "answer": str(answer),
                "answer_source": source,
            })
        prepared.append(base)
    return prepared


def scan_latest(cookie_header: str, section_id: int) -> tuple[str, int | None]:
    chapters = load_chapters(section_id, cookie_header)
    if not chapters:
        return "المنصة لم تُرجع أي فصول لهذا القسم.", None

    incomplete_chapters = [item for item in chapters if not item.get("completed_at")]
    report = [
        f"عدد سجلات الفصول التي أعادتها المنصة: {len(chapters)}",
        "",
    ]
    if not incomplete_chapters:
        report.append("كل الفصول الظاهرة في سجل التقدم مكتملة.")
        return "\n".join(report), None

    chapter = max(
        incomplete_chapters,
        key=lambda item: parse_date(item.get("started_at")),
    )
    chapter_id = int(chapter["chapter_id"])
    report.append(
        f"آخر Chapter غير مكتمل: {chapter.get('seq', '—')} "
        f"| ID: {chapter_id}"
    )

    lectures = load_lectures(chapter_id, cookie_header)
    if not lectures:
        report.append("لم تُرجع المنصة دروسًا لهذا الفصل.")
        return "\n".join(report), None

    incomplete_lectures = [item for item in lectures if not item.get("completed_at")]
    lecture = (
        max(
            incomplete_lectures,
            key=lambda item: parse_date(item.get("started_at")),
        )
        if incomplete_lectures
        else lectures[-1]
    )
    lecture_id = int(lecture["lecture_id"])
    report.extend([
        f"عدد الدروس في الفصل: {len(lectures)}",
        f"آخر Lecture غير مكتمل/آخر درس ظاهر: {lecture_id}",
        "",
    ])
    return "\n".join(report), lecture_id


class QureOHelperApp(App):
    def build(self):
        root = BoxLayout(
            orientation="vertical",
            padding=dp(12),
            spacing=dp(8),
        )

        root.add_widget(ArabicLabel(
            text="QUREO Python Helper",
            font_size=sp(22),
            size_hint_y=None,
            height=dp(42),
        ))
        root.add_widget(ArabicLabel(
            text="الصق Cookie محليًا. لا ترسلها لأي شخص ولا تضعها في GitHub.",
            font_size=sp(13),
            size_hint_y=None,
            height=dp(30),
        ))

        self.cookie_input = ArabicTextInput(
            hint_text="Cookie من طلب QUREO في Network",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=dp(46),
            font_size=sp(13),
        )
        root.add_widget(self.cookie_input)

        self.api_key_input = ArabicTextInput(
            text=os.getenv("OPENAI_API_KEY", ""),
            hint_text="OpenAI API Key (اختياري للأسئلة التي لا تحتوي model_answer)",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=dp(46),
            font_size=sp(13),
        )
        root.add_widget(self.api_key_input)

        self.model_input = ArabicTextInput(
            text=DEFAULT_MODEL,
            hint_text="OpenAI model",
            multiline=False,
            size_hint_y=None,
            height=dp(40),
            font_size=sp(13),
        )
        root.add_widget(self.model_input)

        self.section_input = ArabicTextInput(
            text=SECTION_ID_DEFAULT,
            hint_text="Section ID",
            multiline=False,
            size_hint_y=None,
            height=dp(40),
            font_size=sp(15),
        )
        root.add_widget(self.section_input)

        actions = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(48),
        )
        scan_button = ArabicButton(text="فحص التقدم وحل آخر درس")
        scan_button.bind(on_release=self.start_scan)
        actions.add_widget(scan_button)

        self.lecture_input = ArabicTextInput(
            hint_text="Lecture ID اختياري",
            multiline=False,
            size_hint_x=0.55,
            font_size=sp(14),
        )
        actions.add_widget(self.lecture_input)

        load_button = ArabicButton(text="حل هذا الدرس")
        load_button.bind(on_release=self.start_manual_load)
        actions.add_widget(load_button)
        root.add_widget(actions)

        self.status = ArabicLabel(
            text="جاهز",
            size_hint_y=None,
            height=dp(30),
            font_size=sp(13),
        )
        root.add_widget(self.status)

        self.output = ArabicTextInput(
            text=display_text(
                "اضغط «فحص التقدم وحل آخر درس» لقراءة آخر Chapter وLecture "
                "وتجهيز إجابات الأسئلة."
            ),
            multiline=True,
            readonly=True,
            size_hint_y=0.30,
            font_size=sp(12),
        )
        root.add_widget(self.output)

        root.add_widget(ArabicLabel(
            text="راجع كل إجابة ثم اضغط زر إرسال الخاص بالسؤال.",
            font_size=sp(12),
            size_hint_y=None,
            height=dp(28),
        ))
        self.send_all_button = ArabicButton(
            text="إرسال كل إجابات الدرس المجهزة",
            size_hint_y=None,
            height=dp(46),
        )
        self.send_all_button.bind(on_release=self.start_send_all)
        root.add_widget(self.send_all_button)

        self.questions_scroll = ScrollView(size_hint_y=0.70)
        self.questions_layout = GridLayout(
            cols=1,
            spacing=dp(8),
            padding=dp(4),
            size_hint_y=None,
        )
        self.questions_layout.bind(
            minimum_height=self.questions_layout.setter("height")
        )
        self.questions_scroll.add_widget(self.questions_layout)
        root.add_widget(self.questions_scroll)
        return root

    def _get_inputs(self) -> tuple[str, int, str, str]:
        cookie = normalize_cookie(self.cookie_input.text)
        if not cookie:
            raise ValueError("أدخل Cookie الحالية أولًا.")
        try:
            section_id = int(self.section_input.text.strip())
        except ValueError as exc:
            raise ValueError("Section ID يجب أن يكون رقمًا صحيحًا.") from exc
        if section_id <= 0:
            raise ValueError("Section ID يجب أن يكون أكبر من صفر.")
        api_key = self.api_key_input.text.strip()
        model = self.model_input.text.strip() or DEFAULT_MODEL
        return cookie, section_id, api_key, model

    def start_scan(self, _button):
        try:
            cookie, section_id, api_key, model = self._get_inputs()
        except ValueError as exc:
            self.status.text = str(exc)
            return
        self._display_questions([])
        self.status.text = "جارٍ قراءة التقدم وتحليل الأسئلة..."
        threading.Thread(
            target=self._scan_worker,
            args=(cookie, section_id, api_key, model),
            daemon=True,
        ).start()

    def _scan_worker(
        self, cookie: str, section_id: int, api_key: str, model: str
    ):
        try:
            report, lecture_id = scan_latest(cookie, section_id)
            if lecture_id is None:
                Clock.schedule_once(
                    lambda _dt: self._finish("اكتمل الفحص", report), 0
                )
                return
            payload = load_lecture(lecture_id, cookie)
            output = report + "\n\n" + format_lecture(payload, api_key, model)
            questions = prepare_submission_questions(payload, api_key, model)
            Clock.schedule_once(
                lambda _dt: self._finish_and_show_questions(
                    "تم تحليل الدرس وتجهيز الإجابات", output, questions
                ), 0
            )
        except Exception as exc:
            message = self._friendly_error(exc)
            Clock.schedule_once(
                lambda _dt: self._finish("تعذر إكمال العملية", message), 0
            )

    def start_manual_load(self, _button):
        try:
            cookie, _section_id, api_key, model = self._get_inputs()
            lecture_id = int(self.lecture_input.text.strip())
            if lecture_id <= 0:
                raise ValueError
        except ValueError:
            self.status.text = "أدخل Cookie وLecture ID صحيحًا."
            return
        self._display_questions([])
        self.status.text = f"جارٍ تحليل Lecture {lecture_id}..."
        threading.Thread(
            target=self._manual_worker,
            args=(cookie, lecture_id, api_key, model),
            daemon=True,
        ).start()

    def _manual_worker(
        self, cookie: str, lecture_id: int, api_key: str, model: str
    ):
        try:
            payload = load_lecture(lecture_id, cookie)
            output = format_lecture(payload, api_key, model)
            questions = prepare_submission_questions(payload, api_key, model)
            Clock.schedule_once(
                lambda _dt: self._finish_and_show_questions(
                    "تم تحميل الدرس وتجهيز الإجابات", output, questions
                ), 0
            )
        except Exception as exc:
            message = self._friendly_error(exc)
            Clock.schedule_once(
                lambda _dt: self._finish("تعذر تحميل الدرس", message), 0
            )

    def _finish_and_show_questions(
        self,
        status: str,
        output: str,
        questions: list[dict[str, Any]],
    ):
        self._finish(status, output)
        self._display_questions(questions)

    def _display_questions(self, questions: list[dict[str, Any]]):
        self.questions_layout.clear_widgets()
        self.submission_entries: list[
            tuple[dict[str, Any], list[tuple[str, TextInput]], Button]
        ] = []
        self.send_all_button.disabled = not bool(questions)
        if not questions:
            self.questions_layout.add_widget(ArabicLabel(
                text=(
                    "لم يتم تجهيز إجابات قابلة للإرسال. "
                    "قد لا يحتوي الدرس على model_answer أو placeholders."
                ),
                size_hint_y=None,
                height=dp(55),
            ))
            return

        for number, question in enumerate(questions, start=1):
            card = BoxLayout(
                orientation="vertical",
                spacing=dp(5),
                padding=dp(8),
                size_hint_y=None,
            )
            card.bind(minimum_height=card.setter("height"))
            header = ArabicLabel(
                text=(
                    f"السؤال {number} | Talk ID: {question['talk_id']} "
                    f"| {question['kind']}"
                ),
                size_hint_y=None,
                height=dp(30),
            )
            card.add_widget(header)

            prompt = ArabicTextInput(
                text=display_text(question.get("question_text") or "سؤال بدون نص"),
                readonly=True,
                multiline=True,
                size_hint_y=None,
                height=dp(72),
                font_size=sp(12),
            )
            card.add_widget(prompt)

            source = ArabicLabel(
                text="مصدر الإجابة: " + question.get("answer_source", "غير محدد"),
                size_hint_y=None,
                height=dp(28),
                font_size=sp(11),
            )
            card.add_widget(source)

            answer_fields: list[tuple[str, TextInput]] = []
            if question["kind"] == "try_partial":
                for part in question.get("answers") or []:
                    card.add_widget(ArabicLabel(
                        text=f"الجزء: {part['name']}",
                        size_hint_y=None,
                        height=dp(24),
                    ))
                    field = ArabicTextInput(
                        text=part["code"],
                        multiline=True,
                        size_hint_y=None,
                        height=dp(65),
                        font_size=sp(12),
                    )
                    answer_fields.append((part["name"], field))
                    card.add_widget(field)
            elif question["kind"] == "choice":
                options_text = "\n".join(
                    f"{item['label']}  [value={item['value']}]"
                    for item in question.get("choices") or []
                )
                card.add_widget(ArabicLabel(
                    text=options_text,
                    size_hint_y=None,
                    height=dp(max(35, min(100, 22 * len(question.get("choices") or [])))),
                    font_size=sp(11),
                ))
                field = ArabicTextInput(
                    text=str(question.get("answer") or ""),
                    hint_text="قيمة الاختيار value",
                    multiline=False,
                    size_hint_y=None,
                    height=dp(42),
                    font_size=sp(13),
                )
                answer_fields.append(("value", field))
                card.add_widget(field)
            else:
                field = ArabicTextInput(
                    text=str(question.get("answer") or ""),
                    multiline=True,
                    size_hint_y=None,
                    height=dp(145),
                    font_size=sp(12),
                )
                answer_fields.append(("answer", field))
                card.add_widget(field)

            send_button = ArabicButton(
                text="إرسال إجابة هذا السؤال إلى QUREO",
                size_hint_y=None,
                height=dp(44),
            )
            send_button.bind(
                on_release=lambda _btn, q=question, fields=answer_fields, b=send_button:
                    self.start_send_question(q, fields, b)
            )
            card.add_widget(send_button)
            self.questions_layout.add_widget(card)
            self.submission_entries.append((question, answer_fields, send_button))

    @staticmethod
    def _make_submission_body(
        question: dict[str, Any],
        answer_fields: list[tuple[str, TextInput]],
    ) -> dict[str, Any]:
        kind = question["kind"]
        if kind == "choice":
            value = answer_fields[0][1].text.strip()
            if not value:
                raise ValueError("قيمة الاختيار فارغة.")
            body = {"choice_question": {"value": value}}
        elif kind == "try_partial":
            answers = [
                {"name": name, "code": field.text}
                for name, field in answer_fields
            ]
            if not answers or any(not item["code"].strip() for item in answers):
                raise ValueError("يوجد جزء كود فارغ.")
            body = {
                "try_partial": {
                    "lang": question["lang"],
                    "answers": answers,
                }
            }
        else:
            answer = answer_fields[0][1].text
            if not answer.strip():
                raise ValueError("كود الإجابة فارغ.")
            body = {
                "try": {
                    "lang": question["lang"],
                    "answer": answer,
                }
            }
        return {"value": body}

    def start_send_all(self, _button):
        try:
            cookie = normalize_cookie(self.cookie_input.text)
            if not cookie:
                raise ValueError("أدخل Cookie الحالية أولًا.")
            pending = []
            skipped = []
            for question, fields, send_button in self.submission_entries:
                try:
                    body = self._make_submission_body(question, fields)
                    pending.append((question["talk_id"], body, send_button))
                except ValueError as exc:
                    skipped.append(f"Talk {question['talk_id']}: {exc}")
            if not pending:
                raise ValueError("لا توجد إجابات مكتملة للإرسال.")
        except ValueError as exc:
            self.status.text = str(exc)
            return
        self.send_all_button.disabled = True
        for _talk_id, _body, send_button in pending:
            send_button.disabled = True
        self.status.text = f"جارٍ إرسال {len(pending)} إجابة..."
        threading.Thread(
            target=self._send_all_worker,
            args=(cookie, pending, skipped),
            daemon=True,
        ).start()

    def _send_all_worker(self, cookie, pending, skipped):
        results = list(skipped)
        succeeded = 0
        for talk_id, body, _send_button in pending:
            try:
                status_code, result = put_json(
                    f"/api/study/students/lecture-talks/{talk_id}",
                    cookie,
                    f"{BASE_URL}/",
                    body,
                )
                succeeded += 1
                results.append(
                    f"Talk {talk_id}: HTTP {status_code} — "
                    + json.dumps(result, ensure_ascii=False)[:1000]
                )
            except Exception as exc:
                results.append(f"Talk {talk_id}: فشل — {self._friendly_error(exc)}")
        message = (
            f"نتيجة الإرسال الجماعي: نجح {succeeded} من {len(pending)}\n"
            + "\n".join(results)
        )
        Clock.schedule_once(
            lambda _dt: self._send_all_finished(pending, succeeded, message), 0
        )

    def _send_all_finished(self, pending, succeeded: int, message: str):
        self.send_all_button.disabled = False
        for _talk_id, _body, send_button in pending:
            send_button.disabled = False
        self.status.text = f"انتهى الإرسال: {succeeded} إجابة ناجحة"
        self._raw_output = (
            getattr(self, "_raw_output", "") + "\n\n" + message
        )[-12000:]
        self.output.text = display_text(self._raw_output)

    def start_send_question(
        self,
        question: dict[str, Any],
        answer_fields: list[tuple[str, TextInput]],
        button: Button,
    ):
        try:
            cookie = normalize_cookie(self.cookie_input.text)
            if not cookie:
                raise ValueError("أدخل Cookie الحالية أولًا.")
            request_body = self._make_submission_body(question, answer_fields)
        except (KeyError, IndexError, ValueError) as exc:
            self.status.text = str(exc)
            return

        button.disabled = True
        self.send_all_button.disabled = True
        self.status.text = f"جارٍ إرسال إجابة Talk {question['talk_id']}..."
        threading.Thread(
            target=self._send_worker,
            args=(cookie, question["talk_id"], request_body, button),
            daemon=True,
        ).start()

    def _send_worker(
        self,
        cookie: str,
        talk_id: str,
        request_body: dict[str, Any],
        button: Button,
    ):
        try:
            status_code, result = put_json(
                f"/api/study/students/lecture-talks/{talk_id}",
                cookie,
                f"{BASE_URL}/",
                request_body,
            )
            message = (
                f"تم إرسال إجابة Talk {talk_id} | HTTP {status_code}\n"
                + json.dumps(result, ensure_ascii=False, indent=2)[:3500]
            )
            Clock.schedule_once(
                lambda _dt: self._send_finished(button, "تم الإرسال", message), 0
            )
        except Exception as exc:
            message = self._friendly_error(exc)
            Clock.schedule_once(
                lambda _dt: self._send_finished(button, "فشل الإرسال", message), 0
            )

    def _send_finished(self, button: Button, status: str, message: str):
        button.disabled = False
        self.send_all_button.disabled = not bool(self.submission_entries)
        self.status.text = status
        self._raw_output = (
            getattr(self, "_raw_output", "") + "\n\n" + message
        )[-12000:]
        self.output.text = display_text(self._raw_output)

    @staticmethod
    def _friendly_error(exc: Exception) -> str:
        if isinstance(exc, PermissionError):
            return str(exc)
        if isinstance(exc, requests.RequestException):
            return (
                f"فشل الاتصال ({type(exc).__name__}). "
                "تحقق من الإنترنت وصلاحية Cookie أو مفتاح OpenAI."
            )
        return f"{type(exc).__name__}: {exc}"

    def _finish(self, status: str, output: str):
        self.status.text = status
        self._raw_output = output
        self.output.text = display_text(output)


if __name__ == "__main__":
    QureOHelperApp().run()
