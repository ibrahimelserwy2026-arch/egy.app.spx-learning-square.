# QUREO Python Helper

مساعد تعليمي محلي لأسئلة Python، مع صفحة لمتابعة تقدم الفصول في QUREO وبرنامج Kivy مستقل على نمط `start_learn.py`.

## ما يقدمه

- الصق سؤال Python أو ارفع صورة له للحصول على شرح عربي وكود مقترح من مساعد OpenAI.
- صفحة **QUREO Progress** في Streamlit لمراجعة تقدم الفصول والدروس.
- قارئ محتوى الدرس يعرض Talk IDs وأنواع الأسئلة الثلاثة.
- البرنامج المستقل `start_qureo.py` يفحص آخر Chapter وLecture غير مكتملين، ثم يجلب الدرس تلقائيًا ويستخرج `model_answer` وحقول `placeholders`.
- أسئلة الاختيار تعرض البدائل وقيمها، وتعرض اقتراحًا فقط عندما تتضمن استجابة QUREO ردًا واضحًا وصريحًا على الاختيار.

## تشغيل برنامج Kivy المشابه لـ start_learn.py

يتطلب Python 3.10 أو أحدث.

على Windows:

```powershell
cd qureo_python_helper
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-kivy.txt
python start_qureo.py
```

1. سجّل الدخول إلى QUREO في المتصفح بنفسك.
2. انسخ Cookie من طلب QUREO في Network والصقها داخل البرنامج محليًا.
3. اضغط **فحص التقدم وجلب آخر درس**؛ سيقرأ البرنامج الفصول والدروس ثم يجلب آخر درس غير مكتمل.
4. يمكنك أيضًا إدخال Lecture ID يدويًا والضغط على **جلب هذا الدرس**.

البرنامج لا يخزن Cookie في ملف ولا يرسلها إلى أي خدمة خارج QUREO. تُستخدم في الذاكرة لتنفيذ طلبات GET الخاصة بقراءة التقدم ومحتوى الدرس.

## حدود الإرسال

هذا الإصدار يقرأ المحتوى ويجهز الحلول النموذجية محليًا للمراجعة. لا ينفذ طلبات PUT لإرسال إجابات الأسئلة ولا يستدعي endpoint إكمال الدرس أو الاختبار. لا يحتوي على تسجيل دخول بكلمة المرور؛ استخدم جلسة المتصفح محليًا، ولا تضع كلمة المرور أو Cookie أو Access/Refresh Token في GitHub أو المحادثات.

## تشغيل Streamlit

```powershell
pip install -r requirements.txt
Copy-Item .env.example .env
streamlit run app.py
```

تحتاج صفحة المساعد إلى مفتاح OpenAI API محلي في ملف `.env`. لا ترفع هذا الملف إلى GitHub.

## الأمان

- لا تضع كلمة مرور QUREO أو Access Token أو Refresh Token أو Cookies في GitHub أو المحادثات.
- لا ترفع ملف `.env` إلى GitHub.
- أبطِل الجلسات القديمة وغيّر كلمة المرور إذا سبق أن شاركت بيانات دخول أو رموز جلسة.
