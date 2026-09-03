<template>
  <main class="assessment-page">
    <header class="page-header">
      <div><p>PRODUCT ASSESSMENT / WORKING DRAFT</p><h1>{{ detail?.vulnerability.cve_id ?? '产品评估' }}</h1></div>
      <a :href="returnUrl">返回评估待办</a>
    </header>

    <p v-if="loading" class="state" aria-live="polite">正在装载评估上下文…</p>
    <p v-else-if="loadError" class="state error" role="alert">{{ loadError }}</p>

    <template v-else-if="detail">
      <section v-if="detail.return_reason || detail.reassess_reason" class="reason-banner" role="status">
        <small>{{ detail.return_reason ? 'RETURNED / 退回原因' : 'REASSESS / 复评原因' }}</small>
        <strong>{{ detail.return_reason ?? detail.reassess_reason }}</strong>
      </section>

      <section class="identity-strip" aria-label="当前产品评估上下文">
        <div><small>产品 / 版本</small><strong>{{ detail.product.name }} · {{ detail.product_version.version_no }}</strong></div>
        <div><small>OTS</small><strong>{{ detail.ots.name }} {{ detail.ots.version }}</strong></div>
        <div><small>修订 / 状态</small><strong>REV {{ detail.revision_no }} · {{ statusLabels[detail.status] }}</strong></div>
      </section>

      <section class="revision-panel" aria-label="评估修订历史">
        <header>
          <div><small>REVISION HISTORY</small><h2>修订历史</h2></div>
          <button type="button" data-action="load-revisions" :disabled="historyLoading" @click="loadHistory">
            {{ historyLoading ? '正在加载…' : historyLoaded ? '刷新历史' : '查看修订历史' }}
          </button>
        </header>
        <p v-if="historyError" class="feedback error" role="alert">{{ historyError }}</p>
        <ol v-if="historyLoaded" class="revision-list">
          <li v-for="revision in revisions" :key="revision.assessment_id">
            <button
              type="button"
              :data-revision-id="revision.assessment_id"
              :class="{ selected: revision.assessment_id === detail.assessment_id }"
              @click="openRevision(revision.assessment_id)"
            >
              <strong>REV {{ revision.revision_no }}</strong>
              <span>{{ statusLabels[revision.status] }}{{ revision.is_current ? ' · 当前' : '' }}</span>
            </button>
          </li>
        </ol>
        <p v-if="!detail.is_current" class="history-notice">历史修订只读。当前修订为 REV {{ currentRevision?.revision_no ?? '—' }}。</p>
        <button
          v-if="comparisonPair"
          type="button"
          data-action="compare-parent"
          :disabled="comparisonLoading"
          @click="loadComparison"
        >{{ comparisonLoading ? '正在比较…' : '比较版本' }}</button>
        <dl v-if="comparison" class="revision-diff">
          <div v-for="change in comparison.changes" :key="change.field">
            <dt>{{ change.field }}</dt>
            <dd><del>{{ displayDiffValue(change.before) }}</del><ins>{{ displayDiffValue(change.after) }}</ins></dd>
          </div>
        </dl>
      </section>

      <div class="evidence-layout">
        <section class="evidence-card source">
          <small>SOURCE FACT / 来源事实</small>
          <h2>{{ detail.vulnerability.source_status }}</h2>
          <p>{{ detail.vulnerability.description ?? '来源未提供描述' }}</p>
          <dl>
            <div><dt>CVSS v3.1</dt><dd>{{ detail.vulnerability.cvss31_score ?? '来源未提供' }}</dd></div>
            <div><dt>严重度</dt><dd>{{ detail.vulnerability.cvss31_severity ?? '来源未提供' }}</dd></div>
            <div><dt>评分来源</dt><dd>{{ detail.vulnerability.cvss31_source ?? '来源未提供' }}</dd></div>
            <div><dt>KEV</dt><dd>{{ detail.vulnerability.is_kev ? '已标记' : '未标记' }}</dd></div>
          </dl>
          <p class="source-vector"><strong>来源向量</strong>{{ detail.vulnerability.cvss31_vector ?? '来源未提供' }}</p>
        </section>
        <section class="evidence-card candidate">
          <small>CANDIDATE EVIDENCE / 候选依据</small>
          <template v-if="detail.candidate">
            <h2>{{ detail.candidate.match_method }}</h2>
            <p>{{ detail.candidate.match_basis }}</p>
            <pre>{{ JSON.stringify(detail.candidate.match_evidence, null, 2) }}</pre>
          </template>
          <p v-else>当前产品 OTS 没有可用候选依据。</p>
          <strong class="candidate-warning">{{ detail.candidate_disclaimer }}</strong>
        </section>
      </div>

      <section class="editor-section">
        <header>
          <div><small>CURRENT PRODUCT CONCLUSION</small><h2>当前产品结论</h2></div>
          <span :class="['mode-badge', { readonly: !detail.editable }]">{{ detail.editable ? '草稿可编辑' : '只读' }}</span>
        </header>
        <p v-if="!detail.editable" class="notice" role="status">{{ readonlyMessage }}</p>
        <p v-if="saveError" class="feedback error" role="alert">{{ saveError }}</p>
        <p v-else-if="saveSuccess" class="feedback success" role="status">{{ saveSuccess }}</p>
        <button v-if="conflict" type="button" data-action="refresh-server" class="refresh" @click="load">刷新服务器数据</button>

        <form @submit.prevent="save">
          <TextField v-for="field in firstFields" :key="field.key" :field="field" />

          <div class="field decision">
            <label for="applicability">适用性</label>
            <select id="applicability" v-model="form.applicability" name="applicability" :disabled="formDisabled">
              <option value="pending">待确认</option><option value="affected">受影响</option><option value="not_affected">不受影响</option><option value="partly_affected">部分受影响</option>
            </select>
            <p v-if="fieldErrors.applicability" data-error-for="applicability" class="field-error">{{ fieldErrors.applicability }}</p>
          </div>

          <TextField v-for="field in middleFields" :key="field.key" :field="field" />

          <section class="cvss-panel wide" aria-labelledby="cvss-heading">
            <header>
              <div><small>CVSS v3.1 / ENVIRONMENTAL</small><h3 id="cvss-heading">产品环境评分</h3></div>
              <strong v-if="detail.environmental_scoring.available" class="score-chip">{{ preview?.score.toFixed(1) }}</strong>
            </header>
            <p v-if="!detail.environmental_scoring.available" class="cvss-unavailable">
              {{ detail.environmental_scoring.unavailable_reason === 'SOURCE_NOT_PROVIDED' ? '来源未提供 CVSS v3.1，无法生成或换算产品环境评分。' : '来源 CVSS v3.1 向量无效，暂时无法评分。' }}
            </p>
            <template v-else>
              <p class="cvss-state">{{ metricsDirty ? '未保存预览' : detail.environmental_scoring.metrics ? '已保存结果' : '未覆盖来源指标' }}</p>
              <div v-if="detail.editable" class="metric-grid">
                <label v-for="metric in metricDefinitions" :key="metric.key" :data-cvss-metric="metric.key">
                  <span>{{ metric.label }} <b>{{ metric.key }}</b></span>
                  <select v-model="cvssMetrics[metric.key]" :name="`cvss_metrics.${metric.key}`" :disabled="formDisabled">
                    <option v-for="option in metric.options" :key="option.value" :value="option.value">{{ option.label }}</option>
                  </select>
                  <em v-if="fieldErrors[`cvss_metrics.${metric.key}`]">{{ fieldErrors[`cvss_metrics.${metric.key}`] }}</em>
                </label>
              </div>
              <div v-else-if="detail.environmental_scoring.metrics" class="metric-readonly">
                <span v-for="metric in metricDefinitions" :key="metric.key"><b>{{ metric.key }}</b>{{ cvssMetrics[metric.key] }}</span>
              </div>
              <dl class="score-result">
                <div><dt>环境分数</dt><dd>{{ preview?.score.toFixed(1) ?? '—' }}</dd></div>
                <div><dt>计算器版本</dt><dd>{{ metricsDirty ? '保存后由服务端确认' : detail.environmental_scoring.calculator_version ?? '尚未保存' }}</dd></div>
                <div class="vector"><dt>环境向量</dt><dd>{{ metricsDirty ? preview?.vector : detail.environmental_scoring.vector ?? preview?.vector ?? '—' }}</dd></div>
              </dl>
            </template>
          </section>

          <div class="field decision">
            <label for="treatment">处置建议</label>
            <select id="treatment" v-model="form.treatment" name="treatment" :disabled="formDisabled">
              <option value="">暂未选择</option><option value="patch_or_upgrade">升级 / 补丁</option><option value="configuration_mitigation">配置缓解</option><option value="isolation_or_compensating_control">隔离 / 补偿控制</option><option value="accept_risk">接受风险</option><option value="no_action">无需处置</option><option value="further_investigation">进一步调查</option>
            </select>
            <p v-if="fieldErrors.treatment" data-error-for="treatment" class="field-error">{{ fieldErrors.treatment }}</p>
          </div>

          <TextField v-for="field in lastFields" :key="field.key" :field="field" />

          <footer v-if="detail.editable">
            <p>保存只更新当前草稿，不会提交审核。</p>
            <button type="submit" :disabled="saving">{{ saving ? '正在保存…' : '保存草稿' }}</button>
          </footer>
        </form>

        <section v-if="detail.actions.can_submit || detail.actions.can_approve || detail.actions.can_return || detail.actions.can_create_revision || detail.submitted_at || detail.reviewed_at" class="action-panel" aria-label="评估提交与审核">
          <div>
            <small>WORKFLOW ACTIONS</small><h3>提交与审核</h3>
            <p v-if="detail.submitted_at">提交人 #{{ detail.submitted_by }} · {{ formatTime(detail.submitted_at) }}</p>
            <p v-if="detail.reviewed_at">审核人 #{{ detail.reviewer_id }} · {{ formatTime(detail.reviewed_at) }} · {{ detail.review_decision === 'approved' ? '已通过' : '已退回' }}</p>
            <p v-if="actionError" class="feedback error" role="alert">{{ actionError }}</p>
            <p v-else-if="actionSuccess" class="feedback success" role="status">{{ actionSuccess }}</p>
          </div>
          <div class="action-buttons">
            <button v-if="detail.actions.can_submit" type="button" data-action="submit-assessment" :disabled="acting" @click="dialog = 'submit'">提交审核</button>
            <button v-if="detail.actions.can_approve" type="button" data-action="approve-assessment" :disabled="acting" @click="dialog = 'approve'">审核通过</button>
            <button v-if="detail.actions.can_return" type="button" data-action="return-assessment" :disabled="acting" @click="dialog = 'return'">退回修改</button>
            <button v-if="detail.actions.can_create_revision" type="button" data-action="create-revision" :disabled="acting" @click="dialog = 'revision'">创建新修订</button>
          </div>
        </section>

        <div v-if="dialog" class="dialog-backdrop" role="presentation">
          <section class="action-dialog" role="dialog" aria-modal="true" :aria-labelledby="`${dialog}-title`">
            <h3 :id="`${dialog}-title`">{{ dialog === 'submit' ? '确认提交审核' : dialog === 'approve' ? '确认审核通过' : dialog === 'return' ? '确认退回修改' : '创建新修订' }}</h3>
            <p>{{ dialog === 'submit' ? '提交后当前修订将冻结，不能再直接修改。' : dialog === 'approve' ? '通过后评估将直接进入已完成。' : dialog === 'return' ? '退回将保留审核快照，并创建可修改的新修订。' : '已完成修订保持只读；新修订需要重新提交审核。' }}</p>
            <label v-if="dialog === 'return'" for="review_comment">退回意见</label>
            <textarea v-if="dialog === 'return'" id="review_comment" v-model="reviewComment" name="review_comment" maxlength="10000" rows="5" :disabled="acting" />
            <p v-if="fieldErrors.review_comment" data-error-for="review_comment" class="field-error">{{ fieldErrors.review_comment }}</p>
            <label v-if="dialog === 'revision'" for="revision_reason">修订原因</label>
            <textarea v-if="dialog === 'revision'" id="revision_reason" v-model="revisionReason" name="revision_reason" maxlength="500" rows="4" :disabled="acting" />
            <p v-if="fieldErrors.revision_reason" data-error-for="revision_reason" class="field-error">{{ fieldErrors.revision_reason }}</p>
            <footer>
              <button type="button" :disabled="acting" @click="closeDialog">取消</button>
              <button v-if="dialog === 'submit'" type="button" data-action="confirm-submit" :disabled="acting" @click="executeAction('submit')">{{ acting ? '正在提交…' : '确认提交' }}</button>
              <button v-else-if="dialog === 'approve'" type="button" data-action="confirm-approve" :disabled="acting" @click="executeAction('approve')">{{ acting ? '正在处理…' : '确认通过' }}</button>
              <button v-else-if="dialog === 'return'" type="button" data-action="confirm-return" :disabled="acting" @click="executeAction('return')">{{ acting ? '正在处理…' : '确认退回' }}</button>
              <button v-else type="button" data-action="confirm-create-revision" :disabled="acting" @click="executeAction('revision')">{{ acting ? '正在创建…' : '确认创建' }}</button>
            </footer>
          </section>
        </div>
      </section>
    </template>
  </main>
