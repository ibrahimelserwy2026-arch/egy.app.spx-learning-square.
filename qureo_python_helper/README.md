# QUREO Python Helper

مساعد تعليمي محلي لأسئلة Python. يمكنك كتابة السؤال أو رفع صورة له، ثم الحصول على شرح عربي وكود مقترح. لا يتصل التطبيق بحساب QUREO ولا يقرأ ملفات تعريف الارتباط ولا يرسل إجابات إلى المنصة.

## المتطلبات

- Python 3.10 أو أحدث.
- مفتاح OpenAI API صالح.

## التشغيل على Windows

افتحي PowerShell داخل هذا المجلد ونفّذي:

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item .env.example .env
```

افتحي ملف `.env` بمحرر نصوص، وضعي مفتاح OpenAI API مكان `ضع_مفتاحك_هنا`.

ثم شغّلي:

```powershell
streamlit run app.py
```

سيفتح التطبيق في المتصفح. الصقي نص السؤال أو ارفعي صورة واضحة له.

## التشغيل على macOS أو Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

عدّلي ملف `.env` ثم شغّلي:

```bash
streamlit run app.py
```

## الأمان

- لا تضعي كلمة مرور QUREO أو Access Token أو Refresh Token أو Cookies في التطبيق.
- لا ترفعي ملف `.env` إلى GitHub.
- غيّري أي كلمة مرور أو رمز دخول سبق نشره في محادثة أو مكان عام.
- الإجابات المقترحة أدوات للتعلّم؛ راجعيها وجربي فهم الكود قبل استخدامه.
