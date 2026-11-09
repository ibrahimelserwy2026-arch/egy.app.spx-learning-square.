from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests
import streamlit as st

BASE_URL = "https://me-tp.qureo.education"
COOKIE_ATTRIBUTES = {
    "path", "domain", "expires", "max-age", "httponly",
    "secure", "samesite", "priority",
}


def normalize_cookie(raw: str) -> str:
    """Convert a copied Cookie header or Set-Cookie lines to a Cookie header."""
    parts: dict[str, str] = {}
    cleaned = raw.replace("\r", "").replace("\n", ";")
    for item in cleaned.split(";"):
        item = item.strip()
        if not item:
            continue
        if item.lower().startswith("cookie:"):
            item = item.split(":", 1)[1].strip()
        if item.lower().startswith("set-cookie:"):
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


def load_lectures(chapter_id: int, cookie_header: str) -> list[dict[str, Any]]:
    """Read the lecture list for one chapter; this endpoint is GET-only."""
    url = f"{BASE_URL}/api/study/students/chapters/{chapter_id}/lectures"
    headers = {
        "Accept": "application/json",
        "Cookie": cookie_header,
        "Referer": f"{BASE_URL}/chapter/{chapter_id}",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    response = requests.get(url, headers=headers, timeout=20)
    if response.status_code in (401, 403):
        raise PermissionError(
            "انتهت الجلسة أثناء قراءة الدروس. سجّلي الدخول مجددًا "
            "وانسخي Cookie جديدة من المتصفح."
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("استجابة المنصة ليست قائمة Lectures متوقعة.")
    if any(not isinstance(item, dict) or "lecture_id" not in item for item in payload):
        raise ValueError("بعض بيانات الدروس لا تحتوي على lecture_id.")
    return payload


def load_chapters(section_id: int, cookie_header: str) -> list[dict[str, Any]]:
    url = f"{BASE_URL}/api/study/students/sections/{section_id}/chapters"
    headers = {
        "Accept": "application/json",
        "Cookie": cookie_header,
        "Referer": f"{BASE_URL}/section/{section_id}",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    response = requests.get(url, headers=headers, timeout=20)
    if response.status_code in (401, 403):
        raise PermissionError(
            "انتهت الجلسة أو أن Cookie غير صالحة. سجّلي الدخول مجددًا "
            "وانسخي Cookie جديدة من المتصفح."
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("استجابة المنصة ليست قائمة Chapters متوقعة.")
    if any(not isinstance(item, dict) or "chapter_id" not in item for item in payload):
        raise ValueError("بعض بيانات الفصول لا تحتوي على chapter_id.")
    return payload


st.set_page_config(page_title="QUREO - متابعة التقدم", page_icon="📚", layout="wide")
st.title("📚 متابعة تقدم QUREO")
st.caption(
    "قراءة فقط: يعرض الفصول ويحدد آخر فصل غير مكتمل حسب وقت البدء. "
    "لا يرسل إجابات ولا يغير بيانات الحساب."
)

with st.sidebar:
    st.subheader("اتصال QUREO")
    section_id_text = st.text_input("Section ID", value="106")
    raw_cookie = st.text_input(
        "Cookie الحالية",
        type="password",
        placeholder="الصقي Cookie الحالية هنا",
        help="الصقي Cookie header من طلب المتصفح. لا تضعيها في GitHub أو المحادثات.",
    )
    st.caption("تُستخدم الجلسة للقراءة فقط ولا يحفظ التطبيق Cookie في ملف.")

try:
    section_id = int(section_id_text)
    if section_id <= 0:
        raise ValueError
except ValueError:
    st.error("Section ID يجب أن يكون رقمًا صحيحًا موجبًا.")
    st.stop()

if st.button("جلب الفصول وتحديد آخر فصل", type="primary", use_container_width=True):
    cookie_header = normalize_cookie(raw_cookie)
    if not cookie_header:
        st.warning("الصقي Cookie الحالية أولًا.")
        st.stop()
    if "egy_student_access_token=" not in cookie_header:
        st.warning("لم يتم العثور على egy_student_access_token في Cookie.")
        st.stop()

    try:
        with st.spinner("جارٍ قراءة سجل الفصول..."):
            chapters = load_chapters(section_id, cookie_header)

        if not chapters:
            st.info("لم تُرجع المنصة أي فصول لهذا القسم.")
            st.stop()

        incomplete = [
            (idx, chapter)
            for idx, chapter in enumerate(chapters, start=1)
            if not chapter.get("completed_at")
        ]

        current_id = None
        if incomplete:
            current_number, current_chapter = max(
                incomplete,
                key=lambda pair: parse_date(pair[1].get("started_at")),
            )
            current_id = current_chapter["chapter_id"]
            st.success(f"آخر فصل غير مكتمل بدأتيه: Chapter {current_number}")
            col1, col2 = st.columns(2)
            col1.metric("رقم الفصل داخل الاستجابة", f"Chapter {current_number}")
            col2.metric("Chapter ID", str(current_id))
            st.code(str(current_id), language="text")
        else:
            st.success("كل الفصول الظاهرة مكتملة.")

        rows = []
        for idx, chapter in enumerate(chapters, start=1):
            complete = bool(chapter.get("completed_at"))
            is_current = chapter.get("chapter_id") == current_id
            rows.append({
                "ترتيب السجل": idx,
                "Chapter ID": chapter.get("chapter_id"),
                "الحالة": "مكتمل" if complete else (
                    "آخر فصل بدأتِه" if is_current else "غير مكتمل"
                ),
                "بدأ في": chapter.get("started_at") or "—",
                "اكتمل في": chapter.get("completed_at") or "—",
                "أفضل إجابات صحيحة": chapter.get("best_correct_count", 0),
                "Diamonds": chapter.get("diamond", 0),
            })

        st.subheader("سجل الفصول الذي أعادته المنصة")
        st.dataframe(rows, use_container_width=True, hide_index=True)
        st.info(
            f"الاستجابة الحالية تضم {len(chapters)} سجل فصل. "
            "إذا كان الكورس 25 فصلًا، فقد تكون هذه الواجهة أعادت الفصول التي لها سجل تقدم فقط."
        )

        st.subheader("دروس الفصل الحالي")
        if current_id is not None:
            with st.spinner("جارٍ قراءة قائمة الدروس للفصل الحالي..."):
                lectures = load_lectures(int(current_id), cookie_header)

            if lectures:
                latest_incomplete = [
                    (idx, lecture)
                    for idx, lecture in enumerate(lectures, start=1)
                    if not lecture.get("completed_at")
                ]
                lecture_rows = []
                for idx, lecture in enumerate(lectures, start=1):
                    is_active = (
                        latest_incomplete
                        and lecture.get("lecture_id") == max(
                            latest_incomplete,
                            key=lambda pair: parse_date(pair[1].get("started_at")),
                        )[1].get("lecture_id")
                    )
                    lecture_rows.append({
                        "الدرس": f"Lecture {idx}",
                        "Lecture ID": lecture.get("lecture_id"),
                        "الحالة": "مكتمل" if lecture.get("completed_at") else (
                            "آخر درس بدأتِه" if is_active else "غير مكتمل"
                        ),
                        "بدأ في": lecture.get("started_at") or "—",
                        "اكتمل في": lecture.get("completed_at") or "—",
                    })
                st.dataframe(lecture_rows, use_container_width=True, hide_index=True)

                if latest_incomplete:
                    active_lecture = max(
                        latest_incomplete,
                        key=lambda pair: parse_date(pair[1].get("started_at")),
                    )[1]
                    st.metric("Lecture ID التالي للمراجعة", str(active_lecture["lecture_id"]))
                else:
                    st.success("كل الدروس التي أعادتها المنصة مكتملة.")
            else:
                st.info("لم تُرجع المنصة أي دروس لهذا الفصل.")
        st.caption(
            "لم تتم إضافة خطوة الامتحان بعد؛ نحتاج إلى طلب بيانات الامتحان وطريقة عرضه "
            "قبل بناء متابعة دقيقة له."
        )

    except PermissionError as exc:
        st.error(str(exc))
    except requests.RequestException as exc:
        st.error(f"تعذر الاتصال بالمنصة. نوع الخطأ: {type(exc).__name__}")
    except (ValueError, KeyError) as exc:
        st.error(f"تعذر تحليل استجابة الفصول: {exc}")


def load_lecture(lecture_id: int, cookie_header: str) -> dict[str, Any]:
    """Read one lecture's content and talk/question definitions (GET only)."""
    url = f"{BASE_URL}/api/study/lectures/{lecture_id}"
    headers = {
        "Accept": "application/json",
        "Cookie": cookie_header,
        "Referer": f"{BASE_URL}/chapter/{lecture_id // 1000}/lecture/{lecture_id}",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36"
        ),
    }
    response = requests.get(url, headers=headers, timeout=20)
    if response.status_code in (401, 403):
        raise PermissionError(
            "انتهت الجلسة أو Cookie غير صالحة. سجّلي الدخول إلى QUREO "
            "وانسخي Cookie جديدة من المتصفح."
        )
    response.raise_for_status()
    payload = response.json()
    if not isinstance(payload, dict) or not isinstance(payload.get("talks"), list):
        raise ValueError("استجابة محتوى الدرس لا تحتوي على talks بالشكل المتوقع.")
    return payload


def question_kind(talk: dict[str, Any]) -> str | None:
    """Map QUREO talk payloads to the three exercise formats."""
    talk_type = talk.get("type")
    body = talk.get("body") or {}
    if talk_type == "choice_question":
        return "اختيار من متعدد"
    if talk_type == "try":
        codes = body.get("codes") or []
        if body.get("editor_type") == "part" or any(
            isinstance(item, dict) and item.get("placeholders")
            for item in codes
        ):
            return "إكمال أجزاء الكود"
        return "كتابة كود"
    return None



def clean_qureo_text(value: Any) -> str:
    """Remove QUREO's lightweight inline markers before displaying text."""
    text = str(value or "")
    for marker in (
        "[[bdi]]", "[[/bdi]]", "[[code]]", "[[/code]]",
        "[[copy]]", "[[/copy]]",
    ):
        text = text.replace(marker, "")
    return text


def render_lecture_payload(payload: dict[str, Any]) -> None:
    chapter = payload.get("chapter") or {}
    lecture = payload.get("lecture") or {}
    st.subheader(
        f"📖 {lecture.get('title') or 'محتوى الدرس'} "
        f"(Lecture ID: {lecture.get('id', '—')})"
    )
    st.caption(
        f"Chapter {chapter.get('seq', '—')} · "
        f"{chapter.get('name', '—')} · "
        f"عدد أسئلة الفصل المعلن: {chapter.get('question_count', '—')}"
    )
    if chapter.get("description"):
        st.info(clean_qureo_text(chapter["description"]))

    for summary in payload.get("summaries") or []:
        if isinstance(summary, dict):
            summary_text = summary.get("text")
            check_text = summary.get("check_text")
            if summary_text:
                st.markdown(f"**ملخص:** {clean_qureo_text(summary_text)}")
            if check_text:
                st.caption(clean_qureo_text(check_text))

    talks = payload.get("talks") or []
    question_number = 0
    st.markdown("#### محتوى الدرس والأسئلة")

    for talk in talks:
        if not isinstance(talk, dict):
            continue
        talk_id = talk.get("id", "—")
        talk_type = talk.get("type", "unknown")
        body = talk.get("body") or {}
        kind = question_kind(talk)

        if kind:
            question_number += 1
            question = body.get("question")
            with st.expander(
                f"السؤال {question_number} · {kind} · Talk ID: {talk_id}",
                expanded=True,
            ):
                if kind == "اختيار من متعدد":
                    if isinstance(question, str):
                        st.markdown(clean_qureo_text(question))
                    else:
                        st.markdown(clean_qureo_text(question or "نص السؤال غير متاح."))
                    choices = body.get("choices") or []
                    for choice in choices:
                        if not isinstance(choice, dict):
                            continue
                        label = choice.get("label", "")
                        value = choice.get("value", "")
                        st.markdown(f"- **{clean_qureo_text(label)}** (value: {value})")
                else:
                    if isinstance(question, dict):
                        if question.get("no") is not None:
                            st.caption(f"رقم السؤال داخل الدرس: {question['no']}")
                        if question.get("text"):
                            st.markdown(clean_qureo_text(question["text"]))
                    elif question:
                        st.markdown(clean_qureo_text(question))

                    if kind == "إكمال أجزاء الكود":
                        st.markdown("**الأجزاء المطلوب ملؤها:**")
                    for code_item in body.get("codes") or []:
                        if not isinstance(code_item, dict):
                            continue
                        starter = code_item.get("code")
                        if starter:
                            st.markdown("**الكود المعروض في المحرر:**")
                            st.code(starter, language=code_item.get("lang") or "python")

                        placeholders = code_item.get("placeholders") or []
                        for placeholder in placeholders:
                            if not isinstance(placeholder, dict):
                                continue
                            position = placeholder.get("position") or {}
                            st.markdown(
                                f"- **{placeholder.get('name', 'جزء')}** "
                                f"(السطر {position.get('line', '?')}): "
                                f"{placeholder.get('model_answer', '')}"
                            )

                        model_answer = code_item.get("model_answer")
                        if model_answer:
                            st.markdown("**الإجابة النموذجية:**")
                            st.code(model_answer, language=code_item.get("lang") or "python")

                    hints = body.get("hints") or []
                    if hints:
                        st.markdown("**تلميحات السؤال:**")
                        for hint_index, hint in enumerate(hints, start=1):
                            st.markdown(f"{hint_index}. {clean_qureo_text(hint)}")

                    guide = body.get("guide")
                    if guide:
                        st.caption(f"الناتج/إرشاد المنصة: {clean_qureo_text(guide)}")
        elif talk_type in ("teacher", "student") and body.get("serif"):
            speaker = "المعلم" if talk_type == "teacher" else "الطالب"
            st.markdown(f"**{speaker}:** {clean_qureo_text(body['serif'])}")
        elif talk_type == "supplement":
            title = body.get("title") or body.get("filename") or "مادة إضافية"
            st.caption(f"📎 مادة إضافية: {title}")
        else:
            with st.expander(f"عنصر إضافي · {talk_type} · ID: {talk_id}"):
                st.json(body)

    st.divider()
    st.caption(
        f"تم تحليل {question_number} سؤالًا ظاهرًا في هذا الدرس. "
        "المحتوى المعروض للقراءة والمراجعة فقط؛ لم يتم إرسال إجابات أو إكمال الدرس."
    )


st.divider()
st.subheader("🧩 قراءة أسئلة ومحتوى درس محدد")
st.write(
    "أدخلي Lecture ID لعرض نص الدرس والأسئلة ومعرّف كل سؤال. "
    "تُقرأ البيانات من QUREO بطلب GET فقط."
)
lecture_id_text = st.text_input(
    "Lecture ID",
    value="",
    placeholder="مثال: 511008010",
    key="qureo_lecture_id_input",
)
if st.button("جلب محتوى الدرس وأسئلته", key="qureo_load_lecture", type="primary"):
    st.session_state.pop("qureo_lecture_payload", None)
    cookie_header_for_lecture = normalize_cookie(raw_cookie)
    if not cookie_header_for_lecture:
        st.warning("الصقي Cookie الحالية في الشريط الجانبي أولًا.")
    elif "egy_student_access_token=" not in cookie_header_for_lecture:
        st.warning("لم يتم العثور على egy_student_access_token في Cookie.")
    else:
        try:
            lecture_id_value = int(lecture_id_text.strip())
        except (TypeError, ValueError):
            st.error("Lecture ID يجب أن يكون رقمًا صحيحًا موجبًا.")
        else:
            if lecture_id_value <= 0:
                st.error("Lecture ID يجب أن يكون رقمًا صحيحًا موجبًا.")
            else:
                try:
                    with st.spinner("جارٍ قراءة محتوى الدرس والأسئلة..."):
                        st.session_state["qureo_lecture_payload"] = load_lecture(
                            lecture_id_value, cookie_header_for_lecture
                        )
                        st.session_state["qureo_loaded_lecture_id"] = lecture_id_value
                except PermissionError as exc:
                    st.error(str(exc))
                except requests.RequestException as exc:
                    st.error(f"تعذر الاتصال بـ QUREO. نوع الخطأ: {type(exc).__name__}")
                except (ValueError, KeyError) as exc:
                    st.error(f"تعذر تحليل محتوى الدرس: {exc}")

if st.session_state.get("qureo_lecture_payload"):
    render_lecture_payload(st.session_state["qureo_lecture_payload"])
