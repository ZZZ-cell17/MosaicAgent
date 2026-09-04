import { useEffect, useRef, type KeyboardEvent } from 'react'
import {
  Bot,
  FileSearch,
  ImagePlus,
  Menu,
  PanelRight,
  Send,
  Square,
  Trash2,
  X,
} from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'

import type { ChatTurn, KnowledgeBase, QueryImage } from '../types'

interface ChatPanelProps {
  selectedKnowledgeBase: KnowledgeBase | null
  turns: ChatTurn[]
  question: string
  queryImages: QueryImage[]
  streaming: boolean
  onQuestionChange: (value: string) => void
  onSelectImages: (files: File[]) => void
  onRemoveImage: (id: string) => void
  onSend: (question?: string) => void
  onStop: () => void
  onClear: () => void
  onOpenSidebar: () => void
  onOpenTrace: () => void
}

const suggestedQuestions = [
  '这个知识库的核心内容是什么？',
  '请整理关键概念并给出引用。',
  '知识库中的图表传达了什么信息？',
]

export function ChatPanel({
  selectedKnowledgeBase,
  turns,
  question,
  queryImages,
  streaming,
  onQuestionChange,
  onSelectImages,
  onRemoveImage,
  onSend,
  onStop,
  onClear,
  onOpenSidebar,
  onOpenTrace,
}: ChatPanelProps) {
  const imageInputRef = useRef<HTMLInputElement>(null)
  const bottomRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ block: 'end', behavior: streaming ? 'auto' : 'smooth' })
  }, [streaming, turns])

  const handleKeyDown = (event: KeyboardEvent<HTMLTextAreaElement>) => {
    if (event.key === 'Enter' && !event.shiftKey && !event.nativeEvent.isComposing) {
      event.preventDefault()
      onSend()
    }
  }

  return (
    <main className="chat-panel">
      <header className="chat-header">
        <button className="icon-button mobile-menu" type="button" onClick={onOpenSidebar} title="打开知识库">
          <Menu size={19} />
        </button>
        <div className="chat-heading">
          <h1>{selectedKnowledgeBase?.kb_name || '选择知识库'}</h1>
          <span>{selectedKnowledgeBase?.kb_id || '尚未选择知识库'}</span>
        </div>
        <div className="header-actions">
          <button className="icon-button trace-toggle" type="button" onClick={onOpenTrace} title="查看运行轨迹">
            <PanelRight size={18} />
          </button>
          <button className="icon-button" type="button" onClick={onClear} disabled={!turns.length || streaming} title="清空对话">
            <Trash2 size={17} />
          </button>
        </div>
      </header>

      <div className="conversation" aria-live="polite">
        {turns.length === 0 ? (
          <div className="conversation-empty">
            <div className="empty-icon"><Bot size={25} /></div>
            <h2>基于知识证据开始提问</h2>
            <div className="suggestion-list">
              {suggestedQuestions.map((suggestion) => (
                <button
                  type="button"
                  key={suggestion}
                  disabled={!selectedKnowledgeBase}
                  onClick={() => onSend(suggestion)}
                >
                  <FileSearch size={15} />
                  {suggestion}
                </button>
              ))}
            </div>
          </div>
        ) : (
          turns.map((turn) => (
            <section className="turn" key={turn.id}>
              <div className="user-message">
                {turn.imagePreviews.length ? (
                  <div className="sent-images">
                    {turn.imagePreviews.map((url) => <img src={url} alt="提问附件" key={url} />)}
                  </div>
                ) : null}
                <p>{turn.question}</p>
              </div>
              <div className={`assistant-message is-${turn.status}`}>
                <div className="assistant-avatar"><Bot size={16} /></div>
                <div className="assistant-body">
                  <div className="assistant-meta">
                    <strong>MosaicAgent</strong>
                    {turn.route ? <span className={`route-badge route-${turn.route}`}>{turn.route.toUpperCase()}</span> : null}
                  </div>
                  {turn.answer ? (
                    <div className="markdown-body">
                      <ReactMarkdown
                        remarkPlugins={[remarkGfm]}
                        components={{
                          a: ({ children, ...props }) => <a {...props} target="_blank" rel="noreferrer">{children}</a>,
                        }}
                      >
                        {turn.answer}
                      </ReactMarkdown>
                    </div>
                  ) : turn.status === 'streaming' ? (
                    <div className="thinking-line"><span /><span /><span /></div>
                  ) : null}
                  {turn.error ? <p className="turn-error">{turn.error}</p> : null}
                  {turn.references.length ? (
                    <div className="references">
                      <div className="references-heading">引用证据 · {turn.references.length}</div>
                      {turn.references.map((reference, index) => (
                        <a
                          className="reference-row"
                          href={reference.url || undefined}
                          target={reference.url ? '_blank' : undefined}
                          rel={reference.url ? 'noreferrer' : undefined}
                          key={`${reference.ref_id}-${index}`}
                        >
                          <span>〔{index + 1}〕</span>
                          <div>
                            <strong>{reference.filename || reference.content_type}</strong>
                            {reference.text_preview ? <small>{reference.text_preview}</small> : null}
                          </div>
                        </a>
                      ))}
                    </div>
                  ) : null}
                </div>
              </div>
            </section>
          ))
        )}
        <div ref={bottomRef} className={turns.length ? 'conversation-end' : undefined} />
      </div>

      <div className="composer-shell">
        {queryImages.length ? (
          <div className="composer-images">
            {queryImages.map((image) => (
              <div className="composer-image" key={image.id}>
                <img src={image.previewUrl} alt={image.file.name} />
                <button type="button" onClick={() => onRemoveImage(image.id)} title="移除图片"><X size={13} /></button>
              </div>
            ))}
          </div>
        ) : null}
        <div className="composer">
          <input
            ref={imageInputRef}
            className="visually-hidden"
            type="file"
            accept=".png,.jpg,.jpeg"
            multiple
            onChange={(event) => {
              onSelectImages(Array.from(event.target.files || []))
              event.target.value = ''
            }}
          />
          <button
            className="icon-button composer-tool"
            type="button"
            disabled={!selectedKnowledgeBase || streaming || queryImages.length >= 4}
            onClick={() => imageInputRef.current?.click()}
            title="添加提问图片"
          >
            <ImagePlus size={19} />
          </button>
          <textarea
            value={question}
            rows={1}
            disabled={!selectedKnowledgeBase || streaming}
            placeholder={selectedKnowledgeBase ? '向知识库提问…' : '请先选择知识库'}
            onChange={(event) => onQuestionChange(event.target.value)}
            onKeyDown={handleKeyDown}
          />
          {streaming ? (
            <button className="send-button stop-button" type="button" onClick={onStop} title="停止生成">
              <Square size={16} fill="currentColor" />
            </button>
          ) : (
            <button
              className="send-button"
              type="button"
              disabled={!selectedKnowledgeBase || (!question.trim() && !queryImages.length)}
              onClick={() => onSend()}
              title="发送"
            >
              <Send size={17} />
            </button>
          )}
        </div>
      </div>
    </main>
  )
}
