#!/usr/bin/env python3
"""memory-audit — 跨 Agent 记忆审计（agent-memory-hub 配套工具）

设计定位：**只读检查，不写任何文件**。心跳台账的写入由调用方（哨兵 agent）完成，
脚本保持"只报告、不动手"，避免自动化误改记忆系统。

检查项：
  1. SSOT 画像在位且非空（<1KB 严重；超软线默认 48KB 告警）
  2. 画像软链健康：解析指向 SSOT 真身、不是实体文件、缺失告警
  3. quick 精简版在位（缺失或近空告警）
  4. 各 agent 热记忆体积红线（>8KB 告警，>20KB 严重，阈值可调）
  5. 化石扫描（"原记...有误 / 已推翻 / 删除线"，扫 SSOT + quick + 显式列入的热记忆）

用法示例：
  # 只查中枢内部（SSOT / quick / 化石），不配置任何 agent
  python3 memory-audit.py --hub ~/.agents/memory

  # 完整模式：登记各 agent 的画像软链与热记忆
  python3 memory-audit.py --hub ~/.agents/memory \
      --link "agent-a=~/.agent-a/user-profile.md" \
      --link "agent-b=~/.agent-b/user-profile.md" \
      --hot  "agent-a-MEMORY=~/.agent-a/MEMORY.md"

退出码：0=全绿，1=有告警(🟡)，2=有严重问题(🔴)
"""
import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

VERSION = "3.3"

FOSSIL_PATTERNS = [
    re.compile(r"原记.{0,30}(有误|错误)"),
    re.compile(r"已推翻"),
    re.compile(r"~~(?!~~)"),
]
REVISION_TAG = re.compile(r"\[修正[:：]\s*\d{4}-\d{2}-\d{2}\]")


def md5(p: Path) -> str:
    return hashlib.md5(p.read_bytes()).hexdigest()


def parse_named(arg_value: str):
    """解析 NAME=PATH，路径支持 ~ 展开。"""
    if "=" not in arg_value:
        raise argparse.ArgumentTypeError(f"格式应为 NAME=PATH，收到: {arg_value!r}")
    name, _, raw = arg_value.partition("=")
    return name.strip(), Path(os.path.expanduser(raw.strip()))


def scan_fossils(label: str, path: Path, warns: list) -> None:
    if not path.is_file():
        return
    text = path.read_text(errors="ignore")
    for i, line in enumerate(text.splitlines(), 1):
        if REVISION_TAG.search(line):
            continue  # [修正: 日期] 标签行是唯一跳过信号
        for pat in FOSSIL_PATTERNS:
            if pat.search(line):
                warns.append(f"[{label}] L{i} 疑似化石: {line.strip()[:60]}...")
                break


def check_ssot(hub: Path, args, issues: list, warns: list) -> Path:
    ssot = hub / args.profile
    if not ssot.is_file():
        issues.append(f"SSOT 不存在: {ssot}")
    elif ssot.stat().st_size < 1000:
        issues.append(f"SSOT 异常过小: {ssot.stat().st_size}B")
    else:
        size = ssot.stat().st_size
        soft = args.ssot_warn_kb * 1024
        if size > soft:
            warns.append(f"SSOT {size}B 超 {args.ssot_warn_kb}KB 软线 → 周检评估瘦身")
        if not args.quiet:
            print(f"🟢 SSOT 在位: {ssot} ({size}B)")
    return ssot


def check_links(links, ssot: Path, issues: list, warns: list, quiet: bool) -> None:
    if not links:
        if not quiet:
            print("ℹ️ 未配置 --link，跳过软链检查（首次接入请按 README 登记）")
        return
    ssot_resolved = ssot.resolve() if ssot.exists() else None
    for name, link in links:
        if not link.is_symlink() and not link.exists():
            warns.append(f"[{name}] 画像缺失（无软链也无文件）: {link}")
            continue
        if link.is_symlink():
            target = link.resolve()
            if ssot_resolved and target != ssot_resolved:
                warns.append(f"[{name}] 软链未指向中枢真身: {link} -> {target}")
            elif link.exists() and ssot.exists() and md5(link) != md5(ssot):
                issues.append(f"[{name}] 软链内容与 SSOT 不一致（真身被改未同步?）")
            elif not quiet:
                print(f"🟢 [{name}] 软链正确且内容一致")
        else:
            issues.append(f"[{name}] 是实体文件不是软链（应改为软链接入）: {link}")


