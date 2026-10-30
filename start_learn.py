
from kivy.app import App
from kivy.metrics import dp, sp
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.label import Label
import requests
import json
import time


def process_review(item_id, cookies_dict):
    """
    الدالة الخاصة بالـ Reviews لإرسال طلب الـ GET وتغيير الـ ID في الرابط ديناميكياً
    """
    # تغيير الـ ID داخل الرابط بناءً على المتغير الممرر للدالة (مثال: 55)
    url = f"https://egy.app.spx-learning-square.com/api/v1/reviews/{item_id}/complete"
    
    headers = {
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Not:A-Brand";v="8", "Chromium";v="156", "Google Chrome";v="156"',
        "Sec-Ch-Ua-Mobile": "?0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://egy.app.spx-learning-square.com/subjects/7/curriculum",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Priority": "u=1, i"
    }
    
    try:
        # إرسال طلب الـ POST مع تمرير الكوكيز والعناوين
        response = requests.post(url, headers=headers, cookies=cookies_dict)
        # إرجاع نص الرد البرمجي لمعالجته أو استخراج الـ IDs منه لاحقاً
        return response.text
        
    except Exception as e:
        return None

def extract_only_correct_ids(result_response_text):
    """
    تدخل مباشرة على حقل options وتستخرج لستة تحتوي على الـ IDs الصحيحة فقط
    """
    # فصل الترويسات وتأمين النص المقطوع
    if "{" in result_response_text:
        json_data_str = result_response_text[result_response_text.find("{"):]
    else:
        json_data_str = result_response_text
        
    json_data_str = json_data_str.strip()
    
    # إغلاق تلقائي للأقواس المفتوحة بسبب قطع النص
    if not json_data_str.endswith("]}") and not json_data_str.endswith("}}"):
        if json_data_str.count("[") > json_data_str.count("]"): json_data_str += "]}"
        if json_data_str.count("{") > json_data_str.count("}"): json_data_str += "}"

    try:
        data = json.loads(json_data_str)
    except json.JSONDecodeError:
        if not json_data_str.endswith("]}}"): json_data_str += "]}}"
        data = json.loads(json_data_str)

    inner_data = data.get("data", {})
    options_pool = inner_data.get("options", {})

    # قائمة لحفظ الـ IDs الصحيحة فقط
    correct_ids_only = []

    # الدوران داخل الأسئلة والخيارات
    for q_id, options_list in options_pool.items():
        if isinstance(options_list, list):
            for option in options_list:
                # أخذ الـ id فقط إذا كان هو الخيار الصحيح
                if option.get("is_correct") is True:
                    correct_ids_only.append(option.get("id"))
                    break 

    return correct_ids_only

def process_test_perfect_score(item_id, cookies_dict):

    start_url = f"https://egy.app.spx-learning-square.com/api/v1/tests/{item_id}/start"
    submit_url = f"https://egy.app.spx-learning-square.com/api/v1/tests/{item_id}/submit"
    history_url = f"https://egy.app.spx-learning-square.com/api/v1/tests/{item_id}/history"

    headers = {
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Not:A-Brand";v="8", "Chromium";v="156", "Google Chrome";v="156"',
        "Sec-Ch-Ua-Mobile": "?0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://egy.app.spx-learning-square.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://egy.app.spx-learning-square.com/subjects/7/curriculum",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Priority": "u=1, i"
    }

    try:
        # ------------------------------------------------------------
        # الخطوة 1: بدء الامتحان (المحاولة الأولى)
        # ------------------------------------------------------------
        requests.post(start_url, json={}, headers=headers, cookies=cookies_dict)
        time.sleep(0.5)
        
        # ------------------------------------------------------------
        # الخطوة 2: تسليم الامتحان فوراً (تسجيل الإجابات خطأ)
        # ------------------------------------------------------------
        requests.post(submit_url, json={}, headers=headers, cookies=cookies_dict)
        time.sleep(0.5)

        # ------------------------------------------------------------
        # الخطوة 3: جلب الـ history ثم الـ result لاستخراج الإجابات الصحيحة
        # ------------------------------------------------------------
        history_headers = headers.copy()
        history_headers.pop("Content-Type", None) # طلب الـ GET لا يحتاج Content-Type
        
        history_resp = requests.get(history_url, headers=history_headers, cookies=cookies_dict)
        history_data = history_resp.json()
        
        if not history_data.get("data") or len(history_data["data"]) == 0:
            print(f"[-] لم يتم العثور على سجل محاولات للاختبار {item_id}")
            return
            
        # استخراج الـ id الخاص بالمحاولة المكتملة الأولى
        response_id = history_data["data"][0]["id"]
        result_url = f"https://egy.app.spx-learning-square.com/api/v1/tests/{item_id}/result?response_id={response_id}"
        result_resp = requests.get(result_url, headers=history_headers, cookies=cookies_dict)
        
        # خريطة الإجابات الصحيحة لربط رقم السؤال بالخيار الصحيح
        correct_answers_map = extract_only_correct_ids(result_resp.text)

        time.sleep(0.5)
        start_resp = requests.post(start_url, json={}, headers=headers, cookies=cookies_dict)
        start_data = start_resp.json()
        current_questions = start_data.get("data", {}).get("question_responses", [])
        n = 0
        # ------------------------------------------------------------
        # الخطوة 5: إرسال الإجابات الصحيحة (عبر طلب الـ PUT)
        # ------------------------------------------------------------
        for question in current_questions:
            test_q_id = question.get("test_question_id") # رقم السؤال الحالي من الـ start الجديد
            # مطابقة رقم السؤال مع الخيار الصح اللي جبناه من الـ Result
            correct_option = correct_answers_map[n]
            n = n + 1

            if correct_option:
                answer_put_url = f"https://egy.app.spx-learning-square.com/api/v1/tests/{item_id}/questions/{test_q_id}/answer"
                payload = {
                    "selected_option_id": correct_option
                }
                # إرسال طلب الـ PUT للإجابة على السؤال الحالي
                ans_resp = requests.put(answer_put_url, json=payload, headers=headers, cookies=cookies_dict)
                time.sleep(0.5)
            else:
                print(f"  [-] تخطي: السؤال {test_q_id} لم يتم العثور على خياره الصحيح.")

        # ------------------------------------------------------------
        # الخطوة 6: التسليم النهائي (Submit)
        # ------------------------------------------------------------
        final_submit = requests.post(submit_url, json={}, headers=headers, cookies=cookies_dict)
        print(f"[🎉] مبروك! تم إنهاء وتقفيل الاختبار {item_id} بنجاح تـام!")

    except Exception as e:
        print(f"[-] حدث خطأ أثناء تنفيذ تتابع الحل الذكي للاختبار: {e}")