</template>

<script setup lang="ts">
import { computed, defineComponent, h, nextTick, onMounted, reactive, ref, type PropType } from 'vue'

import { AssessmentApiError, approveAssessment, compareAssessmentRevisions, createAssessmentRevision, getAssessmentDetail, getAssessmentRevisionHistory, returnAssessment, saveAssessmentDraft, submitAssessment, type AssessmentDetail, type AssessmentDraftUpdate, type AssessmentRevisionComparison, type AssessmentRevisionHistory } from '../api/assessmentEditor'
import { calculateEnvironmental, defaultEnvironmentalMetrics, type EnvironmentalMetric, type EnvironmentalMetrics } from '../utils/cvss31'

type TextKey = 'analysis_summary' | 'trigger_conditions' | 'affected_functions' | 'applicability_basis' | 'product_impact' | 'existing_controls' | 'treatment_detail' | 'evidence_text'
type FieldDefinition = { key: TextKey; label: string; wide?: boolean }

const props = defineProps<{ assessmentId: number }>()
const detail = ref<AssessmentDetail | null>(null)
const loading = ref(true)
const saving = ref(false)
const loadError = ref('')
const saveError = ref('')
const saveSuccess = ref('')
const conflict = ref(false)
const acting = ref(false)
const actionError = ref('')
const actionSuccess = ref('')
const dialog = ref<'' | 'submit' | 'approve' | 'return' | 'revision'>('')
const reviewComment = ref('')
const revisionReason = ref('')
const revisions = ref<AssessmentRevisionHistory['items']>([])
const historyLoading = ref(false)
const historyLoaded = ref(false)
const historyError = ref('')
const comparison = ref<AssessmentRevisionComparison | null>(null)
const comparisonLoading = ref(false)
const cvssMetrics = reactive<EnvironmentalMetrics>(defaultEnvironmentalMetrics())
const savedMetrics = ref(JSON.stringify(defaultEnvironmentalMetrics()))
const fieldErrors = reactive<Record<string, string>>({})
const form = reactive<Record<TextKey, string> & {
  applicability: AssessmentDraftUpdate['applicability']
  treatment: NonNullable<AssessmentDraftUpdate['treatment']> | ''
}>({
  analysis_summary: '', trigger_conditions: '', affected_functions: '', applicability: 'pending',
  applicability_basis: '', product_impact: '', existing_controls: '', treatment: '', treatment_detail: '', evidence_text: '',
})
const firstFields: FieldDefinition[] = [
  { key: 'analysis_summary', label: '分析摘要', wide: true },
  { key: 'trigger_conditions', label: '触发条件' },
  { key: 'affected_functions', label: '涉及功能或接口' },
]
const middleFields: FieldDefinition[] = [
  { key: 'applicability_basis', label: '适用性依据' },
  { key: 'product_impact', label: '产品影响' },
  { key: 'existing_controls', label: '现有控制' },
]
const lastFields: FieldDefinition[] = [
  { key: 'treatment_detail', label: '处置说明' },
  { key: 'evidence_text', label: '证据说明或内网引用位置', wide: true },
]
const statusLabels: Record<string, string> = { pending: '待产品评估', returned: '已退回', reassess: '待复评', submitted: '待审核', completed: '已完成' }
const returnQueue = new URL(window.location.href).searchParams.get('from') ?? 'pending'
const returnUrl = `/system/assessments/tasks?queue=${encodeURIComponent(returnQueue)}&page=1`
const formDisabled = computed(() => !detail.value?.editable || saving.value)
const metricsDirty = computed(() => JSON.stringify(cvssMetrics) !== savedMetrics.value)
const preview = computed(() => {
  const vector = detail.value?.vulnerability.cvss31_vector
  if (!detail.value?.environmental_scoring.available || !vector) return null
  try { return calculateEnvironmental(vector, cvssMetrics) } catch { return null }
})
const readonlyMessage = computed(() => detail.value?.status === 'returned'
  ? detail.value.is_current && detail.value.editable
    ? '当前退回修订可由负责人修改并重新提交。'
    : detail.value.is_current
      ? '已退回，等待创建新修订；当前已提交修订保持只读。'
      : '历史退回修订保持只读。'
  : '当前评估为只读状态，人员分配、产品范围或评估状态可能已变化。')
