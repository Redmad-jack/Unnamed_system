# 拯救者主控迁移部署

本文档用于把 Have Some "Ai" 从当前 Mac 迁移到一台全新的 Windows 拯救者电脑，并让拯救者成为现场唯一主控。

如果拯救者上也安装了 Codex，最省事的方式是直接把 `docs/lenovo_codex_prompt.md` 里的 prompt 复制给拯救者 Codex，让它按步骤执行。

## 现场拓扑

- 拯救者 Windows：运行 FastAPI 服务、打开控制页、负责麦克风收音、扬声器发音、ASR/TTS、状态推进、数据库写入和工作人员队列。
- iMac M1：只通过局域网打开 `http://<拯救者局域网IP>:8010/particle-display`，作为观众展示屏。
- 服务启动必须绑定局域网地址：`0.0.0.0:8010`。
- iMac 不打开控制页，不请求麦克风，不负责发声。

注意：`/particle-display` 的 wake 按钮通过 `BroadcastChannel` 通知同源浏览器里的控制页。跨 iMac 和拯救者时，这个通知不会跨电脑生效。现场启动观众应使用拯救者控制页的 New / Start Voice，或把实体按钮接到拯救者。

## 迁移方式

推荐：

1. 当前 Mac 把代码提交并推送到 GitHub。
2. 拯救者从 GitHub `clone` 或 `pull`。
3. `.env` 通过 U 盘或手动安全复制到拯救者项目根目录，不提交到 GitHub。
4. 默认不复制 `data/have_some_ai.db`，让拯救者从空数据库开始。

只有需要保留当前编号、队列或历史记录时，才复制以下文件：

```text
data/have_some_ai.db
data/have_some_ai.db-wal
data/have_some_ai.db-shm
```

复制数据库前先停止服务，避免 WAL 文件处于写入中。

## Windows 首次安装

在拯救者上安装：

- Python 3.11+，推荐 Python 3.13 x64。
- Git。
- Codex 可选，用于现场继续排障。

拉代码：

```powershell
git clone <repo-url>
cd <repo-folder>
```

安装 Python 依赖并跑最小 API 验证：

```powershell
.\scripts\setup_windows.ps1
```

如果系统禁止运行 PowerShell 脚本，只对当前窗口放开：

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\setup_windows.ps1
```

## `.env` 检查

拯救者项目根目录必须有 `.env`。至少确认现场模式包含：

```env
ENTITY_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=...
ANTHROPIC_BASE_URL=...
ENTITY_LLM_MODEL=...
ENTITY_LLM_DISABLE_SYSTEM_PROXY=1

HAVE_SOME_AI_VOICE_PROVIDER=doubao
HAVE_SOME_AI_STT_MODE=asr_tts_stream
DOUBAO_API_KEY=...
DOUBAO_ASR_ENDPOINT=wss://openspeech.bytedance.com/api/v3/sauc/bigmodel_async
DOUBAO_ASR_RESOURCE_ID=volc.seedasr.sauc.duration
DOUBAO_TTS_ENDPOINT=wss://openspeech.bytedance.com/api/v3/tts/bidirection
DOUBAO_TTS_RESOURCE_ID=seed-icl-2.0
DOUBAO_TTS_SPEAKER_ZH=S_sd9II0522
DOUBAO_TTS_SPEAKER_EN=S_r98II0522
```

如果 `.env` 不存在，服务可以启动，但 LLM、ASR 或 TTS 会在实际交互时失败。

## 启动

在拯救者项目根目录运行：

```powershell
.\scripts\start_have_some_ai_windows.ps1
```

脚本会用以下等价命令启动服务：

```powershell
.\.venv\Scripts\python.exe scripts\start_have_some_ai.py --host 0.0.0.0 --port 8010
```

拯救者控制页：

```text
http://127.0.0.1:8010/
```

iMac 展示页：

```text
http://<拯救者局域网IP>:8010/particle-display
```

如果 iMac 打不开展示页，优先检查 Windows 防火墙。可在管理员 PowerShell 中允许 8010 端口：

```powershell
New-NetFirewallRule -DisplayName "Have Some Ai 8010" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8010 -Profile Private
```

同时确认拯救者和 iMac 在同一个局域网，并且 Windows 当前网络类型是 Private。

## 验收

在拯救者本机：

```powershell
Invoke-RestMethod http://127.0.0.1:8010/health
Invoke-RestMethod http://127.0.0.1:8010/api/v1/voice-config
Invoke-RestMethod http://127.0.0.1:8010/api/v1/display-state
```

浏览器验收：

- 拯救者打开 `http://127.0.0.1:8010/` 正常。
- 拯救者控制页能创建观众、请求麦克风、播放 TTS。
- iMac 打开 `http://<拯救者IP>:8010/particle-display` 正常。
- iMac 展示页不请求麦克风、不启动 `conversation-stream`、不写数据库。
- 完整跑一遍：Language Gate -> Food Gate -> 两道正式题 -> TTS/ASR -> 出餐结果 -> 工作人员队列。

## 常见问题

- iMac 能打开页面但 wake 按钮不创建观众：这是跨电脑拓扑的预期限制。用拯救者控制页或接在拯救者上的实体按钮启动。
- 拯救者控制页没有麦克风弹窗：必须用 `http://127.0.0.1:8010/` 或 `http://localhost:8010/` 打开控制页。
- iMac 打不开页面：检查服务是否用 `0.0.0.0` 启动、防火墙是否放行、两台电脑是否同网。
- 没声音或没识别：先检查 `/health` 和 `/api/v1/voice-config`，再检查 `.env`、浏览器麦克风权限、豆包 key 和后端日志。
