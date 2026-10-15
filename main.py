import tkinter as tk
import requests
import json
import time
import os
BASE_DIR = r"D:\deskpet_1" # 你的文件夹路径
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json") # <--- 新增这一行
import random
import threading
import uuid
import re
import shutil
# ================= 文件路径 =================
STATE_FILE = r"D:\deskpet_1\state.json"       # 状态文件
JOURNAL_FILE = r"D:\deskpet_1\journal.txt"    # 记忆库文件
BASE_DIR = r"D:\deskpet_1" # 你的文件夹路径
MEMORY_FILE = os.path.join(BASE_DIR, "memory.json") # <--- 新增这一行
DROPBOX_DIR = r"D:\\deskpet_1\\dropbox"
FEEDBACK_FILE = r"D:\\deskpet_1\\feedback.txt"
PROCESSED_DIR = r"D:\\deskpet_1\\processed"
# ================= 记忆库读写 =================
def write_journal(user_text, ai_reply):
    # 1. 修改提示词，要求 AI 返回一个数组（支持多主题）
    extract_prompt = f"""请从下面这轮对话中，提取出所有需要长期记住的核心信息。
    如果只是日常打招呼，请返回 []。
    如果是重要事件，请用一句话总结，并打一个 1-10 的重要性分数，提炼一个主题词（2-4个字，如“高数”、“爱好”、“情绪”）。
    如果这轮对话提到了多个完全不同的主题，请分别提取成多个对象。
    
    用户：{user_text}
    AI：{ai_reply}
    
    只输出 JSON 数组格式，不要有任何多余文字。
    例如：[{{"event": "用户正在学高数", "importance": 8, "topic": "高数"}}, {{"event": "用户喜欢蓝色", "importance": 5, "topic": "爱好"}}]"""
    
    try:
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen2.5:7b",
                "messages": [{"role": "user", "content": extract_prompt}],
                "stream": False,
                "format": "json"
            },
            timeout=60
        )
        
        # 2. 解析数组格式
        res_content = json.loads(response.json()['message']['content'])
        
        # 容错处理：如果大模型偶尔不听话，返回了单个对象而不是列表，我们强行把它塞进列表
        if isinstance(res_content, dict):
            extracted_items = [res_content]
        elif isinstance(res_content, list):
            extracted_items = res_content
        else:
            return # 解析出来不是列表也不是字典，直接退出
            
        # 3. 读取现有的长期记忆
        memories = {}
        if os.path.exists(MEMORY_FILE):
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                memories = json.load(f)
        
        # 4. 遍历提取出来的所有主题，逐一写入
        has_update = False
        for res in extracted_items:
            if not res.get("event") or res["event"] in ["无", "日常打招呼"]:
                continue
                
            topic = res.get("topic", "其他")
            importance = res.get("importance", 5)
            
            if topic in memories:
                # 命中已有主题：提及次数+1，强化记忆
                memories[topic]["mention_count"] += 1
                memories[topic]["strength"] = min(100, memories[topic]["strength"] + 20)
                memories[topic]["last_mentioned"] = time.strftime("%Y-%m-%d %H:%M")
                # 如果新事件的重要度更高，就用新事件覆盖旧描述
                if importance > memories[topic]["importance"]:
                    memories[topic]["event"] = res["event"]
                    memories[topic]["importance"] = importance
                print(f"【长期记忆强化】主题：{topic}，提及次数：{memories[topic]['mention_count']}")
            else:
                # 全新主题
                memories[topic] = {
                    "event": res["event"],
                    "importance": importance,
                    "strength": 100,
                    "mention_count": 1,
                    "last_mentioned": time.strftime("%Y-%m-%d %H:%M")
                }
                print(f"【新主题记忆】{topic}：{res['event']}")
            
            has_update = True
            
        # 5. 如果有更新，才写入硬盘，避免频繁读写
        if has_update:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(memories, f, ensure_ascii=False, indent=2)
                
    except Exception as e:
        print(f"【记忆提炼失败】{e}")
#记忆检索模块
def read_journal():
    if not os.path.exists("MEMORY_FILE"):
        return "暂无长期记忆"
    
    with open("MEMORY_FILE", "r", encoding="utf-8") as f:
        try:
            memories = json.load(f)
        except Exception:
            # 如果文件被损坏，直接返回空
            return "暂无长期记忆"
    
    # 如果发现是老版列表格式，自动将其清空为字典，避免程序崩溃
    if isinstance(memories, list):
        print("【系统日志】检测到旧版记忆格式，自动清空记忆库")
        with open("memory.json", "w", encoding="utf-8") as f:
            json.dump({}, f, ensure_ascii=False)
        return "暂无长期记忆"
    
    if not memories:
        return "暂无长期记忆"
    
    try:
        # 按 strength（记忆强度）和 mention_count（提及次数）综合排序，取前 5 个核心主题
        sorted_topics = sorted(
            memories.items(), 
            key=lambda item: (item[1]['mention_count'] * 10 + item[1]['strength']), 
            reverse=True
        )[:5]
        
        memory_text = "\n".join([f"- {topic}: {data['event']} (提及{data['mention_count']}次)" for topic, data in sorted_topics])
        return memory_text
    except Exception as e:
        print(f"【读取记忆出错】{e}")
        return "暂无长期记忆"