const currentRevision = computed(() => revisions.value.find(item => item.is_current))
const comparisonPair = computed(() => {
  if (!detail.value) return null
  if (!detail.value.is_current) {
    return { base: detail.value.assessment_id, target: detail.value.current_revision_id }
  }
  if (detail.value.parent_revision_id) {
    return { base: detail.value.parent_revision_id, target: detail.value.assessment_id }
  }
  return null
})
const option = (value: string, label: string) => ({ value, label })
const commonX = option('X', '未定义 / 沿用来源')
const metricDefinitions: { key: EnvironmentalMetric; label: string; options: { value: string; label: string }[] }[] = [
  ...(['CR', 'IR', 'AR'] as EnvironmentalMetric[]).map(key => ({ key, label: ({ CR: '机密性要求', IR: '完整性要求', AR: '可用性要求' } as Record<string, string>)[key], options: [commonX, option('H', '高'), option('M', '中'), option('L', '低')] })),
  { key: 'MAV', label: '修正攻击向量', options: [commonX, option('N', '网络'), option('A', '相邻'), option('L', '本地'), option('P', '物理')] },
  { key: 'MAC', label: '修正攻击复杂度', options: [commonX, option('L', '低'), option('H', '高')] },
  { key: 'MPR', label: '修正所需权限', options: [commonX, option('N', '无'), option('L', '低'), option('H', '高')] },
  { key: 'MUI', label: '修正用户交互', options: [commonX, option('N', '无需'), option('R', '需要')] },
  { key: 'MS', label: '修正范围', options: [commonX, option('U', '不变'), option('C', '改变')] },
  ...(['MC', 'MI', 'MA'] as EnvironmentalMetric[]).map(key => ({ key, label: ({ MC: '修正机密性', MI: '修正完整性', MA: '修正可用性' } as Record<string, string>)[key], options: [commonX, option('H', '高'), option('L', '低'), option('N', '无')] })),
]

