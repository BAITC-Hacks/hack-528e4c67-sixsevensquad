import unittest

from app.analyzer import analyze


class AnalyzerTest(unittest.TestCase):
    def test_finds_created_and_preserved_units(self):
        before = [{"name": "old.txt", "text": "3.4. Блок состоит из следующих структурных подразделений: Департамент контроля качества (ДККМ)."}]
        after = [{"name": "new.txt", "text": "3.4. Блок состоит из следующих структурных подразделений: Департамент контроля качества (ДККМ). Департамент операционного аудита (ДОА)."}]
        result = analyze(before, after)
        self.assertGreaterEqual(result["summary"]["preserved"], 1)
        self.assertGreaterEqual(result["summary"]["created"], 1)


if __name__ == "__main__":
    unittest.main()

