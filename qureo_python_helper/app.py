from __future__ import annotations

import base64
import os

import streamlit as st
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

st.set_page_config(
    page_title="QUREO Python Helper",
    page_icon="🐍",
    layout="centered",
)

st.title("🐍 QUREO Python Helper")
st.caption("مساعد لفهم تدريبات Python — الصقي السؤال أو ارفعي صورة له.")

with st.sidebar:
    st.header("الإعدادات")
    model = st.text_input(
        "نموذج OpenAI",
        value=os.getenv("OPENAI_MODEL", "gpt-5.5"),
        help="يمكن تغيير النموذج حسب النماذج المتاحة في حساب API الخاص بك.",
    )
    answer_style = st.radio(
        "طريقة الشرح",
        ["تلميحات ثم الحل", "الحل كاملًا مع الشرح", "مراجعة إجابتي"],
    )
    st.markdown("---")
    st.caption("لا تضعي كلمة مرور QUREO أو Cookies أو رموز تسجيل الدخول في هذا التطبيق.")

question = st.text_area(
    "نص السؤال",
    height=180,
    placeholder="اكتبي أو الصقي سؤال البرمجة هنا...",
)

uploaded_image = st.file_uploader(
    "أو ارفعي صورة السؤال",
    type=["png", "jpg", "jpeg", "webp"],
)

student_attempt = ""
if answer_style == "مراجعة إجابتي":
    student_attempt = st.text_area(
        "اكتبي محاولتك البرمجية هنا",
        height=140,
        placeholder="الصقي كود Python الذي كتبتيه...",
    )

extra_context = st.text_input(
    "معلومة إضافية (اختياري)",
    placeholder="مثل: أنا أتعلم المتغيرات و if فقط",
)

def build_instructions(style: str) -> str:
    base = (
        "أنت مساعد تعليمي متخصص في تعليم Python للمبتدئين الناطقين بالعربية. "
        "اشرح بالعربية البسيطة، واستخدم أمثلة قصيرة. "
        "التزم بمستوى السؤال ولا تستخدم مفاهيم متقدمة دون شرحها. "
        "لا تخمّن نصًا غير واضح في الصورة؛ اذكر ما يحتاج إلى توضيح. "
        "لا تدّعِ أنك دخلت منصة QUREO أو أرسلت الإجابة إليها. "
        "اعرض الكود داخل كتلة Python، واشرح كل خطوة، ثم أعطِ مثالًا للاختبار "
        "واذكر الناتج المتوقع عند إمكانية تحديده."
    )
    if style == "تلميحات ثم الحل":
        return base + (
            " ابدأ بتلميحين يساعدان الطالبة على التفكير بنفسها، ثم اكتب "
            "حلًا نموذجيًا مشروحًا تحت عنوان منفصل."
        )
    if style == "مراجعة إجابتي":
        return base + (
            " راجع محاولة الطالبة، وحدد ما هو صحيح، واشرح الأخطاء، "
            "ثم قدم تعديلًا بسيطًا يحافظ على أسلوبها قدر الإمكان."
        )
    return base + " قدّم حلًا صحيحًا مع شرح واضح ومختصر."

if st.button("حلّل السؤال واشرحه", type="primary", use_container_width=True):
    if not question.strip() and uploaded_image is None:
        st.warning("اكتبي السؤال أو ارفعي صورة له أولًا.")
        st.stop()

    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        st.error(
            "لم يتم العثور على OPENAI_API_KEY. أضيفي مفتاح API في ملف .env "
            "كما هو موضح في README.md."
        )
        st.stop()

    user_text = "حلّلي سؤال Python التالي."
    if question.strip():
        user_text += "\n\nنص السؤال:\n" + question.strip()
    if student_attempt.strip():
        user_text += "\n\nمحاولة الطالبة:\n" + student_attempt.strip()
    if extra_context.strip():
        user_text += "\n\nمستوى الطالبة أو سياق إضافي:\n" + extra_context.strip()

    content: list[dict] = [{"type": "input_text", "text": user_text}]

    if uploaded_image is not None:
        image_bytes = uploaded_image.getvalue()
        mime_type = uploaded_image.type or "image/png"
        encoded = base64.b64encode(image_bytes).decode("ascii")
        data_url = f"data:{mime_type};base64,{encoded}"
        content.append({"type": "input_image", "image_url": data_url})

    try:
        with st.spinner("جارٍ تحليل السؤال وتجهيز الشرح..."):
            client = OpenAI(api_key=api_key)
            response = client.responses.create(
                model=model.strip() or "gpt-5.5",
                instructions=build_instructions(answer_style),
                input=[{"role": "user", "content": content}],
                max_output_tokens=2500,
                store=False,
            )
            answer = response.output_text

        if not answer:
            st.warning("لم يصل نص للإجابة. جرّبي صياغة السؤال مرة أخرى.")
        else:
            st.subheader("الشرح والحل")
            st.markdown(answer)
            st.download_button(
                "تنزيل الشرح كملف نصي",
                data=answer,
                file_name="qureo_python_solution.txt",
                mime="text/plain",
            )
    except Exception as exc:
        # Avoid printing credentials or request headers into the interface.
        st.error(
            "حدث خطأ أثناء الاتصال بخدمة OpenAI. "
            "راجعي مفتاح API واتصال الإنترنت واسم النموذج، ثم حاولي مرة أخرى."
        )
        st.caption(f"نوع الخطأ: {type(exc).__name__}")
