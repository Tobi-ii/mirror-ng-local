/**
 * AgentChat — Financial intelligence chat interface ("Mirror").
 *
 * Users ask plain-English questions about balances, transactions,
 * trends, and anomalies.  Responses stream back as Markdown rendered
 * by react-markdown.  API fallback chain: chat v1 → chat v2 → error.
 *
 * Key responsibilities:
 *   - Maintain chat history in localStorage under `mirror_chat_history`
 *   - Confirm bulk-edits via a preview card before execution
 *   - Show suggestion buttons on first load
 *   - Scroll to latest message on each update
 */
import { useState, useRef, useEffect } from 'react'
import { api } from '../services/api'
import { Send, Bot, User, RotateCcw } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import rehypeSanitize from 'rehype-sanitize'

// ─── Bulk Edit Preview Card ────────────────────────────────────────────────

/**
 * BulkEditCard — confirmation widget shown when the LLM requests a bulk
 * rename/categorisation.  Displays query, new values, affected count.
 *
 * Props:
 *   data       – { query, new_narration, new_category, count, preview_id }
 *   onConfirm  – fires with data when user clicks Apply
 *   onCancel   – fires when user clicks Cancel
 */
function BulkEditCard({ data, onConfirm, onCancel }) {
  const [executing, setExecuting] = useState(false);
  return (
    <div className="my-2 p-3 bg-white/5 border border-purple-500/30 rounded-xl">
      <div className="flex items-center gap-2 mb-2">
        <span className="text-lg">✏️</span>
        <h4 className="font-bold text-white text-sm">Bulk Update Preview</h4>
      </div>
      <div className="text-xs text-slate-300 space-y-1 mb-3">
        <p>Match: <span className="text-white font-mono">"{data.query}"</span></p>
        <p>Rename to: <span className="text-yellow-400">{data.new_narration}</span></p>
        <p>Category: <span className="text-green-400">{data.new_category}</span></p>
        <p className="text-slate-400">{data.count} transaction{data.count !== 1 ? 's' : ''} found</p>
      </div>
      {data.matches && data.matches.length > 0 && (
        <div className="mb-3 max-h-[150px] overflow-y-auto bg-black/40 rounded-lg p-2 space-y-1">
          {data.matches.slice(0, 5).map((tx, i) => (
            <div key={i} className="text-[10px] flex justify-between border-b border-white/5 pb-1 last:border-0">
              <span className="text-slate-300 truncate max-w-[70%]">{(tx.narration || '').substring(0, 35)}</span>
              <span className={tx.amount > 0 ? 'text-emerald-400' : 'text-red-400'}>
                ₦{Math.abs(tx.amount).toLocaleString()}
              </span>
            </div>
          ))}
          {data.matches.length > 5 && (
            <div className="text-[10px] text-slate-500 text-center pt-1">...and {data.matches.length - 5} more</div>
          )}
        </div>
      )}
      <div className="flex gap-2">
        <button onClick={onCancel} disabled={executing}
          className="flex-1 px-3 py-1.5 bg-white/10 hover:bg-white/20 text-white rounded-lg text-xs transition disabled:opacity-50">
          Cancel
        </button>
        <button onClick={() => { setExecuting(true); onConfirm(data); }} disabled={executing}
          className="flex-1 px-3 py-1.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg text-xs font-semibold transition disabled:opacity-50">
          {executing ? 'Applying...' : '✅ Apply'}
        </button>
      </div>
    </div>
  );
}

// ─── Quick-Action Suggestions ──────────────────────────────────────────────

/** Pre-written prompts shown on initial load so users can one-click query. */
const SUGGESTIONS = [
  "What's my current balance?",
  "How much did I spend this week?",
  "Forecast my spend for next week",
  "What number did I buy airtime for most?",
  "Who sent my highest credit alert?",
  "How much did I spend on transfers?",
  "Any unusual transactions?",
  "What was my biggest single debit?",
]

// ─── Main Component ────────────────────────────────────────────────────────

