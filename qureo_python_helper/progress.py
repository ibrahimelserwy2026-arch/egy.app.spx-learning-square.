from __future__ import annotations

from datetime import datetime
from typing import Any

import requests
import streamlit as st

BASE_URL = "https://me-tp.qureo.education"
COOKIE_ATTRIBUTES = {
    "path", "domain", "expires", "max-age", "httponly",
    "secure", "samesite", "priority",
}


def normalize_cookie(raw: str) -> str:
    """Accept a Cookie header or copied Set-Cookie lines; never log the values."""
    parts: dict[str, str] = {}
    cleaned = raw.replace("\\r", "").replace("\\n", ";")
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
        name = name.strip()
        value = value.strip()
        if not name or name.lower() in COOKIE_ATTRIBUTES or not value:
            continue
        parts[name] = value

    return "; ".join(f"{name}={value}" for name, value in parts.items())


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
            "انتهت الجلسة أو أن ملفات تعريف الارتباط غير صالحة. "
            "سجّلي الدخول مجددًا وانسخي Cookie جديدة من المتصفح."
        )
    response.raise_for_status()

    payload = response.json()
    if not isinstance(payload, list):
        raise ValueError("استجابة المنصة ليست قائمة Chapters متوقعة.")
    for chapter in payload:
        if not isinstance(chapter, dict) or "chapter_id" not in chapter:
            raise ValueError("بيانات Chapter غير مكتملة في استجابة المنصة.")
    return payload


def parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.min


st.set_page_config(page_title="QUREO Progress", page_icon="📚", layout="wide")
st.title("📚 متابعة تقدم QUREO")
st.caption(
    "قراءة فقط: يعرض الفصول وتقدمها ويحدد آخر فصل نشط. "
    "لا يرسل إجابات ولا يغيّر أي بيانات في حسابك."
)

with st.sidebar:
    st.subheader("اتصال QUREO")
    section_id_text = st.text_input("Section ID", value="106")
    raw_cookie = st.text_input(
        "Cookie الحالية",
        type="password",
        placeholder="الصقي Cookie الحالية هنا — لا ترسليها في المحادثة",
        help=(
            "استخدمي جلسة جديدة بعد إبطال الرموز التي سبق نشرها. "
            "يمكن لصق Cookie header أو أسطر Set-Cookie من أدوات المطور."
        ),
    )
    st.caption("يستخدم التطبيق Cookie في طلب قراءة واحد فقط ولا يحفظها في ملف.")

try:
    section_id = int(section_id_text)
    if section_id < 1:
        raise ValueError
except ValueError:
    st.error("Section ID يجب أن يكون رقمًا صحيحًا موجبًا.")
    st.stop()

if st.button("جلب الفصول وتحديد مكاني", type="primary", use_container_width=True):
    cookie_header = normalize_cookie(raw_cookie)
    if not cookie_header:
        st.warning("أدخلي Cookie الحالية من متصفحك أولًا.")
        st.stop()
    if "egy_student_access_token=" not in cookie_header:
        st.warning(
            "لم أجد egy_student_access_token ضمن Cookie. "
            "تأكدي أنك نسختِ Cookie الخاصة بنطاق qureo.education."
        )
        st.stop()

    try:
        with st.spinner("جارٍ قراءة قائمة الفصول..."):
            chapters = load_chapters(section_id, cookie_header)

        if not chapters:
            st.info("لم تُرجع المنصة أي فصول لهذا القسم.")
            st.stop()

        incomplete = [
            (index, chapter)
            for index, chapter in enumerate(chapters, start=1)
            if not chapter.get("completed_at")
        ]
        if incomplete:
            current_number, current_chapter = max(
                incomplete,
                key=lambda pair: parse_date(pair[1].get("started_at")),
            )
            st.success(f"آخر فصل نشط حسب سجل البدء: Chapter {current_number}")
            left, right = st.columns(2)
            left.metric("رقم الفصل", f"Chapter {current_number}")
            right.metric("Chapter ID", str(current_chapter["chapter_id"]))
            st.code(str(current_chapter["chapter_id"]), language="text")
        else:
            st.success("كل الفصول الظاهرة مكتملة حسب البيانات التي أعادتها المنصة.")

        rows = []
        for index, chapter in enumerate(chapters, start=1):
            is_done = bool(chapter.get("completed_at"))
            rows.append({
                "الفصل": f"Chapter {index}",
                "Chapter ID": chapter.get("chapter_id"),
                "الحالة": "مكتمل" if is_done else (
                    "نشط" if incomplete and chapter.get("chapter_id") == current_chapter.get("chapter_id")
                    else "لم يكتمل"
                ),
                "بدأ في": chapter.get("started_at") or "—",
                "اكتمل في": chapter.get("completed_at") or "—",
                "أفضل إجابات صحيحة": chapter.get("best_correct_count", 0),
                "Diamonds": chapter.get("diamond", 0),
            })

        st.subheader("كل الفصول")
        st.dataframe(rows, use_container_width=True, hide_index=True)

        st.subheader("اختيار Chapter")
        choices = {
            f"Chapter {index} — ID {chapter['chapter_id']}": chapter["chapter_id"]
            for index, chapter in enumerate(chapters, start=1)
        }
        selected_label = st.selectbox("اختاري فصلًا لنسخ رقمه", list(choices.keys()))
        st.text_input(
            "Chapter ID المحدد",
            value=str(choices[selected_label]),
            help="انسخي هذا الرقم لاستخدامه في خطوة لاحقة.",
        )

    except PermissionError as exc:
        st.error(str(exc))
    except requests.RequestException as exc:
        st.error(
            "تعذر الاتصال بمنصة QUREO. تحققي من الإنترنت ثم حاولي مجددًا. "
            f"نوع الخطأ: {type(exc).__name__}"
        )
    except (ValueError, KeyError) as exc:
        st.error(f"تعذر فهم بيانات الفصول: {exc}")
