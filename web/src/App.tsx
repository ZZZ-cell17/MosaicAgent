import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import {
  ApiRequestError,
  addUploadedFiles,
  createKnowledgeBase,
  deleteKnowledgeBase,
  deleteKnowledgeFile,
  getReadyStatus,
  listKnowledgeBases,
  listKnowledgeFiles,
  queryAgent,
  uploadDocument,
} from './api'
import { ChatPanel } from './components/ChatPanel'
import { Dialog } from './components/Dialog'
import { KnowledgePanel } from './components/KnowledgePanel'
import { TracePanel } from './components/TracePanel'
import type {
  AgentEvent,
  AgentReference,
  ChatTurn,
  KnowledgeBase,
  KnowledgeFile,
  QueryImage,
} from './types'
import { createClientId } from './utils'

type DeleteTarget =
  | { kind: 'knowledge-base'; item: KnowledgeBase }
  | { kind: 'file'; item: KnowledgeFile }

interface Notice {
  kind: 'success' | 'error'
  message: string
}

const storedKnowledgeBase = localStorage.getItem('mosaic-agent:selected-kb')

export default function App() {
  const [knowledgeBases, setKnowledgeBases] = useState<KnowledgeBase[]>([])
  const [selectedKbId, setSelectedKbId] = useState<string | null>(storedKnowledgeBase)
  const [files, setFiles] = useState<KnowledgeFile[]>([])
  const [serviceReady, setServiceReady] = useState(false)
  const [libraryBusy, setLibraryBusy] = useState(false)
  const [filesVersion, setFilesVersion] = useState(0)
  const [turns, setTurns] = useState<ChatTurn[]>([])
  const [traceEvents, setTraceEvents] = useState<AgentEvent[]>([])
  const [question, setQuestion] = useState('')
  const [queryImages, setQueryImages] = useState<QueryImage[]>([])
  const [streaming, setStreaming] = useState(false)
  const [sidebarOpen, setSidebarOpen] = useState(false)
  const [traceOpen, setTraceOpen] = useState(false)
  const [createOpen, setCreateOpen] = useState(false)
  const [newKbName, setNewKbName] = useState('')
  const [newKbId, setNewKbId] = useState('')
  const [newKbDescription, setNewKbDescription] = useState('')
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null)
  const [notice, setNotice] = useState<Notice | null>(null)
  const abortControllerRef = useRef<AbortController | null>(null)
  const previewUrlsRef = useRef(new Set<string>())

  const selectedKnowledgeBase = useMemo(
    () => knowledgeBases.find((item) => item.kb_id === selectedKbId) || null,
    [knowledgeBases, selectedKbId],
  )

  const showNotice = useCallback((kind: Notice['kind'], message: string) => {
    setNotice({ kind, message })
  }, [])

  const refreshKnowledgeBases = useCallback(async (preferredId?: string) => {
    const items = await listKnowledgeBases()
    setKnowledgeBases(items)
    setSelectedKbId((current) => {
      const candidate = preferredId || current
      if (candidate && items.some((item) => item.kb_id === candidate)) return candidate
      return items[0]?.kb_id || null
    })
    return items
  }, [])

  useEffect(() => {
    let cancelled = false
    const loadInitialState = async () => {
      const [readyResult, knowledgeBaseResult] = await Promise.allSettled([
        getReadyStatus(),
        refreshKnowledgeBases(),
      ])
      if (cancelled) return

      if (readyResult.status === 'fulfilled') {
        setServiceReady(readyResult.value.ready)
        if (!readyResult.value.ready) {
          showNotice('error', 'MosaicAgent 服务未就绪，请检查模型和运行配置')
        }
      } else {
        setServiceReady(false)
        const error = readyResult.reason
        showNotice(
          'error',
          error instanceof ApiRequestError && error.status === 503
            ? 'MosaicAgent 服务未就绪，请检查模型和运行配置'
            : '无法连接 MosaicAgent 服务',
        )
      }

      if (knowledgeBaseResult.status === 'rejected' && readyResult.status === 'fulfilled') {
        showNotice('error', '读取知识库失败')
      }
    }

    void loadInitialState()
    return () => {
      cancelled = true
    }
  }, [refreshKnowledgeBases, showNotice])

  useEffect(() => {
    if (selectedKbId) localStorage.setItem('mosaic-agent:selected-kb', selectedKbId)
    else localStorage.removeItem('mosaic-agent:selected-kb')
  }, [selectedKbId])

  useEffect(() => {
    if (!selectedKbId) {
      setFiles([])
      return
    }
    let cancelled = false
    let timer: number | undefined
    const poll = async () => {
      try {
        const records = await listKnowledgeFiles(selectedKbId)
        if (cancelled) return
        setFiles(records)
        const processing = records.some((file) => ['PENDING', 'RUNNING'].includes(file.file_status || ''))
        timer = window.setTimeout(poll, processing ? 2000 : 8000)
      } catch (error) {
        if (!cancelled) {
          showNotice('error', error instanceof Error ? error.message : '读取文件列表失败')
          timer = window.setTimeout(poll, 10000)
        }
      }
    }
    void poll()
    return () => {
      cancelled = true
      if (timer) window.clearTimeout(timer)
    }
  }, [filesVersion, selectedKbId, showNotice])

  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(null), 3500)
    return () => window.clearTimeout(timer)
  }, [notice])

  useEffect(() => () => {
    previewUrlsRef.current.forEach((url) => URL.revokeObjectURL(url))
  }, [])

  const clearConversation = useCallback(() => {
    setTurns((current) => {
      current.forEach((turn) => turn.imagePreviews.forEach((url) => {
        URL.revokeObjectURL(url)
        previewUrlsRef.current.delete(url)
      }))
      return []
    })
    setTraceEvents([])
  }, [])

  const handleCreateKnowledgeBase = async () => {
    if (!newKbName.trim()) return
    setLibraryBusy(true)
    try {
      const created = await createKnowledgeBase({
        kb_name: newKbName.trim(),
        kb_id: newKbId.trim() || undefined,
        kb_desc: newKbDescription.trim() || undefined,
      })
      clearConversation()
      await refreshKnowledgeBases(created.kb_id)
      setCreateOpen(false)
      setNewKbName('')
      setNewKbId('')
      setNewKbDescription('')
      showNotice('success', '知识库已创建')
    } catch (error) {
      showNotice('error', error instanceof Error ? error.message : '创建知识库失败')
    } finally {
      setLibraryBusy(false)
    }
  }

  const handleUpload = async (selectedFiles: File[]) => {
    if (!selectedKbId || !selectedFiles.length) return
    setLibraryBusy(true)
    try {
      const uploads = []
      for (const file of selectedFiles) uploads.push(await uploadDocument(file))
      await addUploadedFiles(selectedKbId, uploads)
      setFilesVersion((value) => value + 1)
      showNotice('success', `${uploads.length} 个文件已提交入库`)
    } catch (error) {
      showNotice('error', error instanceof Error ? error.message : '文件上传失败')
    } finally {
      setLibraryBusy(false)
    }
  }

  const handleConfirmDelete = async () => {
    if (!deleteTarget) return
    setLibraryBusy(true)
    try {
      if (deleteTarget.kind === 'knowledge-base') {
        await deleteKnowledgeBase(deleteTarget.item.kb_id)
        if (deleteTarget.item.kb_id === selectedKbId) clearConversation()
        await refreshKnowledgeBases()
        showNotice('success', '知识库已删除')
      } else {
        await deleteKnowledgeFile(deleteTarget.item.kb_id, deleteTarget.item.file_id)
        setFilesVersion((value) => value + 1)
        showNotice('success', '文件已删除')
      }
      setDeleteTarget(null)
    } catch (error) {
      showNotice('error', error instanceof Error ? error.message : '删除失败')
    } finally {
      setLibraryBusy(false)
    }
  }

  const handleSelectQueryImages = (selectedFiles: File[]) => {
    const available = Math.max(0, 4 - queryImages.length)
    const validFiles = selectedFiles
      .filter((file) => /\.(png|jpe?g)$/i.test(file.name))
      .slice(0, available)
    if (validFiles.length !== selectedFiles.length) {
      showNotice('error', '提问图片仅支持 PNG、JPG，最多 4 张')
    }
    const additions = validFiles.map((file) => {
      const previewUrl = URL.createObjectURL(file)
      previewUrlsRef.current.add(previewUrl)
      return { id: createClientId('image'), file, previewUrl }
    })
    setQueryImages((current) => [...current, ...additions])
  }

  const handleRemoveQueryImage = (id: string) => {
    setQueryImages((current) => current.filter((image) => {
      if (image.id !== id) return true
      URL.revokeObjectURL(image.previewUrl)
      previewUrlsRef.current.delete(image.previewUrl)
      return false
    }))
  }

  const handleSend = async (suggestedQuestion?: string) => {
    const prompt = (suggestedQuestion ?? question).trim() || '请分析这些图片。'
    if (!selectedKbId || streaming || (!prompt && !queryImages.length)) return

    const pendingImages = [...queryImages]
    const turnId = createClientId('turn')
    const controller = new AbortController()
    abortControllerRef.current = controller
    setQueryImages([])
    setQuestion('')
    setTraceEvents([])
    setStreaming(true)
    setTurns((current) => [
      ...current,
      {
        id: turnId,
        question: prompt,
        imagePreviews: pendingImages.map((image) => image.previewUrl),
        answer: '',
        references: [],
        status: 'streaming',
      },
    ])

    let runFailed = false
    let failureMessage = ''
    try {
      const imageUrls: string[] = []
      for (const image of pendingImages) {
        const uploaded = await uploadDocument(image.file)
        imageUrls.push(uploaded.permanent_url)
      }

      await queryAgent(
        { kbId: selectedKbId, question: prompt, imageUrls },
        {
          signal: controller.signal,
          onEvent: (event) => {
            if (event.event !== 'answer_delta') {
              setTraceEvents((current) => [...current, event])
            }
            if (event.event === 'answer_delta') {
              const content = String(event.data.content || '')
              setTurns((current) => current.map((turn) => (
                turn.id === turnId ? { ...turn, answer: turn.answer + content } : turn
              )))
            }
            if (event.event === 'route_selected') {
              const route = event.data.route
              if (route === 'llm' || route === 'vlm') {
                setTurns((current) => current.map((turn) => (
                  turn.id === turnId ? { ...turn, route } : turn
                )))
              }
            }
            if (event.event === 'generation_started') {
              const references = Array.isArray(event.data.references)
                ? event.data.references as AgentReference[]
                : []
              setTurns((current) => current.map((turn) => (
                turn.id === turnId ? { ...turn, references } : turn
              )))
            }
            if (event.event === 'run_failed') {
              runFailed = true
              failureMessage = String(event.data.message || 'Agent 执行失败')
            }
          },
        },
      )

      setTurns((current) => current.map((turn) => (
        turn.id === turnId
          ? { ...turn, status: runFailed ? 'failed' : 'completed', error: failureMessage || undefined }
          : turn
      )))
    } catch (error) {
      const stopped = error instanceof DOMException && error.name === 'AbortError'
      const message = stopped ? undefined : error instanceof Error ? error.message : 'Agent 请求失败'
      setTurns((current) => current.map((turn) => (
        turn.id === turnId
          ? { ...turn, status: stopped ? 'stopped' : 'failed', error: message }
          : turn
      )))
      if (message) showNotice('error', message)
    } finally {
      if (abortControllerRef.current === controller) abortControllerRef.current = null
      setStreaming(false)
    }
  }

  return (
    <div className="app-shell">
      <KnowledgePanel
        open={sidebarOpen}
        knowledgeBases={knowledgeBases}
        selectedKbId={selectedKbId}
        files={files}
        serviceReady={serviceReady}
        busy={libraryBusy}
        locked={streaming}
        onClose={() => setSidebarOpen(false)}
        onSelect={(kbId) => {
          if (kbId !== selectedKbId) clearConversation()
          setSelectedKbId(kbId)
          setSidebarOpen(false)
        }}
        onCreate={() => setCreateOpen(true)}
        onUpload={(items) => void handleUpload(items)}
        onDeleteKnowledgeBase={(item) => setDeleteTarget({ kind: 'knowledge-base', item })}
        onDeleteFile={(item) => setDeleteTarget({ kind: 'file', item })}
      />
      <ChatPanel
        selectedKnowledgeBase={selectedKnowledgeBase}
        turns={turns}
        question={question}
        queryImages={queryImages}
        streaming={streaming}
        onQuestionChange={setQuestion}
        onSelectImages={handleSelectQueryImages}
        onRemoveImage={handleRemoveQueryImage}
        onSend={(value) => void handleSend(value)}
        onStop={() => abortControllerRef.current?.abort()}
        onClear={clearConversation}
        onOpenSidebar={() => setSidebarOpen(true)}
        onOpenTrace={() => setTraceOpen(true)}
      />
      <TracePanel events={traceEvents} open={traceOpen} onClose={() => setTraceOpen(false)} />

      {(sidebarOpen || traceOpen) ? (
        <button
          aria-label="关闭面板"
          className="panel-scrim"
          type="button"
          onClick={() => {
            setSidebarOpen(false)
            setTraceOpen(false)
          }}
        />
      ) : null}

      {notice ? <div className={`notice notice-${notice.kind}`}>{notice.message}</div> : null}

      {createOpen ? (
        <Dialog
          title="新建知识库"
          onClose={() => setCreateOpen(false)}
          footer={(
            <>
              <button className="secondary-button" type="button" onClick={() => setCreateOpen(false)}>取消</button>
              <button className="primary-button" type="button" disabled={!newKbName.trim() || libraryBusy} onClick={() => void handleCreateKnowledgeBase()}>创建</button>
            </>
          )}
        >
          <label className="field">
            <span>名称</span>
            <input autoFocus maxLength={100} value={newKbName} onChange={(event) => setNewKbName(event.target.value)} />
          </label>
          <label className="field">
            <span>知识库 ID</span>
            <input maxLength={64} placeholder="留空自动生成" value={newKbId} onChange={(event) => setNewKbId(event.target.value)} />
          </label>
          <label className="field">
            <span>描述</span>
            <textarea rows={3} maxLength={500} value={newKbDescription} onChange={(event) => setNewKbDescription(event.target.value)} />
          </label>
        </Dialog>
      ) : null}

      {deleteTarget ? (
        <Dialog
          title={deleteTarget.kind === 'knowledge-base' ? '删除知识库' : '删除文件'}
          onClose={() => setDeleteTarget(null)}
          footer={(
            <>
              <button className="secondary-button" type="button" onClick={() => setDeleteTarget(null)}>取消</button>
              <button className="danger-button" type="button" disabled={libraryBusy} onClick={() => void handleConfirmDelete()}>删除</button>
            </>
          )}
        >
          <p className="confirm-copy">
            {deleteTarget.kind === 'knowledge-base'
              ? `将删除“${deleteTarget.item.kb_name || deleteTarget.item.kb_id}”及其全部索引。`
              : `将从知识库中删除“${deleteTarget.item.title}”。`}
          </p>
        </Dialog>
      ) : null}
    </div>
  )
}
