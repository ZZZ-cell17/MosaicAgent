import {
  Braces,
  Check,
  CircleAlert,
  GitBranch,
  ListFilter,
  Route,
  ScanSearch,
  Sparkles,
  Timer,
  X,
} from 'lucide-react'

import type { AgentEvent } from '../types'

interface TracePanelProps {
  events: AgentEvent[]
  open: boolean
  onClose: () => void
}

const eventLabels: Record<string, string> = {
  run_started: '任务开始',
  query_planned: '查询规划',
  retrieval_completed: '多路检索',
  evidence_evaluated: '证据判断',
  rerank_completed: '文本重排',
  route_selected: '模型路由',
  generation_started: '生成回答',
  run_completed: '任务完成',
  run_failed: '任务失败',
}

const channelLabels: Record<string, string> = {
  text_dense: '文本向量',
  text_sparse: 'BM25',
  image_dense: '图片向量',
  page_dense: '页面向量',
}

function eventIcon(name: string) {
  if (name === 'query_planned') return <GitBranch size={15} />
  if (name === 'retrieval_completed') return <ScanSearch size={15} />
  if (name === 'evidence_evaluated') return <ListFilter size={15} />
  if (name === 'rerank_completed') return <Braces size={15} />
  if (name === 'route_selected') return <Route size={15} />
  if (name === 'generation_started') return <Sparkles size={15} />
  if (name === 'run_failed') return <CircleAlert size={15} />
  return <Check size={15} />
}

function formatDuration(value: unknown): string {
  const duration = Number(value)
  if (!Number.isFinite(duration)) return ''
  return duration >= 1000 ? `${(duration / 1000).toFixed(1)}s` : `${duration}ms`
}

function EventDetail({ event }: { event: AgentEvent }) {
  const data = event.data
  if (event.event === 'run_started') {
    return <p>最多 {String(data.max_rounds || 0)} 轮检索</p>
  }
  if (event.event === 'query_planned') {
    const queries = Array.isArray(data.sub_queries) ? data.sub_queries : []
    return (
      <div className="query-list">
        {queries.map((query, index) => <span key={`${String(query)}-${index}`}>{String(query)}</span>)}
      </div>
    )
  }
  if (event.event === 'retrieval_completed') {
    const channels = (data.channels || {}) as Record<string, { total?: number; status?: string }>
    return (
      <div className="channel-grid">
        {Object.entries(channels).map(([name, channel]) => (
          <div key={name} className={channel.status === 'ok' ? '' : 'is-degraded'}>
            <span>{channelLabels[name] || name}</span>
            <strong>{channel.total || 0}</strong>
          </div>
        ))}
      </div>
    )
  }
  if (event.event === 'evidence_evaluated') {
    return (
      <>
        <p className={data.sufficient ? 'decision-positive' : 'decision-continue'}>
          {data.sufficient ? '证据充分' : data.will_continue ? '继续检索' : '结束检索'}
        </p>
        {data.reason ? <p>{String(data.reason)}</p> : null}
      </>
    )
  }
  if (event.event === 'rerank_completed') {
    return <p>{String(data.input_count || 0)} 条候选 → {String(data.output_count || 0)} 条证据</p>
  }
  if (event.event === 'route_selected') {
    return (
      <>
        <p><span className={`route-badge route-${String(data.route)}`}>{String(data.route).toUpperCase()}</span></p>
        {data.reason ? <p>{String(data.reason)}</p> : null}
      </>
    )
  }
  if (event.event === 'generation_started') {
    const references = Array.isArray(data.references) ? data.references.length : 0
    return <p>{references} 项引用证据</p>
  }
  if (event.event === 'run_completed') {
    return <p>{String(data.round_count || 0)} 轮 · {formatDuration(data.duration_ms)}</p>
  }
  if (event.event === 'run_failed') {
    return <p>{String(data.message || 'Agent 执行失败')}</p>
  }
  return null
}

export function TracePanel({ events, open, onClose }: TracePanelProps) {
  const visibleEvents = events.filter((event) => event.event !== 'answer_delta')
  const latestRoute = [...visibleEvents].reverse().find((event) => event.event === 'route_selected')
  const completed = [...visibleEvents].reverse().find((event) => event.event === 'run_completed')

  return (
    <aside className={`trace-panel ${open ? 'is-open' : ''}`}>
      <header className="trace-header">
        <div>
          <span className="eyebrow">Agent Trace</span>
          <h2>运行轨迹</h2>
        </div>
        <button className="icon-button trace-close" type="button" onClick={onClose} title="关闭轨迹">
          <X size={18} />
        </button>
      </header>

      {visibleEvents.length === 0 ? (
        <div className="trace-empty">
          <ScanSearch size={22} />
          <p>等待 Agent 运行</p>
        </div>
      ) : (
        <>
          <div className="trace-summary">
            <div>
              <span>路由</span>
              <strong>{latestRoute ? String(latestRoute.data.route).toUpperCase() : '—'}</strong>
            </div>
            <div>
              <span>轮次</span>
              <strong>{completed ? String(completed.data.round_count || 0) : '…'}</strong>
            </div>
            <div>
              <span>耗时</span>
              <strong>{completed ? formatDuration(completed.data.duration_ms) : '…'}</strong>
            </div>
          </div>
          <div className="trace-timeline">
            {visibleEvents.map((event, index) => (
              <article className={`trace-event trace-${event.event}`} key={`${event.event}-${event.round_no || 0}-${index}`}>
                <div className="trace-node">{eventIcon(event.event)}</div>
                <div className="trace-content">
                  <div className="trace-title">
                    <strong>{eventLabels[event.event] || event.event}</strong>
                    {event.round_no ? <span>第 {event.round_no} 轮</span> : null}
                  </div>
                  <EventDetail event={event} />
                </div>
              </article>
            ))}
          </div>
        </>
      )}
      <div className="trace-footer"><Timer size={14} /> SSE 实时事件</div>
    </aside>
  )
}
