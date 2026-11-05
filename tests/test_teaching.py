"""Regression checks for the missing-coverage and slider-only outcomes found in the audit."""

import copy
import json
import unittest
from pathlib import Path

from app.lesson_contract import validate_lessons
from app.teaching import validate_coverage

ROOT = Path(__file__).resolve().parents[1]


class TeachingTests(unittest.TestCase):
    def setUp(self):
        folder = ROOT / 'static' / 'attention2d'
        self.analysis = json.loads((folder / 'analysis.json').read_text())
        self.plan = json.loads((folder / 'plan.json').read_text())
        self.lessons = json.loads((folder / 'lessons.json').read_text())
        self.objects = [o['id'] for o in json.loads((folder / 'scene.json').read_text())['objects']]
        self.params = [c['symbol'] for c in self.plan['controls']]

    def test_required_architecture_and_results_cannot_disappear(self):
        validate_coverage(self.analysis, self.plan, self.lessons)
        for topic in ('architecture', 'decoder', 'results'):
            broken = copy.deepcopy(self.plan)
            broken['coverage'] = [e for e in broken['coverage'] if e['topic'] != topic]
            with self.assertRaisesRegex(ValueError, 'Missing coverage'):
                validate_coverage(self.analysis, broken, self.lessons)
        broken = copy.deepcopy(self.plan)
        broken['coverage'][0] = {'topic': 'architecture', 'mode': 'excluded', 'reason': 'too hard'}
        with self.assertRaisesRegex(ValueError, 'cannot silently'):
            validate_coverage(self.analysis, broken, self.lessons)

    def test_coverage_requires_real_lessons_and_instruction(self):
        with self.assertRaisesRegex(ValueError, 'missing lesson'):
            validate_coverage(self.analysis, self.plan, self.lessons[1:])
        self.lessons[0].pop('learning')
        with self.assertRaisesRegex(ValueError, 'observable outcome'):
            validate_coverage(self.analysis, self.plan, self.lessons)

    def test_slider_only_or_clock_only_outcomes_are_rejected(self):
        validate_lessons(self.lessons, self.objects, self.params)
        for expression in ('state.source === 1', 'state.time > 0', 'state.phase > 0'):
            self.lessons[0]['learning']['outcome_js'] = expression
            with self.assertRaisesRegex(ValueError, 'computed result'):
                validate_lessons(self.lessons, self.objects, self.params)
