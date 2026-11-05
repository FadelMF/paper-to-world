"""Independent attention invariants and same-PDF walkthrough selection."""

import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main
from app.demo import SAMPLES
from app.parity import check_port, reference_states


class AttentionTests(unittest.TestCase):
    def test_attention_matches_hand_calculated_limits(self):
        spec = importlib.util.spec_from_file_location('attention_reference', SAMPLES['attention2d'] / 'model.py')
        assert spec is not None and spec.loader is not None
        model = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(model)
        state = model.run({}, 0)
        self.assertEqual(state['future_mass'], 0)
        self.assertAlmostEqual(sum(state['probabilities']), 1)
        self.assertEqual(len(state['generated']), 3)
        self.assertEqual(state['prefix_ids'][1:], state['generated'][:-1])
        self.assertEqual(len(state['concat'][0]), 4)
        self.assertNotEqual(state['head_outputs'][0], state['head_outputs'][1])
        self.assertNotEqual(state['encoder'], state['embedded'])
        self.assertNotEqual(state['decoder'], state['target_embedded'])
        self.assertGreater(model.run({'causal': 0}, 0)['future_mass'], 0)
        cut = model.run({'memory': 0}, 0)
        self.assertEqual(cut['memory_energy'], 0)
        self.assertNotEqual(cut['probabilities'], state['probabilities'])
        self.assertNotEqual(model.run({'position': 0}, 0)['embedded'], state['embedded'])
        self.assertNotEqual(model.run({'source': 1}, 0)['encoder'], state['encoder'])
        # Layer normalization centers each token's four features.
        for row in state['encoder']:
            self.assertAlmostEqual(sum(row), 0, places=10)
        self.assertLess(model.run({'training_step': 8000}, 0)['learning_rate'], state['learning_rate'])

    def test_wide_gain_ranges_change_results_and_match_javascript(self):
        sample = SAMPLES['attention2d']
        spec = importlib.util.spec_from_file_location('wide_attention', sample / 'model.py')
        assert spec and spec.loader
        model = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(model)
        controls = {'input_gain': (10, 300), 'position_gain': (0, 300), 'score_gain': (10, 400), 'memory_gain': (0, 200), 'prefix': (1, 12)}
        cases = []
        for key, (lo, hi) in controls.items():
            low, high = model.run({key: lo}, 0), model.run({key: hi}, 0)
            field = {'input_gain': 'embedded', 'position_gain': 'embedded', 'score_gain': 'enc_weights', 'memory_gain': 'cross', 'prefix': 'generated'}[key]
            self.assertNotEqual(low[field], high[field], key)
            for value in (lo, hi):
                cases.append([{key: value}, 0])
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp)
            for name in ['model.py', 'model.js']:
                shutil.copy(sample / name, run / name)
            self.assertEqual(check_port(run, cases, reference_states(run, cases)), len(cases))

    def test_same_pdf_retains_selected_example(self):
        pdf = (SAMPLES['attention2d'] / 'paper.pdf').read_bytes()
        with TestClient(main.app) as client, patch.object(main, 'start_run', return_value={'id': 'test'}) as start:
            for dimension in ['2d', '3d']:
                key = 'attention' + dimension
                response = client.post('/api/runs', files={'file': ('paper.pdf', pdf, 'application/pdf')}, data={'demo': 'true', 'example_id': key})
                self.assertEqual(response.status_code, 200)
                self.assertEqual(start.call_args.args[1]['example'], key)
            invalid = client.post('/api/runs', files={'file': ('paper.pdf', pdf, 'application/pdf')}, data={'demo': 'true', 'example_id': '3d'})
            self.assertEqual(invalid.status_code, 422)
            self.assertEqual(client.get('/demo/gamma').status_code, 404)