const TextField = defineComponent({
  props: { field: { type: Object as PropType<FieldDefinition>, required: true } },
  setup(componentProps) {
    return () => h('div', { class: ['field', { wide: componentProps.field.wide }] }, [
      h('label', { for: componentProps.field.key }, [
        componentProps.field.label,
        requiredText(componentProps.field.key) ? h('em', '必填') : null,
      ]),
      h('textarea', {
        id: componentProps.field.key,
        name: componentProps.field.key,
        rows: 4,
        maxlength: 10000,
        disabled: formDisabled.value,
        value: form[componentProps.field.key],
        onInput: (event: Event) => { form[componentProps.field.key] = (event.target as HTMLTextAreaElement).value },
      }),
      fieldErrors[componentProps.field.key]
        ? h('p', { class: 'field-error', 'data-error-for': componentProps.field.key }, fieldErrors[componentProps.field.key])
        : null,
    ])
  },
})

onMounted(load)

function requiredText(key: TextKey): boolean {
  return (key === 'applicability_basis' && form.applicability !== 'pending')
    || (key === 'treatment_detail' && ['accept_risk', 'no_action'].includes(form.treatment))
}

async function load(): Promise<void> {
  loading.value = true
  loadError.value = ''
  saveError.value = ''
  saveSuccess.value = ''
  conflict.value = false
  clearFieldErrors()
  try {
    applyDetail(await getAssessmentDetail(props.assessmentId))
  } catch (reason) {
    detail.value = null
    loadError.value = reason instanceof AssessmentApiError && reason.status === 403
      ? '无权查看该评估，产品授权可能已失效。'
      : reason instanceof AssessmentApiError && reason.status === 404
        ? '评估不存在或已不可用。'
        : '评估详情暂时不可用，请稍后重试。'
  } finally {
    loading.value = false
  }
}

