"""
test_api_accuracy.py — Gemini API 在 ISIC 数据集上的准确率测试

使用方法：
    cd skin-cancer-detect
    python test_api_accuracy.py

结果保存到 test_results.csv，支持中断后续跑（已测过的图片自动跳过）。
"""

import os
import sys
import csv
import time
import random
from collections import defaultdict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from analyzer import analyze_file

# ══════════════════════════════════════════════════════════════════
#  配置
# ══════════════════════════════════════════════════════════════════
SAMPLES_PER_CLASS = 20       # 每个类别随机抽取的图片数；None = 用全部
DELAY_SECONDS     = 2.5      # API 调用间隔（秒），避免触发频率限制
RANDOM_SEED       = 42

# 要测试的数据集（True = 启用）
USE_DATASETS = {
    'ISIC2018-Train': False,   # 10015 张，采样建议关闭或用小 SAMPLES_PER_CLASS
    'ISIC2018-Val':   False,   # 193 张
    'ISIC2018-Test':  True,    # 1512 张，官方测试集，最有参考价值
    'ISIC2019-Train': False,   # 25331 张
}

OUTPUT_CSV = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_results.csv')
# ══════════════════════════════════════════════════════════════════

BASE_DATA    = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ISIC_CLASSES = ['MEL', 'NV', 'BCC', 'AKIEC', 'BKL', 'DF', 'VASC']

DATASET_CONFIGS = {
    'ISIC2018-Train': {
        'img_dir':   os.path.join(BASE_DATA, 'ISIC2018', 'ISIC2018_Task3_Training_Input'),
        'csv':       os.path.join(BASE_DATA, 'ISIC2018', 'ISIC2018_Task3_Training_GroundTruth',
                                  'ISIC2018_Task3_Training_GroundTruth.csv'),
        'class_map': {c: c for c in ISIC_CLASSES},
    },
    'ISIC2018-Val': {
        'img_dir':   os.path.join(BASE_DATA, 'ISIC2018', 'ISIC2018_Task3_Validation_Input'),
        'csv':       os.path.join(BASE_DATA, 'ISIC2018', 'ISIC2018_Task3_Validation_GroundTruth',
                                  'ISIC2018_Task3_Validation_GroundTruth.csv'),
        'class_map': {c: c for c in ISIC_CLASSES},
    },
    'ISIC2018-Test': {
        'img_dir':   os.path.join(BASE_DATA, 'ISIC2018', 'ISIC2018_Task3_Test_Input'),
        'csv':       os.path.join(BASE_DATA, 'ISIC2018', 'ISIC2018_Task3_Test_GroundTruth',
                                  'ISIC2018_Task3_Test_GroundTruth.csv'),
        'class_map': {c: c for c in ISIC_CLASSES},
    },
    'ISIC2019-Train': {
        'img_dir':   os.path.join(BASE_DATA, 'ISIC2019', 'ISIC_2019_Training_Input'),
        'csv':       os.path.join(BASE_DATA, 'ISIC2019', 'ISIC_2019_Training_GroundTruth.csv'),
        # AK + SCC 均映射到 AKIEC；UNK 跳过
        'class_map': {'MEL': 'MEL', 'NV': 'NV', 'BCC': 'BCC',
                      'AK': 'AKIEC', 'BKL': 'BKL', 'DF': 'DF',
                      'VASC': 'VASC', 'SCC': 'AKIEC', 'UNK': None},
    },
}


# ── 工具函数 ──────────────────────────────────────────────────────

def load_samples(name: str) -> list[tuple[str, str]]:
    """从 CSV 加载 (img_path, true_class) 列表。"""
    cfg       = DATASET_CONFIGS[name]
    df        = pd.read_csv(cfg['csv'])
    class_map = cfg['class_map']
    img_dir   = cfg['img_dir']
    samples   = []

    for _, row in df.iterrows():
        true_class = None
        for col, mapped in class_map.items():
            if col in row.index and row[col] == 1.0:
                true_class = mapped
                break
        if true_class is None:
            continue

        img_name = row['image']
        for ext in ('.jpg', '.JPG', '.jpeg', '.JPEG', '.png', '.PNG'):
            path = os.path.join(img_dir, img_name + ext)
            if os.path.exists(path):
                samples.append((path, true_class))
                break

    return samples


def stratified_sample(samples: list, n: int | None) -> list:
    """每个类别取 n 张（n=None 则全取）。"""
    by_class = defaultdict(list)
    for path, cls in samples:
        by_class[cls].append(path)

    result = []
    for cls in ISIC_CLASSES:
        paths = by_class.get(cls, [])
        chosen = paths if n is None else random.sample(paths, min(n, len(paths)))
        result.extend((p, cls) for p in chosen)

    random.shuffle(result)
    return result


def load_done(csv_path: str) -> set[str]:
    """读取已完成的图片路径（用于断点续跑）。"""
    if not os.path.exists(csv_path):
        return set()
    with open(csv_path, newline='', encoding='utf-8') as f:
        return {row['img_path'] for row in csv.DictReader(f)}


def analyze_with_retry(path: str, retries: int = 3, wait: float = 10.0) -> dict | None:
    for attempt in range(retries):
        try:
            return analyze_file(path)
        except Exception as e:
            if attempt < retries - 1:
                print(f'    [retry {attempt+1}] {e}')
                time.sleep(wait)
            else:
                print(f'    [failed] {e}')
                return None


