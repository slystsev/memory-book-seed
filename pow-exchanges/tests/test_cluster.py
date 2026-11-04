import unittest
from datetime import datetime, timedelta

from powx.cluster import M, cluster

T0 = datetime(2024, 1, 3, 10)


def m(id, src, tier, side, h, ua=None, ru=None, copy=False):
    return M(id=id, source_id=src, tier=tier, side=side, published_at=T0 + timedelta(hours=h),
             n_to_ua=ua, n_to_ru=ru, is_copy=copy, url=f"u{id}")


class ClusterTest(unittest.TestCase):
    def test_two_sides_one_exchange(self):
        [ev] = cluster([m(1, "koord", 1, "ua", 0, ua=230), m(2, "mod", 1, "ru", 1, ua=230, ru=248),
                        m(3, "wiki", 3, "neutral", 2, ua=230, ru=248)])
        self.assertEqual((ev.n_to_ua, ev.n_to_ru, ev.primary.id, ev.source_count), (230, 248, 1, 3))

    def test_different_numbers_same_day_are_two_events(self):
        self.assertEqual(len(cluster([m(1, "a", 1, "ua", 0, ua=100), m(2, "b", 1, "ua", 3, ua=40)])), 2)

    def test_far_apart_are_two_events(self):
        self.assertEqual(len(cluster([m(1, "a", 1, "ua", 0, ua=100), m(2, "a", 1, "ua", 72, ua=100)])), 2)

    def test_numberless_mention_attaches_but_never_founds(self):
        evs = cluster([m(1, "a", 1, "ua", 0, ua=50), m(2, "b", 2, "ua", 5), m(3, "b", 2, "ua", 200)])
        self.assertEqual([[x.id for x in e.mentions] for e in evs], [[1, 2]])

    def test_primary_skips_copies_and_prefers_tier1(self):
        [ev] = cluster([m(1, "news", 2, "ua", 0, ua=90), m(2, "koord", 1, "ua", 1, ua=90, copy=True),
                        m(3, "zel", 1, "ua", 2, ua=90)])
        self.assertEqual(ev.primary.id, 3)

    def test_tolerance_absorbs_updates(self):
        [ev] = cluster([m(1, "a", 1, "ua", 0, ua=150), m(2, "b", 1, "ua", 2, ua=151),
                        m(3, "c", 2, "ua", 3, ua=151)])
        self.assertEqual(ev.n_to_ua, 151)

    def test_side_specific_consensus(self):
        # UA official says 84 to Ukraine; RU says 85 to Ukraine (within tol). UA side wins for to_ua.
        [ev] = cluster([m(1, "mod", 1, "ru", 0, ua=85, ru=84), m(2, "koord", 1, "ua", 1, ua=84)])
        self.assertEqual((ev.n_to_ua, ev.n_to_ru), (84, 84))
