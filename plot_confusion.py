"""
plot_confusion.py — 从 test_results.csv 生成二分类混淆矩阵

癌症（MEL / BCC / AKIEC）合并为 Cancer
良性（NV / BKL / DF / VASC）合并为 Benign

使用方法：
    python plot_confusion.py
"""

import os
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_results.csv')
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'confusion_matrix.png')

CANCER_CLASSES = {'MEL', 'BCC', 'AKIEC'}


def to_binary(cls: str) -> str:
    return 'Cancer' if cls in CANCER_CLASSES else 'Benign'


def main():
    if not os.path.exists(CSV_PATH):
        print(f'找不到结果文件：{CSV_PATH}')
        print('请先运行 test_api_accuracy.py 生成测试结果。')
        return

    df = pd.read_csv(CSV_PATH)
    print(f'读取 {len(df)} 条记录')

    # 使用 isic_pred（7类中概率最高），更公平
    df['true_bin'] = df['true_class'].apply(to_binary)
    df['pred_bin'] = df['isic_pred'].apply(to_binary)

    # 计算混淆矩阵
    labels = ['Cancer', 'Benign']
    cm = pd.crosstab(df['true_bin'], df['pred_bin'],
                     rownames=['True'], colnames=['Predicted'])[labels].reindex(labels)
    cm = cm.fillna(0).astype(int)

    TP = cm.loc['Cancer', 'Cancer']
    FN = cm.loc['Cancer', 'Benign']
    FP = cm.loc['Benign', 'Cancer']
    TN = cm.loc['Benign', 'Benign']
    total = TP + FN + FP + TN

    sensitivity = TP / (TP + FN) if (TP + FN) else 0   # 癌症召回率
    specificity = TN / (TN + FP) if (TN + FP) else 0   # 良性识别率
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

    # ── 绘图 ──────────────────────────────────────────────────────
    fig = plt.figure(figsize=(10, 7), facecolor='#0f1923')
    gs  = gridspec.GridSpec(1, 2, width_ratios=[1.3, 1], wspace=0.05)

    ax_cm  = fig.add_subplot(gs[0])
    ax_met = fig.add_subplot(gs[1])

    # 混淆矩阵热力图
    colors = np.array([
        [TP, FN],
        [FP, TN],
    ], dtype=float)
    row_sums = colors.sum(axis=1, keepdims=True)
    pct = np.where(row_sums > 0, colors / row_sums * 100, 0)

    cmap = plt.cm.get_cmap('RdYlGn')
    diag_mask = np.eye(2, dtype=bool)
    cell_colors = np.where(diag_mask, pct / 100, 1 - pct / 100)

    for i in range(2):
        for j in range(2):
            color = cmap(cell_colors[i, j])
            ax_cm.add_patch(plt.Rectangle((j, 1 - i), 1, 1, color=color, alpha=0.85))
            count = colors[i, j]
            p     = pct[i, j]
            ax_cm.text(j + 0.5, 1.5 - i, f'{int(count)}\n({p:.1f}%)',
                       ha='center', va='center', fontsize=16, fontweight='bold',
                       color='white' if cell_colors[i, j] < 0.6 else '#111')

    ax_cm.set_xlim(0, 2)
    ax_cm.set_ylim(0, 2)
    ax_cm.set_xticks([0.5, 1.5])
    ax_cm.set_yticks([0.5, 1.5])
    ax_cm.set_xticklabels(['Predicted\nCancer', 'Predicted\nBenign'],
                           color='white', fontsize=11)
    ax_cm.set_yticklabels(['True\nBenign', 'True\nCancer'],
                           color='white', fontsize=11, rotation=90, va='center')
    ax_cm.tick_params(length=0)
    ax_cm.set_facecolor('#0f1923')
    for spine in ax_cm.spines.values():
        spine.set_visible(False)
    ax_cm.set_title('Confusion Matrix (Binary)', color='white', fontsize=13,
                    fontweight='bold', pad=12)

    # 指标面板
    ax_met.set_facecolor('#0f1923')
    ax_met.set_xlim(0, 1)
    ax_met.set_ylim(0, 1)
    ax_met.axis('off')

    metrics = [
        ('Sensitivity',  sensitivity, '#e74c3c',
         'Cancer correctly detected\n(TP / all true cancer)'),
        ('Specificity',  specificity, '#2ecc71',
         'Benign correctly rejected\n(TN / all true benign)'),
        ('Precision',    precision,   '#3498db',
         'Of predicted cancer,\nhow many are real'),
        ('F1 Score',     f1,          '#f39c12',
         'Harmonic mean of\nSensitivity & Precision'),
        ('Accuracy',     accuracy,    '#9b59b6',
         'Overall correct\npredictions'),
    ]

    y_start = 0.95
    for name, val, color, desc in metrics:
        ax_met.text(0.05, y_start, name, color=color,
                    fontsize=11, fontweight='bold', va='top')
        ax_met.text(0.05, y_start - 0.035, desc, color='#aaa',
                    fontsize=7.5, va='top')
        bar_y = y_start - 0.09
        ax_met.add_patch(plt.Rectangle((0.05, bar_y), 0.88, 0.022,
                                        color='#1e2d3d', zorder=1))
        ax_met.add_patch(plt.Rectangle((0.05, bar_y), 0.88 * val, 0.022,
                                        color=color, alpha=0.9, zorder=2))
        ax_met.text(0.97, bar_y + 0.011, f'{val*100:.1f}%',
                    color='white', fontsize=10, fontweight='bold',
                    ha='right', va='center', zorder=3)
        y_start -= 0.19

    ax_met.text(0.05, 0.02, f'n = {total} images  ·  Cancer: {TP+FN}  ·  Benign: {FP+TN}',
                color='#666', fontsize=8, va='bottom')
    ax_met.set_title('Metrics', color='white', fontsize=13,
                     fontweight='bold', pad=12)

    fig.suptitle('Gemini API — Binary Cancer Detection\n(Cancer = MEL + BCC + AKIEC)',
                 color='white', fontsize=14, fontweight='bold', y=0.98)

    plt.savefig(OUT_PATH, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    print(f'图表已保存 → {OUT_PATH}')
    plt.show()


if __name__ == '__main__':
    main()
