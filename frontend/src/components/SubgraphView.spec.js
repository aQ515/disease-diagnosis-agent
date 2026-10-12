/**
 * SubgraphView 组件测试
 *
 * 验证「子图可视化」这个创新点：
 * 给定后端返回的 nodes/links，SVG 里应渲染出对应数量的节点与关系标签。
 * 运行：npm test
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import SubgraphView from './SubgraphView.vue'

const DATA = {
  nodes: [
    { id: '2型糖尿病', label: '2型糖尿病', group: 'Disease', alias: '消渴病' },
    { id: '多饮', label: '多饮', group: 'Symptom' },
    { id: '内分泌科', label: '内分泌科', group: 'Department' },
  ],
  links: [
    { source: '2型糖尿病', target: '多饮', rel: 'HAS_SYMPTOM' },
    { source: '2型糖尿病', target: '内分泌科', rel: 'BELONGS_TO' },
  ],
}

describe('SubgraphView', () => {
  it('按数据渲染节点与边', () => {
    const wrapper = mount(SubgraphView, { props: { data: DATA } })

    // 3 个节点 → 3 个圆
    expect(wrapper.findAll('circle')).toHaveLength(3)
    // 2 条边 → 2 条线
    expect(wrapper.findAll('line')).toHaveLength(2)
    // 关系名要画在边上
    expect(wrapper.text()).toContain('HAS_SYMPTOM')
    expect(wrapper.text()).toContain('BELONGS_TO')
    // 节点名要显示
    expect(wrapper.text()).toContain('内分泌科')
  })

  it('数据为空时给出提示而不是空白', () => {
    const wrapper = mount(SubgraphView, { props: { data: { nodes: [], links: [] } } })
    expect(wrapper.findAll('circle')).toHaveLength(0)
    expect(wrapper.text()).toContain('先做一次检索')
  })
})