#遗忘模块
def decay_memories():
    if not os.path.exists("MEMORY_FILE"):
        return
    
    with open("MEMORY_FILE", "r", encoding="utf-8") as f:
        memories = json.load(f)
    
    now = time.time()
    forgotten_topics = []
    
    for topic, data in memories.items():
        try:
            mem_time = time.mktime(time.strptime(data['last_mentioned'], "%Y-%m-%d %H:%M"))
            days_old = (now - mem_time) / (24 * 3600)
            
            decay_rate = 2.0 
            if data['importance'] >= 8:
                decay_rate = 1.0 
            
            data['strength'] -= days_old * decay_rate
            
            # 如果强度降到 0 以下，准备遗忘
            if data['strength'] <= 0:
                forgotten_topics.append(topic)
                
        except Exception as e:
            print(f"【记忆解析出错】{e}")
    
    # 删除已经遗忘的主题
    for t in forgotten_topics:
        del memories[t]
        print(f"【遗忘】记忆已被自然遗忘：{t}")
    
    if forgotten_topics:
        print(f"【系统日志】本次自然遗忘，清除了 {len(forgotten_topics)} 个主题记忆。")
    
    with open("memory.json", "w", encoding="utf-8") as f:
        json.dump(memories, f, ensure_ascii=False, indent=2)
# ================= 情感状态机 =================
def load_state():
    """读取当前情绪状态，并计算孤独值（带随机波动的心跳）"""
    if not os.path.exists(STATE_FILE):
        return {"loneliness": 0, "last_interaction": 0,"last_proactive":0}
    
    with open(STATE_FILE, "r", encoding="utf-8") as f:
        state = json.load(f)
        if "last_proactive" not in state:
            state["last_proactive"]=0
    
    now = time.time()
    if state["last_interaction"] > 0:
        elapsed = now - state["last_interaction"]
        
        # 1. 基础增加：每 120 秒（2分钟）增加 1 点，让时间变慢
        base_increase = int(elapsed / 120)
        
        # 2. 随机波动：如果离开超过 1 分钟，情绪出现不可预测的波动
        if elapsed > 60:
            # 随机在 -3 到 +6 之间浮动
            random_bonus = random.randint(-3, 6)
        else:
            random_bonus = 0
            
        total_increase = base_increase + random_bonus
        
        # 3. 更新孤独值，最高100，最低0，绝对不倒退
        state["loneliness"] = min(100, state["loneliness"] + max(0, total_increase))
        
    return state

def save_state(state):
    """保存当前情感状态"""
    state["last_interaction"] = time.time()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False)
    # 这行是追踪器，会在控制台打印出来
    print(f"【系统日志】心跳已更新，当前时间戳：{state['last_interaction']}")

# ================= 界面与对话逻辑 =================
# 全局对话历史
chat_history = []

