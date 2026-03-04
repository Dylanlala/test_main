#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将 analog_devices_data_final 下「有信号链」的方案目录完整复制到 analog_devices_signal_data。
有信号链：complete_data.json 中存在 signal_chains.chains 且长度 > 0。
"""
import argparse
import json
import os
import shutil
import sys

# 项目根
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = os.path.join(PROJECT_ROOT, "analog_devices_data_final", "analog_devices_data_final")
DEFAULT_DST = os.path.join(PROJECT_ROOT, "analog_devices_signal_data")


def has_signal_chains(solution_dir: str) -> bool:
    """若 complete_data.json 存在且 signal_chains.chains 非空则返回 True。"""
    path = os.path.join(solution_dir, "complete_data.json")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        sc = data.get("signal_chains") or {}
        chains = sc.get("chains") or []
        return len(chains) > 0
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="复制有信号链的方案目录到 analog_devices_signal_data")
    parser.add_argument(
        "--src",
        type=str,
        default=DEFAULT_SRC,
        help="源目录（方案列表所在目录，默认 analog_devices_data_final/analog_devices_data_final）",
    )
    parser.add_argument(
        "--dst",
        type=str,
        default=DEFAULT_DST,
        help="目标根目录（默认 analog_devices_signal_data）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="仅列出将要复制的目录，不实际复制",
    )
    args = parser.parse_args()

    src_root = os.path.abspath(args.src)
    dst_root = os.path.abspath(args.dst)

    if not os.path.isdir(src_root):
        print(f"错误：源目录不存在: {src_root}")
        sys.exit(1)

    # 收集所有有信号链的方案目录名
    solution_names = []
    for name in sorted(os.listdir(src_root)):
        path = os.path.join(src_root, name)
        if not os.path.isdir(path):
            continue
        if has_signal_chains(path):
            solution_names.append(name)

    print(f"共发现 {len(solution_names)} 个含信号链的方案（源: {src_root}）")
    if not solution_names:
        print("没有需要复制的目录。")
        return 0

    for name in solution_names:
        print(f"  - {name}")

    if args.dry_run:
        print("\n[--dry-run] 未执行复制。")
        return 0

    os.makedirs(dst_root, exist_ok=True)
    ok = 0
    err = 0
    for name in solution_names:
        src_dir = os.path.join(src_root, name)
        dst_dir = os.path.join(dst_root, name)
        try:
            if os.path.exists(dst_dir):
                shutil.rmtree(dst_dir)
            shutil.copytree(src_dir, dst_dir)
            print(f"已复制: {name}")
            ok += 1
        except Exception as e:
            print(f"复制失败 {name}: {e}")
            err += 1

    print(f"\n完成: 成功 {ok}, 失败 {err}，目标目录: {dst_root}")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
