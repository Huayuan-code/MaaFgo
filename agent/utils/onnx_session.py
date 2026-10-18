"""桌面走 Python wheel；Android 复用 MaaFramework 附带的 ONNX Runtime C API。"""
import ctypes as C
import os
from pathlib import Path
import sys
import threading
from types import SimpleNamespace

import numpy as np

# OrtApi v17 的 ABI 前缀稳定，槽位来自官方 onnxruntime_c_api.h。
# https://github.com/microsoft/onnxruntime/blob/v1.23.2/include/onnxruntime/core/session/onnxruntime_c_api.h
_SLOTS = {
    "GetErrorMessage": 2, "CreateEnv": 3, "DisableTelemetryEvents": 6,
    "CreateSession": 7, "Run": 9, "CreateSessionOptions": 10,
    "SetIntraOpNumThreads": 24, "SessionGetInputCount": 30,
    "SessionGetOutputCount": 31, "SessionGetInputName": 36, "SessionGetOutputName": 37,
    "CreateTensorWithDataAsOrtValue": 49, "GetTensorMutableData": 51,
    "GetTensorElementType": 60, "GetDimensionsCount": 61, "GetDimensions": 62,
    "GetTensorTypeAndShape": 65, "CreateCpuMemoryInfo": 69,
    "AllocatorFree": 76, "GetAllocatorWithDefaultOptions": 78,
    "ReleaseEnv": 92, "ReleaseStatus": 93, "ReleaseMemoryInfo": 94,
    "ReleaseSession": 95, "ReleaseValue": 96,
    "ReleaseTensorTypeAndShapeInfo": 99, "ReleaseSessionOptions": 100,
}
_DTYPES = {1: np.float32, 2: np.uint8, 3: np.int8, 4: np.uint16, 5: np.int16,
           6: np.int32, 7: np.int64, 9: np.bool_, 10: np.float16, 11: np.float64,
           12: np.uint32, 13: np.uint64}


