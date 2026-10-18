"""校验 Release APK 的签名、非调试标志、架构和 tag 版本。"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import ssl
import subprocess

ROOT = Path(__file__).resolve().parents[1]
CERTIFICATE = ROOT / "Android/signing/release-certificate.pem"


def certificate_digest(path: Path) -> str:
    der = ssl.PEM_cert_to_DER_cert(path.read_text(encoding="ascii"))
    return hashlib.sha256(der).hexdigest()


def validate_metadata(signers: str, badging: str, expected_digest: str, abi: str, tag: str | None = None) -> dict:
    # SDK 37 使用 V2/V3 Signer 标签；同一证书可在多个签名方案中重复出现。
    signer_counts = re.findall(r"^Number of signers:[ \t]*(\d+)[ \t]*$", signers, re.M)
    fingerprints = re.findall(r"^[^\r\n]*certificate SHA-256 digest:[ \t]*([0-9a-fA-F:]+)[ \t]*$", signers, re.M)
    fingerprints = [digest.replace(":", "").lower() for digest in fingerprints]
    if signer_counts != ["1"] or set(fingerprints) != {expected_digest.lower()}:
        raise ValueError(f"APK 必须仅由仓库记录的正式证书签名：signers={signer_counts}, SHA256={fingerprints}")
    if re.search(r"^\s*application-debuggable(?:\s|:|$)", badging, re.M):
        raise ValueError("Release APK 不得启用 debuggable")
    native = re.search(r"^native-code:\s*(.*)$", badging, re.M)
    if native is None or set(re.findall(r"'([^']+)'", native[1])) != {abi}:
        raise ValueError(f"APK 原生架构必须为 {abi}")
    package = re.search(r"^package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", badging, re.M)
    if package is None or int(package[2]) <= 0:
        raise ValueError("APK 缺少有效的包名或版本信息")
    if tag is not None and package[3] != tag.removeprefix("v"):
        raise ValueError(f"APK 版本 {package[3]} 与 tag {tag} 不一致")
    return {"package": package[1], "version_code": int(package[2]), "version_name": package[3],
            "abi": abi, "debuggable": False, "certificate_sha256": expected_digest.lower()}


def verify(apk: Path, abi: str, build_tools: Path, certificate: Path = CERTIFICATE, tag: str | None = None) -> dict:
    signer = build_tools / ("apksigner.bat" if os.name == "nt" else "apksigner")
    aapt = build_tools / ("aapt.exe" if os.name == "nt" else "aapt")
    # apksigner 校验 APK 的密码学签名；随后核对签名证书身份及 manifest。
    signers = subprocess.run([str(signer), "verify", "--verbose", "--print-certs", str(apk)],
                             check=True, capture_output=True, text=True).stdout
    badging = subprocess.run([str(aapt), "dump", "badging", str(apk)],
                             check=True, capture_output=True, text=True).stdout
    report = validate_metadata(signers, badging, certificate_digest(certificate), abi, tag)
    with apk.open("rb") as stream:
        report["apk_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    report["apk"] = apk.name
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    parser.add_argument("--abi", choices=("arm64-v8a", "x86_64"), required=True)
    parser.add_argument("--tag")
    parser.add_argument("--certificate", type=Path, default=CERTIFICATE)
    sdk = Path(os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or ROOT / "Android/sdk")
    parser.add_argument("--build-tools", type=Path, default=sdk / "build-tools/37.0.0")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = verify(args.apk, args.abi, args.build_tools, args.certificate, args.tag)
    serialized = json.dumps(report, indent=2, ensure_ascii=False)
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)


if __name__ == "__main__":
    main()
