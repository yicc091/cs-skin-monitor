# CS-Skin-Monitor: 基于 TLS 指纹伪装的轻量级饰品监控引擎

## 🚀 项目简介
本项目是一个极简但功能完备的 CS 饰品高频监控与邮件预警系统。摒弃了笨重的自动化浏览器框架，直接在单文件 (Single-file MVP) 中打通了底层反爬、多线程驻留、多用户隔离与前端可视化，实现真正的轻量级全栈闭环。

## 🧠 核心工程亮点

1. **反爬策略重构 (TLS Fingerprinting)**
   - 弃用传统的 Playwright/Selenium，采用底层 `curl_cffi` 库模拟 Chrome 110 的 TLS 握手指纹 (`impersonate="chrome110"`)，无头化绕过悠悠有品 API 的严格风控体系，资源消耗降低 90%。
2. **异步常驻引擎 (Background Daemon)**
   - 内置轻量级线程守护 (`monitor_thread`)，与 Flask 主进程解耦。支持多用户并行轮询，动态冷却时间计算，确保高频监控的同时不触发 IP 封禁。
3. **多租户与上帝视角 (Admin Impersonation)**
   - 基于 SQLAlchemy 构建多用户隔离体系。
   - 包含硬核的“管理员伪装 (Impersonate)”机制：管理员可在后台一键接管任何用户的 Session 状态进行无缝 Debug，并在 UI 侧实现状态感知。
4. **单文件无模板渲染**
   - 采用后端直出 TailwindCSS + Glassmorphism UI 的极客方案，无需额外配置静态资源服务器即可完成部署。

## 🛠️ 技术栈
- **核心框架**: Python 3.10+ / Flask
- **网络与反爬**: `curl_cffi` (TLS Spoofing)
- **数据持久化**: SQLite + SQLAlchemy ORM (支持无痛热升级)
- **UI 渲染**: TailwindCSS + 原生 HTML 字符串插值

## 📦 快速部署

1. 克隆本项目：
   `git clone https://github.com/YourUsername/cs-skin-monitor.git`
2. 安装依赖：
   `pip install -r requirements.txt`
3. 配置环境变量：
   复制 `.env.example` 为 `.env`，并填入你的 QQ 邮箱 SMTP 授权码。
4. 启动系统：
   `python app.py` 
   访问 `http://localhost:5000` 即可进入控制台。
