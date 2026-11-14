import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import Mock, patch

from fastapi import FastAPI, HTTPException


class DeploymentTests(unittest.TestCase):
    def load_deployment(self, state):
        main = types.ModuleType('main')
        main.app = FastAPI()
        engine = types.ModuleType('api.question_engine')
        engine.status = lambda: {'state': state}
        spec = importlib.util.spec_from_file_location('deployment_under_test', Path(__file__).parents[1] / 'deploy_app.py')
        module = importlib.util.module_from_spec(spec)
        with patch.dict(sys.modules, {'main': main, 'api.question_engine': engine}):
            spec.loader.exec_module(module)
        return module

    def test_ready_requires_live_worker_and_models(self):
        module = self.load_deployment('ready')
        with self.assertRaises(HTTPException):
            module.ready()
        module.worker_loaded.set()
        module.worker_thread = Mock()
        module.worker_thread.is_alive.return_value = True
        self.assertEqual(module.ready(), {'status': 'ready'})
        module.worker_thread.is_alive.return_value = False
        with self.assertRaises(HTTPException):
            module.ready()

    def test_worker_starts_once_after_ready(self):
        module = self.load_deployment('ready')
        worker = types.ModuleType('worker')
        worker.run_worker = Mock()
        with patch.dict(sys.modules, {'worker': worker}):
            module.ingestion_loop()
        worker.run_worker.assert_called_once_with()
        self.assertTrue(module.worker_loaded.is_set())

    def test_failed_engine_does_not_claim_jobs(self):
        module = self.load_deployment('unavailable')
        module.ingestion_loop()
        self.assertFalse(module.worker_loaded.is_set())


if __name__ == '__main__':
    unittest.main()