def submit_chapter_answers_smart(chapter_id, block_options_map, cookies_dict):

    url = f"https://egy.app.spx-learning-square.com/api/v1/chapters/{chapter_id}/answer"
    url2 = f"https://egy.app.spx-learning-square.com/api/v1/chapters/{chapter_id}/complete"  
    headers = {
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Not:A-Brand";v="8", "Chromium";v="156", "Google Chrome";v="156"',
        "Sec-Ch-Ua-Mobile": "?0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://egy.app.spx-learning-square.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://egy.app.spx-learning-square.com",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Priority": "u=1, i"
    }

    for block_id, options_list in block_options_map.items():
        if not options_list:
            print(f"[تخطي] البلوك {block_id} لا يحتوي على خيارات للتجربة.")
            continue
            
        print(f"\n[بداية] جاري تجربة خيارات السؤال (Block ID: {block_id})...")
        
        for selected_option in options_list:
            payload = {
                "block_id": block_id,
                "selected_option_id": selected_option,
                "hint_used": 0
            }
            
            try:
                response = requests.post(url, json=payload, headers=headers, cookies=cookies_dict)
                
                
                response_data = response.json()
                
                
                is_correct = response_data.get("data", {}).get("is_correct", False)
                
                if is_correct:
                    print(f"  [صح] الخيار {selected_option} صحيح! ننتقل للسؤال التالي.")
                    time.sleep(0.1) 
                    break 
                else:
                    print(f"  [خطأ] الخيار {selected_option} غير صحيح. جاري تجربة الخيار التالي...")
                    
                
                time.sleep(0.1)
                
            except Exception as e:
                print(f"  [خطأ في الطلب] للبلوك {block_id} مع الخيار {selected_option}: {e}")
                time.sleep(0.1)
    requests.post(url2, json={}, headers=headers, cookies=cookies_dict)

def scan_and_process_items(parsed_items, cookies_dict):
    for key, item_id in parsed_items.items():

        if key.startswith("chapter"):
            process_chapter(item_id, cookies_dict)
        elif key.startswith("test"):
            process_test_perfect_score(item_id, cookies_dict)
        elif key.startswith("review"):
            process_review(item_id, cookies_dict)

def login_and_get_cookies(id , password):
    url = "https://egy.app.spx-learning-square.com/api/v1/auth/login"
    
    headers = {
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Not:A-Brand";v="8", "Chromium";v="156", "Google Chrome";v="156"',
        "Sec-Ch-Ua-Mobile": "?0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json",
        "Origin": "https://spx-learning-square.com",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://spx-learning-square.com/login",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Priority": "u=1, i"
    }
    
    payload = {
        "login_id": id,
        "password": password
    }
    
    session = requests.Session()
    response = session.post(url, json=payload, headers=headers)
    
    return session.cookies.get_dict()


def get_curriculum_text(cookies_dict):
    url = "https://egy.app.spx-learning-square.com/api/v1/subjects/7/curriculum"
    
    headers = {
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Not:A-Brand";v="8", "Chromium";v="156", "Google Chrome";v="156"',
        "Sec-Ch-Ua-Mobile": "?0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://spx-learning-square.com/subjects/7/curriculum",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Priority": "u=1, i"
    }
    
    response = requests.get(url, headers=headers, cookies=cookies_dict)
    
    return response.text

