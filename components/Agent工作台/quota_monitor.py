"""Import a browser-observed Claude quota snapshot. Does not control accounts."""
import argparse
import json
from pathlib import Path
from task_station.quota import QuotaStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, required=True)
    parser.add_argument('--data-dir', type=Path, default=Path(__file__).resolve().parent / 'data/station')
    args = parser.parse_args()
    if args.input.stat().st_size > 16384:
        raise ValueError('输入记录过大')
    value = json.loads(args.input.read_text(encoding='utf-8-sig'))
    result = QuotaStore(args.data_dir / 'claude-quota.json').save(value)
    print(json.dumps({k:result[k] for k in ('state','effective_state','checked_at','reset_at')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