def isic_top(all_probs: dict) -> str:
    """只在 7 个 ISIC 类别中取概率最高的。"""
    return max(ISIC_CLASSES, key=lambda c: all_probs.get(c, 0.0))


# ── 主流程 ────────────────────────────────────────────────────────

def main():
    random.seed(RANDOM_SEED)

    # 收集样本
    print('Loading datasets...')
    all_samples = []
    for name, enabled in USE_DATASETS.items():
        if not enabled:
            continue
        samples = load_samples(name)
        sampled = stratified_sample(samples, SAMPLES_PER_CLASS)
        print(f'  {name}: {len(sampled)} images sampled')
        all_samples.extend(sampled)

    if not all_samples:
        print('No datasets enabled. Edit USE_DATASETS in the config.')
        sys.exit(1)

    # 断点续跑
    done = load_done(OUTPUT_CSV)
    todo = [(p, c) for p, c in all_samples if p not in done]
    print(f'\nTotal: {len(all_samples)} | Already done: {len(done)} | To run: {len(todo)}')

    # 费用 & 时间预估
    est_minutes = len(todo) * (DELAY_SECONDS + 3) / 60
    print(f'Estimated time: ~{est_minutes:.0f} min  |  API calls: {len(todo)}')
    print(f'Results → {OUTPUT_CSV}')
    input('\nPress Enter to start (Ctrl+C to cancel)...\n')

    # CSV 写入
    is_new = not os.path.exists(OUTPUT_CSV)
    csv_file = open(OUTPUT_CSV, 'a', newline='', encoding='utf-8')
    fieldnames = ['img_path', 'true_class', 'top1_pred', 'isic_pred',
                  'top1_correct', 'isic_correct', 'top1_conf'] + ISIC_CLASSES
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    if is_new:
        writer.writeheader()

    # 统计
    top1_results  = defaultdict(lambda: {'correct': 0, 'total': 0})
    isic_results  = defaultdict(lambda: {'correct': 0, 'total': 0})

    # 读取已有结果到统计中
    if done:
        with open(OUTPUT_CSV, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                cls = row['true_class']
                top1_results[cls]['total'] += 1
                isic_results[cls]['total'] += 1
                if row['top1_correct'] == 'True':
                    top1_results[cls]['correct'] += 1
                if row['isic_correct'] == 'True':
                    isic_results[cls]['correct'] += 1

    try:
        for i, (img_path, true_class) in enumerate(todo, 1):
            fname = os.path.basename(img_path)
            print(f'[{i:>4}/{len(todo)}] {fname}  (true: {true_class})', end='  ', flush=True)

            result = analyze_with_retry(img_path)

            if result is None:
                print('ERROR - skipped')
                time.sleep(DELAY_SECONDS)
                continue

            top1_pred   = result['top_prediction']
            isic_pred   = isic_top(result['all_probs'])
            top1_correct = top1_pred == true_class
            isic_correct = isic_pred == true_class
            top1_conf    = round(result['all_probs'].get(top1_pred, 0), 2)

            top1_results[true_class]['total']   += 1
            isic_results[true_class]['total']   += 1
            top1_results[true_class]['correct'] += int(top1_correct)
            isic_results[true_class]['correct'] += int(isic_correct)

            status = '✓' if isic_correct else f'✗ (pred:{isic_pred})'
            print(status)

            row = {
                'img_path':     img_path,
                'true_class':   true_class,
                'top1_pred':    top1_pred,
                'isic_pred':    isic_pred,
                'top1_correct': top1_correct,
                'isic_correct': isic_correct,
                'top1_conf':    top1_conf,
                **{c: round(result['all_probs'].get(c, 0), 2) for c in ISIC_CLASSES},
            }
            writer.writerow(row)
            csv_file.flush()

            time.sleep(DELAY_SECONDS)

    except KeyboardInterrupt:
        print('\nInterrupted — progress saved.')
    finally:
        csv_file.close()

    # 汇总
    print('\n' + '═' * 62)
    print(f'{"Class":<10} {"Top-1 Acc":>12} {"ISIC Acc":>12} {"N":>6}')
    print('─' * 62)

    top1_total_c = top1_total_n = 0
    isic_total_c = isic_total_n = 0

    for cls in ISIC_CLASSES:
        t1 = top1_results[cls]
        ic = isic_results[cls]
        if t1['total'] == 0:
            continue
        t1_acc = t1['correct'] / t1['total'] * 100
        ic_acc = ic['correct'] / ic['total'] * 100
        print(f'{cls:<10} {t1_acc:>11.1f}% {ic_acc:>11.1f}% {t1["total"]:>6}')
        top1_total_c += t1['correct']; top1_total_n += t1['total']
        isic_total_c += ic['correct']; isic_total_n += ic['total']

    print('─' * 62)
    if top1_total_n:
        print(f'{"Overall":<10} {top1_total_c/top1_total_n*100:>11.1f}% '
              f'{isic_total_c/isic_total_n*100:>11.1f}% {top1_total_n:>6}')
    print('═' * 62)
    print()
    print('Top-1 Acc  : model 最高概率预测 == 真实类别（含新增16类）')
    print('ISIC Acc   : 7个ISIC类别中概率最高的 == 真实类别（更公平）')
    print(f'Results saved → {OUTPUT_CSV}')


if __name__ == '__main__':
    main()