/**
 * AgentChat — root chat component.
 *
 * Props:
 *   userId    – current user ID sent with every API request
 *   sinceDate – earliest transaction date for queries
 *   untilDate – latest transaction date for queries
 *
 * State machine: idle (greeting + suggestions) → user sends →
 * loading (spinner) → response appended → idle (repeat).
 */
const stripToolResults = (text) => {
  if (!text) return '';

  // 1. Remove the literal "Tool result:" text
  let cleaned = text.replace(/Tool result:\s*/gi, '');

  // 2. Robustly remove nested JSON blocks
  let result = '';
  let i = 0;

  while (i < cleaned.length) {
    if (cleaned[i] === '{') {
      // Look ahead 300 characters to see if this is a tool response
      const snippet = cleaned.substring(i, i + 300);
      const toolKeys = ['"transactions"', '"phone_number_breakdown"', '"success"', '"preview_id"', '"matched_count"'];

      if (toolKeys.some(key => snippet.includes(key))) {
        // Count braces to find the EXACT end of this JSON block
        let braceCount = 0;
        let j = i;

        while (j < cleaned.length) {
          if (cleaned[j] === '{') braceCount++;
          if (cleaned[j] === '}') {
            braceCount--;
            if (braceCount === 0) {
              i = j + 1; // Skip past the final closing brace
              break;
            }
          }
          j++;
        }
        continue; // Skip adding this entire JSON block to the result
      }
    }

    result += cleaned[i];
    i++;
  }

  // 3. Clean up leftover whitespace/newlines
  return result.replace(/\n{3,}/g, '\n\n').trim();
};

