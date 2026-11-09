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
    """Accept a Cookie header or copied Set-Cookie lines; never log values."""
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
        name, value = name.strip(), value.strip()
        if not name or name.lower() in COOKIE_ATTRIBUTES or not value:
            continue
        parts[name] = value
    return "; ".join(f"{name}={value}" for name, value in parts.items())


def parse_date(value: str | None) -> datetime:
    if not value:
        return datetime.min
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return datetime.min


def load_chapters(section_id: int, cookie_header: str) -> list[dict[str, Any]]:
    url = f"{BASE_URL}/api/study/students/sections/{section_id}/chapters"
    headers = {
        "Accept": "application/json",
        "Cookie": cookie_header,
        "Referer": f"{BASE_URL}/section/{section_id}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
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
            col1.metric("رقم الفصل", f"Chapter {current_number}")
            col2.metric("Chapter ID", str(current_id))
            st.code(str(current_id), language="text")
        else:
            st.success("كل الفصول الظاهرة مكتملة.")

        rows = []
        for idx, chapter in enumerate(chapters, start=1):
            complete = bool(chapter.get("completed_at"))
            is_current = chapter.get("chapter_id") == current_id
            rows.append({
                "الفصل": f"Chapter {idx}",
                "Chapter ID": chapter.get("chapter_id"),
                "الحالة": "مكتمل" if complete else ("آخر فصل بدأتِه" if is_current else "غير مكتمل"),
                "بدأ في": chapter.get("started_at") or "—",
                "اكتمل في": chapter.get("completed_at") or "—",
                "أفضل إجابات صحيحة": chapter.get("best_correct_count", 0),
                "Diamonds": chapter.get("diamond", 0),
            })

        st.subheader("سجل الفصول")
        st.dataframe(rows, use_container_width=True, hide_index=True)

        options = {
            f"Chapter {idx} — ID {chapter['chapter_id']}": chapter["chapter_id"]
            for idx, chapter in enumerate(chapters, start=1)
        }
        st.subheader("اختيار Chapter")
        selected = st.selectbox("اختاري فصلًا", list(options))
        st.text_input("Chapter ID المحدد", value=str(options[selected]))

    except PermissionError as exc:
        st.error(str(exc))
    except requests.RequestException as exc:
        st.error(f"تعذر الاتصال بالمنصة. نوع الخطأ: {type(exc).__name__}")
    except (ValueError, KeyError) as exc:
        st.error(f"تعذر تحليل استجابة الفصول: {exc}")
