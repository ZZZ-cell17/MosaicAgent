import { useRef } from 'react'
import {
  CircleAlert,
  CircleCheck,
  CircleDashed,
  Database,
  FileImage,
  FileText,
  LoaderCircle,
  Plus,
  Trash2,
  Upload,
  X,
} from 'lucide-react'

import type { KnowledgeBase, KnowledgeFile } from '../types'

interface KnowledgePanelProps {
  open: boolean
  knowledgeBases: KnowledgeBase[]
  selectedKbId: string | null
  files: KnowledgeFile[]
  serviceReady: boolean
  busy: boolean
  locked: boolean
  onClose: () => void
  onSelect: (kbId: string) => void
  onCreate: () => void
  onUpload: (files: File[]) => void
  onDeleteKnowledgeBase: (knowledgeBase: KnowledgeBase) => void
  onDeleteFile: (file: KnowledgeFile) => void
}

const statusLabels = {
  PENDING: '等待处理',
  RUNNING: '正在入库',
  SUCCESS: '已入库',
  FAILED: '入库失败',
}

function StatusIcon({ file }: { file: KnowledgeFile }) {
  const status = file.file_status || 'PENDING'
  if (status === 'SUCCESS') return <CircleCheck className="status-success" size={15} />
  if (status === 'FAILED') return <CircleAlert className="status-failed" size={15} />
  if (status === 'RUNNING') return <LoaderCircle className="status-running spin" size={15} />
  return <CircleDashed className="status-pending" size={15} />
}

function FileIcon({ name }: { name: string }) {
  return /\.(png|jpe?g)$/i.test(name) ? <FileImage size={16} /> : <FileText size={16} />
}

export function KnowledgePanel({
  open,
  knowledgeBases,
  selectedKbId,
  files,
  serviceReady,
  busy,
  locked,
  onClose,
  onSelect,
  onCreate,
  onUpload,
  onDeleteKnowledgeBase,
  onDeleteFile,
}: KnowledgePanelProps) {
  const inputRef = useRef<HTMLInputElement>(null)

  const handleFiles = (fileList: FileList | null) => {
    if (!fileList?.length) return
    onUpload(Array.from(fileList))
    if (inputRef.current) inputRef.current.value = ''
  }

  return (
    <aside className={`knowledge-panel ${open ? 'is-open' : ''}`}>
      <div className="brand-row">
        <div className="mosaic-mark" aria-hidden="true">
          <span />
          <span />
          <span />
          <span />
        </div>
        <div>
          <strong>MosaicAgent</strong>
          <small>多模态知识智能体</small>
        </div>
        <button className="icon-button sidebar-close" type="button" onClick={onClose} title="关闭侧栏">
          <X size={18} />
        </button>
      </div>

      <section className="sidebar-section kb-section">
        <div className="section-heading">
          <span>知识库</span>
          <button className="icon-button" type="button" onClick={onCreate} title="新建知识库">
            <Plus size={17} />
          </button>
        </div>
        <div className="kb-list" role="listbox" aria-label="知识库列表">
          {knowledgeBases.length === 0 ? (
            <div className="sidebar-empty">暂无知识库</div>
          ) : (
            knowledgeBases.map((kb) => (
              <div
                className={`kb-row ${kb.kb_id === selectedKbId ? 'is-selected' : ''}`}
                key={kb.kb_id}
              >
                <button
                  className="kb-select"
                  type="button"
                  onClick={() => onSelect(kb.kb_id)}
                  disabled={busy || locked}
                >
                  <Database size={16} />
                  <span>
                    <strong>{kb.kb_name || kb.kb_id}</strong>
                    <small>{kb.kb_id}</small>
                  </span>
                </button>
                <button
                  className="icon-button row-action danger-action"
                  type="button"
                  onClick={() => onDeleteKnowledgeBase(kb)}
                  disabled={busy || locked}
                  title="删除知识库"
                >
                  <Trash2 size={15} />
                </button>
              </div>
            ))
          )}
        </div>
      </section>

      <section className="sidebar-section files-section">
        <div className="section-heading">
          <span>知识文件</span>
          <span className="section-count">{files.length}</span>
        </div>
        <div className="file-list">
          {!selectedKbId ? (
            <div className="sidebar-empty">请选择知识库</div>
          ) : files.length === 0 ? (
            <div className="sidebar-empty">暂无文件</div>
          ) : (
            files.map((file) => (
              <div className="file-row" key={file.file_id}>
                <div className="file-kind"><FileIcon name={file.title} /></div>
                <div className="file-copy">
                  <strong title={file.title}>{file.title}</strong>
                  <small title={file.task_status?.error || statusLabels[file.file_status || 'PENDING']}>
                    <StatusIcon file={file} />
                    {statusLabels[file.file_status || 'PENDING']}
                  </small>
                </div>
                <button
                  className="icon-button row-action danger-action"
                  type="button"
                  onClick={() => onDeleteFile(file)}
                  disabled={busy || locked || file.file_status === 'RUNNING'}
                  title="删除文件"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))
          )}
        </div>
        <input
          ref={inputRef}
          className="visually-hidden"
          type="file"
          accept=".pdf,.docx,.md,.txt,.png,.jpg,.jpeg"
          multiple
          onChange={(event) => handleFiles(event.target.files)}
        />
        <button
          className="upload-button"
          type="button"
          disabled={!selectedKbId || busy || locked}
          onClick={() => inputRef.current?.click()}
        >
          {busy ? <LoaderCircle className="spin" size={16} /> : <Upload size={16} />}
          上传文件
        </button>
      </section>

      <div className="service-status" title="服务就绪状态">
        <span className={serviceReady ? 'ready-dot' : 'offline-dot'} />
        <span>{serviceReady ? 'MRAG 服务就绪' : 'MRAG 服务不可用'}</span>
      </div>
    </aside>
  )
}
