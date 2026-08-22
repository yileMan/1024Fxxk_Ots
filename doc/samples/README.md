# OTS-07 数据包样例

以下样例均由 `backend/scripts/generate_ots07_samples.py` 生成。外部数据采集服务应以
`manifest.csv` 和 `nvd_cves.csv` 的字段、编码、CRLF 记录换行及 JSON 结构为参考，完整规则以
`doc/OTS-离线数据包契约-V1.0.md` 为准。

| 文件 | 用途 | 预期 | SHA-256 |
| --- | --- | --- | --- |
| `ots_intelligence_20260822_010203.zip` | 单 CVE 最小合规包；同时提供同名解压目录便于查看 CSV | 校验、预览和确认导入成功 | `33793794807e0277317224fdb3df094bf6303aa6058e28646a2038cfbb5d2e64` |
| `ots_intelligence_20260822_120000.zip` | 从旧的最近一日 1,215 条 NVD 样例完整转换；同时提供同名解压目录 | 校验、预览和确认导入成功 | `eb30176ab3de1ea4d23a898817568e7ad870b597be466ec157523734fb61be81` |
| `ots_intelligence_20260822_120001.zip` | `cvss_json` 非法的错误包 | `PACKAGE_CSV_INVALID`，第 2 物理行、`cvss_json` | `a422bdefee1776644415ba207a3770020af2f3b7b678391408b4297f9e981317` |
| `ots_intelligence_20260822_120002.zip` | `configurations_json` 恰好 1 MiB 的边界包 | 校验、预览和确认导入成功 | `a604e8069dd90f20420c3f54713e8398a4be0527c9da9ad2c5d4cfd983a1ec01` |
| `ots_intelligence_20260822_000009.zip` | 旧三文件历史输入，仅作为转换源和不兼容测试 | `PACKAGE_STRUCTURE_INVALID` | `025762caf542395fd56b19f6a3d36e8d840160df1b2d5b3d010a17db0a4abdb3` |

完整转换包包含：

- 1,215 个 CVE，ID 集合和顺序与旧最近一日输入一致；
- 35 个 Rejected CVE；
- 425 个带归一化受影响软件/版本范围的 CVE，790 个尚无可用 applicability 的 CVE；
- 733 个带开闭版本边界的受影响软件对象；
- 最大真实 `configurations_json` 为 `CVE-2019-10219` 的 71,123 字节。

重新生成命令：

```powershell
cd D:\261024\backend
.\.venv\Scripts\python.exe scripts\generate_ots07_samples.py `
  --source ..\doc\samples\ots_intelligence_20260822_000009.zip `
  --output-dir ..\doc\samples
```

生成器使用固定 ZIP 时间、稳定字段顺序和紧凑 JSON；相同输入重复生成的 ZIP 字节和 SHA-256 一致。
