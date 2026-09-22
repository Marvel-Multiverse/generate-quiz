from __future__ import annotations

import unittest

from src.duplicate_detector import DuplicateDetector, canonical_question


class DuplicateDetectorTests(unittest.TestCase):
    def test_normalization_removes_case_accents_punctuation_and_extra_spaces(self):
        left = canonical_question("  Qual É o nome verdadeiro do Homem-Aranha?! ")
        right = canonical_question("qual e o nome verdadeiro do homem aranha")
        self.assertEqual(left, right)

    def test_detects_exact_normalized_duplicate(self):
        detector = DuplicateDetector(["Qual é o nome verdadeiro do Homem-Aranha?"])
        self.assertTrue(detector.is_duplicate("Qual e o nome verdadeiro do Homem Aranha"))

    def test_detects_simple_near_duplicate(self):
        detector = DuplicateDetector(["Qual é o nome verdadeiro do Homem-Aranha?"])
        self.assertTrue(detector.is_duplicate("Qual o verdadeiro nome do Homem Aranha?"))

    def test_accepts_different_question(self):
        detector = DuplicateDetector(["Qual é o nome verdadeiro do Homem-Aranha?"])
        self.assertFalse(detector.is_duplicate("Qual equipe tem como integrante o Ciclope?"))


if __name__ == "__main__":
    unittest.main()