def check_quick(hub: Path, args, warns: list, quiet: bool) -> None:
    quick = hub / args.quick
    if not quick.is_file() or quick.stat().st_size < 200:
        warns.append(f"quick 版画像缺失或近空: {quick}")
    elif not quiet:
        print(f"🟢 quick 版在位: {quick.stat().st_size}B")


def check_hot(hot_list, args, issues: list, warns: list, quiet: bool) -> None:
    for name, p in hot_list:
        if not p.is_file():
            warns.append(f"[{name}] 不存在: {p}")
            continue
        size = p.stat().st_size
        if size > args.hot_critical_kb * 1024:
            issues.append(f"[{name}] {size}B 超严重线 {args.hot_critical_kb}KB → 必须瘦身手术")
        elif size > args.hot_limit_kb * 1024:
            warns.append(f"[{name}] {size}B 超红线 {args.hot_limit_kb}KB → 触发瘦身")
        elif not quiet:
            print(f"🟢 [{name}] {size}B 体积合规")


def main() -> int:
    ap = argparse.ArgumentParser(description="跨 Agent 记忆审计（只读，不写任何文件）")
    ap.add_argument("--hub", default="~/.agents/memory", help="记忆中枢目录（默认 ~/.agents/memory）")
    ap.add_argument("--profile", default="user-profile.md", help="SSOT 文件名（默认 user-profile.md）")
    ap.add_argument("--quick", default="user-profile-quick.md", help="精简版文件名")
    ap.add_argument("--link", action="append", default=[], metavar="NAME=PATH",
                    help="画像软链，可重复传入，如 --link \"agent-a=~/.agent-a/user-profile.md\"")
    ap.add_argument("--hot", action="append", default=[], metavar="NAME=PATH",
                    help="agent 热记忆文件，可重复传入，如 --hot \"agent-a=~/.agent-a/MEMORY.md\"")
    ap.add_argument("--ssot-warn-kb", type=int, default=48, help="SSOT 体积软线（KB，默认 48）")
    ap.add_argument("--hot-limit-kb", type=int, default=8, help="热记忆红线（KB，默认 8）")
    ap.add_argument("--hot-critical-kb", type=int, default=20, help="热记忆严重线（KB，默认 20）")
    ap.add_argument("--no-fossil", action="store_true", help="关闭化石扫描")
    ap.add_argument("--quiet", action="store_true", help="只输出告警与汇总")
    args = ap.parse_args()

    hub = Path(os.path.expanduser(args.hub))
    issues, warns = [], []

    if not args.quiet:
        print(f"== memory-audit v{VERSION} ==")
        print(f"hub: {hub}")

    ssot = check_ssot(hub, args, issues, warns)
    check_links([parse_named(x) for x in args.link], ssot, issues, warns, args.quiet)
    check_quick(hub, args, warns, args.quiet)
    check_hot([parse_named(x) for x in args.hot], args, issues, warns, args.quiet)

    if not args.no_fossil:
        scan_fossils("SSOT", ssot, warns)
        scan_fossils("quick", hub / args.quick, warns)
        for name, p in [parse_named(x) for x in args.hot]:
            scan_fossils(name, p, warns)

    print()
    for w in warns:
        print(f"🟡 {w}")
    for i in issues:
        print(f"🔴 {i}")
    print(f"\n结果: 🟡告警={len(warns)} 🔴严重={len(issues)}")
    return 2 if issues else (1 if warns else 0)


if __name__ == "__main__":
    sys.exit(main())
