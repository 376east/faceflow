"""Focused checks for benchmark instrumentation; no inference or external data."""
import importlib.util
from pathlib import Path
import sys
import unittest
from werkzeug.formparser import parse_form_data
from werkzeug.test import EnvironBuilder

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import measure_demo


class Measurement(unittest.TestCase):
    def test_latency_summary_and_nearest_rank(self):
        result = measure_demo.stats(list(range(1,21)))
        self.assertEqual(result['samples'],20)
        self.assertEqual(result['median'],10.5)
        self.assertEqual(result['p95_nearest_rank'],19)
        self.assertEqual(measure_demo.stats([7])['p95_nearest_rank'],7)

    def test_multipart_preserves_bytes_and_consent(self):
        raw = b'\x00\xff\r\nphoto bytes'
        body, content_type = measure_demo.multipart('selfie',raw,'selfie.jpg',True)
        builder = EnvironBuilder(method='POST',data=body,content_type=content_type)
        try:
            _, form, files = parse_form_data(builder.get_environ())
            self.assertEqual(files['selfie'].read(),raw)
            self.assertEqual(form['consent'],'yes')
            files['selfie'].close()
        finally:
            builder.close()

    def test_process_memory_is_real_and_cpu_delta_nonnegative(self):
        result = measure_demo.elapsed(measure_demo.snapshot())
        self.assertGreater(result['wall_seconds'],0)
        self.assertGreaterEqual(result['process_cpu_seconds'],0)
        self.assertGreater(result['peak_working_set_bytes'],0)


if __name__ == '__main__':
    unittest.main()
