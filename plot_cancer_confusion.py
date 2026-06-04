"""
plot_cancer_confusion.py — 3x3 confusion matrix for cancer classes only

Uses test_results.csv (N_RUNS=3).
Filters to true cancer images (MEL / BCC / AKIEC) and compares against
the predicted cancer class (argmax of MEL, BCC, AKIEC probability columns).

Usage:
    python plot_cancer_confusion.py
"""

import os
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

CSV_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'test_results.csv')
OUT_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'confusion_cancer_only.png')

CLASSES = ['MEL', 'BCC', 'AKIEC']
LABELS  = ['Melanoma\n(MEL)', 'Basal Cell\nCarcinoma\n(BCC)', 'Actinic Keratosis\n(AKIEC)']


def main():
    if not os.path.exists(CSV_PATH):
        print(f'File not found: {CSV_PATH}')
        return

    df = pd.read_csv(CSV_PATH)

    # Keep only true cancer images
    df = df[df['true_class'].isin(CLASSES)].copy()
    print(f'Cancer images: {len(df)}  (MEL={len(df[df.true_class=="MEL"])}, '
          f'BCC={len(df[df.true_class=="BCC"])}, AKIEC={len(df[df.true_class=="AKIEC"])})')

    # Predicted class = argmax among cancer probability columns
    df['pred_class'] = df[CLASSES].idxmax(axis=1)

    # 3x3 confusion matrix
    cm = pd.crosstab(df['true_class'], df['pred_class'],
                     rownames=['True'], colnames=['Predicted'])
    for c in CLASSES:
        if c not in cm.columns: cm[c] = 0
        if c not in cm.index:   cm.loc[c] = 0
    cm = cm[CLASSES].reindex(CLASSES).fillna(0).astype(int)

    # Per-class recall
    recalls = {}
    for c in CLASSES:
        total = cm.loc[c].sum()
        recalls[c] = cm.loc[c, c] / total if total else 0

    overall_acc = np.diag(cm.values).sum() / cm.values.sum()

    print(f'\n{"─"*40}')
    for c in CLASSES:
        print(f'  {c:6s} recall : {recalls[c]*100:.1f}%')
    print(f'  Overall accuracy : {overall_acc*100:.1f}%')
    print(f'{"─"*40}\n')

    # ── Plot ─────────────────────────────────────────────────────
    fig = plt.figure(figsize=(11, 7), facecolor='#0f1923')
    gs  = gridspec.GridSpec(1, 2, width_ratios=[1.6, 1], wspace=0.08)
    ax_cm  = fig.add_subplot(gs[0])
    ax_met = fig.add_subplot(gs[1])

    mat = cm.values.astype(float)
    row_sums = mat.sum(axis=1, keepdims=True)
    pct = np.where(row_sums > 0, mat / row_sums * 100, 0)

    cmap = matplotlib.colormaps['RdYlGn']
    diag = np.eye(3, dtype=bool)
    cell_val = np.where(diag, pct / 100, 1 - pct / 100)

    n = 3
    for i in range(n):
        for j in range(n):
            color = cmap(cell_val[i, j])
            ax_cm.add_patch(plt.Rectangle((j, n - 1 - i), 1, 1, color=color, alpha=0.85))
            ax_cm.text(j + 0.5, n - 0.5 - i,
                       f'{int(mat[i, j])}\n({pct[i, j]:.0f}%)',
                       ha='center', va='center', fontsize=13, fontweight='bold',
                       color='white' if cell_val[i, j] < 0.55 else '#111')

    ax_cm.set_xlim(0, n); ax_cm.set_ylim(0, n)
    ax_cm.set_xticks([0.5, 1.5, 2.5])
    ax_cm.set_yticks([0.5, 1.5, 2.5])
    ax_cm.set_xticklabels([f'Pred\n{l}' for l in LABELS], color='white', fontsize=9)
    ax_cm.set_yticklabels([f'True\n{l}' for l in reversed(LABELS)],
                           color='white', fontsize=9, rotation=0, va='center')
    ax_cm.tick_params(length=0)
    ax_cm.set_facecolor('#0f1923')
    for spine in ax_cm.spines.values(): spine.set_visible(False)
    ax_cm.set_title('Cancer Class Confusion Matrix', color='white',
                    fontsize=13, fontweight='bold', pad=12)

    # Metrics panel
    ax_met.set_facecolor('#0f1923')
    ax_met.set_xlim(0, 1); ax_met.set_ylim(0, 1)
    ax_met.axis('off')

    colors_map = {'MEL': '#e74c3c', 'BCC': '#3498db', 'AKIEC': '#2ecc71'}
    descs      = {
        'MEL':   'Melanoma correctly\nidentified',
        'BCC':   'Basal Cell Carcinoma\ncorrectly identified',
        'AKIEC': 'Actinic Keratosis\ncorrectly identified',
    }

    y = 0.92
    for c in CLASSES:
        val   = recalls[c]
        color = colors_map[c]
        ax_met.text(0.05, y, c, color=color, fontsize=12, fontweight='bold', va='top')
        ax_met.text(0.05, y - 0.04, descs[c], color='#aaa', fontsize=8, va='top')
        bar_y = y - 0.105
        ax_met.add_patch(plt.Rectangle((0.05, bar_y), 0.88, 0.025, color='#1e2d3d', zorder=1))
        ax_met.add_patch(plt.Rectangle((0.05, bar_y), 0.88 * val, 0.025,
                                        color=color, alpha=0.9, zorder=2))
        ax_met.text(0.97, bar_y + 0.012, f'{val*100:.1f}%',
                    color='white', fontsize=11, fontweight='bold',
                    ha='right', va='center', zorder=3)
        y -= 0.26

    ax_met.add_patch(plt.Rectangle((0.05, 0.06), 0.88, 0.025, color='#1e2d3d', zorder=1))
    ax_met.add_patch(plt.Rectangle((0.05, 0.06), 0.88 * overall_acc, 0.025,
                                    color='#9b59b6', alpha=0.9, zorder=2))
    ax_met.text(0.05, 0.10, 'Overall Accuracy', color='#9b59b6',
                fontsize=10, fontweight='bold', va='bottom')
    ax_met.text(0.97, 0.06 + 0.012, f'{overall_acc*100:.1f}%',
                color='white', fontsize=11, fontweight='bold',
                ha='right', va='center', zorder=3)

    total = len(df)
    ax_met.text(0.05, 0.01,
                f'n = {total} cancer images  (MEL={len(df[df.true_class=="MEL"])}, '
                f'BCC={len(df[df.true_class=="BCC"])}, AKIEC={len(df[df.true_class=="AKIEC"])})',
                color='#666', fontsize=7.5, va='bottom')

    ax_met.set_title('Per-Class Recall', color='white', fontsize=13,
                     fontweight='bold', pad=12)

    fig.suptitle('Gemini API — Cancer Class Identification  [N_RUNS=3]\n'
                 'Predicted class = argmax(MEL, BCC, AKIEC)',
                 color='white', fontsize=13, fontweight='bold', y=0.98)

    plt.savefig(OUT_PATH, dpi=150, bbox_inches='tight', facecolor=fig.get_facecolor())
    print(f'Saved -> {OUT_PATH}')


if __name__ == '__main__':
    main()
