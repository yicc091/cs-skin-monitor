from flask import Flask, request, session, redirect, url_for, render_template_string
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Boolean
from sqlalchemy.orm import sessionmaker, relationship, declarative_base
from curl_cffi import requests
import time
import random
import smtplib
from email.mime.text import MIMEText
from email.header import Header
import threading
import sqlite3

app = Flask(__name__, static_folder='static')
app.secret_key = 'your_secret_key_here' # 开源展示占位符

# ================= 1. 数据库模型 =================
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True)
    youpin_token = Column(String)
    receive_email = Column(String)
    is_monitoring = Column(Boolean, default=False) 
    tasks = relationship("Task", back_populates="owner")
    feedbacks = relationship("Feedback", back_populates="user")

class Task(Base):
    __tablename__ = 'tasks'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    item_name = Column(String)
    template_id = Column(String)
    target_price = Column(Float)
    cooldown_seconds = Column(Integer, default=3600)
    last_alert_at = Column(Float, default=0.0)
    owner = relationship("User", back_populates="tasks")

class Feedback(Base):
    __tablename__ = 'feedbacks'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey('users.id'))
    content = Column(String)
    submit_time = Column(Float, default=time.time)
    user = relationship("User", back_populates="feedbacks")

engine = create_engine('sqlite:///monitor_multi_user.db', connect_args={'check_same_thread': False})
Base.metadata.create_all(engine)

try:
    conn = sqlite3.connect('monitor_multi_user.db')
    conn.execute('ALTER TABLE users ADD COLUMN is_monitoring BOOLEAN DEFAULT 0')
    conn.commit()
    conn.close()
except Exception:
    pass 

Session = sessionmaker(bind=engine)

# ================= 2. 核心网络请求与发信 =================
SMTP_HOST = "smtp.qq.com"
SMTP_PORT = 465
SENDER_EMAIL = "YOUR_EMAIL@qq.com"  # 开源展示占位符
SENDER_PASS = "YOUR_AUTH_CODE"      # 开源展示占位符
def get_search_headers(token):
    return {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/147.0.0.0 Safari/537.36 Edg/147.0.0.0",
        "Content-Type": "application/json",
        "app-version": "5.26.0",
        "apptype": "1",
        "platform": "pc",
        "secret-v": "h5_v1",
        "authorization": token,
        "deviceid": "6e3bf57b-4d11-4da6-b7a3-516bb9517da5",
        "deviceuk": "5HtJJkrC4pFxxA1rR7p9jGjxhNKUrG39BRVW2yVdacOrFxpzJCMPHHPr6J98hq91J",
        "uk": "5FTRVBWitDiSUV4sutiRamDXx8UxQhOb56mCwHHgB7beWiUIA0jLsXywTCjWcjl1N"
    }

def send_email(to_email, item_name, price, target):
    subject = f"🚨 降价预警：{item_name}"
    content = f"监控中的 {item_name} 当前底价 {price}，已低于目标 {target}。"
    msg = MIMEText(content, 'plain', 'utf-8')
    msg['From'] = SENDER_EMAIL
    msg['To'] = to_email
    msg['Subject'] = Header(subject, 'utf-8')
    try:
        server = smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT)
        server.login(SENDER_EMAIL, SENDER_PASS)
        server.sendmail(SENDER_EMAIL, [to_email], msg.as_string())
        server.quit()
        return True
    except:
        return False

def fetch_price(t_id, token):
    url = "https://api.youpin898.com/api/homepage/pc/goods/market/queryOnSaleCommodityList"
    payload = {"gameId": "730", "templateId": str(t_id), "pageIndex": 1, "pageSize": 5, "listSortType": 1, "sortType": 0}
    try:
        res = requests.post(url, headers=get_search_headers(token), json=payload, impersonate="chrome110", timeout=10)
        data = res.json()
        if "Data" in data and len(data["Data"]) > 0:
            item = data["Data"][0]
            return item["commodityName"], float(item["price"])
    except:
        return None, None

# ================= 3. 后台引擎 =================
engine_running = False
monitor_thread = None

def run_monitor_background():
    global engine_running
    print("\n🚀 [全局引擎] 已启动驻留！")
    while engine_running:
        db_session = Session()
        try:
            tasks = db_session.query(Task).all()
            for task in tasks:
                if not engine_running: break
                
                if not getattr(task.owner, 'is_monitoring', False):
                    continue
                
                name, current = fetch_price(task.template_id, task.owner.youpin_token)
                now_ts = time.time()
                if current is not None:
                    remaining = int(task.last_alert_at + task.cooldown_seconds - now_ts)
                    status = "✅ 就绪" if remaining <= 0 else f"⏳ 冷却中({remaining}s)"
                    print(f"[{time.strftime('%H:%M:%S')}] {task.owner.username} | {name[:12]}.. | 现价: {current} | 状态: {status}")
                    if current <= task.target_price:
                        if now_ts - task.last_alert_at >= task.cooldown_seconds:
                            if send_email(task.owner.receive_email, name, current, task.target_price):
                                task.last_alert_at = now_ts
                                db_session.commit()
                time.sleep(random.randint(4, 7))
        except Exception as e:
            print(f"引擎异常: {e}")
        finally:
            db_session.close()
            
        if engine_running:
            time.sleep(random.randint(30, 60))

