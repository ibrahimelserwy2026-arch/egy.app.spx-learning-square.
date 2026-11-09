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
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.button import Button
from kivy.uix.label import Label
from kivy.uix.textinput import TextInput


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
        "تم تجهيز الحلول المقترحة محليًا. لم يتم إرسال إجابات إلى QUREO "
        "ولم يتم استدعاء endpoint إكمال الدرس أو الاختبار.",
        "=" * 66,
    ])
    return "\n".join(lines)


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

        root.add_widget(Label(
            text="QUREO Python Helper",
            font_size=sp(22),
            size_hint_y=None,
            height=dp(42),
        ))
        root.add_widget(Label(
            text="الصق Cookie محليًا. لا ترسلها لأي شخص ولا تضعها في GitHub.",
            font_size=sp(13),
            size_hint_y=None,
            height=dp(30),
        ))

        self.cookie_input = TextInput(
            hint_text="Cookie من طلب QUREO في Network",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=dp(46),
            font_size=sp(13),
        )
        root.add_widget(self.cookie_input)

        self.api_key_input = TextInput(
            text=os.getenv("OPENAI_API_KEY", ""),
            hint_text="OpenAI API Key (اختياري للأسئلة التي لا تحتوي model_answer)",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=dp(46),
            font_size=sp(13),
        )
        root.add_widget(self.api_key_input)

        self.model_input = TextInput(
            text=DEFAULT_MODEL,
            hint_text="OpenAI model",
            multiline=False,
            size_hint_y=None,
            height=dp(40),
            font_size=sp(13),
        )
        root.add_widget(self.model_input)

        self.section_input = TextInput(
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
        scan_button = Button(text="فحص التقدم وحل آخر درس")
        scan_button.bind(on_release=self.start_scan)
        actions.add_widget(scan_button)

        self.lecture_input = TextInput(
            hint_text="Lecture ID اختياري",
            multiline=False,
            size_hint_x=0.55,
            font_size=sp(14),
        )
        actions.add_widget(self.lecture_input)

        load_button = Button(text="حل هذا الدرس")
        load_button.bind(on_release=self.start_manual_load)
        actions.add_widget(load_button)
        root.add_widget(actions)

        self.status = Label(
            text="جاهز",
            size_hint_y=None,
            height=dp(30),
            font_size=sp(13),
        )
        root.add_widget(self.status)

        self.output = TextInput(
            text=(
                "اضغط «فحص التقدم وحل آخر درس» لقراءة آخر Chapter وLecture "
                "واستخراج الإجابات النموذجية أو اقتراح حلول للأسئلة."
            ),
            multiline=True,
            readonly=True,
            size_hint_y=1,
            font_size=sp(13),
        )
        root.add_widget(self.output)

        root.add_widget(Label(
            text=(
                "مساعد الحل لا يرسل إجابات أو ينهي الدرس/الاختبار. "
                "راجع الاقتراحات وأدخل إجاباتك بنفسك على المنصة."
            ),
            font_size=sp(12),
            size_hint_y=None,
            height=dp(38),
        ))
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
            Clock.schedule_once(
                lambda _dt: self._finish("تم تحليل الدرس وتجهيز الحلول", output), 0
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
            Clock.schedule_once(
                lambda _dt: self._finish("تم تحميل الدرس وتجهيز الحلول", output), 0
            )
        except Exception as exc:
            message = self._friendly_error(exc)
            Clock.schedule_once(
                lambda _dt: self._finish("تعذر تحميل الدرس", message), 0
            )

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
        self.output.text = output


if __name__ == "__main__":
    QureOHelperApp().run()
