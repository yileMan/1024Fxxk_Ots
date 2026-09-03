# OTS-13 CVSS v3.1 环境评分

## 评分契约

- 产品环境评分只在漏洞来源提供完整、合法的 `CVSS:3.1` 基础向量时可用；缺失时显示“来源未提供”，非法时显示来源向量无效，不生成或换算评分。
- 产品负责人可设置 `CR`、`IR`、`AR`、`MAV`、`MAC`、`MPR`、`MUI`、`MS`、`MC`、`MI`、`MA`。`X` 表示未定义：修正指标沿用来源基础值，安全要求使用 CVSS v3.1 默认权重。
- 浏览器计算仅用于未保存预览。保存请求提交结构化 `cvss_metrics`；环境分数、完整向量、`cvss_version=3.1` 和 `calculator_version=ots-cvss31-1` 均由服务端权威计算。
- 评分字段与核心评估草稿共用 `PUT /api/v1/assessments/{assessment_id}/draft`、`row_version`、负责人/产品范围校验和同事务审计。客户端提交派生字段会被契约拒绝。
- 本 change 复用 `product_assessment` 既有字段，不新增表、字段、索引或迁移。回滚应用代码时保留已经保存的用户评估数据。
- V1 不接受、计算、写入或返回 CVSS v4.0；数据库预留字段保持不变。

## 需求与测试追溯

| 基线 | 实现行为 | 主要证据 |
| --- | --- | --- |
| FR-MASTER-007、FR-ASSESS-005 | 产品版本使用 v3.1；后端从结构化环境指标计算分数和向量 | `backend/tests/test_cvss31.py`、`backend/tests/test_assessment_editor.py`、`front/src/utils/cvss31.test.ts` |
| FR-VULN-002 | 详情返回来源 v3.1 分数、严重度、向量和评分来源 | `backend/tests/test_assessment_editor.py`、`front/src/pages/AssessmentDetailPage.test.ts` |
| FR-VULN-003 | 来源缺失或非法时不生成环境评分并隐藏编辑控件 | 后端评估接口测试、前端组件测试、`front/e2e/assessment-editor.spec.ts` |
| 系统方案 6 | 服务端权威计算、指标/向量/分数/版本留痕、FIRST 回归 | CVSS 后端/前端纯函数测试和评估草稿审计测试 |
| 11 表约束 | 复用 `product_assessment` 评分列且无迁移 | MySQL 全量迁移及评估集成测试 |

公式与指标允许值依据 [FIRST CVSS v3.1 Specification](https://www.first.org/cvss/v3.1/specification-document)，回归同时覆盖 Modified Scope、`MPR` 权重、零影响、上限和 Roundup 边界。