async function loadHistory(): Promise<void> {
  if (!detail.value || historyLoading.value) return
  historyLoading.value = true
  historyError.value = ''
  try {
    const response = await getAssessmentRevisionHistory(detail.value.assessment_id)
    revisions.value = response.items
    historyLoaded.value = true
  } catch (reason) {
    historyError.value = reason instanceof AssessmentApiError ? reason.message : '修订历史暂时不可用。'
  } finally {
    historyLoading.value = false
  }
}

async function openRevision(assessmentId: number): Promise<void> {
  if (assessmentId === detail.value?.assessment_id) return
  try {
    applyDetail(await getAssessmentDetail(assessmentId))
    comparison.value = null
  } catch (reason) {
    historyError.value = reason instanceof AssessmentApiError ? reason.message : '修订详情暂时不可用。'
  }
}

async function loadComparison(): Promise<void> {
  const pair = comparisonPair.value
  if (!detail.value || !pair || comparisonLoading.value) return
  comparisonLoading.value = true
  historyError.value = ''
  try {
    comparison.value = await compareAssessmentRevisions(
      detail.value.assessment_id, pair.base, pair.target,
    )
  } catch (reason) {
    historyError.value = reason instanceof AssessmentApiError ? reason.message : '版本比较暂时不可用。'
  } finally {
    comparisonLoading.value = false
  }
}

function displayDiffValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  return typeof value === 'object' ? JSON.stringify(value) : String(value)
}

function applyDetail(response: AssessmentDetail): void {
  detail.value = response
  for (const field of [...firstFields, ...middleFields, ...lastFields]) form[field.key] = response.draft[field.key] ?? ''
  form.applicability = response.draft.applicability
  form.treatment = response.draft.treatment ?? ''
  const metrics = response.draft.cvss_metrics ?? defaultEnvironmentalMetrics()
  Object.assign(cvssMetrics, metrics)
  savedMetrics.value = JSON.stringify(cvssMetrics)
}

