"""Evaluate local sdvx.in transcriptions; never fetch or redistribute charts.

Usage: uv run python tests/eval/eval_sdvxin.py [corpus/sdvxin]
"""

import argparse
from pathlib import Path

from ksmauto.sdvxin import report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', nargs='?', type=Path,
                        default=Path(__file__).resolve().parents[2] / 'corpus' / 'sdvxin')
    args = parser.parse_args()
    report(args.directory)


if __name__ == '__main__':
    main()
