import unittest
from powx.prefilter import is_candidate, text_hash


class PrefilterTest(unittest.TestCase):
    def test_candidates_in_three_languages(self):
        for t in ["Відбувся 51-й обмін полоненими. Додому повертаються 84 українці.",
                  "Возвращены 150 российских военнослужащих",
                  "Russia and Ukraine swapped 1,000 POWs",
                  "Україні повернули тіла 909 загиблих",
                  "Ще 12 наших захисників вдома"]:
            self.assertTrue(is_candidate(t), t)

    def test_unrelated(self):
        self.assertFalse(is_candidate("Обстріл Харкова: є поранені"))
        self.assertFalse(is_candidate(""))

    def test_hash_ignores_case_whitespace_urls(self):
        self.assertEqual(text_hash("Обмін  відбувся https://t.me/x/1"), text_hash("обмін відбувся"))
