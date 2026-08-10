/**
 * 世界文件树：按目录层级构建 + 文件夹可折叠 + 文件选中/删除
 * （从 WorldDesignPage 拆分；移动端目录导航复用 buildWorldTree）
 */
import { ChevronRight, Folder, FolderOpen, Trash2 } from 'lucide-react'
import { fileTypeIcon } from './FileContentPane'

export interface WorldFile {
  path: string
  size: number
}

export interface WorldTreeNode {
  name: string
  path: string
  children: WorldTreeNode[]
  isDir: boolean
}

/** 扁平文件列表 → 目录树（文件夹在前、按名排序） */
export function buildWorldTree(files: WorldFile[]): WorldTreeNode {
  const root: WorldTreeNode = { name: '', path: '', children: [], isDir: true }
  for (const f of files) {
    const parts = f.path.split('/')
    let node = root
    let acc = ''
    for (let i = 0; i < parts.length; i++) {
      acc = acc ? `${acc}/${parts[i]}` : parts[i]
      const isLast = i === parts.length - 1
      let child = node.children.find((c) => c.name === parts[i] && c.isDir === !isLast)
      if (!child) {
        child = { name: parts[i], path: acc, children: [], isDir: !isLast }
        node.children.push(child)
      }
      node = child
    }
  }
  const sortNodes = (nodes: WorldTreeNode[]) => {
    nodes.sort((a, b) => (a.isDir === b.isDir ? a.name.localeCompare(b.name) : a.isDir ? -1 : 1))
    nodes.forEach((n) => sortNodes(n.children))
  }
  sortNodes(root.children)
  return root
}

interface WorldFileTreeProps {
  files: WorldFile[]
  currentFile: string
  collapsedDirs: Set<string>
  onToggleDir: (path: string) => void
  onSelect: (path: string) => void
  onDelete: (path: string) => void
}

export default function WorldFileTree({ files, currentFile, collapsedDirs, onToggleDir, onSelect, onDelete }: WorldFileTreeProps) {
  const tree = buildWorldTree(files)

  const renderTree = (nodes: WorldTreeNode[], depth: number): React.ReactElement[] =>
    nodes.map((n) => (
      <div key={n.path}>
        {n.isDir ? (
          <>
            <button
              onClick={() => onToggleDir(n.path)}
              style={{ paddingLeft: 6 + depth * 14 }}
              className="flex items-center gap-1 w-full text-left text-xs py-1 pr-2 rounded transition-colors hover:bg-elevated text-textSecondary"
              title={n.path}
            >
              <ChevronRight size={12} className={`shrink-0 transition-transform ${collapsedDirs.has(n.path) ? '' : 'rotate-90'}`} />
              {collapsedDirs.has(n.path) ? <Folder size={13} className="text-textMuted shrink-0" /> : <FolderOpen size={13} className="text-primary-400 shrink-0" />}
              <span className="truncate">{n.name}</span>
            </button>
            {!collapsedDirs.has(n.path) && renderTree(n.children, depth + 1)}
          </>
        ) : (
          <div key={n.path} className="group flex items-center">
            <button
              onClick={() => onSelect(n.path)}
              style={{ paddingLeft: 24 + depth * 14 }}
              className={`flex items-center gap-1 flex-1 min-w-0 text-left text-xs py-1 pr-1 rounded truncate transition-colors ${currentFile === n.path ? 'bg-primary-500/20 text-primary-300' : 'hover:bg-elevated text-textSecondary'}`}
              title={n.path}
            >
              <span className="shrink-0">{fileTypeIcon(n.name)}</span>
              <span className="truncate">{n.name}</span>
            </button>
            <button
              onClick={(ev) => { ev.stopPropagation(); onDelete(n.path) }}
              className="hidden group-hover:flex shrink-0 items-center justify-center w-6 h-6 text-textMuted hover:text-rose-400 transition-colors"
              title="删除此文件"
            >
              <Trash2 size={13} />
            </button>
          </div>
        )}
      </div>
    ))

  return <>{renderTree(tree.children, 0)}</>
}