class NativeOrtSession:
    """单输入图像模型会话；所有 OrtValue 在复制输出后释放。"""

    def __init__(self, model_path, library=None):
        factory = C.WINFUNCTYPE if sys.platform == "win32" else C.CFUNCTYPE
        loader = C.WinDLL if sys.platform == "win32" else C.CDLL
        self.lib = loader(str(library or Path(os.environ["MAAFW_BINARY_PATH"]) / "libonnxruntime.so"))
        class ApiBase(C.Structure):
            _fields_ = [("GetApi", factory(C.c_void_p, C.c_uint32)),
                        ("GetVersionString", factory(C.c_char_p))]
        self.lib.OrtGetApiBase.restype = C.POINTER(ApiBase)
        address = self.lib.OrtGetApiBase().contents.GetApi(17)
        if not address:
            raise RuntimeError("ONNX Runtime 不支持 C API v17")
        self.table = C.cast(address, C.POINTER(C.c_void_p))
        self.factory = factory
        self.functions = {}
        self.env, self.options, self.session, self.memory = (C.c_void_p() for _ in range(4))
        self.lock = threading.Lock()
        try:
            self._call("CreateEnv", [C.c_int, C.c_char_p, C.POINTER(C.c_void_p)], 3, b"MaaFGO", C.byref(self.env))
            self._call("DisableTelemetryEvents", [C.c_void_p], self.env)
            self._call("CreateSessionOptions", [C.POINTER(C.c_void_p)], C.byref(self.options))
            self._call("SetIntraOpNumThreads", [C.c_void_p, C.c_int], self.options, 2)
            path_type = C.c_wchar_p if sys.platform == "win32" else C.c_char_p
            path = str(Path(model_path).resolve())
            self._call("CreateSession", [C.c_void_p, path_type, C.c_void_p, C.POINTER(C.c_void_p)],
                       self.env, path if sys.platform == "win32" else os.fsencode(path), self.options, C.byref(self.session))
            self._call("CreateCpuMemoryInfo", [C.c_int, C.c_int, C.POINTER(C.c_void_p)], 1, 0, C.byref(self.memory))
            self.inputs = self._names("Input")
            self.outputs = self._names("Output")
            if len(self.inputs) != 1:
                raise ValueError("MaaFGO ONNX 后端仅支持单输入图像模型")
        except BaseException:
            self.close()
            raise

    def _function(self, name, result, args):
        if name not in self.functions:
            self.functions[name] = self.factory(result, *args)(self.table[_SLOTS[name]])
        return self.functions[name]

    def _call(self, name, types, *args):
        status = self._function(name, C.c_void_p, types)(*args)
        if status:
            message = self._function("GetErrorMessage", C.c_char_p, [C.c_void_p])(status)
            text = message.decode("utf-8", errors="replace")
            self._release("Status", status)
            raise RuntimeError(f"ONNX Runtime {name}: {text}")

    def _release(self, kind, pointer):
        if pointer:
            self._function("Release" + kind, None, [C.c_void_p])(pointer)

    def _names(self, kind):
        count, allocator = C.c_size_t(), C.c_void_p()
        self._call(f"SessionGet{kind}Count", [C.c_void_p, C.POINTER(C.c_size_t)], self.session, C.byref(count))
        self._call("GetAllocatorWithDefaultOptions", [C.POINTER(C.c_void_p)], C.byref(allocator))
        result = []
        for index in range(count.value):
            name = C.c_void_p()
            self._call(f"SessionGet{kind}Name", [C.c_void_p, C.c_size_t, C.c_void_p, C.POINTER(C.c_void_p)],
                       self.session, index, allocator, C.byref(name))
            try:
                result.append(C.string_at(name).decode("utf-8"))
            finally:
                self._call("AllocatorFree", [C.c_void_p, C.c_void_p], allocator, name)
        return result

    def get_inputs(self):
        return [SimpleNamespace(name=name) for name in self.inputs]

    def run(self, output_names, inputs):
        if set(inputs) != set(self.inputs):
            raise ValueError(f"模型需要输入 {self.inputs}，实际 {list(inputs)}")
        image = np.ascontiguousarray(inputs[self.inputs[0]], dtype=np.float32)
        shape = (C.c_int64 * image.ndim)(*image.shape)
        names = output_names or self.outputs
        if not set(names).issubset(self.outputs):
            raise ValueError(f"未知模型输出: {names}")
        input_value = C.c_void_p()
        values = (C.c_void_p * len(names))()
        with self.lock:
            if not self.session:
                raise RuntimeError("ONNX 会话已关闭")
            try:
                self._call("CreateTensorWithDataAsOrtValue",
                           [C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_int64), C.c_size_t, C.c_int, C.POINTER(C.c_void_p)],
                           self.memory, image.ctypes.data, image.nbytes, shape, image.ndim, 1, C.byref(input_value))
                self._call("Run", [C.c_void_p, C.c_void_p, C.POINTER(C.c_char_p), C.POINTER(C.c_void_p), C.c_size_t,
                                   C.POINTER(C.c_char_p), C.c_size_t, C.POINTER(C.c_void_p)],
                           self.session, None, (C.c_char_p * 1)(self.inputs[0].encode()),
                           (C.c_void_p * 1)(input_value), 1,
                           (C.c_char_p * len(names))(*(name.encode() for name in names)), len(names), values)
                return [self._copy_tensor(value) for value in values]
            finally:
                self._release("Value", input_value)
                for value in values:
                    self._release("Value", value)

    def _copy_tensor(self, value):
        info = C.c_void_p()
        self._call("GetTensorTypeAndShape", [C.c_void_p, C.POINTER(C.c_void_p)], value, C.byref(info))
        try:
            count, element = C.c_size_t(), C.c_int()
            self._call("GetDimensionsCount", [C.c_void_p, C.POINTER(C.c_size_t)], info, C.byref(count))
            dims = (C.c_int64 * count.value)()
            self._call("GetDimensions", [C.c_void_p, C.POINTER(C.c_int64), C.c_size_t], info, dims, count.value)
            self._call("GetTensorElementType", [C.c_void_p, C.POINTER(C.c_int)], info, C.byref(element))
            dtype = np.dtype(_DTYPES[element.value])
            pointer = C.c_void_p()
            self._call("GetTensorMutableData", [C.c_void_p, C.POINTER(C.c_void_p)], value, C.byref(pointer))
            size = int(np.prod(dims, dtype=np.int64)) * dtype.itemsize
            return np.frombuffer(C.string_at(pointer, size), dtype=dtype).reshape(tuple(dims)).copy()
        finally:
            self._release("TensorTypeAndShapeInfo", info)

    def close(self):
        with self.lock:
            for attr, kind in (("session", "Session"), ("memory", "MemoryInfo"), ("options", "SessionOptions"), ("env", "Env")):
                pointer = getattr(self, attr, None)
                if pointer:
                    self._release(kind, pointer)
                    setattr(self, attr, C.c_void_p())

    def __del__(self):
        if hasattr(self, "lock"):
            self.close()


def create_session(model_path):
    if sys.platform == "android" or os.environ.get("MAAFGO_PLATFORM") == "android":
        return NativeOrtSession(model_path)
    import onnxruntime as ort
    return ort.InferenceSession(str(model_path), providers=["CPUExecutionProvider"])
