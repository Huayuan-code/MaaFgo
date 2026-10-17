"""在同一份原生 ONNX 库上比较 C API 桥和官方 Python binding 的数值与生命周期。"""
from pathlib import Path
import sys
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "agent"))
from utils.onnx_session import NativeOrtSession

try:
    import onnxruntime as ort
except ImportError:
    ort = None


@unittest.skipUnless(ort, "需要 onnxruntime 以对比官方 binding")
class NativeOrtTests(unittest.TestCase):
    def library(self):
        filename = "onnxruntime.dll" if sys.platform == "win32" else "libonnxruntime.so*"
        paths = list((Path(ort.__file__).parent / "capi").glob(filename))
        if not paths:
            self.skipTest("测试平台未提供独立 ONNX Runtime 动态库")
        return paths[0]

    def test_yolo_models_match_official_binding(self):
        rng = np.random.default_rng(42)
        for model, shape in (("support_det.onnx", (1, 3, 384, 640)), ("quest_detect.onnx", (1, 3, 192, 256))):
            with self.subTest(model=model):
                path = ROOT / "agent/utils" / model
                reference = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
                session = NativeOrtSession(path, self.library())
                try:
                    image = rng.random(shape, dtype=np.float32)
                    expected = reference.run(None, {reference.get_inputs()[0].name: image})[0]
                    actual = session.run(None, {session.get_inputs()[0].name: image})[0]
                    np.testing.assert_allclose(actual, expected, rtol=1e-4, atol=1e-4)
                    saved = actual.copy()
                    session.run(None, {session.get_inputs()[0].name: np.zeros_like(image)})
                    session.close()
                    np.testing.assert_array_equal(actual, saved)
                finally:
                    session.close()

    def test_errors_release_status_and_session_remains_usable(self):
        session = NativeOrtSession(ROOT / "agent/utils/support_det.onnx", self.library())
        try:
            with self.assertRaisesRegex(ValueError, "模型需要输入"):
                session.run(None, {"wrong": np.zeros((1,), np.float32)})
            with self.assertRaises(RuntimeError):
                session.run(None, {session.inputs[0]: np.zeros((1, 3, 1, 1), np.float32)})
            result = session.run(None, {session.inputs[0]: np.zeros((1, 3, 384, 640), np.float32)})
            self.assertEqual(result[0].shape, (1, 5, 5040))
        finally:
            session.close()
        with self.assertRaisesRegex(RuntimeError, "已关闭"):
            session.run(None, {session.inputs[0]: np.zeros((1, 3, 384, 640), np.float32)})

    def test_invalid_model_is_a_python_exception(self):
        with self.assertRaisesRegex(RuntimeError, "CreateSession"):
            NativeOrtSession(ROOT / "missing-model.onnx", self.library())


if __name__ == "__main__":
    unittest.main()
