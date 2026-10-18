# 安卓正式签名

所有 `v*` tag（包括 beta）使用 Release 构建和同一把长期签名密钥。分支和 PR 默认生成 debug APK；仓库维护者可手动运行安卓工作流，将 `release` 设为 `true`，在合并前验证签名构建，产物仅保存到 Actions 附件。

## 公开证书

`release-certificate.pem` 只包含公开证书，可用于校验 APK；不包含签名私钥或密码。证书的 SHA-256 指纹为：

```text
1822fd4a3d09ed5400d72b72c6b8857d2a4f60d5b9e17bd464f2b469def2c929
```

CI 使用 Android SDK 的 `apksigner verify` 验证 APK 签名，并用 `aapt` 检查非调试标志、ABI 和版本。tag 构建的 APK 版本必须与 tag 一致；任一校验失败均阻止上传。每个正式签名构建还会保存 `release-verification-<abi>.json` 验证报告。

## GitHub Secrets

主项目配置以下仓库级 Secrets，统一发布流程显式传给安卓工作流：

| Secret | 用途 |
| --- | --- |
| `ANDROID_KEYSTORE_BASE64` | PKCS12 密钥库的 Base64 内容 |
| `ANDROID_KEYSTORE_PASSWORD` | 密钥库密码 |
| `ANDROID_KEY_ALIAS` | 签名密钥别名 |
| `ANDROID_KEY_PASSWORD` | 签名密钥密码 |

缺少签名配置时，Release 构建会失败，不会退回调试签名。CI 将密钥恢复到 runner 的临时文件，构建收尾时清理；APK 附件仅包含指定架构和构建类型的文件。

## 备份与升级

私钥、密码和跨盘备份均保存在 Git 仓库之外，并限制本机文件访问权限。只提交公开证书，不提交密钥库、密码或 Base64 内容。备份恢复时需核对文件哈希、重新打开密钥库，并确认导出的证书指纹仍与本文件一致。

后续正式版和 beta 应继续使用同一证书。已有 debug 包切换到新证书时通常无法直接覆盖安装，应先备份运行配置、库存和队伍缓存，再处理旧包。不要为解决构建问题重新生成正式签名密钥。
