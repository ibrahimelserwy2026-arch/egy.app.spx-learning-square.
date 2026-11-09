from __future__ import annotations

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
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
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
    """Make a read-only GET request. No answer or completion requests exist here."""
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


def infer_choice_from_feedback(choices: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Suggest a choice only when the lesson payload explicitly includes clear feedback."""
    positive_markers = (
        "صحيح", "ممتاز", "أحسنت", "إجابة صحيحة", "correct", "great job",
    )
    negative_markers = (
        "حظا أوفر", "حظًا أوفر", "خطأ", "غير صحيح", "wrong", "try again",
    )
    positives: list[dict[str, Any]] = []
    for choice in choices:
        feedback = " ".join(choice_feedback(choice)).lower()
        is_positive = any(marker in feedback for marker in positive_markers)
        is_negative = any(marker in feedback for marker in negative_markers)
        if is_positive and not is_negative:
            positives.append(choice)
    return positives[0] if len(positives) == 1 else None


def question_kind(talk: dict[str, Any]) -> str | None:
    kind = talk.get("type")
    body = talk.get("body") or {}
    if kind == "choice_question":
        return "اختيار من متعدد"
    if kind == "try":
        codes = body.get("codes") or []
        has_parts = body.get("editor_type") == "part" or any(
            isinstance(item, dict) and item.get("placeholders")
            for item in codes
        )
        return "إكمال أجزاء الكود" if has_parts else "كتابة كود"
    return None


def format_lecture(payload: dict[str, Any]) -> str:
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
            lines.extend([
                "-" * 66,
                f"السؤال {question_number} | النوع: {kind} | Talk ID: {talk_id}",
            ])
            question = body.get("question")

            if isinstance(question, dict):
                if question.get("no") is not None:
                    lines.append(f"رقم السؤال داخل الدرس: {question['no']}")
                question_text = question.get("text")
            else:
                question_text = question
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
                    for feedback in choice_feedback(choice):
                        lines.append("      رد المنصة: " + feedback)
                suggested = infer_choice_from_feedback(choices)
                if suggested:
                    lines.append(
                        "اقتراح ظاهر من رد المنصة: "
                        f"{clean_text(suggested.get('label', ''))} "
                        f"[value={suggested.get('value', '')}]"
                    )
                else:
                    lines.append("لم يظهر رد واضح يسمح باقتراح اختيار تلقائي.")
            else:
                for code_item in body.get("codes") or []:
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
                        for placeholder in placeholders:
                            if not isinstance(placeholder, dict):
                                continue
                            position = placeholder.get("position") or {}
                            lines.append(
                                f"  {placeholder.get('name', 'جزء')} "
                                f"(السطر {position.get('line', '?')}): "
                                f"{placeholder.get('model_answer', '')}"
                            )

                    model_answer = code_item.get("model_answer")
                    if model_answer:
                        lines.append(f"الإجابة النموذجية ({language}):")
                        lines.append(str(model_answer))
                    else:
                        lines.append("لا توجد إجابة نموذجية في استجابة هذا السؤال.")

                hints = body.get("hints") or []
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
        "تم جلب المحتوى وتجهيز الحلول محليًا. لم يتم إرسال إجابات أو إكمال الدرس.",
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
            text="الصق Cookie محليًا؛ لا ترسلها لأي شخص ولا تحفظها في GitHub.",
            font_size=sp(13),
            size_hint_y=None,
            height=dp(30),
        ))

        self.cookie_input = TextInput(
            hint_text="Cookie من طلب QUREO في Network",
            password=True,
            multiline=False,
            size_hint_y=None,
            height=dp(48),
            font_size=sp(13),
        )
        root.add_widget(self.cookie_input)

        self.section_input = TextInput(
            text=SECTION_ID_DEFAULT,
            hint_text="Section ID",
            multiline=False,
            size_hint_y=None,
            height=dp(42),
            font_size=sp(15),
        )
        root.add_widget(self.section_input)

        actions = BoxLayout(
            orientation="horizontal",
            spacing=dp(8),
            size_hint_y=None,
            height=dp(48),
        )
        scan_button = Button(text="فحص التقدم وجلب آخر درس")
        scan_button.bind(on_release=self.start_scan)
        actions.add_widget(scan_button)

        self.lecture_input = TextInput(
            hint_text="Lecture ID اختياري",
            multiline=False,
            size_hint_x=0.55,
            font_size=sp(14),
        )
        actions.add_widget(self.lecture_input)

        load_button = Button(text="جلب هذا الدرس")
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
                "اضغط «فحص التقدم وجلب آخر درس» لقراءة آخر Chapter وLecture "
                "وعرض الأسئلة والحلول النموذجية المتاحة."
            ),
            multiline=True,
            readonly=True,
            size_hint_y=1,
            font_size=sp(13),
        )
        root.add_widget(self.output)
        return root

    def _get_cookie_and_section(self) -> tuple[str, int]:
        cookie = normalize_cookie(self.cookie_input.text)
        if not cookie:
            raise ValueError("أدخل Cookie الحالية أولًا.")
        try:
            section_id = int(self.section_input.text.strip())
        except ValueError as exc:
            raise ValueError("Section ID يجب أن يكون رقمًا صحيحًا.") from exc
        if section_id <= 0:
            raise ValueError("Section ID يجب أن يكون أكبر من صفر.")
        return cookie, section_id

    def start_scan(self, _button):
        try:
            cookie, section_id = self._get_cookie_and_section()
        except ValueError as exc:
            self.status.text = str(exc)
            return
        self.status.text = "جارٍ قراءة التقدم وتحميل آخر درس..."
        threading.Thread(
            target=self._scan_worker,
            args=(cookie, section_id),
            daemon=True,
        ).start()

    def _scan_worker(self, cookie: str, section_id: int):
        try:
            report, lecture_id = scan_latest(cookie, section_id)
            if lecture_id is None:
                Clock.schedule_once(
                    lambda _dt: self._finish("اكتمل الفحص", report), 0
                )
                return
            payload = load_lecture(lecture_id, cookie)
            output = report + "\n\n" + format_lecture(payload)
            Clock.schedule_once(
                lambda _dt: self._finish("تم تحميل الدرس وتجهيز الحلول", output), 0
            )
        except Exception as exc:
            message = self._friendly_error(exc)
            Clock.schedule_once(
                lambda _dt: self._finish("تعذر إكمال العملية", message), 0
            )

    def start_manual_load(self, _button):
        try:
            cookie, _section_id = self._get_cookie_and_section()
            lecture_id = int(self.lecture_input.text.strip())
            if lecture_id <= 0:
                raise ValueError
        except ValueError:
            self.status.text = "أدخل Cookie وLecture ID صحيحًا."
            return
        self.status.text = f"جارٍ تحميل Lecture {lecture_id}..."
        threading.Thread(
            target=self._manual_worker,
            args=(cookie, lecture_id),
            daemon=True,
        ).start()

    def _manual_worker(self, cookie: str, lecture_id: int):
        try:
            payload = load_lecture(lecture_id, cookie)
            output = format_lecture(payload)
            Clock.schedule_once(
                lambda _dt: self._finish("تم تحميل الدرس", output), 0
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
                f"فشل الاتصال بـ QUREO ({type(exc).__name__}). "
                "تحقق من الإنترنت وصلاحية Cookie."
            )
        return f"{type(exc).__name__}: {exc}"

    def _finish(self, status: str, output: str):
        self.status.text = status
        self.output.text = output


if __name__ == "__main__":
    QureOHelperApp().run()