function closeDialog(): void {
  if (!acting.value) dialog.value = ''
}

function formatTime(value: string): string {
  return new Date(value).toLocaleString('zh-CN')
}

async function executeAction(action: 'submit' | 'approve' | 'return' | 'revision'): Promise<void> {
  if (!detail.value || acting.value) return
  clearFieldErrors()
  if (action === 'return' && !reviewComment.value.trim()) {
    fieldErrors.review_comment = '退回意见必须填写'
    return
  }
  if (action === 'revision' && !revisionReason.value.trim()) {
    fieldErrors.revision_reason = '修订原因必须填写'
    return
  }
  acting.value = true
  actionError.value = ''
  actionSuccess.value = ''
  try {
    const payload = { row_version: detail.value.row_version }
    const assessmentId = detail.value.assessment_id
    const response = action === 'submit'
      ? await submitAssessment(assessmentId, payload)
      : action === 'approve'
        ? await approveAssessment(assessmentId, payload)
        : action === 'return'
          ? (await returnAssessment(assessmentId, { ...payload, review_comment: reviewComment.value })).current_revision
          : await createAssessmentRevision(assessmentId, { ...payload, revision_reason: revisionReason.value })
    applyDetail(response)
    actionSuccess.value = action === 'submit' ? '评估已提交审核' : action === 'approve' ? '评估已审核通过' : action === 'return' ? '评估已退回并创建新修订' : '新修订已创建'
    dialog.value = ''
    if (action === 'return') reviewComment.value = ''
    if (action === 'revision') revisionReason.value = ''
    historyLoaded.value = false
    revisions.value = []
  } catch (reason) {
    if (reason instanceof AssessmentApiError && reason.status === 422 && reason.fields.length) {
      for (const item of reason.fields) fieldErrors[item.path] = item.message
    }
    actionError.value = reason instanceof AssessmentApiError ? reason.message : '操作失败，请稍后重试。'
    if (reason instanceof AssessmentApiError && reason.status === 409) conflict.value = true
  } finally {
    acting.value = false
  }
}

async function save(): Promise<void> {
  if (!detail.value?.editable || saving.value) return
  saving.value = true
  saveError.value = ''
  saveSuccess.value = ''
  conflict.value = false
  clearFieldErrors()
  try {
    const response = await saveAssessmentDraft(detail.value.assessment_id, {
      row_version: detail.value.row_version,
      analysis_summary: form.analysis_summary,
      trigger_conditions: form.trigger_conditions,
      affected_functions: form.affected_functions,
      applicability: form.applicability,
      applicability_basis: form.applicability_basis,
      product_impact: form.product_impact,
      existing_controls: form.existing_controls,
      treatment: form.treatment || null,
      treatment_detail: form.treatment_detail,
      evidence_text: form.evidence_text,
      cvss_metrics: (detail.value.environmental_scoring.available
        ? { ...cvssMetrics }
        : null) as AssessmentDraftUpdate['cvss_metrics'],
    })
    applyDetail(response)
    saveSuccess.value = '草稿已保存'
  } catch (reason) {
    if (reason instanceof AssessmentApiError && reason.status === 422 && reason.fields.length) {
      for (const item of reason.fields) fieldErrors[item.path] = item.message
      saveError.value = reason.message
      saving.value = false
      await nextTick()
      document.querySelector<HTMLElement>(`[name="${reason.fields[0].path}"]`)?.focus()
    } else if (reason instanceof AssessmentApiError && reason.status === 409) {
      saveError.value = reason.message
      conflict.value = true
      if (reason.code === 'ASSESSMENT_NOT_EDITABLE' && detail.value) detail.value.editable = false
    } else {
      saveError.value = reason instanceof AssessmentApiError ? reason.message : '保存失败，请稍后重试。'
    }
  } finally {
    saving.value = false
  }
}

function clearFieldErrors(): void {
  for (const key of Object.keys(fieldErrors)) delete fieldErrors[key]
}
</script>

