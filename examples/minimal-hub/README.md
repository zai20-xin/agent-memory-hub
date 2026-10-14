# 最小可运行示例（minimal-hub）

> 目标：不装任何东西，用仓库内现成文件跑通 **接入 → 审计 → 心跳** 全流程。
> 所有画像数据均为虚构假数据；目录内的软链（`user-profile.md`、`hygiene-protocol.md`）本身就是「软链接入」的活示范。

## 目录结构

```
examples/minimal-hub/
├── hub/                          # 迷你记忆中枢
│   ├── user-profile.md           # SSOT 真身（假数据，1277B）
│   ├── user-profile-quick.md     # quick 精简版
│   ├── agent-registry.md         # Agent 台账
│   ├── hygiene-protocol.md       # → 软链指向 ../../docs/hygiene-protocol.md
│   └── archive/audit-log.md      # 哨兵心跳台账
└── agents/
    ├── agent-a/                  # 主力 agent（MEMORY.md + 画像软链）
    └── agent-b/                  # 第二主力 agent（MEMORY.md + 画像软链）
```

## 三步跑通

```bash
cd examples/minimal-hub

# 第 1 步 · 看接入：两个 agent 通过软链共享同一份 SSOT 真身
ls -l agents/agent-a/user-profile.md agents/agent-b/user-profile.md
readlink agents/agent-a/user-profile.md   # → ../../hub/user-profile.md

# 第 2 步 · 跑审计（哨兵的日频动作）
python3 ../../tools/memory-audit.py --hub hub \
    --link "agent-a=agents/agent-a/user-profile.md" \
    --link "agent-b=agents/agent-b/user-profile.md" \
    --hot  "agent-a-MEMORY=agents/agent-a/MEMORY.md" \
    --hot  "agent-b-MEMORY=agents/agent-b/MEMORY.md"
# 预期：全部 🟢，退出码 0

# 第 3 步 · 写心跳（全绿也留痕，格式见 hub/archive/audit-log.md）
echo "$(date +%F) 全绿 🟡0 🔴0" >> hub/archive/audit-log.md
```

## 故意留的"教学细节"

- 两条画像软链用**相对路径**（`../../hub/user-profile.md`）——整个目录可随意搬动，软链不断
- `hub/hygiene-protocol.md` 是指向仓库 `docs/` 的软链——协议只维护一份；若要把本示例单独拷走使用，把它改成复制文件即可
- 审计命令里 `--link` / `--hot` 用 `NAME=PATH` 显式登记——**审计范围和你的 agent 清单一致，不多测也不少测**

## 在自己的环境复用

1. 把 `hub/` 复制为你的 `~/.agents/memory/`，把假画像换成真画像
2. 按 `templates/agent-registry.md` 登记你的 agent，建软链：`ln -s ~/.agents/memory/user-profile.md ~/.你的agent/user-profile.md`
3. 用第 2 步的命令模板换成你的路径，挂到每日定时任务（哨兵）
4. 每周跑一次周检（模板见 `templates/weekly-review.md`）
