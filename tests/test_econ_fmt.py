# -*- coding: utf-8 -*-
"""econ_results.fmt()/_num() 순수 함수 단위 테스트. 네트워크 없음.

입력: 없음
출력: 없음(pytest 결과)
실행: pytest tests/test_econ_fmt.py
관련: econ_results.py
"""
import pytest

from econ_results import fmt


@pytest.mark.parametrize("v,unit,potency,expected", [
    (54, None, "K", "54K"),
    (2.1, "%", None, "2.1%"),
    (-60.2, "$", "B", "-$60.2B"),
    (55.6, None, None, "55.6"),
    (None, "%", None, None),
    (3.0, "%", None, "3%"),
])
def test_fmt(v, unit, potency, expected):
    assert fmt(v, unit, potency) == expected