<style scoped>
.assessment-page{max-width:1220px;margin:0 auto;padding:48px 32px 96px}.page-header{display:flex;align-items:flex-end;justify-content:space-between;gap:24px}.page-header p{margin:0;color:var(--brand-red);font-size:11px;font-weight:900;letter-spacing:.18em}.page-header h1{margin:10px 0 0;color:var(--ink);font:750 clamp(40px,6vw,72px)/1 var(--font-display)}.page-header a{border-bottom:2px solid var(--brand-red);padding:8px 0;text-decoration:none;font-size:12px;font-weight:900}.state{margin-top:24px;padding:22px;border:1px solid var(--line-strong);background:#fff}.state.error,.feedback.error{border-left:5px solid var(--brand-red)}.reason-banner{display:grid;gap:9px;margin-top:30px;padding:20px 24px;border-left:7px solid var(--brand-red);color:#fff;background:var(--ink)}.reason-banner small{color:#ff8d92;font-size:10px;font-weight:900;letter-spacing:.16em}.reason-banner strong{font-size:15px;line-height:1.6}.identity-strip{display:grid;grid-template-columns:1.25fr 1fr .8fr;margin-top:12px;border:1px solid var(--line-strong);background:#fff}.identity-strip div{padding:18px 22px;border-right:1px solid var(--line)}.identity-strip div:last-child{border-right:0}.identity-strip small,.evidence-card>small,.editor-section header small{display:block;color:var(--brand-red);font-size:9px;font-weight:900;letter-spacing:.14em}.identity-strip strong{display:block;margin-top:7px;color:var(--ink);font-size:14px}.evidence-layout{display:grid;grid-template-columns:1.2fr .8fr;gap:12px;margin-top:12px}.evidence-card{padding:26px;border:1px solid var(--line);border-top:6px solid var(--ink);background:#fff}.evidence-card.candidate{border-top-color:var(--brand-red)}.evidence-card h2{margin:9px 0;color:var(--ink);font:750 26px var(--font-display)}.evidence-card p{color:var(--text-muted);font-size:13px;line-height:1.7}.evidence-card dl{display:flex;gap:28px;margin:22px 0 0}.evidence-card dt{color:var(--text-muted);font-size:9px;font-weight:900}.evidence-card dd{margin:5px 0 0;color:var(--ink);font-weight:800}.evidence-card pre{max-height:150px;overflow:auto;padding:12px;background:var(--paper-warm);font:11px/1.5 Consolas,monospace;white-space:pre-wrap}.candidate-warning{display:block;margin-top:18px;color:var(--brand-red-deep);font-size:11px}.editor-section{margin-top:20px;border:1px solid var(--line-strong);background:#fff;box-shadow:var(--shadow-card)}.editor-section>header{display:flex;align-items:center;justify-content:space-between;padding:26px 30px;color:#fff;background:var(--ink)}.editor-section h2{margin:7px 0 0;font:750 30px var(--font-display)}.mode-badge{padding:7px 10px;border:1px solid #ff9296;font-size:10px;font-weight:900}.mode-badge.readonly{border-color:#858d94;color:#cdd2d6}.notice,.feedback{margin:18px 30px 0;padding:14px 16px;background:var(--paper-warm);font-size:13px}.feedback.success{border-left:5px solid var(--success)}.refresh{margin:12px 30px 0;border:1px solid var(--brand-red);padding:9px 13px;color:var(--brand-red-deep);background:#fff;cursor:pointer;font-weight:800}.editor-section form{display:grid;grid-template-columns:1fr 1fr;gap:22px;padding:30px}.field{display:grid;align-content:start;gap:8px}.field.wide,.editor-section form footer{grid-column:1/-1}.field label{color:var(--ink);font-size:12px;font-weight:900}.field label em{margin-left:7px;color:var(--brand-red);font-size:10px;font-style:normal}.field textarea,.field select{width:100%;border:1px solid var(--line-strong);border-radius:0;padding:12px 13px;color:var(--ink);background:#fff;font:13px/1.55 var(--font-body);resize:vertical}.field textarea:disabled,.field select:disabled{color:#626b73;background:#f1f3f5}.field.decision select{min-height:46px;border-left:5px solid var(--brand-red);font-weight:800}.field-error{margin:0;color:var(--danger);font-size:11px;font-weight:800}.editor-section form footer{display:flex;align-items:center;justify-content:space-between;margin-top:4px;padding-top:22px;border-top:1px solid var(--line)}.editor-section form footer p{margin:0;color:var(--text-muted);font-size:12px}.editor-section form footer button{min-width:150px;border:0;padding:13px 20px;color:#fff;background:var(--brand-red);font-weight:900;cursor:pointer}.editor-section form footer button:disabled{cursor:wait;opacity:.65}@media(max-width:780px){.assessment-page{padding:30px 14px}.page-header{align-items:flex-start;flex-direction:column}.identity-strip,.evidence-layout,.editor-section form{grid-template-columns:1fr}.identity-strip div{border-right:0;border-bottom:1px solid var(--line)}.field.wide,.editor-section form footer{grid-column:auto}.evidence-card dl{flex-wrap:wrap}.editor-section>header,.editor-section form footer{align-items:flex-start;flex-direction:column;gap:16px}.editor-section form footer button{width:100%}}@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
.source-vector{display:grid;gap:5px;overflow-wrap:anywhere}.source-vector strong{color:var(--ink);font-size:10px}.cvss-panel{grid-column:1/-1;border:1px solid var(--line-strong);border-left:7px solid var(--brand-red);padding:22px;background:var(--paper-warm)}.cvss-panel>header{display:flex;align-items:center;justify-content:space-between}.cvss-panel h3{margin:5px 0 0;color:var(--ink);font:750 24px var(--font-display)}.score-chip{display:grid;place-items:center;min-width:68px;min-height:54px;color:#fff;background:var(--ink);font:800 25px var(--font-display)}.cvss-state{margin:12px 0;color:var(--brand-red-deep);font-size:11px;font-weight:900}.cvss-unavailable{margin:16px 0 0;padding:14px;border-left:4px solid var(--brand-red);background:#fff}.metric-grid{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}.metric-grid label{display:grid;gap:6px}.metric-grid span{font-size:11px;font-weight:800}.metric-grid b{float:right;color:var(--brand-red)}.metric-grid select{min-height:40px;border:1px solid var(--line-strong);padding:8px;background:#fff}.metric-grid em{color:var(--danger);font-size:10px;font-style:normal}.metric-readonly{display:flex;flex-wrap:wrap;gap:8px}.metric-readonly span{display:flex;gap:8px;border:1px solid var(--line);padding:7px 9px;background:#fff;font-size:11px}.score-result{display:grid;grid-template-columns:140px 1fr;gap:12px;margin:18px 0 0}.score-result div{padding:12px;background:#fff}.score-result .vector{grid-column:1/-1}.score-result dt{font-size:9px;font-weight:900}.score-result dd{margin:5px 0 0;overflow-wrap:anywhere;font:12px/1.5 Consolas,monospace}@media(max-width:780px){.metric-grid{grid-template-columns:1fr}.cvss-panel{grid-column:auto}.score-result{grid-template-columns:1fr}.score-result .vector{grid-column:auto}}
.action-panel{display:flex;justify-content:space-between;gap:20px;margin:0 30px 30px;padding:22px;border-left:7px solid var(--brand-red);background:var(--paper-warm)}.action-panel h3{margin:5px 0;font:750 24px var(--font-display)}.action-panel p{margin:7px 0;font-size:12px}.action-buttons{display:flex;align-items:center;gap:8px}.action-buttons button,.action-dialog button{border:0;padding:12px 16px;color:#fff;background:var(--brand-red);font-weight:900;cursor:pointer}.action-buttons button:disabled,.action-dialog button:disabled{opacity:.6}.dialog-backdrop{position:fixed;inset:0;z-index:20;display:grid;place-items:center;padding:20px;background:rgb(20 25 29 / .68)}.action-dialog{width:min(520px,100%);padding:28px;border-top:7px solid var(--brand-red);background:#fff;box-shadow:var(--shadow-card)}.action-dialog h3{margin:0;font:750 28px var(--font-display)}.action-dialog label{display:block;margin:18px 0 7px;font-weight:900}.action-dialog textarea{width:100%;box-sizing:border-box;padding:12px}.action-dialog footer{display:flex;justify-content:flex-end;gap:9px;margin-top:20px}.action-dialog footer button:first-child{color:var(--ink);background:#dfe3e6}
.revision-panel{margin-top:12px;padding:22px;border:1px solid var(--line-strong);background:#fff}.revision-panel>header{display:flex;align-items:center;justify-content:space-between;gap:16px}.revision-panel h2{margin:5px 0 0;font:750 24px var(--font-display)}.revision-panel small{color:var(--brand-red);font-size:9px;font-weight:900;letter-spacing:.14em}.revision-panel button{border:1px solid var(--line-strong);padding:9px 12px;background:#fff;cursor:pointer}.revision-list{display:flex;gap:8px;margin:18px 0;padding:0;list-style:none;overflow-x:auto}.revision-list button{display:grid;gap:4px;min-width:120px;text-align:left}.revision-list button.selected{border-color:var(--brand-red);box-shadow:inset 0 -4px 0 var(--brand-red)}.revision-list span,.history-notice{color:var(--text-muted);font-size:11px}.revision-diff{display:grid;gap:8px;margin:18px 0 0}.revision-diff div{display:grid;grid-template-columns:180px 1fr;gap:12px;padding:10px;background:var(--paper-warm)}.revision-diff dd{display:grid;gap:5px;margin:0;overflow-wrap:anywhere}.revision-diff del{color:var(--danger)}.revision-diff ins{color:var(--success);text-decoration:none}
</style>
