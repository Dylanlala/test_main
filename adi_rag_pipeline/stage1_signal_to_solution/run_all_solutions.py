#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对指定数据根目录下的**所有解决方案目录**依次执行：Step1（图片→器件+流向）+ Step2（器件↔CSV 映射）。
适用于批量处理 50+ 方案，与 signal_chain_image_to_csv_mapping.py 单方案用法互补。

用法:
  # 处理 analog_test1 下所有含 complete_data.json 的子目录（默认）
  python run_all_solutions.py

  # 指定数据根
  python run_all_solutions.py --data-root D:/analog_solutions

  # 仅 Step1（只生成 description，不调 LLM 建映射）
  python run_all_solutions.py --step1-only

  # 仅 Step2（用已有 signal_chain_descriptions/*.txt 建映射）
  python run_all_solutions.py --step2-only

  # 只处理前 2 个方案（试跑）
  python run_all_solutions.py --limit 2

  # 只处理指定方案名（逗号分隔）
  python run_all_solutions.py --solutions "下一代气象雷达,eVTOL BMS和电源"
"""
import argparse
import os
import re
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from adi_rag_pipeline.config import ANALOG_DATA_ROOT
from adi_rag_pipeline.stage1_signal_to_solution.signal_chain_image_to_csv_mapping import (
    DESCRIPTION_SUBDIR,
    MAPPING_JSON_FILENAME,
    run_step1,
    run_step2,
)


def get_solution_dirs(data_root: str, require_complete_data: bool = True) -> list:
    """返回数据根下所有「解决方案目录」名列表（子目录名）。若 require_complete_data 为 True 则仅含存在 complete_data.json 的目录。"""
    if not os.path.isdir(data_root):
        return []
    out = []
    for name in sorted(os.listdir(data_root)):
        if name.startswith("."):
            continue
        path = os.path.join(data_root, name)
        if not os.path.isdir(path):
            continue
        if require_complete_data and not os.path.isfile(os.path.join(path, "complete_data.json")):
            continue
        out.append(name)
    return out


def run_one_solution(
    data_root: str,
    solution_name: str,
    step1_only: bool,
    step2_only: bool,
    no_download: bool,
) -> tuple:
    """
    对单个方案执行 Step1（可选）+ Step2（可选）。返回 (success: bool, message: str)。
    """
    solution_dir = os.path.join(data_root, solution_name.strip())
    if not os.path.isdir(solution_dir):
        return False, f"目录不存在: {solution_dir}"

    signal_chains_dir = os.path.join(solution_dir, "signal_chains")
    csv_dir = os.path.join(solution_dir, "exports_signal_chain_csv")
    descriptions_dir = os.path.join(solution_dir, DESCRIPTION_SUBDIR)
    mapping_json_path = os.path.join(solution_dir, MAPPING_JSON_FILENAME)

    step1_results = []

    if not step2_only:
        try_download = not no_download
        step1_results = run_step1(
            solution_dir,
            signal_chains_dir,
            descriptions_dir,
            try_download=try_download,
        )
        if step1_only:
            return True, f"Step1 完成，生成 {len(step1_results)} 条描述"

    if step2_only:
        if os.path.isdir(descriptions_dir):
            for fname in os.listdir(descriptions_dir):
                if fname.endswith("_description.txt"):
                    name_no_ext = fname.replace("_description.txt", "")
                    match = re.search(r"signal_chain[_\s\-]*(\d+)", name_no_ext, re.I)
                    chain_id = match.group(1) if match else name_no_ext
                    step1_results.append(
                        (
                            name_no_ext + ".png",
                            os.path.join(descriptions_dir, fname),
                            chain_id,
                        )
                    )
        if not step1_results:
            return False, "未找到已有描述文件，请先运行 Step1"

    if step1_results:
        try:
            run_step2(solution_dir, csv_dir, step1_results, mapping_json_path)
            return True, f"Step1+Step2 完成，{len(step1_results)} 条链已写映射"
        except Exception as e:
            return False, str(e)

    if not step2_only and not step1_results:
        return True, "未找到图片，跳过（无 Step1 输出）"
    return True, "完成"


def main():
    parser = argparse.ArgumentParser(
        description="对数据根下所有解决方案目录执行 Step1（图→描述）+ Step2（描述↔CSV 映射）"
    )
    parser.add_argument(
        "--data-root",
        default=ANALOG_DATA_ROOT,
        help="解决方案根目录，其下每个子目录为一个方案（默认 analog_test1）",
    )
    parser.add_argument("--step1-only", action="store_true", help="仅执行 Step1：图片→器件+流向描述")
    parser.add_argument("--step2-only", action="store_true", help="仅执行 Step2：用已有描述建映射")
    parser.add_argument("--no-download", action="store_true", help="不尝试从 complete_data.json 下载图片")
    parser.add_argument(
        "--require-complete-data",
        action="store_true",
        default=True,
        help="只处理含 complete_data.json 的子目录（默认 True）",
    )
    parser.add_argument(
        "--no-require-complete-data",
        action="store_false",
        dest="require_complete_data",
        help="处理所有子目录，不要求 complete_data.json",
    )
    parser.add_argument("--limit", type=int, default=0, help="最多处理 N 个方案（0=不限制）")
    parser.add_argument(
        "--solutions",
        type=str,
        default="",
        help="只处理这些方案名，逗号分隔，如 \"下一代气象雷达,eVTOL BMS和电源\"",
    )
    args = parser.parse_args()

    data_root = os.path.abspath(args.data_root)
    if not os.path.isdir(data_root):
        print(f"错误：数据根目录不存在: {data_root}")
        sys.exit(1)

    solution_names = get_solution_dirs(data_root, require_complete_data=args.require_complete_data)
    if args.solutions.strip():
        want = [s.strip() for s in args.solutions.split(",") if s.strip()]
        solution_names = [n for n in solution_names if n in want]
        if not solution_names:
            print(f"未找到指定方案（在数据根下且符合筛选）: {want}")
            sys.exit(1)
    if args.limit > 0:
        solution_names = solution_names[: args.limit]

    print(f"数据根: {data_root}")
    print(f"待处理方案数: {len(solution_names)}")
    print(f"方案列表: {solution_names}")
    if args.step1_only:
        print("模式: 仅 Step1（图片→描述）")
    elif args.step2_only:
        print("模式: 仅 Step2（已有描述→映射）")
    else:
        print("模式: Step1 + Step2")
    print("-" * 60)

    ok, fail, skip = 0, 0, 0
    for i, name in enumerate(solution_names, 1):
        print(f"\n[{i}/{len(solution_names)}] 方案: {name}")
        try:
            success, msg = run_one_solution(
                data_root=data_root,
                solution_name=name,
                step1_only=args.step1_only,
                step2_only=args.step2_only,
                no_download=args.no_download,
            )
            if success:
                ok += 1
                print(f"  ✅ {msg}")
            else:
                fail += 1
                print(f"  ❌ {msg}")
        except Exception as e:
            fail += 1
            print(f"  ❌ 异常: {e}")

    print("-" * 60)
    print(f"完成: 成功 {ok}, 失败 {fail}, 共 {len(solution_names)} 个方案。")


if __name__ == "__main__":
    main()
