"""Lock the supplemental LLM review contract to the CLI evidence boundary."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SemanticReviewContractTests(unittest.TestCase):
    def test_schema_requires_evidence_and_separate_provenance(self):
        schema = json.loads((ROOT / 'references/semantic-review.schema.json').read_text())
        review = schema['properties']['review']
        decision = schema['properties']['decisions']['items']

        self.assertEqual(review['properties']['provenance']['const'], 'manual-review')
        self.assertEqual(review['properties']['method']['const'], 'skill-llm-semantic-review')
        self.assertIn('evidence', decision['required'])
        self.assertIn('decision', decision['required'])
        self.assertIn('confidence', decision['required'])
        self.assertIn('missing_context', decision['properties'])
        self.assertEqual('^[0-9a-f]{64}$', schema['properties']['source_report_sha256']['pattern'])
        self.assertIn('unresolved', decision['properties']['decision']['enum'])

    def test_fallback_cannot_masquerade_as_cli_coverage(self):
        schema = json.loads((ROOT / 'references/semantic-review.schema.json').read_text())
        encoded = json.dumps(schema)
        self.assertNotIn('implementation_status', encoded)
        self.assertNotIn('coverage_summary', encoded)
        self.assertNotIn('rule_coverage', encoded)

        skill = (ROOT / 'SKILL.md').read_text()
        self.assertIn('never mutate the CLI', (ROOT / 'references/semantic-review.md').read_text())
        self.assertIn('do not change a rule\'s implementation status merely because an LLM reviewed it', skill)


if __name__ == '__main__':
    unittest.main()
