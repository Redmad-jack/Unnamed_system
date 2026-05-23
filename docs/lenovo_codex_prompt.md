# 给拯救者 Codex 的执行 Prompt

把下面整段复制到拯救者 Windows 上的 Codex。它的目标是让拯救者成为 Have Some "Ai" 的唯一主控，iMac 只打开展示页。

```text
你现在在一台 Windows 拯救者电脑上。请帮我把 Have Some "Ai" 展览系统在这台电脑上跑起来。目标拓扑：

- 这台 Windows 拯救者是唯一主控：运行 FastAPI 服务、打开控制页、负责麦克风收音和扬声器发音。
- iMac M1 只通过局域网打开粒子展示页 `/particle-display`。
- 服务必须绑定 `0.0.0.0:8010`，这样 iMac 才能访问。
- `.env` 不在 GitHub 里；如果当前项目根目录没有 `.env`，请明确让我从 Mac 用 U 盘复制过来，不要自己编造密钥。
- 默认不要复制旧数据库；让新电脑从空库开始。除非我明确要求保留历史，才复制 `data/have_some_ai.db`、`data/have_some_ai.db-wal`、`data/have_some_ai.db-shm`。
- 不要修改核心业务逻辑、ConversationOrchestrator、MealService、数据库 schema、语音 provider 或展示页只读边界。

请按下面顺序执行：

1. 确认当前目录是否已经是项目仓库。
   - 如果还没有仓库，优先使用：`git clone https://github.com/Redmad-jack/Unnamed_system.git`
   - 如果我已经配置好 GitHub SSH，也可以使用：`git clone git@github.com:Redmad-jack/Unnamed_system.git`
   - clone 后进入仓库根目录。
   - 如果已经是仓库，先运行 `git status --short --branch` 和 `git pull`。

2. 检查 Python 和 Git：
   - 需要 Python 3.11+，推荐 Python 3.13 x64。
   - 如果没有 Python 或 Git，请告诉我需要安装，不要绕过。

3. 在仓库根目录运行 Windows setup：
   ```powershell
   .\scripts\setup_windows.ps1
   ```
   如果 PowerShell 禁止运行脚本，则只对当前窗口执行：
   ```powershell
   Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
   .\scripts\setup_windows.ps1
   ```

4. 检查 `.env`：
   - 如果 `.env` 不存在，停下来告诉我：需要从 Mac 把 `.env` 复制到这个仓库根目录。
   - 如果 `.env` 存在，不要打印密钥原文，只确认这些变量名是否存在：
     `ENTITY_LLM_PROVIDER`、`ANTHROPIC_API_KEY` 或 `ANTHROPIC_AUTH_TOKEN`、`ANTHROPIC_BASE_URL`、`ENTITY_LLM_MODEL`、`HAVE_SOME_AI_VOICE_PROVIDER`、`HAVE_SOME_AI_STT_MODE`、`DOUBAO_API_KEY`、`DOUBAO_ASR_ENDPOINT`、`DOUBAO_ASR_RESOURCE_ID`、`DOUBAO_TTS_ENDPOINT`、`DOUBAO_TTS_RESOURCE_ID`、`DOUBAO_TTS_SPEAKER_ZH`、`DOUBAO_TTS_SPEAKER_EN`。

5. 启动服务：
   ```powershell
   .\scripts\start_have_some_ai_windows.ps1
   ```
   这个脚本应启动：
   ```powershell
   .\.venv\Scripts\python.exe scripts\start_have_some_ai.py --host 0.0.0.0 --port 8010
   ```

6. 如果 Windows 防火墙弹窗出现，请提示我允许 Python 在 Private network 访问。
   如果 iMac 访问不了，请让我用管理员 PowerShell 执行：
   ```powershell
   New-NetFirewallRule -DisplayName "Have Some Ai 8010" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8010 -Profile Private
   ```

7. 启动后做本机验证：
   ```powershell
   Invoke-RestMethod http://127.0.0.1:8010/health
   Invoke-RestMethod http://127.0.0.1:8010/api/v1/voice-config
   Invoke-RestMethod http://127.0.0.1:8010/api/v1/display-state
   ```

8. 告诉我两个地址：
   - 拯救者控制页：`http://127.0.0.1:8010/`
   - iMac 粒子展示页：`http://<这台拯救者的局域网IP>:8010/particle-display`

9. 重要提醒：
   - iMac 只开 `/particle-display`，不要开控制页。
   - 观众启动要在拯救者控制页点 New / Start Voice，或使用接在拯救者上的实体按钮。
   - `/particle-display` 的 wake 按钮跨电脑不能唤醒控制页，这是预期限制，不要当成 bug 修代码。
   - 如果没声音或没识别，先检查 `/health`、`/api/v1/voice-config`、浏览器麦克风权限、`.env` 和后端日志。

请一步步执行，并把每一步结果告诉我。遇到缺少 GitHub 地址、缺少 `.env`、Python/Git 未安装、防火墙阻挡、端口被占用时，停下来告诉我最小下一步。
```
