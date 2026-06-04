"""
test_api_accuracy.py — Gemini API 在 ISIC 数据集上的准确率测试

使用方法：
    cd skin-cancer-detect
    python test_api_accuracy.py

结果保存到 OUTPUT_CSV，支持中断后续跑（已测过的图片自动跳过）。

Binary prediction rule:
    cancer_total >= CANCER_THRESHOLD → predicted Cancer
    cancer_total <  CANCER_THRESHOLD → predicted Benign
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
N_RUNS_PER_IMAGE  = 1        # 每张图跑几次（1 = 快速/省钱；3 = 更稳定）
CANCER_THRESHOLD  = 15       # cancer_total >= 此值 → 预测为 Cancer
SAMPLES_PER_CLASS = 20       # 每个类别随机抽取的图片数；None = 用全部
DELAY_SECONDS     = 2.5      # API 调用间隔（秒）
RANDOM_SEED       = 42

USE_DATASETS = {
    'ISIC2018-Train': False,
    'ISIC2018-Val':   False,
    'ISIC2018-Test':  True,
    'ISIC2019-Train': False,
}

OUTPUT_CSV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    f'test_results_n{N_RUNS_PER_IMAGE}.csv'
)
# ══════════════════════════════════════════════════════════════════

BASE_DATA    = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'data'))
ISIC_CLASSES = ['MEL', 'NV', 'BCC', 'AKIEC', 'BKL', 'DF', 'VASC']
CANCER_CLASSES = {'MEL', 'BCC', 'AKIEC'}
CANCER_COLS    = ['MEL', 'BCC', 'AKIEC']

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
        'class_map': {'MEL': 'MEL', 'NV': 'NV', 'BCC': 'BCC',
                      'AK': 'AKIEC', 'BKL': 'BKL', 'DF': 'DF',
                      'VASC': 'VASC', 'SCC': 'AKIEC', 'UNK': None},
    },
}


def load_samples(name: str) -> list[tuple[str, str]]:
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
    if not os.path.exists(csv_path):
        return set()
    with open(csv_path, newline='', encoding='utf-8') as f:
        return {row['img_path'] for row in csv.DictReader(f)}


def analyze_with_retry(path: str, n_runs: int, retries: int = 3, wait: float = 10.0) -> dict | None:
    for attempt in range(retries):
        try:
            return analyze_file(path, n_runs=n_runs)
        except Exception as e:
            if attempt < retries - 1:
                print(f'    [retry {attempt+1}] {e}')
                time.sleep(wait)
            else:
                print(f'    [failed] {e}')
                return None


def to_binary(cls: str) -> str:
    return 'Cancer' if cls in CANCER_CLASSES else 'Benign'


def main():
    random.seed(RANDOM_SEED)

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

    done = load_done(OUTPUT_CSV)
    todo = [(p, c) for p, c in all_samples if p not in done]
    print(f'\nTotal: {len(all_samples)} | Already done: {len(done)} | To run: {len(todo)}')
    print(f'N_RUNS_PER_IMAGE = {N_RUNS_PER_IMAGE}  |  CANCER_THRESHOLD = {CANCER_THRESHOLD}%')

    est_minutes = len(todo) * (DELAY_SECONDS + 3) / 60
    print(f'Estimated time: ~{est_minutes:.0f} min  |  API calls: ~{len(todo) * N_RUNS_PER_IMAGE}')
    print(f'Results → {OUTPUT_CSV}')
    print('Starting...\n')

    is_new = not os.path.exists(OUTPUT_CSV)
    csv_file = open(OUTPUT_CSV, 'a', newline='', encoding='utf-8')
    fieldnames = ['img_path', 'true_class', 'true_bin', 'top_pred',
                  'cancer_total', 'pred_bin', 'correct_bin',
                  'skipped', 'lighting_ok', 'framing_ok'] + CANCER_COLS
    writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
    if is_new:
        writer.writeheader()

    correct_bin = 0
    total_bin   = 0
    skipped_n   = 0

    # 统计已有结果
    if done:
        with open(OUTPUT_CSV, newline='', encoding='utf-8') as f:
            for row in csv.DictReader(f):
                if row.get('skipped') == 'True':
                    skipped_n += 1
                    continue
                total_bin += 1
                if row.get('correct_bin') == 'True':
                    correct_bin += 1

    try:
        for i, (img_path, true_class) in enumerate(todo, 1):
            fname    = os.path.basename(img_path)
            true_bin = to_binary(true_class)
            print(f'[{i:>4}/{len(todo)}] {fname}  (true: {true_class}/{true_bin})', end='  ', flush=True)

            result = analyze_with_retry(img_path, n_runs=N_RUNS_PER_IMAGE)

            if result is None:
                print('ERROR - skipped')
                time.sleep(DELAY_SECONDS)
                continue

            if result.get('skipped'):
                reason = []
                if not result.get('lighting_ok', True): reason.append('lighting')
                if not result.get('framing_ok',  True): reason.append('framing')
                print(f'SKIPPED ({", ".join(reason)})')
                skipped_n += 1
                writer.writerow({
                    'img_path':    img_path,
                    'true_class':  true_class,
                    'true_bin':    true_bin,
                    'top_pred':    '',
                    'cancer_total': '',
                    'pred_bin':    '',
                    'correct_bin': '',
                    'skipped':     True,
                    'lighting_ok': result.get('lighting_ok', ''),
                    'framing_ok':  result.get('framing_ok', ''),
                    **{c: '' for c in CANCER_COLS},
                })
                csv_file.flush()
                time.sleep(DELAY_SECONDS)
                continue

            cancer_total = result['cancer_total']
            pred_bin     = 'Cancer' if cancer_total >= CANCER_THRESHOLD else 'Benign'
            is_correct   = pred_bin == true_bin
            correct_bin += int(is_correct)
            total_bin   += 1

            status = 'OK' if is_correct else f'WRONG (pred:{pred_bin}, total:{cancer_total}%)'
            print(status)

            writer.writerow({
                'img_path':     img_path,
                'true_class':   true_class,
                'true_bin':     true_bin,
                'top_pred':     result['top_prediction'],
                'cancer_total': cancer_total,
                'pred_bin':     pred_bin,
                'correct_bin':  is_correct,
                'skipped':      False,
                'lighting_ok':  result.get('lighting_ok', True),
                'framing_ok':   result.get('framing_ok', True),
                **{c: round(result['cancer'].get(c, 0), 2) for c in CANCER_COLS},
            })
            csv_file.flush()
            time.sleep(DELAY_SECONDS)

    except KeyboardInterrupt:
        print('\nInterrupted — progress saved.')
    finally:
        csv_file.close()

    print('\n' + '═' * 50)
    print(f'  Binary accuracy : {correct_bin}/{total_bin} = '
          f'{correct_bin/total_bin*100:.1f}%' if total_bin else '  No results.')
    print(f'  Skipped (quality gate): {skipped_n}')
    print('═' * 50)
    print(f'Results saved → {OUTPUT_CSV}')
    print(f'Run plot_confusion.py to generate the confusion matrix.')


if __name__ == '__main__':
    main()
