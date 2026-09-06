import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import SystemOperationsPage from './SystemOperationsPage.vue'

const fetchMock=vi.fn()
const component=(status='ok',summary='正常')=>({status,observed_at:'2026-09-06T02:00:00Z',summary,version:null,commit:null,latency_ms:null,total_bytes:null,free_bytes:null,used_percent:null,batch_no:null,batch_status:null,started_at:null,finished_at:null,file_name:null,size_bytes:null,error_code:null})
const response={overall_status:'error',observed_at:'2026-09-06T02:00:00Z',application:{...component(),version:'1.0.0'},database:component(),disk:{...component('warning','空间不足'),total_bytes:1000,free_bytes:100,used_percent:90},backup:component('unknown','未配置'),latest_import:component('unknown','暂无导入'),latest_failure:component('error','最近导入失败')}
beforeEach(()=>{fetchMock.mockReset();vi.stubGlobal('fetch',fetchMock)})

describe('SystemOperationsPage',()=>{
  it('shows all components and visible failure states',async()=>{
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(response),{status:200}))
    const wrapper=mount(SystemOperationsPage);await flushPromises()
    expect(wrapper.text()).toContain('系统运行状态');expect(wrapper.text()).toContain('最近导入失败');expect(wrapper.text()).toContain('90%')
    expect(wrapper.findAll('.grid article')).toHaveLength(6)
  })

  it('marks prior observations stale after refresh fails',async()=>{
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify(response),{status:200})).mockResolvedValueOnce(new Response('bad',{status:503}))
    const wrapper=mount(SystemOperationsPage);await flushPromises();await wrapper.get('[data-action="refresh"]').trigger('click');await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('陈旧');expect(wrapper.text()).toContain('状态陈旧')
  })
})
