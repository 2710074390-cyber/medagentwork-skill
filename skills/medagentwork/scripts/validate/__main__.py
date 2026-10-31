"""
scripts.validate.__main__ — 支持 python -m scripts.validate 运行

用法:
  python -m scripts.validate --batch batch005
  python -m scripts.validate --file path/to/file.json
  python -m scripts.validate --batch batch004 --verbose
"""
import sys
import argparse
from pathlib import Path

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

from . import validate_file, validate_batch


def main():
    parser = argparse.ArgumentParser(
        description="选项设计机械化校验器 — HC-7 子规则硬编码检测"
    )
    parser.add_argument("--batch", "-b", help="批次ID（如 batch005）")
    parser.add_argument("--file", "-f", help="单个文件路径")
    parser.add_argument("--mode", "-m", choices=['basic', 'full'], default='full',
                        help='校验模式: basic=R1-R9+B1（快速）, full=R1-R9+B1+R10-R13+JS1+S3（完整，默认）')
    parser.add_argument("--verbose", "-v", action="store_true", help="显示通过题目")
    args = parser.parse_args()

    if not args.batch and not args.file:
        parser.print_help()
        sys.exit(2)

    summary = None

    if args.file:
        summary = validate_file(args.file, mode=args.mode, verbose=args.verbose)
    elif args.batch:
        summary = validate_batch(args.batch, mode=args.mode, verbose=args.verbose)

    # 门禁口径：FAIL>0 才阻断；WARN 只记录，不阻断交付（与 README/runbook 的
    # “FAIL==0 才放行”一致）。退出码 1 仅代表存在 FAIL，避免把 WARN 误判为阻断；
    # 文件不存在/未解析到题目属于脚本/数据错误，退出 2。
    if summary is None:
        sys.exit(2)
    if summary['fail'] > 0:
        print("\n提示: 存在 FAIL 项，退出码 1；修复后重跑。")
        sys.exit(1)
    if summary['warn'] > 0:
        print("\n提示: 仅存在 WARN，按门禁口径不阻断放行（退出码 0）。")
    sys.exit(0)


if __name__ == '__main__':
    main()
