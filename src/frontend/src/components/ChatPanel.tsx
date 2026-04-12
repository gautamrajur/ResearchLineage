import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import Markdown from 'react-markdown';
import type { Theme } from '../lib/theme';

interface Message {
  role: 'user' | 'model';
  content: string;
  streaming?: boolean;
}

interface ChatPanelProps {
  paperId: string;
  seedTitle: string;
  theme: Theme;
  open: boolean;
  onOpenChange: (v: boolean) => void;
}

const SUGGESTED = [
  'Which paper had the biggest breakthrough?',
  'Summarize this lineage in 3 sentences',
  'What problem does the seed paper ultimately solve?',
  'What limitations were never fully resolved?',
];

export function ChatPanel({ paperId, seedTitle, theme, open, onOpenChange }: ChatPanelProps) {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const messagesRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const isDark = theme.id === 'dark';

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 150);
  }, [open]);

  useEffect(() => {
    const el = messagesRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || streaming) return;
    setInput('');

    const next: Message[] = [...messages, { role: 'user', content: q }];
    setMessages(next);
    setStreaming(true);
    setMessages((m) => [...m, { role: 'model', content: '', streaming: true }]);

    abortRef.current?.abort();
    abortRef.current = new AbortController();

    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        signal: abortRef.current.signal,
        body: JSON.stringify({
          paper_id: paperId,
          messages: next.map((m) => ({ role: m.role, content: m.content })),
        }),
      });

      if (!res.ok || !res.body) {
        let detail = `HTTP ${res.status}`;
        try {
          const body = await res.json();
          detail = body?.detail ?? detail;
        } catch { /* ignore */ }
        throw new Error(detail);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buf = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });

        const lines = buf.split('\n');
        buf = lines.pop() ?? '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;
          const payload = line.slice(6).trim();
          if (payload === '[DONE]') break;
          try {
            const parsed = JSON.parse(payload);
            if (parsed.error) throw new Error(parsed.error);
            if (parsed.text) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last?.role === 'model') {
                  updated[updated.length - 1] = { ...last, content: last.content + parsed.text };
                }
                return updated;
              });
            }
          } catch (parseErr) {
            if ((parseErr as Error).message !== 'Unexpected token') throw parseErr;
          }
        }
      }
    } catch (e) {
      if ((e as Error).name === 'AbortError') return;
      const raw = (e as Error).message ?? 'Unknown error';
      // Only treat as cache-miss if our endpoint said so — Gemini errors also contain "404"
      const errMsg = raw.includes('No timeline') || raw.includes('Run /analyze')
        ? 'No cached timeline for this paper. Run /analyze first.'
        : `Error: ${raw.slice(0, 200)}`;
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last?.role === 'model') {
          updated[updated.length - 1] = {
            ...last,
            content: last.content || errMsg,
            streaming: false,
          };
        }
        return updated;
      });
    } finally {
      setStreaming(false);
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last?.role === 'model') {
          updated[updated.length - 1] = { ...last, streaming: false };
        }
        return updated;
      });
    }
  }

  const panelBg = isDark ? '#0E1018' : '#FFFFFF';
  const headerBg = isDark ? 'rgba(18,20,26,0.98)' : 'rgba(255,255,255,0.98)';
  const userBubbleBg = `linear-gradient(135deg, ${theme.seed}, ${theme.accent})`;
  const aiBubbleBg = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)';
  const inputBg = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)';
  const borderColor = isDark ? 'rgba(255,255,255,0.08)' : theme.border;
  const chipBg = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)';

  return (
    <>
      {/* Toggle button — fixed bottom-right, above ThemePicker */}
      <motion.button
        onClick={() => onOpenChange(!open)}
        whileHover={{ scale: 1.05, y: -2 }}
        whileTap={{ scale: 0.97 }}
        className="fixed bottom-[72px] right-6 z-50 flex items-center gap-2 px-4 py-2.5 rounded-2xl text-[13px] font-semibold shadow-xl"
        style={{
          background: `linear-gradient(135deg, ${theme.seed}, ${theme.accent})`,
          color: '#fff',
          boxShadow: `0 8px 32px ${theme.accent}55`,
        }}
      >
        <span>{open ? '✕' : '◎'}</span>
        {open ? 'Close chat' : 'Ask about this lineage'}
      </motion.button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, width: 0, x: 20 }}
            animate={{ opacity: 1, width: 380, x: 0 }}
            exit={{ opacity: 0, width: 0, x: 20 }}
            transition={{ type: 'spring', stiffness: 340, damping: 32 }}
            className="shrink-0 flex flex-col rounded-2xl overflow-hidden"
            style={{
              width: 380,
              background: panelBg,
              border: `1px solid ${borderColor}`,
              boxShadow: isDark
                ? '0 16px 48px rgba(0,0,0,0.5)'
                : '0 8px 32px rgba(0,0,0,0.10)',
            }}
          >
            {/* Header */}
            <div className="flex items-center gap-3 px-4 py-3 shrink-0"
              style={{ background: headerBg, borderBottom: `1px solid ${borderColor}` }}>
              <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0"
                style={{ background: `linear-gradient(135deg, ${theme.seed}, ${theme.accent})` }}>
                <span className="text-[11px] text-white font-bold">◎</span>
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-[12px] font-semibold truncate" style={{ color: theme.textPrimary }}>
                  Lineage Assistant
                </div>
                <div className="text-[10px] truncate" style={{ color: theme.textMuted }}>
                  {seedTitle}
                </div>
              </div>
              <div className="flex items-center gap-1.5 shrink-0">
                <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: '#4ADE80' }} />
                <span className="text-[10px]" style={{ color: theme.textMuted }}>Gemini</span>
              </div>
            </div>

            {/* Messages — scrollable, capped height */}
            <div ref={messagesRef} className="px-4 py-4 space-y-3 overflow-y-auto max-h-[60vh]">
              {messages.length === 0 && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}
                  className="space-y-3">
                  <p className="text-[11.5px] text-center pb-1" style={{ color: theme.textMuted }}>
                    Ask anything about this paper lineage
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {SUGGESTED.map((s) => (
                      <button key={s} onClick={() => send(s)}
                        className="px-3 py-1.5 rounded-xl text-[11px] text-left transition-all hover:scale-[1.02] active:scale-[0.98]"
                        style={{ background: chipBg, border: `1px solid ${borderColor}`, color: theme.textSecondary }}>
                        {s}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}

              {messages.map((msg, i) => (
                <motion.div key={i}
                  initial={{ opacity: 0, y: 8 }} animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.22 }}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {msg.role === 'user' ? (
                    <div className="max-w-[82%] px-3.5 py-2.5 rounded-2xl rounded-br-md text-[12.5px] leading-relaxed text-white"
                      style={{ background: userBubbleBg }}>
                      {msg.content}
                    </div>
                  ) : (
                    <div className="max-w-[90%] px-3.5 py-2.5 rounded-2xl rounded-bl-md text-[12.5px] leading-relaxed prose prose-sm max-w-none"
                      style={{ background: aiBubbleBg, color: theme.textPrimary }}>
                      {msg.content ? (
                        <Markdown
                          components={{
                            p: ({ children }) => <p className="mb-1.5 last:mb-0">{children}</p>,
                            h3: ({ children }) => <p className="font-semibold mt-2 mb-1">{children}</p>,
                            h2: ({ children }) => <p className="font-bold mt-2.5 mb-1">{children}</p>,
                            strong: ({ children }) => <strong className="font-semibold">{children}</strong>,
                            li: ({ children }) => <li className="ml-3 list-disc">{children}</li>,
                            ul: ({ children }) => <ul className="mb-1.5 space-y-0.5">{children}</ul>,
                            ol: ({ children }) => <ol className="mb-1.5 space-y-0.5 list-decimal ml-3">{children}</ol>,
                          }}
                        >{msg.content}</Markdown>
                      ) : (msg.streaming && (
                        <span className="flex gap-1 items-center py-0.5">
                          {[0, 1, 2].map((d) => (
                            <motion.span key={d} className="w-1.5 h-1.5 rounded-full"
                              style={{ background: theme.accent }}
                              animate={{ opacity: [0.3, 1, 0.3] }}
                              transition={{ duration: 1.2, delay: d * 0.2, repeat: Infinity }} />
                          ))}
                        </span>
                      ))}
                      {msg.streaming && msg.content && (
                        <span className="inline-block w-1.5 h-3 ml-0.5 rounded-sm animate-pulse align-middle"
                          style={{ background: theme.accent }} />
                      )}
                    </div>
                  )}
                </motion.div>
              ))}
            </div>

            {/* Input */}
            <div className="shrink-0 px-3 py-3"
              style={{ borderTop: `1px solid ${borderColor}`, background: headerBg }}>
              <div className="flex items-center gap-2 px-3 py-2 rounded-xl"
                style={{ background: inputBg, border: `1px solid ${borderColor}` }}>
                <input
                  ref={inputRef}
                  value={input}
                  onChange={(e) => setInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(input); } }}
                  placeholder="Ask about the lineage..."
                  className="flex-1 bg-transparent outline-none text-[13px]"
                  style={{ color: theme.textPrimary }}
                  disabled={streaming}
                />
                <button onClick={() => send(input)} disabled={!input.trim() || streaming}
                  className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 transition-all"
                  style={input.trim() && !streaming
                    ? { background: `linear-gradient(135deg, ${theme.seed}, ${theme.accent})`, color: '#fff' }
                    : { background: isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.06)', color: theme.textMuted }}>
                  {streaming
                    ? <span className="w-2 h-2 rounded-full animate-pulse" style={{ background: theme.accent }} />
                    : <span className="text-[13px]">↑</span>}
                </button>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}
