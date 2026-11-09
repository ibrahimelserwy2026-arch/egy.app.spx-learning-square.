"""
QUREO Python Assistant
Reads progress and lesson questions, then prepares local answer suggestions.
Uses GET requests only: it does not submit answers or complete lessons/tests.
"""
import json
import os
import queue
import re
import threading
from datetime import datetime

import requests
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText

BASE = "https://me-tp.qureo.education"
TIMEOUT = 25
MODEL_DEFAULT = "gpt-4.1-mini"


def clean(value):
    text = str(value or "")
    for marker in ("[[bdi]]", "[[/bdi]]", "[[code]]", "[[/code]]", "[[copy]]", "[[/copy]]"):
        text = text.replace(marker, "")
    return text.strip()


def timestamp(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).timestamp()
    except (TypeError, ValueError, OverflowError):
        return 0


def as_list(data, *keys):
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        for key in keys:
            if isinstance(data.get(key), list):
                return [x for x in data[key] if isinstance(x, dict)]
        nested = data.get("data")
        if isinstance(nested, list):
            return [x for x in nested if isinstance(x, dict)]
        if isinstance(nested, dict):
            for key in keys:
                if isinstance(nested.get(key), list):
                    return [x for x in nested[key] if isinstance(x, dict)]
    return []


