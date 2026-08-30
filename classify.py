# -*- coding: utf-8 -*-
import os
import sys
import json
import shutil
import argparse
from pathlib import Path

# 颜色定义
class Colors:
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    ENDC = "\033[0m"
    BOLD = "\033[1m"

def cprint(text, color=Colors.ENDC, bold=False):
    prefix = Colors.BOLD if bold else ""
    print(f"{prefix}{color}{text}{Colors.ENDC}")

def load_rules(rules_path):
    with open(rules_path, "r", encoding="utf-8") as f:
        return json.load(f)

# 需要排除的文件/目录
EXCLUDE_NAMES = {
    "classify.py", "rules.json", "classification_report.md",
    "settings.local.json", "settings.json", "素材清单.md",
    "test_sim", "__pycache__"
}
EXCLUDE_EXTENSIONS = {".py", ".json", ".md"}

def scan_directory(source_dir, case_name=None):
    files = []
    source_path = Path(source_dir)
    for item in source_path.rglob("*"):
        if item.is_file():
            rel_path = item.relative_to(source_path)
            # 排除归档目录
            if "归档" in rel_path.parts:
                continue
            # 排除指定的文件/目录
            if item.name in EXCLUDE_NAMES:
                continue
            # 排除脚本文件（可配置是否跳过）
            if item.suffix.lower() in EXCLUDE_EXTENSIONS:
                continue
            # 限定案件名
            if case_name and case_name not in str(rel_path):
                continue
            files.append({
                "name": item.name,
                "full_path": str(item),
                "rel_path": str(rel_path),
                "extension": item.suffix.lower()
            })
    return files

def classify_file(filename, rules):
    for cat in rules["categories"]:
        for keyword in cat["keywords"]:
            if keyword in filename:
                return cat["name"], cat["target_path"]
    return rules["default_category"]["name"], rules["default_category"]["target_path"]

def step1_scan_statistics(files):
    cprint("\n" + "="*60, Colors.BLUE, bold=True)
    cprint("第1步：扫描统计", Colors.BLUE, bold=True)
    cprint("="*60 + "\n", Colors.BLUE)
    ext_count = {}
    for f in files:
        ext = f["extension"] or "(无扩展名)"
        ext_count[ext] = ext_count.get(ext, 0) + 1
    cprint(f"共扫描到 {len(files)} 个文件\n", Colors.GREEN, bold=True)
    cprint("文件类型分布：", bold=True)
    for ext, count in sorted(ext_count.items(), key=lambda x: -x[1]):
        cprint(f"  {ext:20s} : {count:3d} 个")
    return ext_count

def step2_preview(files, rules, manual_overrides):
    cprint("\n" + "="*60, Colors.BLUE, bold=True)
    cprint("第2步：分类预览", Colors.BLUE, bold=True)
    cprint("="*60 + "\n", Colors.BLUE)
    classified = []
    for i, f in enumerate(files):
        filename = f["name"]
        if i in manual_overrides:
            if manual_overrides[i] == "skip":
                category, target = "保持原样", "不移动"
            else:
                category, target = manual_overrides[i]["category"], manual_overrides[i]["target"]
        else:
            category, target = classify_file(filename, rules)
        classified.append({
            "index": i,
            "filename": filename,
            "category": category,
            "target": target,
            "full_path": f["full_path"]
        })
    print(f"\n{'序号':<6}{'文件名':<45}{'分类':<15}{'目标路径'}")
    print("-" * 100)
    for c in classified:
        display_name = c["filename"][:42] + "..." if len(c["filename"]) > 45 else c["filename"]
        cprint(f"{c['index']:<6}{display_name:<45}{c['category']:<15}{c['target']}")
    return classified

def step3_confirm_execute(classified, dry_run=True):
    cprint("\n" + "="*60, Colors.BLUE, bold=True)
    cprint("第3步：确认执行", Colors.BLUE, bold=True)
    cprint("="*60 + "\n", Colors.BLUE)
    to_move = [c for c in classified if c["category"] != "保持原样"]
    skip = [c for c in classified if c["category"] == "保持原样"]
    cprint(f"待复制文件: {len(to_move)} 个", Colors.YELLOW, bold=True)
    cprint(f"保持原样:   {len(skip)} 个", Colors.GREEN)
    cprint(f"总计:       {len(classified)} 个\n")
    if dry_run:
        cprint("【DRY-RUN 模式】仅显示预览，不实际复制文件\n", Colors.YELLOW, bold=True)
    while True:
        prompt = "输入 y 执行复制 | n 退出 | r 重新预览: " if not dry_run else "输入 y 确认预览 | n 退出 | r 重新预览: "
        user_input = input(prompt).strip().lower()
        if user_input == "y":
            return True, to_move
        elif user_input == "n":
            return False, []
        elif user_input == "r":
            return "retry", []