export default function AgentChat({ userId, sinceDate, untilDate }) {
  // Start fresh — no localStorage persistence to avoid token waste on refresh
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content: "I'm Mirror — your financial intelligence layer. Ask me anything about your money.",
      tool_calls: []
    }
  ])
  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [modelUsed, setModelUsed] = useState(null)
  const [showHelper, setShowHelper] = useState(false)

  /** pendingBulkEdit holds a preview_bulk_update tool call args until
   *  the user confirms or cancels the card. */
  const [pendingBulkEdit, setPendingBulkEdit] = useState(null)
  const bottomRef = useRef(null)

  // Scroll smoothly to bottom on message updates or loading state changes
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages, loading])

  // Show confirmation card when backend returns preview_metadata
  useEffect(() => {
    const lastMsg = messages[messages.length - 1]
    if (lastMsg?.role === 'assistant' && lastMsg.preview_metadata) {
      setPendingBulkEdit(lastMsg.preview_metadata)
    } else {
      setPendingBulkEdit(null)
    }
  }, [messages])


  /**
   * Build history payload for the API, excluding the greeting (index 0).
   * Includes tool_calls when present so the LLM can see its own prior actions.
   */
  const buildHistory = () =>
    messages
      .filter((_, idx) => idx !== 0)
      .map(m => {
        const entry = { role: m.role, content: m.content }
        if (m.tool_calls?.length) entry.tool_calls = m.tool_calls
        return entry
      })

  /** Core send — dispatches user text through the API fallback chain. */
  const send = async (text) => {
    // Deduplicate fast entries early
    if (loading) return;

    const userMsg = (text || input).trim()
    if (!userMsg) return

    // Clear input instantly before processing the async payload execution chain
    setInput('')
    setLoading(true)
    setMessages(prev => [...prev, { role: 'user', content: userMsg }])

    try {
      const historyPayload = buildHistory()
      const res = await api.chat(userId, userMsg, historyPayload, sinceDate, untilDate)

      if (res.success) {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: res.response,
          tool_calls: res.tool_calls_made || [],
          preview_metadata: res.preview_metadata || null
        }])
        setModelUsed(res.model_used)
        setLoading(false)
        return
      }
    } catch (err) {
      // v1 failed — fall through to v2
    }

    // Fall back to v2 (intent-based, no LLM needed)
    try {
      const res = await api.chatV2(userId, userMsg, historyPayload, sinceDate, untilDate)
      if (res.success) {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: res.response,
          tool_calls: []
        }])
        setModelUsed(res.model_used || 'intent-agent')
      } else {
        setMessages(prev => [...prev, {
          role: 'assistant',
          content: 'Something went wrong. Please try again.',
          tool_calls: []
        }])
      }
    } catch (err) {
      setMessages(prev => [...prev, {
        role: 'assistant',
        content: 'Could not reach the agent. Please check if the financial service backend is active.',
        tool_calls: []
      }])
    } finally {
      setLoading(false)
    }
  }

  /** Clear history from state and localStorage and restore greeting. */
  const reset = () => {
    if (loading) return
    localStorage.removeItem('mirror_chat_history')
    setMessages([
      {
        role: 'assistant',
        content: "Fresh start. What do you want to know?",
        tool_calls: []
      }
    ])
    setModelUsed(null)
    setPendingBulkEdit(null)
  }

  /**
   * POST the confirmed bulk-edit to the backend, then send a clear status
   * message to the assistant so it can report the result to the user.
   */
  const handleConfirmBulkEdit = async (data) => {
    if (!data || !data.preview_id) {
      console.error('Bulk update failed: Missing preview_id', data)
      setPendingBulkEdit(null)
      return
    }

    try {
      const res = await fetch('/api/transactions/bulk-execute/' + data.preview_id, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': getCsrfToken() },
        credentials: 'include',
      })

      if (!res.ok) {
        const errorData = await res.json().catch(() => ({}))
        throw new Error(errorData.detail || `HTTP ${res.status}`)
      }

      const result = await res.json()
      setPendingBulkEdit(null)

      if (result.success && result.updated_count > 0) {
        window.dispatchEvent(new Event('mirror-data-updated'))
        send(`Done! ${result.updated_count} transactions updated to "${data.new_narration}". I also saved this as a rule so future transactions will be renamed automatically.`)
      } else {
        send(`Bulk update completed but no transactions were modified. The preview may have expired.`)
      }
    } catch (err) {
      console.error('Bulk update error:', err)
      setPendingBulkEdit(null)
      send(`Bulk update failed: ${err.message}. Let the user know.`)
    }
  }

  /** Read CSRF token from cookie (set by backend middleware). */
  const getCsrfToken = () => {
    const match = document.cookie.match(/csrf_token=([^;]+)/)
    return match ? match[1] : null
  }

  const handleCancelBulkEdit = () => {
    setPendingBulkEdit(null)
    send('Cancel the bulk update.')
  }

  // Preserve suggestions on screen while the initial user request is pending
  const showSuggestions = messages.length === 1 && !loading

  return (
    <div className="flex flex-col h-[calc(100vh-100px)] sm:h-[calc(100vh-120px)] max-w-3xl mx-auto px-4 sm:px-0">

      {/* ─── Header ─────────────────────────────────────────────────── */}
      <div className="flex items-center justify-between mb-4 sm:mb-6 border-b border-white/5 pb-4 shrink-0">
        <div className="min-w-0">
          <h1 className="text-2xl sm:text-3xl font-black text-white tracking-tighter uppercase italic">Ask Mirror</h1>
          <p className="text-[10px] sm:text-xs text-slate-500 mt-0.5">
            {/* Show model name when available, otherwise "Ready" */}
            Ask anything in plain English · {modelUsed ? <span className="text-indigo-400 font-mono">{modelUsed}</span> : 'Ready'}
          </p>
        </div>
        {/* Reset button — disabled while a request is in flight */}
        <button
          onClick={reset}
          disabled={loading}
          className="p-2 rounded-xl hover:bg-white/5 transition-colors shrink-0 disabled:opacity-20 disabled:hover:bg-transparent"
          title="Reset Conversation"
        >
          <RotateCcw size={16} className="text-slate-400" />
        </button>
      </div>

      {/* ─── Messages Window ────────────────────────────────────────── */}
      <div className="flex-1 overflow-y-auto space-y-4 pr-1 scrollbar-thin scrollbar-thumb-white/10">

        {/* Render each chat message as a bubble with avatar.
         *  User bubbles flush-right (reverse flex), assistant left. */}
        {messages.map((msg, i) => (
          <div key={i} className={`flex gap-2 sm:gap-3 ${msg.role === 'user' ? 'flex-row-reverse' : ''}`}>

            {/* Avatar icon — Bot for assistant, User for user */}
            <div className={`w-7 h-7 sm:w-8 sm:h-8 rounded-xl flex-shrink-0 flex items-center justify-center border ${
              msg.role === 'assistant'
                ? 'bg-indigo-600 border-indigo-500 shadow-lg shadow-indigo-600/10'
                : 'bg-white/5 border-white/10'
            }`}>
              {msg.role === 'assistant'
                ? <Bot size={12} className="text-white" />
                : <User size={12} className="text-slate-300" />
              }
            </div>

            <div className={`max-w-[85%] sm:max-w-[75%] space-y-1.5 flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>

              {/* Message bubble — assistant content rendered via Markdown,
               *  user content shown as plain pre-wrapped text. */}
              <div className={`px-4 py-2.5 rounded-2xl text-xs sm:text-sm leading-relaxed break-words ${
                msg.role === 'assistant'
                  ? 'bg-[#0a0c10] border border-white/5 text-slate-200'
                  : 'bg-indigo-600 text-white rounded-tr-none'
              }`}>
                {msg.role === 'assistant' ? (
                      <ReactMarkdown
                    remarkPlugins={[remarkGfm]}
                    rehypePlugins={[rehypeSanitize]}
                    components={{
                      table: ({ children }) => (
                        <div className="overflow-x-auto my-3">
                          <table className="min-w-full text-sm border-collapse">{children}</table>
                        </div>
                      ),
                      thead: ({ children }) => (
                        <thead className="bg-white/10 border-b border-white/20">{children}</thead>
                      ),
                      tbody: ({ children }) => (
                        <tbody className="divide-y divide-white/10">{children}</tbody>
                      ),
                      tr: ({ children }) => <tr className="hover:bg-white/5">{children}</tr>,
                      th: ({ children }) => (
                        <th className="px-3 py-2 text-left font-semibold text-white">{children}</th>
                      ),
                      td: ({ children }) => (
                        <td className="px-3 py-2 text-slate-200">{children}</td>
                      ),
                      strong: ({ children }) => <strong className="font-bold text-white">{children}</strong>,
                      p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
                      ul: ({ children }) => <ul className="list-disc list-inside mb-2 space-y-1">{children}</ul>,
                      li: ({ children }) => <li className="ml-2">{children}</li>,
                    }}
                  >
                    {stripToolResults(msg.content)}
                  </ReactMarkdown>
                ) : (
                  <span className="whitespace-pre-wrap">{msg.content}</span>
                )}
              </div>
            </div>
          </div>
        ))}

        {/* Bulk Update Confirmation Card — sits below the last assistant message */}
        {pendingBulkEdit && (
          <BulkEditCard
            data={pendingBulkEdit}
            onConfirm={handleConfirmBulkEdit}
            onCancel={handleCancelBulkEdit}
          />
        )}

        {/* Loading indicator — three bouncing dots, only after a user message */}
        {loading && messages[messages.length - 1]?.role === 'user' && (
          <div className="flex gap-2 sm:gap-3">
            <div className="w-7 h-7 sm:w-8 sm:h-8 rounded-xl bg-indigo-600 border border-indigo-500 flex items-center justify-center flex-shrink-0">
              <Bot size={12} className="text-white" />
            </div>
            <div className="px-4 py-3 bg-[#0a0c10] border border-white/5 rounded-2xl flex items-center">
              <div className="flex gap-1">
                {[0, 1, 2].map(i => (
                  <div
                    key={i}
                    className="w-1.5 h-1.5 bg-indigo-400 rounded-full animate-bounce"
                    style={{ animationDelay: `${i * 150}ms`, animationDuration: '0.6s' }}
                  />
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Suggestion buttons grid — visible only on initial greeting */}
        {showSuggestions && (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 pt-2 animate-fadeIn">
            {SUGGESTIONS.map((s, i) => (
              <button
                key={i}
                onClick={() => send(s)}
                disabled={loading}
                className="text-left px-4 py-3 bg-white/[0.02] border border-white/5 rounded-xl text-xs text-slate-400 hover:bg-white/5 hover:border-white/10 hover:text-slate-200 transition-all disabled:opacity-50 disabled:pointer-events-none"
              >
                {s}
              </button>
            ))}
          </div>
        )}

        {/* Invisible anchor — scrollIntoView target */}
        <div ref={bottomRef} />
      </div>

      {/* ─── Helper Card ──────────────────────────────────────────────── */}
      {showHelper && (
        <div className="shrink-0 bg-[#1a1a1a] border border-white/10 rounded-xl p-4 mb-2">
          <div className="flex justify-between items-center mb-3">
            <span className="text-sm font-bold text-white">💡 Batch Aliasing Guide</span>
            <button onClick={() => setShowHelper(false)} className="text-slate-500 hover:text-white text-lg leading-none">&times;</button>
          </div>
          <p className="text-xs text-slate-500 mb-3">Click an example to try it, or type your own command:</p>
          {[
            { cmd: 'Group all Ebill transactions as "E-Bill Third Party" in Data & Airtime', desc: 'Create a custom alias for a specific pattern' },
            { cmd: 'Put all POS purchases in Shopping category', desc: 'Categorize multiple transactions at once' },
            { cmd: 'Rename transfers to John as "Personal Loans"', desc: 'Alias specific people or merchants' },
          ].map((ex, i) => (
            <div
              key={i}
              onClick={() => { send(ex.cmd); setShowHelper(false); }}
              className="bg-black/40 border border-white/5 rounded-lg p-2.5 mb-2 cursor-pointer hover:bg-black/60 transition-colors"
            >
              <div className="text-xs text-emerald-400 font-mono mb-1">"{ex.cmd}"</div>
              <div className="text-[10px] text-slate-500">{ex.desc}</div>
            </div>
          ))}
          <div className="text-[9px] text-slate-600 mt-2">
            Categories: Transfer, Utilities, Food, Transport, Shopping, Entertainment, Health, Education, Fuel, Data & Airtime, Family, Business, General, Salary
          </div>
        </div>
      )}

      {/* ─── Input Dock ─────────────────────────────────────────────── */}
      <div className="mt-4 flex gap-2 sm:gap-3 bg-[#05070a] pt-2 pb-4 shrink-0">
        <button
          onClick={() => setShowHelper(!showHelper)}
          className={`w-9 h-9 rounded-lg flex items-center justify-center shrink-0 transition-all ${
            showHelper ? 'bg-emerald-500 text-black font-bold' : 'bg-white/10 text-white hover:bg-white/20'
          }`}
          title="Show batch aliasing examples"
        >
          ?
        </button>
        <input
          type="text"
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={e => {
            // Enter sends; Shift+Enter would be for newlines, but we suppress it
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault()
              send()
            }
          }}
          placeholder="Ask Mirror about balances, trends, or unusual spikes..."
          className="flex-1 bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-white text-xs sm:text-sm placeholder-slate-600 focus:outline-none focus:border-indigo-500 transition-colors disabled:opacity-50"
          disabled={loading}
        />
        <button
          onClick={() => send()}
          disabled={loading || !input.trim()}
          className="w-10 h-10 sm:w-11 sm:h-11 bg-indigo-600 rounded-xl flex items-center justify-center hover:bg-indigo-700 disabled:opacity-20 transition-all active:scale-95 shrink-0"
        >
          <Send size={14} className="text-white" />
        </button>
      </div>
    </div>
  )
}
