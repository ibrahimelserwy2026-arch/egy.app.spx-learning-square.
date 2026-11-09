# QUREO Python Helper

مساعد تعليمي محلي لأسئلة Python، مع صفحة منفصلة لمتابعة تقدم الفصول في QUREO.

## ما يقدمه

- الصق سؤال Python أو ارفع صورة له للحصول على شرح عربي وكود مقترح.
- اختر وضع التلميحات، الحل المشروح، أو مراجعة كودك.
- افتح صفحة **QUREO Progress** من قائمة صفحات Streamlit لمراجعة تقدم الفصول.
- صفحة التقدم تقرأ قائمة الفصول عبر طلب GET فقط، وتعرض رقم آخر Chapter غير مكتمل و `chapter_id`، مع أفضل عدد إجابات صحيحة وDiamonds.

## المتطلبات

- Python 3.10 أو أحدث.
- مفتاح OpenAI API صالح لاستخدام مساعد الحل.
- Cookie جلسة QUREO صالحة لاستخدام صفحة متابعة التقدم.

## التشغيل على Windows

افتحي PowerShell داخل هذا المجلد ونفّذي:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

افتحي ملف `.env` بمحرر نصوص، وضعي مفتاح OpenAI API محليًا. ثم شغّلي:

```powershell
streamlit run app.py
```

## متابعة تقدم QUREO

1. افتحي صفحة **QUREO Progress** من قائمة الصفحات في الشريط الجانبي.
2. سجّلي الدخول إلى QUREO في المتصفح بنفسك.
3. من أدوات المطور، افتحي Network واختاري طلب `/api/study/students/sections/106/chapters`.
4. انسخي قيمة ترويسة الطلب `Cookie` من جهازك والصقيها في حقل Cookie داخل التطبيق.
5. اضغطي **جلب الفصول وتحديد آخر فصل**.

التطبيق يستخدم Cookie محليًا لتنفيذ طلب قراءة الفصول فقط. لا يحفظها في ملف ولا يطبع قيمتها في السجلات، ولا يرسل إجابات أو يغيّر تقدم الحساب. عند انتهاء صلاحية الجلسة، أعيدي تسجيل الدخول وانسخي Cookie جديدة.

## التشغيل على macOS أو Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
streamlit run app.py
```

## الأمان

- لا تضعي كلمة مرور QUREO أو Access Token أو Refresh Token أو Cookies في GitHub أو المحادثات.
- لا ترفعي ملف `.env` إلى GitHub.
- بما أن بيانات جلسة سبق مشاركتها في محادثة، أبطلي الجلسات القديمة/سجّلي الخروج من كل الأجهزة وغيّري كلمة المرور قبل استخدام Cookie جديدة.
- الإجابات المقترحة أدوات للتعلّم؛ راجعيها وجربي فهم الكود قبل استخدامها.
