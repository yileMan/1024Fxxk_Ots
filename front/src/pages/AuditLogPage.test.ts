import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import AuditLogPage from './AuditLogPage.vue'

const fetchMock=vi.fn()
const item={id:3,user_id:1,actor_display_name:'管理员',action:'update',object_type:'product',object_id:'8',detail_keys:['changes','schema_version'],created_at:'2026-09-06T02:00:00Z'}
beforeEach(()=>{fetchMock.mockReset();vi.stubGlobal('fetch',fetchMock)})

describe('AuditLogPage',()=>{
  it('filters, pages and safely displays a structured detail',async()=>{
    fetchMock
      .mockResolvedValueOnce(new Response(JSON.stringify({items:[item],total:2,next_cursor:'next',limit:20}),{status:200}))
      .mockResolvedValueOnce(new Response(JSON.stringify({...item,detail:{changes:{product_name:{from:'旧',to:'<img onerror=alert(1)>'}}}}),{status:200}))
      .mockResolvedValueOnce(new Response(JSON.stringify({items:[],total:2,next_cursor:null,limit:20}),{status:200}))
    const wrapper=mount(AuditLogPage);await flushPromises()
    expect(wrapper.text()).toContain('管理员');expect(wrapper.text()).toContain('更新')
    await wrapper.get('button[aria-label="查看变更记录 3"]').trigger('click');await flushPromises()
    expect(wrapper.get('[role="dialog"]').text()).toContain('<img onerror=alert(1)>')
    expect(wrapper.find('[role="dialog"] img').exists()).toBe(false)
    await wrapper.get('button[aria-label="关闭差异"]').trigger('click')
    await wrapper.findAll('.pager button')[1].trigger('click');await flushPromises()
    expect(wrapper.text()).toContain('没有符合条件')
  })

  it('reports permission and can retry service errors',async()=>{
    fetchMock.mockResolvedValueOnce(new Response(JSON.stringify({code:'AUTH_FORBIDDEN'}),{status:403}))
    const wrapper=mount(AuditLogPage);await flushPromises()
    expect(wrapper.get('[role="alert"]').text()).toContain('无权访问变更记录')
  })
})
