#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
删除 analog_devices_data_test 下「无产品且无信号链」的方案目录。
保留条件：至少有一类产品（hardware/evaluation/reference/satellite_components）或至少有一条信号链。
"""
import json
import os
import shutil
import sys

# 项目根
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_ROOT = os.path.join(PROJECT_ROOT, "analog_devices_data_test")


def has_useful_content(complete_data: dict) -> bool:
    """有产品列表或信号链则视为有用。"""
    # 产品
    for key in ("hardware_products", "evaluation_products", "reference_products"):
        lst = complete_data.get(key)
        if isinstance(lst, list) and len(lst) > 0:
            return True
    # 卫星等页面的组件
    satellite = complete_data.get("satellite_components")
    if isinstance(satellite, list) and len(satellite) > 0:
        return True
    # 信号链
    chains = complete_data.get("signal_chains") or {}
    if isinstance(chains, dict):
        clist = chains.get("chains")
        if isinstance(clist, list) and len(clist) > 0:
            return True
    return False


def main():
    if not os.path.isdir(DATA_ROOT):
        print(f"目录不存在: {DATA_ROOT}", file=sys.stderr)
        sys.exit(1)

    to_delete = []
    for name in os.listdir(DATA_ROOT):
        solution_dir = os.path.join(DATA_ROOT, name)
        if not os.path.isdir(solution_dir):
            continue
        complete_path = os.path.join(solution_dir, "complete_data.json")
        if not os.path.isfile(complete_path):
            continue
        try:
            with open(complete_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            continue
        if not has_useful_content(data):
            to_delete.append((name, solution_dir))

    if not to_delete:
        print("没有需要删除的空方案目录。")
        return

    print(f"将删除以下 {len(to_delete)} 个无产品且无信号链的方案目录：")
    for name, path in to_delete:
        print(f"  - {name}")

    do_yes = "--yes" in sys.argv or "-y" in sys.argv
    if not do_yes:
        confirm = input("确认删除？(y/N): ").strip().lower()
        if confirm != "y":
            print("已取消。")
            return

    for name, path in to_delete:
        try:
            shutil.rmtree(path)
            print(f"已删除: {name}")
        except Exception as e:
            print(f"删除失败 {name}: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()
