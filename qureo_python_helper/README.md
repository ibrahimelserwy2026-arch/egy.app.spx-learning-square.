# QUREO Python Helper

مساعد تعليمي محلي لأسئلة Python، مع صفحة لمتابعة تقدم الفصول في QUREO وبرنامج Kivy مستقل على نمط `start_learn.py`.

## ما يقدمه

- الصق سؤال Python أو ارفع صورة له للحصول على شرح عربي وكود مقترح من مساعد OpenAI.
- صفحة **QUREO Progress** في Streamlit لمراجعة تقدم الفصول والدروس.
- قارئ محتوى الدرس يعرض Talk IDs وأنواع الأسئلة الثلاثة.
- البرنامج المستقل `start_qureo.py` يفحص آخر Chapter وLecture غير مكتملين، ثم يجلب الدرس تلقائيًا.
- أسئلة الكتابة وإكمال الكود تستخدم `model_answer` و`placeholders` الموجودة في استجابة QUREO عندما تكون متاحة.
- أسئلة الاختيار، والأسئلة التي لا تحتوي على إجابة نموذجية، يمكن أن تحصل على اقتراح حل من OpenAI عند إدخال API Key محليًا في البرنامج.

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
3. أدخل OpenAI API Key إذا أردت اقتراح إجابات للأسئلة التي لا تحتوي على `model_answer`؛ المفتاح اختياري إذا كانت الإجابات النموذجية موجودة في رد الدرس.
4. اضغط **فحص التقدم وحل آخر درس**؛ سيقرأ البرنامج الفصول والدروس ثم يجلب آخر درس غير مكتمل ويجهز الحلول المقترحة.
5. يمكنك أيضًا إدخال Lecture ID يدويًا والضغط على **حل هذا الدرس**.

البرنامج لا يخزن Cookie أو مفتاح OpenAI في ملف. تُستخدم Cookie في الذاكرة لطلبات GET إلى QUREO فقط. عند طلب اقتراح من OpenAI، يُرسل نص السؤال والكود والاختيارات فقط؛ لا تُرسل Cookie أو بيانات الجلسة إلى OpenAI.

## إرسال إجابات QUREO

بعد تحميل الدرس، يعرض البرنامج بطاقة مستقلة لكل سؤال يمكن تجهيز إجابته:

- **كتابة كود (\`try\`)**: يستخدم \`model_answer\` من بيانات الدرس، أو اقتراحًا من OpenAI إذا لم توجد إجابة نموذجية.
- **إكمال أجزاء (\`try_partial\`)**: يملأ قائمة \`answers\` من \`model_answer\` لكل \`fitbBlock\`/placeholder.
- **اختيار من متعدد (\`choice_question\`)**: يستخدم علامة الإجابة الصحيحة إن كانت موجودة في البيانات، أو يحاول تحديدها من التغذية الراجعة الإيجابية في \`after_talks\`، أو يقترح قيمة باستخدام OpenAI عند تفعيل المفتاح. إذا لم تتوفر إجابة مؤكدة، اترك القيمة فارغة أو اخترها بنفسك.

يمكن إرسال السؤال منفردًا من زر البطاقة، أو إرسال كل الإجابات المكتملة من زر **إرسال كل إجابات الدرس المجهزة**. راجع الحقول قبل الضغط؛ الطلبات تستخدم \`PUT /api/study/students/lecture-talks/{talk_id}\` وبنية \`value.try\` أو \`value.try_partial\` أو \`value.choice_question\` حسب نوع السؤال. يعرض البرنامج HTTP status ورد QUREO بعد الإرسال.

لا يستدعي البرنامج تلقائيًا endpoint إكمال الدرس \`/api/study/students/lectures/{lecture_id}/complete\`. ولا يحتوي على تسجيل دخول بكلمة المرور؛ استخدم جلسة المتصفح محليًا، ولا تضع كلمة المرور أو Cookie أو Access/Refresh Token في GitHub أو المحادثات.

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
