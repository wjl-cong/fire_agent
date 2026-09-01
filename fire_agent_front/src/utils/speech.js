/**
 * 通用语音工具 — TTS 播报（百炼语音合成）+ 语音输入（录音 WAV → 百炼 ASR）
 *
 * 全局单例状态，供多个页面复用：
 *   import { speakState, speakText, stopSpeak, recordState, startRecord, stopRecord } from '@/utils/speech'
 */
import { reactive } from 'vue'
import { ElMessage } from 'element-plus'
import authFetch from '@/utils/authFetch'

const MEDIA_API = 'http://localhost:8000/api/v1/vision'

// ====== TTS 播报 ======
export const speakState = reactive({ speaking: false, loading: false })
let currentAudio = null

// Markdown → 播报用纯文本（去标题符/加粗/表格线/链接语法等）
export const mdToPlain = (md = '') => md
  .replace(/```[\s\S]*?```/g, '（代码略）')
  .replace(/!\[[^\]]*\]\([^)]*\)/g, '')
  .replace(/\[([^\]]*)\]\([^)]*\)/g, '$1')
  .replace(/[#>*_~`|-]+/g, ' ')
  .replace(/&[a-z]+;/g, ' ')
  .replace(/\s{2,}/g, ' ')
  .trim()

/**
 * 语音播报文本（再次调用或传入空文本则停止）
 * @param {string} text 播报内容（自动截断至 500 字以内）
 */
export async function speakText(text) {
  if (speakState.speaking || speakState.loading) { stopSpeak(); return }
  const plain = mdToPlain(String(text || '')).slice(0, 480)
  if (!plain) { ElMessage.warning('无内容可播报'); return }
  try {
    speakState.loading = true
    const res = await authFetch(`${MEDIA_API}/audio/speech`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text: plain }),
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({}))
      ElMessage.error(err.detail || '语音合成失败')
      speakState.loading = false
      return
    }
    const blob = await res.blob()
    currentAudio = new Audio(URL.createObjectURL(blob))
    speakState.loading = false
    speakState.speaking = true
    currentAudio.onended = () => { speakState.speaking = false }
    currentAudio.onerror = () => { speakState.speaking = false }
    currentAudio.play()
  } catch {
    ElMessage.error('语音合成请求失败')
    speakState.loading = false
  }
}

export function stopSpeak() {
  if (currentAudio) { currentAudio.pause(); currentAudio = null }
  speakState.speaking = false
  speakState.loading = false
}

// ====== 语音输入（录音 → WAV → ASR） ======
export const recordState = reactive({ recording: false, loading: false })
let audioCtx = null
let mediaStream = null
let scriptNode = null
let pcmChunks = []
let pendingCallback = null

// PCM Float32 → 16bit WAV Blob
const encodeWav = (chunks, sampleRate) => {
  const length = chunks.reduce((s, c) => s + c.length, 0)
  const buffer = new ArrayBuffer(44 + length * 2)
  const view = new DataView(buffer)
  const writeStr = (off, str) => { for (let i = 0; i < str.length; i++) view.setUint8(off + i, str.charCodeAt(i)) }
  writeStr(0, 'RIFF'); view.setUint32(4, 36 + length * 2, true); writeStr(8, 'WAVE')
  writeStr(12, 'fmt '); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true)
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true)
  view.setUint16(32, 2, true); view.setUint16(34, 16, true)
  writeStr(36, 'data'); view.setUint32(40, length * 2, true)
  let off = 44
  for (const chunk of chunks) {
    for (let i = 0; i < chunk.length; i++, off += 2) {
      const s = Math.max(-1, Math.min(1, chunk[i]))
      view.setInt16(off, s < 0 ? s * 0x8000 : s * 0x7fff, true)
    }
  }
  return new Blob([buffer], { type: 'audio/wav' })
}

/**
 * 开始录音；识别完成后回调 onText(text)
 * @param {(text: string) => void} onText 识别结果回调
 */
export async function startRecord(onText) {
  if (recordState.recording) { stopRecord(); return }
  if (!navigator.mediaDevices?.getUserMedia || !window.AudioContext) {
    ElMessage.error('当前浏览器不支持录音功能')
    return
  }
  try {
    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true })
    audioCtx = new AudioContext()
    const source = audioCtx.createMediaStreamSource(mediaStream)
    scriptNode = audioCtx.createScriptProcessor(4096, 1, 1)
    pcmChunks = []
    pendingCallback = onText
    scriptNode.onaudioprocess = (e) => {
      pcmChunks.push(new Float32Array(e.inputBuffer.getChannelData(0)))
    }
    source.connect(scriptNode)
    scriptNode.connect(audioCtx.destination)
    recordState.recording = true
    ElMessage.info('录音中，再次点击结束')
  } catch {
    ElMessage.error('无法访问麦克风，请检查浏览器权限')
  }
}

/** 停止录音并触发 ASR 识别（silent=true 时静默清理不上传） */
export function stopRecord(silent = false) {
  const doCleanup = () => {
    if (scriptNode) { scriptNode.disconnect(); scriptNode = null }
    if (mediaStream) { mediaStream.getTracks().forEach(t => t.stop()); mediaStream = null }
    if (audioCtx) { audioCtx.close(); audioCtx = null }
    recordState.recording = false
  }
  if (silent) { pcmChunks = []; doCleanup(); return }
  const cb = pendingCallback
  pendingCallback = null
  const sampleRate = audioCtx ? audioCtx.sampleRate : 48000
  const chunks = pcmChunks
  pcmChunks = []
  doCleanup()
  if (!chunks.length) return
  const wav = encodeWav(chunks, sampleRate)
  if (wav.size < 2000) { ElMessage.warning('录音太短，请重试'); return }
  ElMessage.info('语音识别中...')
  recordState.loading = true
  ;(async () => {
    try {
      const fd = new FormData()
      fd.append('file', wav, 'speech.wav')
      const res = await authFetch(`${MEDIA_API}/audio/transcriptions`, { method: 'POST', body: fd })
      const json = await res.json()
      if (json.code === 200 && json.data.ok) {
        const text = (json.data.text || '').trim()
        if (text) {
          ElMessage.success(`识别结果：${text.slice(0, 30)}${text.length > 30 ? '...' : ''}`)
          cb && cb(text)
        } else {
          ElMessage.warning('未识别到语音内容')
        }
      } else {
        ElMessage.error(json.data?.detail || '语音识别失败')
      }
    } catch {
      ElMessage.error('语音识别请求失败')
    } finally {
      recordState.loading = false
    }
  })()
}

/** 页面卸载时静默清理全部语音资源 */
export function cleanupSpeech() {
  if (recordState.recording) stopRecord(true)
  stopSpeak()
}
