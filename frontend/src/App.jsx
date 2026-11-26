import { useEffect, useRef, useState } from 'react'
import { AudioLines, Check, ChevronDown, CircleHelp, Clock3, Copy, FileAudio2, Languages, LoaderCircle, Mic, Plus, Search, Settings2, Sparkles, Square, Trash2, WandSparkles, X } from 'lucide-react'

const API = import.meta.env.VITE_API_URL || (import.meta.env.DEV ? '' : 'http://127.0.0.1:8000')

function formatDuration(seconds = 0) {
  const total = Math.round(seconds)
  return `${Math.floor(total / 60)}:${String(total % 60).padStart(2, '0')}`
}

function formatDate(value) {
  return new Date(value).toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function resampleTo16k(input, inputRate) {
  const ratio = inputRate / 16000
  const outputLength = Math.floor(input.length / ratio)
  const output = new Int16Array(outputLength)
  for (let i = 0; i < outputLength; i++) {
    const position = i * ratio
    const left = Math.floor(position)
    const fraction = position - left
    const sample = input[left] * (1 - fraction) + (input[Math.min(left + 1, input.length - 1)] || 0) * fraction
    output[i] = Math.max(-1, Math.min(1, sample)) * 32767
  }
  return output
}

function base64FromInt16(samples) {
  const bytes = new Uint8Array(samples.buffer, samples.byteOffset, samples.byteLength)
  let binary = ''
  const step = 0x8000
  for (let i = 0; i < bytes.length; i += step) binary += String.fromCharCode(...bytes.subarray(i, Math.min(i + step, bytes.length)))
  return btoa(binary)
}

function App() {
  const [items, setItems] = useState([])
  const [active, setActive] = useState(null)
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('idle')
  const [seconds, setSeconds] = useState(0)
  const [liveText, setLiveText] = useState('')
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [copied, setCopied] = useState(false)
  const [showSettings, setShowSettings] = useState(false)
  const [languageMenu, setLanguageMenu] = useState(false)
  const [language, setLanguage] = useState('Auto detect')
  const recorder = useRef(null)

  const loadHistory = async () => {
    try {
      const response = await fetch(`${API}/api/transcriptions`)
      if (!response.ok) throw new Error('Could not load transcription history')
      const rows = await response.json()
      setItems(rows)
      if (!active && rows.length) setActive(rows[0])
    } catch (e) { setError(`API unavailable. Start the FastAPI server, then refresh. ${e.message}`) }
  }

  useEffect(() => { loadHistory() }, [])
  useEffect(() => {
    if (status !== 'recording') return
    const timer = window.setInterval(() => setSeconds((value) => value + 1), 1000)
    return () => window.clearInterval(timer)
  }, [status])
  useEffect(() => {
    if (!notice) return
    const timer = window.setTimeout(() => setNotice(''), 3000)
    return () => window.clearTimeout(timer)
  }, [notice])

  const startRecording = async () => {
    setError(''); setLiveText(''); setSeconds(0); setStatus('recording')
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true } })
      const context = new AudioContext()
      const source = context.createMediaStreamSource(stream)
      const processor = context.createScriptProcessor(4096, 1, 1)
      const muteOutput = context.createGain()
      muteOutput.gain.value = 0
      const socketUrl = API
        ? `${API.replace(/^http/, 'ws')}/api/live`
        : `${window.location.protocol === 'https:' ? 'wss' : 'ws'}://${window.location.host}/api/live`
      const socket = new WebSocket(socketUrl)
      const chunks = []
      socket.onmessage = (event) => {
        const message = JSON.parse(event.data)
        if (message.type === 'preview') setLiveText(message.text)
        if (message.type === 'error') setError(message.message)
      }
      processor.onaudioprocess = (event) => {
        const samples = resampleTo16k(event.inputBuffer.getChannelData(0), context.sampleRate)
        chunks.push(samples)
        if (socket.readyState === WebSocket.OPEN) socket.send(samples.buffer.slice(0))
      }
      source.connect(processor); processor.connect(muteOutput); muteOutput.connect(context.destination)
      recorder.current = { stream, context, source, processor, muteOutput, socket, chunks }
    } catch (e) {
      setStatus('idle'); setError(e.name === 'NotAllowedError' ? 'Allow microphone access in your browser to start recording.' : `Could not start microphone: ${e.message}`)
    }
  }

  const stopRecording = async () => {
    const current = recorder.current
    if (!current) { setStatus('idle'); return }
    setStatus('processing'); setNotice('Transcribing your recording…')
    current.processor.disconnect(); current.muteOutput.disconnect(); current.source.disconnect(); current.stream.getTracks().forEach((track) => track.stop())
    await current.context.close()
    if (current.socket.readyState === WebSocket.OPEN) current.socket.close()
    const joined = new Int16Array(current.chunks.reduce((sum, chunk) => sum + chunk.length, 0))
    let offset = 0
    current.chunks.forEach((chunk) => { joined.set(chunk, offset); offset += chunk.length })
    recorder.current = null
    try {
      const response = await fetch(`${API}/api/transcribe`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ audio_base64: base64FromInt16(joined), sample_rate: 16000 }) })
      const result = await response.json()
      if (!response.ok) throw new Error(result.detail || 'Transcription failed')
      const finalText = result.text || liveText
      if (!finalText.trim()) throw new Error('No speech detected. Try speaking a little closer to the microphone.')
      const saved = await fetch(`${API}/api/transcriptions`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: finalText, language: result.language, duration_seconds: result.duration_seconds }) })
      if (!saved.ok) throw new Error('Transcription succeeded but could not be saved')
      const item = await saved.json()
      setItems((previous) => [item, ...previous]); setActive(item); setNotice('Transcription saved'); setLiveText('')
    } catch (e) { setError(e.message) }
    finally { setStatus('idle') }
  }

  const updateItem = async (id, changes) => {
    try {
      const response = await fetch(`${API}/api/transcriptions/${id}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(changes) })
      if (!response.ok) throw new Error('Could not update transcription')
      const updated = await response.json()
      setItems((previous) => previous.map((item) => item.id === id ? updated : item)); setActive(updated); setNotice('Changes saved')
    } catch (e) { setError(e.message) }
  }

  const deleteItem = async (item) => {
    if (!window.confirm(`Delete “${item.title}”? This cannot be undone.`)) return
    try {
      const response = await fetch(`${API}/api/transcriptions/${item.id}`, { method: 'DELETE' })
      if (!response.ok) throw new Error('Could not delete transcription')
      const remaining = items.filter((entry) => entry.id !== item.id)
      setItems(remaining); setActive(remaining[0] || null); setNotice('Transcription deleted')
    } catch (e) { setError(e.message) }
  }

  const createBlank = () => { setActive(null); setLiveText(''); setNotice('Ready for a new recording') }
  const copyText = async () => { if (active?.text) { await navigator.clipboard.writeText(active.text); setCopied(true); setTimeout(() => setCopied(false), 1600) } }
  const filtered = items.filter((item) => `${item.title} ${item.text}`.toLowerCase().includes(query.toLowerCase()))
  const currentText = status === 'recording' ? liveText : active?.text || ''
  const recording = status === 'recording' || status === 'processing'

  return <div className="app-shell">
    <aside className="sidebar">
      <div className="brand"><div className="brand-icon"><AudioLines size={20} /></div><div><strong>vaani</strong><span>VOICE WORKSPACE</span></div></div>
      <button className="new-button" onClick={createBlank}><Plus size={17} /> New transcription <span>⌘ N</span></button>
      <div className="history-heading"><span>YOUR LIBRARY</span><span className="history-count">{items.length}</span></div>
      <div className="search-box"><Search size={15} /><input placeholder="Search transcripts" value={query} onChange={(e) => setQuery(e.target.value)} /><kbd>⌘ K</kbd></div>
      <div className="history-list">
        {filtered.length ? filtered.map((item) => <button className={`history-item ${active?.id === item.id ? 'selected' : ''}`} key={item.id} onClick={() => { setActive(item); setLiveText('') }}>
          <span className="history-file"><FileAudio2 size={17} /></span><span className="history-copy"><strong>{item.title}</strong><small>{formatDate(item.created_at)}</small></span><span className="history-duration">{formatDuration(item.duration_seconds)}</span>
        </button>) : <div className="empty-history">{query ? 'No matches found' : 'Your saved transcripts will appear here.'}</div>}
      </div>
      <div className="sidebar-bottom"><div className="plan-card"><div className="plan-icon"><Sparkles size={15} /></div><div><strong>All yours, always</strong><p>Audio is processed on your machine.</p></div></div><button className="profile"><div className="avatar">V</div><span><strong>My workspace</strong><small>Local account</small></span><ChevronDown size={16} /></button></div>
    </aside>

    <main className="main-panel">
      <header className="topbar"><div className="breadcrumbs">Workspace <span>/</span> <strong>{active?.title || 'New transcription'}</strong></div><div className="top-actions"><span className="secure"><span className="green-dot" /> Private workspace</span><button className="icon-button" title="Settings" onClick={() => setShowSettings((value) => !value)}><Settings2 size={18} /></button><button className="help-button" title="Help"><CircleHelp size={18} /></button></div></header>
      {showSettings && <div className="settings-popover"><div className="settings-title"><strong>Model settings</strong><button onClick={() => setShowSettings(false)}><X size={15} /></button></div><div className="model-setting"><span>Local Whisper model</span><strong>tiny · fastest</strong></div><p>To change it, set <code>WHISPER_MODEL</code> to <code>base</code> or <code>small</code> in the backend environment, then restart the API.</p></div>}
      <section className="workspace-content">
        <div className="eyebrow"><span className="eyebrow-line" /> YOUR VOICE, IN EVERY LANGUAGE</div>
        <h1>Words, as they <span>happen.</span></h1><p className="intro">Speak naturally in any language. Your words appear in real time, ready to save, edit, and revisit.</p>
        <div className={`record-card ${recording ? 'is-recording' : ''}`}>
          <div className="record-card-top"><span className="record-label"><span className={recording ? 'red-dot pulse' : 'purple-dot'} />{status === 'recording' ? 'LISTENING LIVE' : status === 'processing' ? 'TRANSCRIBING' : 'READY WHEN YOU ARE'}</span><button className="language-select" onClick={() => setLanguageMenu((value) => !value)}><Languages size={15} /> {language} <ChevronDown size={14} /></button>
            {languageMenu && <div className="language-menu">{['Auto detect', 'English', 'Hindi', 'Spanish', 'French'].map((option) => <button key={option} onClick={() => { setLanguage(option); setLanguageMenu(false) }}>{option}</button>)}<p>Whisper automatically detects the spoken language.</p></div>}
          </div>
          <div className="record-center"><div className={`mic-orb ${recording ? 'active' : ''}`}><div className="mic-orb-inner">{status === 'processing' ? <LoaderCircle className="spin" size={25} /> : <Mic size={25} />}</div><span className="orb-ring ring-one"/><span className="orb-ring ring-two"/></div>
            <div className="record-status">{status === 'recording' ? <><strong>Your voice is being captured</strong><span>Speak naturally — language detection is automatic.</span></> : status === 'processing' ? <><strong>Turning speech into text…</strong><span>Your recording stays on this device.</span></> : <><strong>Ready to capture your thoughts?</strong><span>Click the microphone and start speaking.</span></>}</div>
            <div className="timer">{formatDuration(seconds)}<span>{recording ? 'REC' : 'MIN'}</span></div>
          </div>
          <div className="waveform" aria-label="Audio activity visualization">{Array.from({ length: 47 }, (_, index) => <span key={index} style={{ '--h': `${recording ? 10 + Math.abs(Math.sin(index * 1.7 + seconds) * Math.cos(index / 3)) * 30 : 5 + Math.abs(Math.sin(index * 2.3)) * 8}px`, '--d': `${index * 14}ms` }} />)}</div>
          <div className="record-footer"><span className="model-note"><WandSparkles size={14} /> Powered by open-source Whisper</span>{recording ? <button className="stop-button" onClick={stopRecording}>{status === 'processing' ? <LoaderCircle className="spin" size={15} /> : <Square size={13} fill="currentColor" />} {status === 'processing' ? 'Working…' : 'Stop recording'}</button> : <button className="start-button" onClick={startRecording} disabled={status === 'processing'}><Mic size={16} /> Start recording <span className="shortcut">Space</span></button>}</div>
        </div>
        <div className="live-caption"><div className="caption-label"><span className={status === 'recording' ? 'caption-dot active' : 'caption-dot'} /> LIVE TRANSCRIPTION</div><div className="caption-body">{status === 'recording' && !liveText ? <span className="caption-placeholder">Listening… your words will appear here</span> : currentText ? <>{currentText}{status === 'recording' && <span className="cursor" />}</> : <span className="caption-placeholder">Your transcript will appear here once you start speaking</span>}</div><span className="caption-language">{active?.language ? active.language.toUpperCase() : 'AUTO'}</span></div>
        {error && <div className="error-banner"><span>{error}</span><button onClick={() => setError('')}><X size={15} /></button></div>}
        <div className="privacy-note"><span className="lock">⌑</span> Audio is processed by your configured API and is not saved as a recording.</div>
        <section className="transcript-section"><div className="section-heading"><div><div className="eyebrow small"><span className="eyebrow-line" /> YOUR TRANSCRIPT</div><h2>{active?.title || 'The conversation, captured.'}</h2></div><div className="transcript-actions"><button className="action-button" onClick={copyText} disabled={!active?.text}>{copied ? <Check size={15} /> : <Copy size={15} />} {copied ? 'Copied' : 'Copy'}</button><button className="action-button more-button" onClick={() => active && deleteItem(active)} disabled={!active}><Trash2 size={15} /><span>Delete</span></button></div></div>
        {active ? <div className="transcript-body"><input className="transcript-title-input" aria-label="Edit transcript title" value={active.title} onChange={(e) => setActive({ ...active, title: e.target.value })} onBlur={(e) => e.target.value.trim() && e.target.value !== items.find((item) => item.id === active.id)?.title && updateItem(active.id, { title: e.target.value })} /><textarea aria-label="Edit transcript" value={active.text} onChange={(e) => setActive({ ...active, text: e.target.value })} onBlur={(e) => e.target.value.trim() && e.target.value !== items.find((item) => item.id === active.id)?.text && updateItem(active.id, { text: e.target.value })} /><div className="transcript-meta"><span><Clock3 size={13} /> {formatDate(active.created_at)}</span><span><Languages size={13} /> {active.language}</span><span>{active.text.trim().split(/\s+/).filter(Boolean).length} words</span></div></div> : <div className="transcript-empty"><div className="empty-icon"><FileAudio2 size={20} /></div><div><strong>A little space for what you said.</strong><p>Start recording to see your transcript here. It saves automatically to your library.</p></div><button onClick={startRecording} disabled={recording}><Mic size={15} /> Start a recording</button></div>}
        </section>
        <footer className="page-footer"><span><span className="green-dot" /> Running locally</span><span>Built with Whisper · Open source</span><button onClick={() => setShowSettings(true)}>Settings <ChevronDown size={13} /></button></footer>
      </section>
    </main>
    {notice && <div className="toast"><Check size={15} />{notice}</div>}
  </div>
}

export default App