def parse_curriculum_items(response_text):
    
    if "{" in response_text:
        json_start_index = response_text.find("{")
        json_data_str = response_text[json_start_index:]
    else:
        json_data_str = response_text

    
    try:
        data = json.loads(json_data_str)
    except json.JSONDecodeError:
        
        if not json_data_str.strip().endswith("]}]}"):
            json_data_str = json_data_str.strip()
            
            if not json_data_str.endswith("]"): json_data_str += "]}"
            if not json_data_str.endswith("}"): json_data_str += "}"
        data = json.loads(json_data_str)

    result_dict = {}
    
    
    counters = {
        "chapter": 0,
        "review": 0,
        "test": 0
    }

    if "data" in data:
        for unit in data["data"]:
            if "items" in unit:
                for item in unit["items"]:
                    item_type = item.get("item_type")
                    item_id = item.get("id")
                    
                    
                    if item_type in counters:
                        counters[item_type] += 1 
                        key_name = f"{item_type}{counters[item_type]}" 
                        result_dict[key_name] = item_id 
    return result_dict

def extract_block_options_map(response_text):
   
    if "{" in response_text:
        json_start_index = response_text.find("{")
        json_data_str = response_text[json_start_index:]
    else:
        json_data_str = response_text

   
    json_data_str = json_data_str.strip()
    if not json_data_str.endswith("]}") and not json_data_str.endswith("]}]}"):
        if json_data_str.count("[") > json_data_str.count("]"):
            json_data_str += "]}"
        if json_data_str.count("{") > json_data_str.count("}"):
            json_data_str += "}"

    try:
        data = json.loads(json_data_str)
    except json.JSONDecodeError as e:
        print(f"فشل فك الـ JSON التلقائي للنص المقطوع: {e}")
        return {}

    options_map = {}

    if "data" in data and "blocks" in data["data"]:
        for block in data["data"]["blocks"]:
            block_id = block.get("id")
            
            if "options" in block and isinstance(block["options"], list):
                opt_ids = [opt["id"] for opt in block["options"] if "id" in opt]
                if opt_ids:
                    options_map[block_id] = opt_ids
                    
            elif "questions" in block and isinstance(block["questions"], list):
                for question in block["questions"]:
                    if "options" in question and isinstance(question["options"], list):
                        opt_ids = [opt["id"] for opt in question["options"] if "id" in opt]
                        if opt_ids:
                            options_map[block_id] = opt_ids

    return options_map

def process_chapter(item_id, cookies_dict):
    """الدالة الخاصة بالـ chapters لإرسال طلب الـ GET وتغيير الـ ID في الرابط ديناميكياً"""
    
    url = f"https://egy.app.spx-learning-square.com/api/v1/chapters/{item_id}/blocks"
    
    headers = {
        "Sec-Ch-Ua-Platform": '"Windows"',
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
        "Sec-Ch-Ua": '"Not:A-Brand";v="8", "Chromium";v="156", "Google Chrome";v="156"',
        "Sec-Ch-Ua-Mobile": "?0",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Sec-Fetch-Site": "same-origin",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Dest": "empty",
        "Referer": "https://egy.app.spx-learning-square.com/subjects/7/curriculum",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept-Language": "en-US,en;q=0.9",
        "Priority": "u=1, i"
    }
    
    try:
        response = requests.get(url, headers=headers, cookies=cookies_dict)
        options_map = extract_block_options_map(response.text)
        submit_chapter_answers_smart(item_id, options_map, cookies_dict)
             
    except Exception as e:
        print(f"خطأ أثناء معالجة الـ Chapter {item_id}: {e}")
        return None

def main(id, password):
    cookies_dict = login_and_get_cookies(id, password)
    curriculum_text = get_curriculum_text(cookies_dict)
    parsed_items = parse_curriculum_items(curriculum_text)
    scan_and_process_items(parsed_items, cookies_dict)

def my_function(user, password):
    main(user, password)


class MyApp(App):

    def build(self):
        layout = BoxLayout(
            orientation="vertical",
            padding=dp(25),
            spacing=dp(15)
        )

        # خانة اسم المستخدم
        self.user_input = TextInput(
            hint_text="Enter Username",
            multiline=False,
            font_size=sp(18),
            size_hint_y=None,
            height=dp(55)
        )

        # خانة كلمة المرور
        self.password_input = TextInput(
            hint_text="Enter Password",
            password=True,
            multiline=False,
            font_size=sp(18),
            size_hint_y=None,
            height=dp(55)
        )

        # زر تنفيذ الدالة
        button = Button(
            text="Login",
            font_size=sp(20),
            size_hint_y=None,
            height=dp(55)
        )

        # مكان عرض النتيجة
        self.result = Label(
            text="",
            font_size=sp(16)
        )

        # ربط الزر بالدالة
        button.bind(on_release=self.on_button_click)

        layout.add_widget(self.user_input)
        layout.add_widget(self.password_input)
        layout.add_widget(button)
        layout.add_widget(self.result)

        return layout

    # يتم تنفيذها عند الضغط على الزر
    def on_button_click(self, instance):

        user = self.user_input.text
        password = self.password_input.text

        # إرسال القيم إلى الدالة المطلوبة
        result = my_function(user, password)


if __name__ == "__main__":
    MyApp().run()