# ================= 4. UI 模板系统 =================

HTML_HEAD = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CS 监控中心</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        body { font-family: 'Inter', sans-serif; overflow-x: hidden; color: #fafafa; }
        .shader-bg { position: fixed; inset: 0; z-index: -10; background: linear-gradient(135deg, #1275d8 0%, #2563eb 30%, #e19136 100%); transform: translateZ(0); }
        .reveal { opacity: 0; transform: translateY(30px); transition: all 0.6s cubic-bezier(0.25, 0.8, 0.25, 1); will-change: transform, opacity; }
        .reveal.visible { opacity: 1; transform: translateY(0); }
        input, textarea { background: transparent !important; border: none; border-bottom: 1px solid rgba(250,250,250,0.3) !important; color: #fafafa !important; border-radius: 0 !important; }
        input:focus, textarea:focus { outline: none !important; border-bottom: 1px solid #fafafa !important; box-shadow: none !important; }
        .magnetic-btn { transition: transform 0.2s cubic-bezier(0.25, 1, 0.5, 1); will-change: transform; }
        .glass-card { background: rgba(255,255,255,0.06); backdrop-filter: blur(12px); -webkit-backdrop-filter: blur(12px); border: 1px solid rgba(255,255,255,0.1); transform: translateZ(0); }
        .list-input { border-bottom: 1px solid rgba(255,255,255,0.1) !important; padding: 2px 0 !important; font-size: 0.875rem !important; }
        .list-input:focus { border-bottom: 1px solid rgba(255,255,255,0.6) !important; }
        input:-webkit-autofill { -webkit-text-fill-color: #fafafa; transition: background-color 5000s ease-in-out 0s; }
        ::-webkit-scrollbar { width: 6px; }
        ::-webkit-scrollbar-track { background: transparent; }
        ::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.2); border-radius: 10px; }
    </style>
</head>
<body class="antialiased selection:bg-white/20 selection:text-white">
    <div class="shader-bg"></div>
"""

HTML_FOOTER = """
    <script>
        document.querySelectorAll('.magnetic-btn').forEach(btn => {
            btn.addEventListener('mousemove', (e) => {
                const rect = btn.getBoundingClientRect();
                const x = e.clientX - rect.left - rect.width / 2;
                const y = e.clientY - rect.top - rect.height / 2;
                btn.style.transform = `translate(${x * 0.15}px, ${y * 0.15}px)`;
            });
            btn.addEventListener('mouseleave', () => btn.style.transform = 'translate(0px, 0px)');
        });
        const observer = new IntersectionObserver((entries) => {
            entries.forEach(entry => { if (entry.isIntersecting) entry.target.classList.add('visible'); });
        }, { threshold: 0.1 });
        document.querySelectorAll('.reveal').forEach(el => observer.observe(el));
    </script>
</body>
</html>
"""

# ================= 5. 业务逻辑路由 =================

@app.route('/')
def index():
    global engine_running
    u_id = session.get('user_id')
    if not u_id: return redirect(url_for('login'))
    
    db_session = Session()
    user = db_session.query(User).get(u_id)

    if user.username == 'admin' and not session.get('admin_id'):
        db_session.close()
        return redirect(url_for('admin_dashboard'))

    impersonate_banner = ""
    admin_id = session.get('admin_id')
    if admin_id:
        real_admin = db_session.query(User).get(admin_id)
        if real_admin and real_admin.username == 'admin':
            impersonate_banner = f"""
            <div class="fixed bottom-8 left-1/2 -translate-x-1/2 z-50 bg-white/10 backdrop-blur-xl border border-white/20 px-6 py-3 rounded-full flex items-center gap-6 shadow-2xl transition-all hover:bg-white/15">
                <span class="text-xs font-medium text-white/70">
                    <span class="uppercase tracking-widest">👁️ 监管中: 正在查看</span> 
                    <b class="text-white ml-1 normal-case tracking-normal">{user.username}</b>
                </span>
                <a href="/revert_admin" class="bg-white/20 hover:bg-white text-white hover:text-black border border-white/30 px-5 py-1.5 rounded-full text-xs font-bold transition-all shadow-md">退出监管</a>
            </div>
            """
        else:
            session.pop('admin_id', None)
    
    user_monitoring = getattr(user, 'is_monitoring', False)
    status_html = f"""
        <div class="glass-card rounded-2xl p-8 reveal">
            <p class="font-mono text-xs text-white/50 mb-2 uppercase tracking-widest">个人监控状态</p>
            <div class="flex items-center gap-4">
                <div class="text-3xl font-light">{"🟢 检测中" if user_monitoring else "🔴 已暂停"}</div>
                <a href="/toggle_engine" class="magnetic-btn ml-auto rounded-full {'bg-white/10 hover:bg-white/20' if user_monitoring else 'bg-white text-black hover:scale-105 shadow-xl'} px-6 py-2 text-sm font-medium transition-all">
                    {"🛑 暂停所有任务" if user_monitoring else "🚀 开启自动监控"}
                </a>
            </div>
        </div>
    """

    tasks_html = ""
    for idx, t in enumerate(user.tasks):
        l_time = time.strftime('%H:%M:%S', time.localtime(t.last_alert_at)) if t.last_alert_at > 0 else "尚未触发"
        cd_mins = t.cooldown_seconds // 60

        tasks_html += f"""
        <form action="/update_task/{t.id}" method="post" class="reveal glass-card flex flex-col md:flex-row md:items-center justify-between rounded-xl px-8 py-6 transition-all hover:bg-white/10 mb-4">
            <div class="flex items-center gap-6 mb-4 md:mb-0">
                <span class="font-mono text-xl font-light text-white/20">{(idx + 1):02d}</span>
                <div>
                    <h3 class="text-2xl font-light tracking-wide">{t.item_name}</h3>
                    <div class="flex items-center gap-2 mt-1">
                        <span class="font-mono text-xs text-white/40">目标:¥</span>
                        <input name="target_price" type="number" step="0.01" value="{t.target_price}" class="list-input w-20 font-bold text-white/90">
                        <span class="mx-1 text-white/10">|</span>
                        <span class="font-mono text-xs text-white/40">冷却:</span>
                        <input name="cooldown_mins" type="number" value="{cd_mins}" class="list-input w-12 text-white/80">
                        <span class="font-mono text-xs text-white/40">分</span>
                    </div>
                </div>
            </div>
            <div class="flex items-center gap-4">
                <span class="font-mono text-sm text-white/70 mr-4 font-medium">上次预警: {l_time}</span>
                <button type="submit" class="text-xs font-bold text-white/60 hover:text-white bg-white/5 hover:bg-white/20 px-4 py-2 rounded-lg transition-all uppercase tracking-widest border border-white/10">保存</button>
                <a href='/delete_task/{t.id}' class="text-xs font-bold text-red-200 hover:text-white hover:bg-red-600/90 bg-red-600/30 px-4 py-2 rounded-lg transition-all uppercase tracking-widest border border-red-500/40">删除</a>
            </div>
        </form>
        """

    html = HTML_HEAD + impersonate_banner + f"""
    <nav class="fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-8 py-8 md:px-12">
        <div class="flex items-center gap-3">
            <div class="h-10 w-10 flex items-center justify-center rounded-lg bg-white/10 border border-white/20 text-xl font-bold">A</div>
            <span class="text-xl font-semibold tracking-tight">Acme Monitor</span>
        </div>
        <div class="flex gap-6 md:gap-8 text-sm font-medium">
            <a href="/profile" class="text-white/60 hover:text-white transition-colors">账号设置</a>
            <a href="/feedback" class="text-white/60 hover:text-white transition-colors">问题反馈</a>
            <a href="/logout" class="text-white/40 hover:text-red-400 transition-colors">退出</a>
        </div>
    </nav>

    <main class="relative z-10 pt-32 px-6 md:px-12 max-w-7xl mx-auto pb-24">
        <div class="reveal mb-16">
            <h1 class="text-6xl md:text-8xl font-light tracking-tighter leading-none mb-4">Dashboard</h1>
            <p class="text-xl text-white/50 font-light">/ 欢迎回来, <span class="normal-case">{user.username}</span></p>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-8 mb-20">
            {status_html}
            <div class="glass-card rounded-2xl p-8 reveal" style="transition-delay: 200ms">
                <p class="font-mono text-xs text-white/50 mb-2 uppercase tracking-widest">Active Tasks</p>
                <div class="flex items-center gap-4">
                    <div class="text-5xl font-light">{len(user.tasks)}</div>
                    <p class="text-sm text-white/40 leading-relaxed max-w-[150px]">目前云端为你盯盘的饰品数量</p>
                    <a href="/search" class="magnetic-btn ml-auto rounded-full bg-white/5 border border-white/10 px-8 py-3 text-sm hover:bg-white/10 transition-all">添加监控项</a>
                </div>
            </div>
        </div>

        <div class="reveal mb-10 flex items-end justify-between">
            <div>
                <h2 class="text-4xl font-light mb-2">Live Monitoring</h2>
                <p class="font-mono text-xs text-white/30 uppercase tracking-widest">/ 实时监控清单</p>
            </div>
            <p class="text-xs text-white/50 font-medium uppercase tracking-widest mb-1">提示：修改参数后请点击保存</p>
        </div>

        <div class="space-y-2">
            {tasks_html if tasks_html else '<p class="reveal text-white/20 py-20 text-center font-light text-xl border border-dashed border-white/10 rounded-2xl">目前清单为空，请点击上方添加监控项</p>'}
        </div>
    </main>
    """ + HTML_FOOTER
    db_session.close()
    return html

@app.route('/update_task/<int:task_id>', methods=['POST'])
def update_task(task_id):
    u_id = session.get('user_id')
    if not u_id: return redirect(url_for('login'))
    new_price = float(request.form.get('target_price'))
    new_cd_mins = int(request.form.get('cooldown_mins'))
    db_session = Session()
    task = db_session.query(Task).filter(Task.id == task_id, Task.user_id == u_id).first()
    if task:
        task.target_price = new_price
        task.cooldown_seconds = new_cd_mins * 60
        db_session.commit()
    db_session.close()
    return redirect(url_for('index'))

@app.route('/profile', methods=['GET', 'POST'])
def profile():
    u_id = session.get('user_id')
    if not u_id: return redirect(url_for('login'))
    db_session = Session()
    user = db_session.query(User).get(u_id)
    msg = ""
    if request.method == 'POST':
        user.youpin_token = request.form.get('token')
        user.receive_email = request.form.get('email')
        db_session.commit()
        msg = "信息更新成功"

    html = HTML_HEAD + f"""
    <nav class="fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-8 py-8 md:px-12">
        <div class="flex items-center gap-3">
            <div class="h-10 w-10 flex items-center justify-center rounded-lg bg-white/10 border border-white/20 text-xl font-bold">A</div>
            <span class="text-xl font-semibold tracking-tight">Acme Monitor</span>
        </div>
        <div class="flex gap-6 md:gap-8 text-sm font-medium">
            <a href="/" class="text-white/60 hover:text-white transition-colors">控制台</a>
            <a href="/feedback" class="text-white/60 hover:text-white transition-colors">问题反馈</a>
            <a href="/logout" class="text-white/40 hover:text-red-400 transition-colors">退出</a>
        </div>
    </nav>
    <div class="min-h-screen flex items-center justify-center px-6 md:px-12">
        <div class="max-w-xl w-full">
            <div class="reveal mb-12">
                <h1 class="text-6xl md:text-7xl font-light tracking-tighter mb-4">Settings</h1>
                <p class="text-white/40 font-mono text-xs uppercase tracking-widest">/ 更新你的账号凭证</p>
            </div>
            {f'<p class="reveal font-mono text-sm text-green-400 mb-8">{msg}</p>' if msg else ''}
            <form method="post" class="space-y-12 reveal" style="transition-delay: 200ms">
                <div>
                    <label class="block font-mono text-xs text-white/60 font-medium uppercase tracking-widest mb-4">悠悠 Token</label>
                    <textarea name="token" rows="3" required class="w-full text-lg font-light py-2 focus:outline-none">{user.youpin_token}</textarea>
                </div>
                <div>
                    <label class="block font-mono text-xs text-white/60 font-medium uppercase tracking-widest mb-4">接收预警邮箱</label>
                    <input name="email" type="email" value="{user.receive_email}" required class="w-full text-2xl font-light py-2 normal-case">
                </div>
                <div class="flex items-center justify-between pt-8">
                    <a href="/" class="text-white/40 hover:text-white transition-colors">&larr; 返回控制台</a>
                    <button type="submit" class="magnetic-btn rounded-full bg-white px-12 py-4 text-black font-bold hover:scale-105 transition-all">保存修改</button>
                </div>
            </form>
        </div>
    </div>
    """ + HTML_FOOTER
    db_session.close()
    return html

@app.route('/feedback', methods=['GET', 'POST'])
def feedback_page():
    u_id = session.get('user_id')
    if not u_id: return redirect(url_for('login'))
    db_session = Session()
    msg = ""
    if request.method == 'POST':
        content = request.form.get('content')
        if content and content.strip():
            db_session.add(Feedback(user_id=u_id, content=content))
            db_session.commit()
            msg = "✅ 提交成功！感谢您的宝贵建议，开发者已收到。"
    db_session.close()

    html = HTML_HEAD + f"""
    <nav class="fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-8 py-8 md:px-12">
        <div class="flex items-center gap-3">
            <div class="h-10 w-10 flex items-center justify-center rounded-lg bg-white/10 border border-white/20 text-xl font-bold">A</div>
            <span class="text-xl font-semibold tracking-tight">Acme Monitor</span>
        </div>
        <div class="flex gap-6 md:gap-8 text-sm font-medium">
            <a href="/" class="text-white/60 hover:text-white transition-colors">控制台</a>
            <a href="/profile" class="text-white/60 hover:text-white transition-colors">账号设置</a>
            <a href="/logout" class="text-white/40 hover:text-red-400 transition-colors">退出</a>
        </div>
    </nav>
    <div class="min-h-screen flex items-center justify-center px-6 md:px-12 pt-20">
        <div class="max-w-2xl w-full">
            <div class="reveal mb-10">
                <h1 class="text-6xl md:text-7xl font-light tracking-tighter mb-4">Feedback</h1>
                <p class="text-white/40 font-mono text-xs uppercase tracking-widest">/ 提交您的 Bug 报告或优化思路</p>
            </div>
            {f'<p class="reveal font-mono text-sm text-green-400 mb-8">{msg}</p>' if msg else ''}
            <form method="post" class="space-y-8 reveal glass-card p-8 rounded-2xl" style="transition-delay: 200ms">
                <div>
                    <label class="block font-mono text-xs text-white/60 font-medium uppercase tracking-widest mb-4">你想对开发者说的话...</label>
                    <textarea name="content" rows="6" placeholder="请详细描述您遇到的问题，或者期待的新功能..." required class="w-full text-lg font-light py-4 px-2 focus:outline-none resize-none bg-white/5 rounded-lg border-b-0"></textarea>
                </div>
                <div class="flex items-center justify-between pt-4">
                    <a href="/" class="text-white/40 hover:text-white transition-colors">&larr; 返回控制台</a>
                    <button type="submit" class="magnetic-btn rounded-full bg-white px-12 py-4 text-black font-bold hover:scale-105 transition-all shadow-xl">提交反馈</button>
                </div>
            </form>
        </div>
    </div>
    """ + HTML_FOOTER
    return html

@app.route('/search', methods=['GET', 'POST'])
def search_page():
    u_id = session.get('user_id')
    if not u_id: return redirect(url_for('login'))
    results = []
    keyword = request.form.get('keyword', '')
    if request.method == 'POST' and keyword:
        db_session = Session()
        user = db_session.query(User).get(u_id)
        url = "https://api.youpin898.com/api/homepage/pc/goods/market/querySaleTemplate"
        payload = {"listSortType": 0, "sortType": 0, "keyWords": keyword, "pageSize": 20, "pageIndex": 1}
        res = requests.post(url, headers=get_search_headers(user.youpin_token), json=payload, impersonate="chrome110", timeout=10)
        results = res.json().get("Data", [])
        db_session.close()

    results_html = ""
    for r in results:
        t_id = r.get('templateId') or r.get('id')
        name = r.get('commodityName', '未知')
        price = r.get('price', 'N/A')
        results_html += f"""
        <div class="reveal glass-card rounded-2xl p-6 md:p-8 flex flex-col md:flex-row justify-between items-center gap-8 mb-4 border border-white/10 hover:border-white/30 transition-all">
            <div class="flex-1 w-full">
                <h4 class="text-2xl font-light mb-2">{name}</h4>
                <p class="font-mono text-xs text-white/40 tracking-widest uppercase">当前市场底价: <span class="text-white/80">¥{price}</span></p>
            </div>
            <form action="/add_task" method="post" class="flex flex-wrap gap-4 md:gap-6 items-end w-full md:w-auto">
                <input type="hidden" name="t_id" value="{t_id}">
                <input type="hidden" name="name" value="{name}">
                <div class="w-24 flex-1 md:flex-none">
                    <label class="block font-mono text-xs text-white/60 font-medium uppercase tracking-widest mb-2">期望目标价 ¥</label>
                    <input name="price" type="number" step="0.01" required class="w-full text-lg">
                </div>
                <div class="w-24 flex-1 md:flex-none">
                    <label class="block font-mono text-xs text-white/60 font-medium uppercase tracking-widest mb-2">冷却(分钟)</label>
                    <input name="cooldown_mins" type="number" value="60" required class="w-full text-lg">
                </div>
                <button type="submit" class="magnetic-btn w-full md:w-auto rounded-full bg-white/10 border border-white/20 px-8 py-3 text-sm font-semibold hover:bg-white hover:text-black transition-all">添加监控</button>
            </form>
        </div>
        """

    html = HTML_HEAD + f"""
    <nav class="fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-8 py-8 md:px-12">
        <div class="flex items-center gap-3">
            <div class="h-10 w-10 flex items-center justify-center rounded-lg bg-white/10 border border-white/20 text-xl font-bold">A</div>
            <span class="text-xl font-semibold tracking-tight">Acme Monitor</span>
        </div>
        <div class="flex gap-6 md:gap-8 text-sm font-medium">
            <a href="/" class="text-white/60 hover:text-white transition-colors">控制台</a>
            <a href="/profile" class="text-white/60 hover:text-white transition-colors">账号设置</a>
        </div>
    </nav>
    <div class="pt-32 px-6 md:px-12 max-w-7xl mx-auto pb-24">
        <div class="reveal mb-16 flex items-end justify-between">
            <div>
                <h1 class="text-6xl md:text-8xl font-light tracking-tighter mb-4">Search</h1>
                <p class="text-xl text-white/50 font-light">/ 搜索饰品模板</p>
            </div>
            <a href="/" class="text-white/40 hover:text-white mb-4">&larr; 返回控制台</a>
        </div>
        <form method="post" class="reveal mb-20">
            <label class="block font-mono text-xs text-white/60 font-medium uppercase tracking-widest mb-4">输入关键词</label>
            <div class="flex flex-col md:flex-row gap-6 md:gap-8">
                <input name="keyword" value="{keyword}" placeholder="例如: 蝴蝶刀" required class="flex-1 text-3xl md:text-5xl font-light py-4 focus:outline-none normal-case">
                <button type="submit" class="magnetic-btn rounded-full bg-white px-12 py-4 text-black font-bold hover:scale-105 transition-all w-full md:w-auto">搜索</button>
            </div>
        </form>
        <div class="space-y-4">{results_html}</div>
    </div>
    """ + HTML_FOOTER
    return html

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        un = request.form.get('username')
        db_session = Session()
        user = db_session.query(User).filter(User.username == un).first()
        db_session.close()
        if user:
            session['user_id'] = user.id
            session.pop('admin_id', None)
            session.modified = True
            if user.username == 'admin':
                return redirect(url_for('admin_dashboard'))
            return redirect(url_for('index'))

    return HTML_HEAD + """
    <div class="min-h-screen flex items-center justify-center">
        <div class="max-w-md w-full px-8 reveal">
            <h1 class="text-7xl font-light tracking-tighter mb-12">Login</h1>
            <form method="post" class="space-y-12">
                <div>
                    <label class="block font-mono text-xs text-white/60 font-medium uppercase tracking-widest mb-4">用户名 Username</label>
                    <input name="username" required class="w-full text-3xl font-light py-2 normal-case">
                </div>
                <button type="submit" class="magnetic-btn w-full rounded-full bg-white py-4 text-black font-bold hover:scale-105">进入系统</button>
                <a href="/register" class="block text-center text-white/40 text-sm hover:text-white transition-colors">没有账号？点击注册</a>
            </form>
        </div>
    </div>
    """ + HTML_FOOTER

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        un, tk, em = request.form.get('username'), request.form.get('token'), request.form.get('email')
        db_session = Session()
        if not db_session.query(User).filter(User.username == un).first():
            db_session.add(User(username=un, youpin_token=tk, receive_email=em))
            db_session.commit()
        db_session.close()
        return redirect(url_for('login'))
        
    return HTML_HEAD + """
    <div class="min-h-screen flex items-center justify-center py-12">
        <div class="max-w-md w-full px-8 reveal">
            <h1 class="text-7xl font-light tracking-tighter mb-12">Register</h1>
            <form method="post" class="space-y-8">
                <div><label class="block font-mono text-xs text-white/60 font-medium uppercase tracking-widest mb-2">用户名</label><input name="username" required class="w-full text-xl font-light py-2 normal-case"></div>
                <div><label class="block font-mono text-xs text-white/60 font-medium uppercase tracking-widest mb-2">悠悠 Token</label><input name="token" required class="w-full text-xl font-light py-2"></div>
                <div><label class="block font-mono text-xs text-white/60 font-medium uppercase tracking-widest mb-2">接收邮箱</label><input name="email" type="email" required class="w-full text-xl font-light py-2 normal-case"></div>
                
                <div class="pt-4">
                    <button type="submit" class="magnetic-btn w-full rounded-full bg-white py-4 text-black font-bold hover:scale-105 shadow-xl">提交注册</button>
                </div>
                
                <div class="text-center pt-2">
                    <button type="button" onclick="document.getElementById('tutorial-modal').style.display='flex'" class="text-white/40 text-xs hover:text-white transition-colors underline decoration-white/20 underline-offset-4 cursor-pointer">不知道如何获取悠悠 Token？点击查看教程</button>
                </div>
                
                <div class="text-center pt-4">
                    <a href="/login" class="text-white/40 text-sm hover:text-white transition-colors">&larr; 返回登录</a>
                </div>
            </form>
        </div>
    </div>

    <div id="tutorial-modal" style="display: none;" class="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-6">
        <div class="glass-card max-w-4xl w-full max-h-[85vh] overflow-y-auto rounded-3xl p-8 md:p-12 relative border border-white/20 shadow-2xl">
            <button type="button" onclick="document.getElementById('tutorial-modal').style.display='none'" class="absolute top-6 right-8 text-white/50 hover:text-white font-bold text-2xl hover:rotate-90 transition-transform">✕</button>
            
            <h2 class="text-3xl font-light mb-2">获取 Token 教程</h2>
            <p class="text-sm text-white/40 mb-10 font-mono">/ Tutorial: How to get Youpin Token</p>
            
            <div class="space-y-12">
                <div>
                    <div class="flex items-center gap-3 mb-3">
                        <span class="flex items-center justify-center w-8 h-8 rounded-full bg-white text-black font-bold">1</span>
                        <h3 class="text-xl font-medium text-white/90">登录官网</h3>
                    </div>
                    <p class="text-sm text-white/50 mb-4 ml-11 leading-relaxed">首先打开悠悠有品官网，并登录自己的账号。</p>
                    <img src="/static/step1.png" alt="步骤1" class="w-full rounded-xl border border-white/10 shadow-lg ml-11" onerror="this.style.display='none';">
                </div>
                
                <div>
                    <div class="flex items-center gap-3 mb-3">
                        <span class="flex items-center justify-center w-8 h-8 rounded-full bg-white text-black font-bold">2</span>
                        <h3 class="text-xl font-medium text-white/90">打开开发者工具</h3>
                    </div>
                    <p class="text-sm text-white/50 mb-4 ml-11 leading-relaxed">按下键盘上的 F12 -> 选择网络 (Network) -> 筛选 Fetch/XHR -> 随便点击进入一个饰品的详情页。</p>
                    <img src="/static/step2.png" alt="步骤2" class="w-full rounded-xl border border-white/10 shadow-lg ml-11" onerror="this.style.display='none';">
                </div>
                
                <div>
                    <div class="flex items-center gap-3 mb-3">
                        <span class="flex items-center justify-center w-8 h-8 rounded-full bg-white text-black font-bold">3</span>
                        <h3 class="text-xl font-medium text-white/90">提取 Token</h3>
                    </div>
                    <p class="text-sm text-white/50 mb-4 ml-11 leading-relaxed">在名称列表中随便点击一个以“query”开头的选项 -> 在右侧的“标头 (Headers)”中向下滑动找到“Authorization” -> 复制右侧的一大串代码，该段代码即为悠悠 token。</p>
                    <img src="/static/step3.png" alt="步骤3" class="w-full rounded-xl border border-white/10 shadow-lg ml-11" onerror="this.style.display='none';">
                </div>
            </div>
        </div>
    </div>
    """ + HTML_FOOTER

@app.route('/toggle_engine')
def toggle_engine():
    u_id = session.get('user_id')
    if not u_id: return redirect(url_for('login'))
    
    db_session = Session()
    user = db_session.query(User).get(u_id)
    if user:
        user.is_monitoring = not getattr(user, 'is_monitoring', False)
        db_session.commit()
    db_session.close()

    global engine_running, monitor_thread
    if not engine_running:
        engine_running = True
        monitor_thread = threading.Thread(target=run_monitor_background, daemon=True)
        monitor_thread.start()
        
    return redirect(url_for('index'))

@app.route('/add_task', methods=['POST'])
def add_task():
    u_id = session.get('user_id')
    t_id = request.form.get('t_id')
    name = request.form.get('name')
    target_p = float(request.form.get('price'))
    cd_seconds = int(request.form.get('cooldown_mins', 60)) * 60
    db_session = Session()
    exists = db_session.query(Task).filter(Task.user_id == u_id, Task.template_id == t_id).first()
    if not exists:
        db_session.add(
            Task(user_id=u_id, item_name=name, template_id=t_id, target_price=target_p, cooldown_seconds=cd_seconds))
        db_session.commit()
    db_session.close()
    return redirect(url_for('index'))

@app.route('/delete_task/<int:task_id>')
def delete_task(task_id):
    u_id = session.get('user_id')
    db_session = Session()
    task = db_session.query(Task).filter(Task.id == task_id, Task.user_id == u_id).first()
    if task:
        db_session.delete(task)
        db_session.commit()
    db_session.close()
    return redirect(url_for('index'))

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('admin_id', None)
    return redirect(url_for('login'))

# ================= 6. 开发者专属后台与账户模拟机制 =================

@app.route('/admin')
def admin_dashboard():
    global engine_running

    if session.get('admin_id'):
        session['user_id'] = session.get('admin_id')
        session.pop('admin_id', None)
        session.modified = True

    u_id = session.get('user_id')
    if not u_id: return redirect(url_for('login'))

    db_session = Session()
    user = db_session.query(User).get(u_id)

    if not user or user.username != 'admin':
        db_session.close()
        return "<script>alert('权限不足：非系统开发者。');window.location.href='/';</script>", 403

    all_users = db_session.query(User).all()

    users_html = ""
    for u in all_users:
        if u.username == 'admin': continue
        task_count = len(u.tasks)
        
        is_user_monitoring = getattr(u, 'is_monitoring', False)
        is_monitoring_active = engine_running and is_user_monitoring and task_count > 0
        
        if is_monitoring_active:
            monitor_badge = '<span class="px-3 py-1 bg-green-500/20 text-green-400 border border-green-500/30 rounded-full text-[10px] font-bold tracking-widest uppercase shadow-[0_0_10px_rgba(34,197,94,0.2)]">🟢 正在检测</span>'
        else:
            monitor_badge = '<span class="px-3 py-1 bg-white/5 text-white/40 border border-white/10 rounded-full text-[10px] font-bold tracking-widest uppercase">🔴 待机中</span>'

        users_html += f"""
        <div class="reveal glass-card flex flex-col md:flex-row justify-between items-center px-8 py-6 mb-4 rounded-xl border border-white/10 hover:bg-white/10 transition-all">
            <div class="flex items-center gap-6">
                <span class="font-mono text-xl text-white/20">ID:{u.id:03d}</span>
                <div>
                    <div class="flex items-center gap-4">
                        <h3 class="text-2xl font-light normal-case">{u.username}</h3>
                        {monitor_badge}
                    </div>
                    <p class="text-sm text-white/50 font-mono mt-1">邮箱: <span class="normal-case">{u.receive_email}</span> <span class="mx-2 text-white/20">|</span> 监控项: <span class="text-white/90 font-bold">{task_count}</span> 个</p>
                </div>
            </div>
            <div class="flex gap-4 mt-4 md:mt-0">
                <a href="/impersonate/{u.id}" class="text-sm font-bold text-black bg-white px-6 py-2 rounded-full hover:scale-105 shadow-lg transition-all">登录其账号</a>
            </div>
        </div>
        """
        
    all_feedbacks = db_session.query(Feedback).order_by(Feedback.submit_time.desc()).all()
    feedbacks_html = ""
    for fb in all_feedbacks:
        fb_time = time.strftime('%Y-%m-%d %H:%M', time.localtime(fb.submit_time))
        fb_author = fb.user.username if fb.user else "未知用户"
        feedbacks_html += f"""
        <div class="reveal glass-card p-6 mb-4 rounded-xl border-l-4 border-l-blue-500 border-white/10">
            <div class="flex justify-between items-center mb-3">
                <span class="font-bold text-white/90 normal-case">{fb_author}</span>
                <span class="text-xs text-white/40 font-mono">{fb_time}</span>
            </div>
            <p class="text-white/70 leading-relaxed">{fb.content}</p>
        </div>
        """

    html = HTML_HEAD + f"""
    <nav class="fixed top-0 left-0 right-0 z-40 flex items-center justify-between px-8 py-8 md:px-12">
        <div class="flex items-center gap-3">
            <div class="h-10 w-10 flex items-center justify-center rounded-lg bg-red-600/90 border border-red-500 text-xl font-bold text-white shadow-[0_0_15px_rgba(239,68,68,0.5)]">S</div>
            <span class="text-xl font-semibold tracking-tight text-red-100">Admin Center</span>
        </div>
        <div class="flex gap-8 text-sm font-medium">
            <a href="/logout" class="text-white/40 hover:text-red-400 transition-colors">退出登录</a>
        </div>
    </nav>

    <main class="relative z-10 pt-32 px-6 md:px-12 max-w-5xl mx-auto pb-24">
        <div class="reveal mb-12">
            <h1 class="text-6xl font-light tracking-tighter mb-2">User Data</h1>
            <p class="text-sm text-red-400/80 font-mono uppercase tracking-widest">/ 全局用户管理与状态审计</p>
        </div>

        <div class="glass-card rounded-2xl p-6 mb-10 reveal flex flex-col md:flex-row md:items-center gap-6 border-red-500/20 bg-red-500/5">
            <div class="text-6xl font-light text-white">{len(all_users) - 1 if len(all_users) > 0 else 0}</div>
            <div>
                <p class="text-lg font-medium text-white/90">有效外部用户</p>
                <p class="text-sm text-white/50">当前系统内已注册并存活的普通用户总数</p>
            </div>
            <div class="ml-auto flex flex-col items-end">
                <span class="text-sm text-white/40 mb-1">全局多线程引擎状态</span>
                <span class="text-lg font-bold {'text-green-400' if engine_running else 'text-white/50'}">{'🚀 引擎驻留中，随时待命' if engine_running else '🛑 引擎休眠中'}</span>
            </div>
        </div>

        <div class="space-y-2 mb-20">
            {users_html if users_html else '<p class="text-white/30 text-center py-10 font-light glass-card rounded-xl">暂无其他用户注册</p>'}
        </div>
        
        <div class="reveal mb-8">
            <h2 class="text-4xl font-light mb-2">User Feedbacks</h2>
            <p class="text-sm text-blue-400/80 font-mono uppercase tracking-widest">/ 用户提交的优化思路与 Bug 报告</p>
        </div>
        <div class="space-y-2">
            {feedbacks_html if feedbacks_html else '<p class="text-white/30 text-center py-10 font-light glass-card rounded-xl border-dashed">暂时还没有用户提交反馈</p>'}
        </div>
        
    </main>
    """ + HTML_FOOTER
    db_session.close()
    return html

@app.route('/impersonate/<int:target_id>')
def impersonate(target_id):
    u_id = session.get('user_id')
    if not u_id: return redirect(url_for('login'))

    db_session = Session()
    admin_user = db_session.query(User).get(u_id)

    if admin_user and admin_user.username == 'admin':
        session['admin_id'] = admin_user.id
        session['user_id'] = target_id
        session.modified = True

    db_session.close()
    return redirect(url_for('index'))

@app.route('/revert_admin')
def revert_admin():
    admin_id = session.get('admin_id')
    if admin_id:
        session['user_id'] = admin_id
        session.pop('admin_id', None)
        session.modified = True
        return redirect('/admin')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', debug=True, port=5000, use_reloader=False)
