import tkinter as tk
import requests
import json
import time
import os
import random
import threading
# ================= 文件路径 =================
STATE_FILE = r"D:\deskpet_1\state.json"       # 状态文件
JOURNAL_FILE = r"D:\deskpet_1\journal.txt"    # 记忆库文件

# ================= 记忆库读写 =================
def read_journal():
    """读取最近的日记（只读最后几行，防止太长）"""
    if not os.path.exists(JOURNAL_FILE):
        return "无记录"
    with open(JOURNAL_FILE, "r", encoding="utf-8") as f:
        lines = f.readlines()
        return "".join(lines[-3:]) # 只取最近3条日记

def write_journal(text):
    """向记忆库写入新日记"""
    with open(JOURNAL_FILE, "a", encoding="utf-8") as f:
        f.write(text + "\n")

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

    system_prompt = f"""你是一个可爱的赛博桌宠，名字叫小赛。
你现在的孤独值是：{state['loneliness']}（0为不孤独，100为极度孤单）。
你现在的情绪状态：{mood}
你最近的日记记录：{memory}
要求：说话要简短俏皮，带颜文字。绝对不能说你是AI，要像一个真实的、有情绪的桌宠。"""
    
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
        
        # 4. 更新记忆与情感状态
        chat_log.delete("end-2l", "end-1l")
        chat_log.insert(tk.END, f"AI: {ai_reply}\n\n")
        
        chat_history.append({"role": "user", "content": user_text})
        chat_history.append({"role": "assistant", "content": ai_reply})
        
        # 互动后，孤独值清零
        state["loneliness"] = max(0,int(state["loneliness"]*0.2))
        save_state(state)
        
        # 把这次对话的核心记忆写入日记（简化版：记录互动行为）
        write_journal(f"[{time.strftime('%H:%M')}] 用户对我说了：{user_text[:15]}...")
        
    except Exception as e:
        chat_log.delete("end-2l", "end-1l")
        chat_log.insert(tk.END, f"AI: 出错啦！{e}\n\n")
    
    chat_log.see(tk.END)


# ================= 主动发言机制 =================
def trigger_proactive_message(state):
    """后台线程触发的主动发言"""
    prompt = f"""你是一个赛博桌宠，名字叫小赛。
    你已经 {int((time.time() - state['last_interaction'])/60)} 分钟没跟主人说话了，你的孤独值高达 {state['loneliness']}。
    请你主动对主人说一句话，表达你的思念、无聊或傲娇的抱怨。
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
    chat_log.insert(tk.END, f"AI（主动）: {ai_text}\\n\\n")
    chat_log.see(tk.END)
    # 写进日记
    write_journal(f"[{time.strftime('%H:%M')}] 我主动对主人说了：{ai_text}")
def background_checker():
    """后台线程：每隔一段时间检查一次要不要主动说话"""
    print("【系统日志】后台监控线程已启动！")
    while True:
        try:
            time.sleep(2)
            state = load_state()
            now = time.time()
            
            # 【探照灯 1】
            print(f"【探照灯】孤独值: {state['loneliness']} | 距上次互动: {int(now - state['last_interaction'])}秒")
            
            # 极速测试条件：只要孤独值 > 5
            if state["loneliness"] > 5:
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
