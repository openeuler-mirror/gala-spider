from typing import List

import numpy as np

from cause_inference.model import AnomalyTrend


def trend(hist_data: List[float], win_len=None) -> AnomalyTrend:
    if not win_len:
        win_len = len(hist_data) // 2

    if np.mean(hist_data[:win_len]) < np.mean(hist_data[win_len:]):
        return AnomalyTrend.RISE
    elif np.mean(hist_data[:win_len]) > np.mean(hist_data[win_len:]):
        return AnomalyTrend.FALL
    else:
        return AnomalyTrend.DEFAULT


def check_trend(expect: AnomalyTrend, real: AnomalyTrend) -> bool:
    if expect and real and expect != real:
        if expect != AnomalyTrend.DEFAULT:
            return False
    return True


def parse_trend(trend_s) -> AnomalyTrend:
    if trend_s == 'rise':
        return AnomalyTrend.RISE
    elif trend_s == 'fall':
        return AnomalyTrend.FALL
    else:
        return AnomalyTrend.DEFAULT