class Qureo:
    def __init__(self, cookie):
        if not cookie.strip():
            raise ValueError("أدخل Cookie جلسة QUREO.")
        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/json",
            "Cookie": cookie.strip(),
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/157.0.0.0 Safari/537.36",
        })

    def get(self, path, referer=None):
        headers = {"Referer": referer} if referer else {}
        response = self.session.get(BASE + path, headers=headers, timeout=TIMEOUT)
        if response.status_code in (401, 403):
            raise PermissionError("Cookie غير صالحة أو انتهت. سجّل الدخول وانسخ Cookie جديدة.")
        response.raise_for_status()
        try:
            return response.json()
        except ValueError as exc:
            raise ValueError("استجابة QUREO ليست JSON صالحًا.") from exc

    def latest_chapter(self, section):
        data = self.get("/api/study/students/sections/" + str(section) + "/chapters")
        rows = as_list(data, "chapters")
        rows = [x for x in rows if not x.get("completed_at")]
        if not rows:
            raise LookupError("لم يظهر فصل غير مكتمل. يمكنك إدخال Chapter ID يدويًا.")
        return max(rows, key=lambda x: timestamp(x.get("started_at")))

    def latest_lecture(self, chapter):
        data = self.get("/api/study/students/chapters/" + str(chapter) + "/lectures")
        rows = as_list(data, "lectures")
        rows = [x for x in rows if not x.get("completed_at")]
        if not rows:
            raise LookupError("لم يظهر درس غير مكتمل. يمكنك إدخال Lecture ID يدويًا.")
        return max(rows, key=lambda x: timestamp(x.get("started_at")))

    def lecture(self, lecture_id):
        data = self.get(
            "/api/study/lectures/" + str(lecture_id),
            BASE + "/chapter/" + str(int(lecture_id) // 1000) + "/lecture/" + str(lecture_id),
        )
        if not isinstance(data, dict) or not isinstance(data.get("talks"), list):
            raise ValueError("بيانات الدرس لا تحتوي على talks.")
        return data


def openai_text(api_key, model, prompt):
    if not api_key.strip():
        raise ValueError("أدخل مفتاح OpenAI API لتوليد اقتراح لهذا السؤال.")
    response = requests.post(
        "https://api.openai.com/v1/responses",
        headers={"Authorization": "Bearer " + api_key.strip(), "Content-Type": "application/json"},
        json={"model": model or MODEL_DEFAULT, "input": prompt},
        timeout=60,
    )
    response.raise_for_status()
    data = response.json()
    if isinstance(data.get("output_text"), str):
        return data["output_text"].strip()
    result = []
    for item in data.get("output", []):
        for part in item.get("content", []):
            if part.get("type") == "output_text":
                result.append(part.get("text", ""))
    return "\n".join(result).strip()


def json_object(text):
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


def complete_partial(code_item):
    code = str(code_item.get("code") or "")
    for part in code_item.get("placeholders") or []:
        name = str(part.get("name") or "")
        answer = part.get("model_answer") or part.get("alternative_code") or part.get("default_code")
        if name and answer is not None:
            pattern = r"(?m)^([ \t]*)" + re.escape(name) + r"[ \t]*$"
            code = re.sub(pattern, lambda match: match.group(1) + str(answer), code)
    return code


def suggested_choice(question, choices, api_key, model):
    options = [
        {"label": clean(c.get("label")), "value": str(c.get("value", ""))}
        for c in choices if isinstance(c, dict)
    ]
    prompt = (
        "حل سؤال Python التالي اعتمادًا على منطق الكود. اختر value واحدة من القائمة فقط. "
        'أعد JSON فقط بهذا الشكل: {"value":"...","reason":"سبب مختصر بالعربية"}.\n'
        "السؤال:\n" + clean(question) +
        "\nالاختيارات:\n" + json.dumps(options, ensure_ascii=False)
    )
    raw = openai_text(api_key, model, prompt)
    parsed = json_object(raw)
    allowed = {x["value"] for x in options}
    if not parsed or str(parsed.get("value", "")) not in allowed:
        return "تعذر التحقق من اقتراح النموذج: " + raw
    value = str(parsed["value"])
    label = next((x["label"] for x in options if x["value"] == value), value)
    return "الاختيار المقترح: " + label + " (value=" + value + ")\nالسبب: " + str(parsed.get("reason", ""))


def suggested_code(question, code_item, hints, api_key, model):
    answer = code_item.get("model_answer")
    if answer:
        return str(answer), "الإجابة النموذجية الموجودة في بيانات الدرس."
    if code_item.get("placeholders"):
        return complete_partial(code_item), "تم ملء أجزاء الكود من model_answer لكل جزء متاح."
    prompt = (
        'حل تمرين Python وأعد JSON فقط: {"code":"كود كامل","explanation":"شرح عربي مختصر"}.\n'
        "نص السؤال:\n" + clean(question) +
        "\nالكود الابتدائي:\n" + str(code_item.get("code") or "") +
        "\nالتلميحات:\n" + "\n".join(clean(x) for x in hints)
    )
    parsed = json_object(openai_text(api_key, model, prompt))
    if not parsed or not isinstance(parsed.get("code"), str):
        raise ValueError("لم أتمكن من قراءة كود الإجابة من رد النموذج.")
    return parsed["code"], str(parsed.get("explanation") or "")


def prepare(payload, api_key, model):
    chapter = payload.get("chapter") or {}
    lecture = payload.get("lecture") or {}
    lines = [
        "الفصل: " + str(chapter.get("name", "—")) + " | Chapter ID: " + str(chapter.get("id", "—")),
        "الدرس: " + str(lecture.get("title", "—")) + " | Lecture ID: " + str(lecture.get("id", "—")),
        "=" * 68,
    ]
    number = 0
    for talk in payload.get("talks", []):
        kind = talk.get("type")
        if kind not in ("try", "choice_question"):
            continue
        number += 1
        body = talk.get("body") or {}
        question = body.get("question")
        text = question.get("text", "") if isinstance(question, dict) else str(question or "")
        lines.extend(["", "السؤال " + str(number) + " | Talk ID: " + str(talk.get("id", "—"))])
        lines.append("النوع: " + ("اختيار من متعدد" if kind == "choice_question" else "كتابة/إكمال كود"))
        lines.append(clean(text) or "(لا يوجد نص سؤال)")

        if kind == "choice_question":
            choices = body.get("choices") or []
            for option in choices:
                lines.append(" - " + clean(option.get("label")) + " [value=" + str(option.get("value", "")) + "]")
            try:
                lines.append(suggested_choice(text, choices, api_key, model))
            except Exception as exc:
                lines.append("الاقتراح غير متاح: " + str(exc))
        else:
            hints = body.get("hints") or []
            for item in body.get("codes") or []:
                try:
                    code, explanation = suggested_code(text, item, hints, api_key, model)
                    lines.extend(["الحل المقترح:", code, "الشرح: " + explanation])
                except Exception as exc:
                    lines.append("تعذر تجهيز كود لهذا الجزء: " + str(exc))
            if hints:
                lines.append("التلميحات:")
                lines.extend(str(i) + ". " + clean(h) for i, h in enumerate(hints, 1))

    lines.extend([
        "", "=" * 68,
        "عدد الأسئلة التي تم تحليلها: " + str(number),
        "اقتراحات محلية فقط: لم يتم إرسال إجابات، ولم يتم استدعاء /complete.",
    ])
    return "\n".join(lines), number


class App:
    def __init__(self, root):
        self.root = root
        root.title("QUREO Python Assistant")
        root.geometry("960x740")
        root.minsize(720, 560)
        self.events = queue.Queue()
        self.cookie = tk.StringVar()
        self.api_key = tk.StringVar(value=os.getenv("OPENAI_API_KEY", ""))
        self.model = tk.StringVar(value=MODEL_DEFAULT)
        self.section = tk.StringVar(value="106")
        self.chapter = tk.StringVar()
        self.lecture = tk.StringVar()
        self._build()
        root.after(120, self._poll)

    def _build(self):
        frame = ttk.Frame(self.root, padding=14)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="مساعد QUREO — تحديد آخر درس وتجهيز الحلول", font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 8))
        ttk.Label(frame, text="الصق Cookie من جلسة المتصفح. لا تدخل كلمة المرور ولا يتم حفظ Cookie على الجهاز.", wraplength=900).pack(anchor="w")
        form = ttk.Frame(frame)
        form.pack(fill="x", pady=8)
        fields = [
            ("Cookie", self.cookie, True),
            ("OpenAI API Key (اختياري)", self.api_key, True),
            ("Model", self.model, False),
            ("Section ID", self.section, False),
            ("Chapter ID (اختياري)", self.chapter, False),
            ("Lecture ID (اختياري)", self.lecture, False),
        ]
        for row, (label, variable, secret) in enumerate(fields):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            ttk.Entry(form, textvariable=variable, show="*" if secret else "").grid(row=row, column=1, sticky="ew", pady=4)
        form.columnconfigure(1, weight=1)

        bar = ttk.Frame(frame)
        bar.pack(fill="x", pady=8)
        self.run_button = ttk.Button(bar, text="جلب آخر درس وتجهيز الحلول", command=self.start)
        self.run_button.pack(side="left")
        ttk.Button(bar, text="مسح النتائج", command=lambda: self.show("")).pack(side="left", padx=8)
        self.status = tk.StringVar(value="جاهز.")
        ttk.Label(frame, textvariable=self.status).pack(anchor="w", pady=(0, 6))
        self.output = ScrolledText(frame, wrap="word", font=("Consolas", 10))
        self.output.pack(fill="both", expand=True)
        self.output.insert("end", "ستظهر هنا الأسئلة والحلول المقترحة.\n")
        ttk.Label(
            frame,
            text="البرنامج يقرأ QUREO ويجهّز اقتراحات فقط؛ لا يرسل PUT للإجابات ولا ينهي الدرس أو الامتحان.",
            foreground="#8a4b08", wraplength=900
        ).pack(anchor="w", pady=(8, 0))

    def show(self, text):
        self.output.delete("1.0", "end")
        self.output.insert("end", text)

    def start(self):
        if not self.cookie.get().strip():
            messagebox.showwarning("بيانات ناقصة", "الصق Cookie أولًا.")
            return
        self.run_button.configure(state="disabled")
        self.status.set("جارٍ جلب التقدم ومحتوى الدرس...")
        self.show("جارٍ الاتصال بـ QUREO...\n")
        args = (
            self.cookie.get(), self.api_key.get(), self.model.get(),
            self.section.get(), self.chapter.get(), self.lecture.get()
        )
        threading.Thread(target=self.worker, args=args, daemon=True).start()

    def worker(self, cookie, api_key, model, section, chapter, lecture):
        try:
            client = Qureo(cookie)
            if lecture.strip():
                lecture_id = int(lecture)
                payload = client.lecture(lecture_id)
                chapter_id = (payload.get("chapter") or {}).get("id", "—")
            else:
                if chapter.strip():
                    chapter_id = int(chapter)
                else:
                    chapter_data = client.latest_chapter(section)
                    chapter_id = int(chapter_data["chapter_id"])
                lecture_data = client.latest_lecture(chapter_id)
                lecture_id = int(lecture_data["lecture_id"])
                payload = client.lecture(lecture_id)
            result, count = prepare(payload, api_key, model)
            self.events.put(("done", (result, count, chapter_id, lecture_id)))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                if kind == "done":
                    result, count, chapter, lecture = data
                    self.show(result)
                    self.status.set("تم تحليل " + str(count) + " سؤالًا | Chapter " + str(chapter) + " | Lecture " + str(lecture))
                    self.run_button.configure(state="normal")
                else:
                    self.show("تعذر إكمال العملية:\n" + str(data))
                    self.status.set("حدث خطأ.")
                    self.run_button.configure(state="normal")
        except queue.Empty:
            pass
        self.root.after(120, self._poll)


if __name__ == "__main__":
    window = tk.Tk()
    App(window)
    window.mainloop()
