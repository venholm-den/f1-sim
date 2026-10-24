import pandas as pd

from scripts.benchmark_degradation_stages import screen_diagnostics


def test_q_cannot_pass_on_loss_improvement_when_qualifying_order_wins():
    rows, baselines = [], []
    for stage in ('PRE', 'FP2', 'Q'):
        for round_ in range(1, 7):
            for variant, error in [('legacy', 4.), ('single_degradation_v1', 3.5)]:
                rows.append(dict(year=2025, round=round_, session=stage, split='previously_seen_diagnostic',
                    variant=variant, finish_mae=error, loss=error+.1, win_brier=.03, podium_brier=.08,
                    top10_brier=.1, dnf_brier=.12))
            baselines.append(dict(year=2025, round=round_, session=stage, split='previously_seen_diagnostic',
                                  variant='grid_order', finish_mae=3.))
    decisions = screen_diagnostics(pd.DataFrame(rows), pd.DataFrame(baselines))
    assert all(d['passes_diagnostic_screen'] for d in decisions[:2])
    assert decisions[2]['reasons'] == ['does_not_beat_qualifying_order']
    assert all(d['fresh_races'] == 0 and not d['promotion_approved'] for d in decisions)
    incomplete = pd.DataFrame(rows).drop(index=1)
    decision = screen_diagnostics(incomplete, pd.DataFrame(baselines))[0]
    assert not decision['passes_diagnostic_screen']
    assert 'insufficient_matched_diagnostic_coverage' in decision['reasons']
