"""Dilution measurement shared by the Europe/US pool scripts.

The dilution gate compares the last and first reported diluted share counts.
Capital IQ's "Weighted Avg. Diluted Shares Out." series for a company that
listed (IPO / reverse merger / re-denomination) inside the 10-slot window
often starts with a stub: the first slot holds a pre-listing or part-year
weighted count (e.g. Angling Direct 4.65m -> 45.4m, Trainline 1.1m -> 427m),
so last/first - 1 reads as hundreds of percent although nothing was diluted.

Rule (2026-10-26): if one of the first two year-on-year steps of the
share-count series is a jump of >= 2.0x, the counts before the jump are a
pre-listing stub and are ignored; dilution is measured from the first
post-jump count to the last. It applies only when >= 3 counts remain after
the jump, so a thin series is never "rescued" on two points. A company that
keeps issuing shares after listing (Angling Direct: 45.4m -> 77.5m, +71%)
still fails the gate, and a company without such a jump is untouched.
"""

STUB_JUMP = 2.0
STUB_WINDOW = 2
MIN_POST_POINTS = 3


def measure_dilution(shares_hist):
    """shares_hist: list with None for missing slots. Returns
    (dilution, ipo_adjusted); dilution is None when < 2 usable counts."""
    s = [v for v in shares_hist if v is not None]
    if len(s) < 2:
        return None, False
    for i in range(min(STUB_WINDOW, len(s) - 1)):
        if s[i + 1] / s[i] >= STUB_JUMP:
            post = s[i + 1:]
            if len(post) >= MIN_POST_POINTS:
                return post[-1] / post[0] - 1, True
            break
    return s[-1] / s[0] - 1, False