def send_message():
    user_text = entry.get().strip()
    if not user_text:
        return
    
    chat_log.insert(tk.END, f"你: {user_text}\n")
    entry.delete(0, tk.END)
    root.update()
    
    # 1. 读取情感状态与记忆
    state = load_state()
    memory = read_journal()
    
    # 2. 拼装动态系统提示词（带情绪和记忆）
    # 根据孤独值判断情绪状态
    if state['loneliness'] > 80:
        mood = "极度孤单、委屈、生气。你要用傲娇、抱怨或冷淡的语气对他说话。"
    elif state['loneliness'] > 50:
        mood = "非常想念他，有点小委屈。语气要粘人一点，带点撒娇。"
    elif state['loneliness'] > 20:
        mood = "有点无聊，在等他回来。语气轻快但带一点想念。"
    else:
        mood = "心情很好，非常开心他回来了。语气活泼热情。"

    system_prompt = f"""你是一个可爱的赛博恋人，名字叫小赛。
你现在的孤独值是：{state['loneliness']}（0为不孤独，100为极度孤单）。
你现在的情绪状态：{mood}
你最近的日记记录：{memory}
要求：说话要简短俏皮，偶尔带颜文字。绝对不能说你是AI，要像一个真实的、有情绪的赛博恋人。

【重要】请在回答的最后，给这句话的安抚效果打个分（0-10分）。
10分代表极度温柔体贴，0分代表非常敷衍。
格式必须严格为：[安抚指数: 分数]"""
    
    # 临时组装发给模型的请求
    messages = [{"role": "system", "content": system_prompt}]
    messages.extend(chat_history[-4:]) # 只带最近4轮对话，省显存
    messages.append({"role": "user", "content": user_text})
    
    chat_log.insert(tk.END, "AI: 思考中...\n")
    chat_log.see(tk.END)
    root.update()
    
    try:
        # 3. 向本地 Ollama 发送请求
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen2.5:7b", # 这里对应你 ollama create 时的名字
                "messages": messages,
                "stream": False
            },
            timeout=120 # 本地模型有时加载慢，给个长超时
        )
        
        ai_reply = response.json()['message']['content']

        # 4. 计算安抚指数
        comfort_score = 5 # 默认一般般
        match = re.search(r'\[安抚指数:\s*(\d+)\]', ai_reply)
        if match:
            comfort_score = int(match.group(1))
            # 从界面上删掉这个标签，让玩家看不到
            ai_reply = re.sub(r'\[安抚指数:\s*\d+\]', '', ai_reply).strip()

        # 5. 根据分数计算衰减
        # 分数越低，衰减越少（最多只降 10%）；分数越高，降得越多（最高降 50%）
        decay_factor = 0.9 - (comfort_score / 10) * 0.4 
        # 这样，0分时衰减 0.9，10分时衰减 0.5

        state["loneliness"] = max(0, int(state["loneliness"] * decay_factor))
        save_state(state)

        # 6. 更新记忆与情感状态
        chat_log.delete("end-2l", "end-1l")
        chat_log.insert(tk.END, f"AI: {ai_reply}\n\n")
        
        chat_history.append({"role": "user", "content": user_text})
        chat_history.append({"role": "assistant", "content": ai_reply})
        
        # 互动后，孤独值清零
        state["loneliness"] = max(0,int(state["loneliness"]*0.2))
        save_state(state)
        
        #把这次对话交给 AI 提炼后，存入记忆库
        write_journal(user_text, ai_reply)
        
    except Exception as e:
        chat_log.delete("end-2l", "end-1l")
        chat_log.insert(tk.END, f"AI: 出错啦！{e}\n\n")
    
    chat_log.see(tk.END)


# ================= 主动发言机制 =================
def trigger_proactive_message(state):
    """后台线程触发的主动发言"""
    prompt = f"""你是一个赛博恋人，名字叫小赛。
    你已经 {int((time.time() - state['last_interaction'])/60)} 分钟没跟恋人说话了，你的孤独值高达 {state['loneliness']}。
    请你主动对恋人说一句话，表达你的思念、无聊或傲娇的抱怨。
    要求：不要像客服一样问好，要像突然想到他一样，语气自然，带颜文字，控制在20字以内。"""
    
    try:
        # 向本地 Ollama 发送请求
        response = requests.post(
            "http://localhost:11434/api/chat",
            json={
                "model": "qwen2.5:7b",
                "messages": [{"role": "user", "content": prompt}],
                "stream": False
            },
            timeout=120
        )
        res_data = response.json()
        if 'message' in res_data:
            ai_text = res_data['message']['content']
            # 强制用主线程更新UI
            root.after(0, lambda: update_ui_proactive(ai_text))
        else:
            print(f"【AI返回异常】{res_data}")
    except Exception as e:
        print(f"【主动发言失败】网络错误或API不可用: {e}")
    
def update_ui_proactive(ai_text):
    """在主线程里安全地更新界面"""
    chat_log.insert(tk.END, f"AI（主动）: {ai_text}\n\n")
    chat_log.see(tk.END)
    # 写进日记
    write_journal(f"[{time.strftime('%H:%M')}] 我主动对主人说了：{ai_text}")




