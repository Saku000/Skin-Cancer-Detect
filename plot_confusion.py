"""
plot_confusion.py — 从 test_results*.csv 生成二分类混淆矩阵

自动识别 CSV 格式：
  旧格式（7类）: 含 isic_pred 列，用 top-1 类别映射到 Cancer/Benign
  新格式（3类）: 含 cancer_total + pred_bin 列，用阈值判断

使用方法：
    python plot_confusion.py                          # 默认 test_results_n1.csv
    python plot_confusion.py test_results.csv         # 指定文件
    python plot_confusion.py test_results_n1.csv
"""

import os
import sys
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

CANCER_CLASSES = {'MEL', 'BCC', 'AKIEC'}

# ── CSV 路径 ──────────────────────────────────────────────────────
if len(sys.argv) > 1:
    CSV_PATH = sys.argv[1]
    if not os.path.isabs(CSV_PATH):
        CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), CSV_PATH)
else:
    CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_results_n1.csv')

OUT_PATH = os.path.splitext(CSV_PATH)[0] + '_confusion.png'


def to_binary(cls: str) -> str:
    return 'Cancer' if cls in CANCER_CLASSES else 'Benign'


def main():
    if not os.path.exists(CSV_PATH):
        print(f'找不到结果文件：{CSV_PATH}')
        print('请先运行 test_api_accuracy.py 生成测试结果。')
        return

    df = pd.read_csv(CSV_PATH)

    # 过滤掉 skipped 的图片
    if 'skipped' in df.columns:
        skipped_n = df['skipped'].astype(str).str.lower().eq('true').sum()
        df = df[df['skipped'].astype(str).str.lower() != 'true'].copy()
        print(f'读取 {len(df)} 条有效记录（跳过 {skipped_n} 张质量不合格图片）')
    else:
        print(f'读取 {len(df)} 条记录')

    # ── 判断格式，统一生成 true_bin / pred_bin ──
    if 'pred_bin' in df.columns:
        # 新格式：直接用现成列
        df['true_bin'] = df['true_class'].apply(to_binary)
        print(f'格式：新（3类，cancer_total 阈值判断）')
        threshold_note = f'Cancer threshold: cancer_total ≥ 15%'
    else:
        # 旧格式：用 isic_pred top-1 映射
        df['true_bin'] = df['true_class'].apply(to_binary)
        df['pred_bin'] = df['isic_pred'].apply(to_binary)
        print(f'格式：旧（7类，top-1 映射）')
        threshold_note = 'Predicted class mapped to Cancer/Benign'

    # ── 混淆矩阵 ─────────────────────────────────────────────────
    labels = ['Cancer', 'Benign']
    cm = pd.crosstab(df['true_bin'], df['pred_bin'],
                     rownames=['True'], colnames=['Predicted'])
    for lbl in labels:
        if lbl not in cm.columns: cm[lbl] = 0
        if lbl not in cm.index:   cm.loc[lbl] = 0
    cm = cm[labels].reindex(labels).fillna(0).astype(int)

    TP = cm.loc['Cancer', 'Cancer']
    FN = cm.loc['Cancer', 'Benign']
    FP = cm.loc['Benign', 'Cancer']
    TN = cm.loc['Benign', 'Benign']
    total = TP + FN + FP + TN

    sensitivity = TP / (TP + FN) if (TP + FN) else 0
    specificity = TN / (TN + FP) if (TN + FP) else 0
    precision   = TP / (TP + FP) if (TP + FP) else 0
    f1          = 2 * precision * sensitivity / (precision + sensitivity) if (precision + sensitivity) else 0
    accuracy    = (TP + TN) / total if total else 0

    print(f'\n{"─"*40}')
    print(f'  Sensitivity (cancer recall) : {sensitivity*100:.1f}%')
    print(f'  Specificity (benign recall) : {specificity*100:.1f}%')
    print(f'  Precision                   : {precision*100:.1f}%')
    print(f'  F1 Score                    : {f1:.3f}')
    print(f'  Overall Accuracy            : {accuracy*100:.1f}%')
    print(f'{"─"*40}\n')

    # ── 绘图（只显示 True Cancer 那行）────────────────────────────
    fig = plt.figure(figsize=(10, 5), facecolor='#0f1923')
    gs  = gridspec.GridSpec(1, 2, width_ratios=[1.3, 1], wspace=0.05)
    ax_cm  = fig.add_subplot(gs[0])
    ax_met = fig.add_subplot(gs[1])

    cmap = matplotlib.colormaps['RdYlGn']

    # 1×2: [TP, FN]
    cancer_total_n = TP + FN
    tp_pct = TP / cancer_total_n * 100 if cancer_total_n else 0
    fn_pct = FN / cancer_total_n * 100 if cancer_total_n else 0

    cell_data = [(TP, tp_pct, cmap(tp_pct / 100)),
                 (FN, fn_pct, cmap(1 - fn_pct / 100))]

    for j, (count, pct_val, color) in enumerate(cell_data):
        ax_cm.add_patch(plt.Rectangle((j, 0), 1, 1, color=color, alpha=0.85))
        ax_cm.text(j + 0.5, 0.5, f'{int(count)}\n({pct_val:.1f}%)',
                   ha='center', va='center', fontsize=20, fontweight='bold',
                   color='white' if pct_val < 60 else '#111')

    ax_cm.set_xlim(0, 2); ax_cm.set_ylim(0, 1)
    ax_cm.set_xticks([0.5, 1.5]); ax_cm.set_yticks([0.5])
    ax_cm.set_xticklabels(['Predicted\nCancer', 'Predicted\nBenign'], color='white', fontsize=12)
    ax_cm.set_yticklabels(['True\nCancer'], color='white', fontsize=12,
                           rotation=90, va='center')
    ax_cm.tick_params(length=0)
    ax_cm.set_facecolor('#0f1923')
    for spine in ax_cm.spines.values(): spine.set_visible(False)
    ax_cm.set_title('Cancer Detection Rate', color='white', fontsize=13,
                    fontweight='bold', pad=12)

    # 指标面板
    ax_met.set_facecolor('#0f1923')
    ax_met.set_xlim(0, 1); ax_met.set_ylim(0, 1)
    ax_met.axis('off')

    metrics = [
        ('Sensitivity',  sensitivity, '#e74c3c', 'Cancer correctly detected\n(TP / all true cancer)'),
        ('Precision',    precision,   '#3498db', 'Of predicted cancer,\nhow many are real'),
        ('F1 Score',     f1,          '#f39c12', 'Harmonic mean of\nSensitivity & Precision'),
    ]

    y_start = 0.88
    for name, val, color, desc in metrics:
        ax_met.text(0.05, y_start, name, color=color, fontsize=11, fontweight='bold', va='top')
        ax_met.text(0.05, y_start - 0.05, desc, color='#aaa', fontsize=7.5, va='top')
        bar_y = y_start - 0.115
        ax_met.add_patch(plt.Rectangle((0.05, bar_y), 0.88, 0.028, color='#1e2d3d', zorder=1))
        ax_met.add_patch(plt.Rectangle((0.05, bar_y), 0.88 * val, 0.028, color=color, alpha=0.9, zorder=2))
        ax_met.text(0.97, bar_y + 0.014, f'{val*100:.1f}%',
                    color='white', fontsize=11, fontweight='bold', ha='right', va='center', zorder=3)
        y_start -= 0.28

    csv_name = os.path.basename(CSV_PATH)
    ax_met.text(0.05, 0.02,
                f'n = {TP+FN} cancer images  ·  {threshold_note}',
                color='#666', fontsize=7.5, va='bottom')
    ax_met.set_title('Metrics', color='white', fontsize=13, fontweight='bold', pad=12)

    fig.suptitle(f'Gemini API — Cancer Detection  [{csv_name}]\n'
                 f'(Cancer = MEL + BCC + AKIEC)',
                 color='white', fontsize=13, fontweight='bold', y=1.02)

    plt.savefig(OUT_PATH, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    print(f'图表已保存 → {OUT_PATH}')


if __name__ == '__main__':
    main()
