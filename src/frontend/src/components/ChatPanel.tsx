import { useEffect, useRef, useState } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
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
}

const SUGGESTED = [
  'Which paper had the biggest breakthrough?',
  'Summarize this lineage in 3 sentences',
  'What problem does the seed paper ultimately solve?',
  'What limitations were never fully resolved?',
];

export function ChatPanel({ paperId, seedTitle, theme }: ChatPanelProps) {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const abortRef = useRef<AbortController | null>(null);
  const isDark = theme.id === 'dark';

  useEffect(() => {
    if (open) setTimeout(() => inputRef.current?.focus(), 150);
  }, [open]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function send(text: string) {
    const q = text.trim();
    if (!q || streaming) return;
    setInput('');

    const next: Message[] = [...messages, { role: 'user', content: q }];
    setMessages(next);
    setStreaming(true);

    // Append empty assistant bubble immediately
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

      if (!res.ok || !res.body) throw new Error(`HTTP ${res.status}`);

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
            if (parsed.text) {
              setMessages((prev) => {
                const updated = [...prev];
                const last = updated[updated.length - 1];
                if (last.role === 'model') {
                  updated[updated.length - 1] = { ...last, content: last.content + parsed.text };
                }
                return updated;
              });
            }
            if (parsed.error) throw new Error(parsed.error);
          } catch {
            // ignore parse errors on partial chunks
          }
        }
      }
    } catch (e) {
      if ((e as Error).name === 'AbortError') return;
      const msg = (e as Error).message ?? 'Unknown error';
      setMessages((prev) => {
        const updated = [...prev];
        const last = updated[updated.length - 1];
        if (last.role === 'model') {
          updated[updated.length - 1] = {
            ...last,
            content: last.content || `Error: ${msg}. Make sure the backend is running and the timeline is cached.`,
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
        if (last.role === 'model') {
          updated[updated.length - 1] = { ...last, streaming: false };
        }
        return updated;
      });
    }
  }

  // ── Colours that work on both dark and light themes ──────────────────────
  const panelBg = isDark ? '#0E1018' : '#FFFFFF';
  const headerBg = isDark ? 'rgba(18,20,26,0.95)' : 'rgba(255,255,255,0.95)';
  const userBubbleBg = `linear-gradient(135deg, ${theme.seed}, ${theme.accent})`;
  const aiBubbleBg = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)';
  const aiBubbleColor = theme.textPrimary;
  const inputBg = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)';
  const borderColor = isDark ? 'rgba(255,255,255,0.08)' : theme.border;
  const chipBg = isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)';

  return (
    <>
      {/* Floating trigger button — sits above the ThemePicker (bottom-6 right-6) */}
      <motion.button
        onClick={() => setOpen((v) => !v)}
        whileHover={{ scale: 1.05, y: -2 }}
        whileTap={{ scale: 0.97 }}
        className="fixed bottom-[72px] right-6 z-50 flex items-center gap-2.5 px-4 py-2.5 rounded-2xl text-[13px] font-semibold shadow-xl"
        style={{
          background: `linear-gradient(135deg, ${theme.seed}, ${theme.accent})`,
          color: '#fff',
          boxShadow: `0 8px 32px ${theme.accent}55`,
        }}
      >
        <span className="text-[15px]">{open ? '✕' : '◎'}</span>
        {open ? 'Close chat' : 'Ask about this lineage'}
      </motion.button>

      {/* Panel */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: 32, scale: 0.97 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: 24, scale: 0.97 }}
            transition={{ type: 'spring', stiffness: 340, damping: 30 }}
            className="fixed bottom-[136px] right-6 z-50 flex flex-col rounded-2xl overflow-hidden"
            style={{
              width: 'min(420px, calc(100vw - 32px))',
              height: 'min(560px, calc(100vh - 160px))',
              background: panelBg,
              border: `1px solid ${borderColor}`,
              boxShadow: isDark
                ? '0 32px 80px rgba(0,0,0,0.7)'
                : '0 24px 64px rgba(0,0,0,0.15)',
            }}
          >
            {/* Header */}
            <div className="flex items-center gap-3 px-4 py-3 shrink-0"
              style={{ background: headerBg, borderBottom: `1px solid ${borderColor}`, backdropFilter: 'blur(12px)' }}>
              <div className="w-7 h-7 rounded-full flex items-center justify-center shrink-0"
                style={{ background: `linear-gradient(135deg, ${theme.seed}, ${theme.accent})` }}>
                <span className="text-[11px] text-white font-bold">◎</span>
              </div>
              <div className="min-w-0">
                <div className="text-[12px] font-semibold truncate" style={{ color: theme.textPrimary }}>
                  Lineage Assistant
                </div>
                <div className="text-[10px] truncate" style={{ color: theme.textMuted }}>
                  {seedTitle}
                </div>
              </div>
              <div className="ml-auto flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full animate-pulse" style={{ background: '#4ADE80' }} />
                <span className="text-[10px]" style={{ color: theme.textMuted }}>Gemini</span>
              </div>
            </div>

            {/* Messages */}
            <div className="flex-1 overflow-y-auto px-4 py-4 space-y-3">
              {messages.length === 0 && (
                <motion.div initial={{ opacity: 0 }} animate={{ opacity: 1 }} transition={{ delay: 0.1 }}
                  className="space-y-3">
                  <p className="text-[12px] text-center pb-1" style={{ color: theme.textMuted }}>
                    Ask anything about this paper lineage
                  </p>
                  <div className="flex flex-wrap gap-2">
                    {SUGGESTED.map((s) => (
                      <button key={s}
                        onClick={() => send(s)}
                        className="px-3 py-1.5 rounded-xl text-[11px] text-left transition-all hover:scale-[1.02]"
                        style={{ background: chipBg, border: `1px solid ${borderColor}`, color: theme.textSecondary }}>
                        {s}
                      </button>
                    ))}
                  </div>
                </motion.div>
              )}

              {messages.map((msg, i) => (
                <motion.div
                  key={i}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.25 }}
                  className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
                >
                  {msg.role === 'user' ? (
                    <div className="max-w-[82%] px-3.5 py-2.5 rounded-2xl rounded-br-md text-[12.5px] leading-relaxed text-white"
                      style={{ background: userBubbleBg }}>
                      {msg.content}
                    </div>
                  ) : (
                    <div className="max-w-[88%] px-3.5 py-2.5 rounded-2xl rounded-bl-md text-[12.5px] leading-relaxed"
                      style={{ background: aiBubbleBg, color: aiBubbleColor }}>
                      {msg.content}
                      {msg.streaming && (
                        <span className="inline-block w-1.5 h-3.5 ml-0.5 rounded-sm animate-pulse align-middle"
                          style={{ background: theme.accent }} />
                      )}
                    </div>
                  )}
                </motion.div>
              ))}
              <div ref={bottomRef} />
            </div>

            {/* Input */}
            <div className="shrink-0 px-3 py-3"
              style={{ borderTop: `1px solid ${borderColor}`, background: headerBg, backdropFilter: 'blur(12px)' }}>
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
                <button
                  onClick={() => send(input)}
                  disabled={!input.trim() || streaming}
                  className="w-7 h-7 rounded-lg flex items-center justify-center shrink-0 transition-all"
                  style={input.trim() && !streaming
                    ? { background: `linear-gradient(135deg, ${theme.seed}, ${theme.accent})`, color: '#fff' }
                    : { background: isDark ? 'rgba(255,255,255,0.07)' : 'rgba(0,0,0,0.06)', color: theme.textMuted }}
                >
                  {streaming
                    ? <span className="w-2.5 h-2.5 rounded-full animate-pulse" style={{ background: theme.accent }} />
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