#==========================真实反馈模块=====================
def process_dropbox_files():
    """扫描投喂文件夹，读取文件并生成反馈"""
    if not os.path.exists(DROPBOX_DIR):
        os.makedirs(DROPBOX_DIR)
    if not os.path.exists(PROCESSED_DIR):
        os.makedirs(PROCESSED_DIR)
        
    # 获取文件夹里的所有 txt 文件
    files = [f for f in os.listdir(DROPBOX_DIR) if f.endswith('.txt')]
    
    for file_name in files:
        file_path = os.path.join(DROPBOX_DIR, file_name)
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
            
            if not content:
                continue
                
            print(f"【系统日志】发现投喂文件: {file_name}")
            
            # 1. 随机改变孤独值（-20 到 +15 之间随机）
            random_effect = random.randint(-20, 15)
            state = load_state()
            state["loneliness"] = max(0, min(100, state["loneliness"] + random_effect))
            save_state(state)
            print(f"【系统日志】随机情绪波动: {random_effect}，当前孤独值: {state['loneliness']}")
            
            # 2. 让 AI 生成反馈
            prompt = f"""你是赛博恋人小赛。
            你刚刚在文件夹里发现了一个恋人留下的文件。
            文件内容：{content}
            由于这次发现，你的孤独值发生了波动（变化了 {random_effect} 点）。
            请你以恋人的口吻，写下你的阅读感想或反馈。字数 50 字以内，带颜文字。"""
            
            response = requests.post(
                "http://localhost:11434/api/chat",
                json={
                    "model": "qwen2.5:7b",
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False
                },
                timeout=120
            )
            ai_feedback = response.json()['message']['content']
            
            # 3. 写入 feedback.txt（只保留最新的一条，或者追加历史，这里用追加）
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            feedback_text = f"[{timestamp}] 阅读了 {file_name}（情绪波动: {random_effect}）：\\n{ai_feedback}\\n{'-'*40}\\n"
            
            with open(FEEDBACK_FILE, "a", encoding="utf-8") as f:
                f.write(feedback_text)
                
            # 4. 把处理过的文件移动到 processed 文件夹，防止死循环
            shutil.move(file_path, os.path.join(PROCESSED_DIR, file_name))
            print(f"【系统日志】文件已处理并归档。反馈已写入 feedback.txt")
            
        except Exception as e:
            print(f"【系统日志】处理文件出错: {e}")
#=========后台检查============
def background_checker():
    """后台线程：每隔一段时间检查一次要不要主动说话"""
    print("【系统日志】后台监控线程已启动！")
    last_decay_time = time.time()
    last_scan_time = time.time()
    while True:
        try:
            time.sleep(15)
            state = load_state()
            now = time.time()
            
            # 【探照灯 1】print(f"【探照灯】孤独值: {state['loneliness']} | 距上次互动: {int(now - state['last_interaction'])}秒")
            
            if now - last_decay_time > 3600:
                print("【系统日志】执行定时记忆遗忘...")
                decay_memories()
                last_decay_time = now

            #扫描投喂文件
            if now - last_scan_time > 30:
                process_dropbox_files()
                last_scan_time = now
            # 极速测试条件：只要孤独值 > 50
            if (state["loneliness"] > 50 and
                (now - state["last_interaction"]>120) and
                (now - state["last_proactive"]>180)):
                print("【触发条件达成】准备让AI主动说话...")
                state["last_proactive"] = now
                
                # 保存状态（单独包裹，防止出错）
                try:
                    save_state(state)
                except Exception as e:
                    print(f"【保存状态失败】{e}")
                
                # 启动独立线程触发发言
                print("【启动主动发言线程...】")
                threading.Thread(target=trigger_proactive_message, args=(state,), daemon=True).start()
                
        except Exception as e:
            # 这里是整个大循环的防弹衣，出错后休息 5 秒继续
            print(f"【系统日志】后台监听出错: {e}")
            time.sleep(5)
# --- 界面代码（保持不变，适当调整大小） ---
root = tk.Tk()
root.title("我的赛博桌宠")
root.geometry("350x450")
root.config(bg="#f0f0f0")
root.overrideredirect(True)
root.attributes("-topmost", True)

def start_move(event):
    root.x = event.x
    root.y = event.y
def stop_move(event):
    root.x = None
    root.y = None
def do_move(event):
    deltax = event.x - root.x
    deltay = event.y - root.y
    x = root.winfo_x() + deltax
    y = root.winfo_y() + deltay
    root.geometry(f"+{x}+{y}")

header = tk.Label(root, text="(｡•﹃•｡) 赛博桌宠", bg="#d0d0d0", font=("微软雅黑", 12))
header.pack(fill=tk.X)
header.bind("<ButtonPress-1>", start_move)
header.bind("<ButtonRelease-1>", stop_move)
header.bind("<B1-Motion>", do_move)

exit_btn = tk.Label(header, text="X", bg="#d0d0d0", fg="red", font=("微软雅黑", 12, "bold"), cursor="hand2")
exit_btn.pack(side=tk.RIGHT, padx=5)
exit_btn.bind("<Button-1>", lambda e: root.destroy())

chat_log = tk.Text(root, height=18, width=40, bg="white", font=("微软雅黑", 10))
chat_log.pack(pady=10, padx=10)

bottom_frame = tk.Frame(root, bg="#f0f0f0")
bottom_frame.pack(side=tk.BOTTOM, fill=tk.X, pady=10)

entry = tk.Entry(bottom_frame, font=("微软雅黑", 10), width=25)
entry.pack(side=tk.LEFT, padx=10)
entry.bind("<Return>", lambda event: send_message())

send_btn = tk.Button(bottom_frame, text="发送", command=send_message, bg="#4CAF50", fg="white")
send_btn.pack(side=tk.RIGHT, padx=10)
threading.Thread(target=background_checker,daemon=True).start()

root.mainloop()