def copy_files(to_move, source_dir, dry_run=True):
    results = {"success": 0, "skipped": 0, "failed": 0, "details": []}
    for item in to_move:
        target_dir = Path(source_dir) / item["target"]
        target_path = target_dir / item["filename"]
        if target_path.exists():
            base = Path(item["filename"]).stem
            ext = Path(item["filename"]).suffix
            counter = 1
            while target_path.exists():
                new_name = f"{base}_{counter}{ext}"
                target_path = target_dir / new_name
                counter += 1
        if dry_run:
            results["success"] += 1
            results["details"].append({
                "filename": item["filename"],
                "from": item["full_path"],
                "to": str(target_path),
                "status": "success"
            })
        else:
            try:
                target_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(item["full_path"], str(target_path))
                results["success"] += 1
                results["details"].append({
                    "filename": item["filename"],
                    "from": item["full_path"],
                    "to": str(target_path),
                    "status": "success"
                })
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "filename": item["filename"],
                    "from": item["full_path"],
                    "to": str(target_path),
                    "status": "failed",
                    "error": str(e)
                })
    return results

def generate_report(results, output_path):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("# 分类报告\n\n")
        f.write("## 摘要\n\n")
        f.write(f"- 成功: {results['success']} 个\n")
        f.write(f"- 跳过: {results['skipped']} 个\n")
        f.write(f"- 失败: {results['failed']} 个\n\n")
        f.write("## 详细列表\n\n")
        f.write("| 文件名 | 状态 | 目标路径 |\n")
        f.write("|--------|------|----------|\n")
        for d in results["details"]:
            f.write(f"| {d['filename']} | {d['status']} | {d.get('to', 'N/A')} |\n")
    return output_path

def main():
    parser = argparse.ArgumentParser(description="法律材料自动分类脚本")
    parser.add_argument("--apply", action="store_true", help="执行真实复制（默认dry-run）")
    parser.add_argument("--case", type=str, help="限定案件名")
    parser.add_argument("--rules", type=str, default="rules.json", help="规则文件路径")
    parser.add_argument("--source", type=str, default=".", help="源目录")
    args = parser.parse_args()

    rules_path = Path(args.source) / args.rules
    if not rules_path.exists():
        cprint(f"错误: 规则文件不存在: {rules_path}", Colors.RED)
        sys.exit(1)

    rules = load_rules(rules_path)
    files = scan_directory(args.source, args.case)
    if not files:
        cprint("未扫描到任何文件", Colors.RED)
        sys.exit(1)

    step1_scan_statistics(files)
    input("\n按回车继续...")

    manual_overrides = {}
    while True:
        classified = step2_preview(files, rules, manual_overrides)
        cprint("\n操作说明:", bold=True)
        cprint("  输入序号+新分类  - 调整该文件归类")
        cprint("  输入s+序号       - 保持原样")
        cprint("  输入c            - 确认继续")
        cprint("  输入q            - 退出")

        user_input = input("\n请输入: ").strip()

        if user_input.lower() == "c":
            break
        elif user_input.lower() == "q":
            sys.exit(0)
        elif user_input.lower().startswith("s"):
            try:
                idx = int(user_input[1:]) - 1
                manual_overrides[idx] = "skip"
            except:
                cprint("输入格式错误", Colors.RED)
        elif user_input and user_input[0].isdigit():
            parts = user_input.split()
            if len(parts) >= 2:
                try:
                    idx = int(parts[0]) - 1
                    new_category = parts[1]
                    all_categories = [c["name"] for c in rules["categories"]] + [rules["default_category"]["name"]]
                    if new_category in all_categories:
                        for cat in rules["categories"]:
                            if cat["name"] == new_category:
                                manual_overrides[idx] = {"category": new_category, "target": cat["target_path"]}
                                break
                        else:
                            manual_overrides[idx] = {"category": new_category, "target": rules["default_category"]["target_path"]}
                except:
                    cprint("输入格式错误", Colors.RED)

    dry_run = not args.apply
    while True:
        confirmed, to_move = step3_confirm_execute(classified, dry_run)
        if confirmed == "retry":
            continue
        if confirmed:
            results = copy_files(to_move, args.source, dry_run)
            cprint("\n" + "="*60, Colors.GREEN, bold=True)
            cprint("执行完成", Colors.GREEN, bold=True)
            cprint("="*60, Colors.GREEN)
            cprint(f"成功: {results['success']} 个", Colors.GREEN)
            if results["failed"] > 0:
                cprint(f"失败: {results['failed']} 个", Colors.RED)
            report_path = Path(args.source) / "classification_report.md"
            generate_report(results, report_path)
            cprint(f"\n报告已生成: {report_path}", Colors.BLUE)
            break
        else:
            cprint("已取消执行", Colors.YELLOW)
            sys.exit(0)

if __name__ == "__main__":
    main()