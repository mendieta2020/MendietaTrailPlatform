import React, { useState } from 'react'
import { createReport, sendReportEmail } from '../api/reports'

const PERIOD_OPTIONS = [
  { label: '30 días', days: 30 },
  { label: '3 meses', days: 90 },
  { label: '6 meses', days: 180 },
  { label: '1 año', days: 365 },
]

/**
 * ShareReportModal — PR-154
 *
 * Allows a coach to generate a shareable athlete training report and
 * share it via WhatsApp link, email, or clipboard copy.
 *
 * Props:
 *   open          Boolean — whether the modal is visible
 *   onClose       Function — called when user closes the modal
 *   membershipId  Number  — athlete's Membership PK
 *   athleteName   String  — athlete display name
 *   currentDays   Number  — currently selected period in the parent view
 *   previewKPIs   Object  — { readiness_score, ctl, acwr } from already-loaded PMC data
 */
const ShareReportModal = ({
  open,
  onClose,
  membershipId,
  athleteName,
  currentDays = 90,
  previewKPIs = {},
}) => {
  const [periodDays, setPeriodDays] = useState(currentDays)
  const [message, setMessage]       = useState('')
  const [generating, setGenerating] = useState(false)
  const [generated, setGenerated]   = useState(null)  // { token, url, preview }
  const [error, setError]           = useState(null)

  const [emailMode, setEmailMode]   = useState(false)
  const [email, setEmail]           = useState('')
  const [emailSent, setEmailSent]   = useState(false)
  const [emailSending, setEmailSending] = useState(false)
  const [emailError, setEmailError] = useState(null)

  const [copied, setCopied]         = useState(false)

  if (!open) return null

  // ── generate report ───────────────────────────────────────────────────────
  async function handleGenerate() {
    setGenerating(true)
    setError(null)
    try {
      const res = await createReport(membershipId, {
        period_days: periodDays,
        coach_message: message,
      })
      setGenerated(res.data)
    } catch {
      setError('No se pudo generar el reporte. Intentá de nuevo.')
    } finally {
      setGenerating(false)
    }
  }

  // ── share via WhatsApp ────────────────────────────────────────────────────
  function handleWhatsApp() {
    const text = encodeURIComponent(
      `📊 Tu reporte de entrenamiento está listo.\n${generated.url}`
    )
    window.open(`https://wa.me/?text=${text}`, '_blank', 'noopener')
  }

  // ── send email ────────────────────────────────────────────────────────────
  async function handleEmail() {
    if (!email || !email.includes('@')) {
      setEmailError('Ingresá un email válido.')
      return
    }
    setEmailSending(true)
    setEmailError(null)
    try {
      await sendReportEmail(membershipId, generated.token, { recipient_email: email })
      setEmailSent(true)
    } catch {
      setEmailError('No se pudo enviar el email. Verificá la dirección.')
    } finally {
      setEmailSending(false)
    }
  }

  // ── copy link ─────────────────────────────────────────────────────────────
  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(generated.url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    } catch {
      // fallback
      const el = document.createElement('textarea')
      el.value = generated.url
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
      setCopied(true)
      setTimeout(() => setCopied(false), 2500)
    }
  }

  function handleClose() {
    setGenerated(null)
    setError(null)
    setEmailMode(false)
    setEmail('')
    setEmailSent(false)
    setEmailError(null)
    setCopied(false)
    onClose()
  }

  const preview = generated?.preview ?? previewKPIs

  return (
    <div
      style={{ position: 'fixed', inset: 0, zIndex: 1200, display: 'flex', alignItems: 'center', justifyContent: 'center', background: 'rgba(15,23,42,0.45)', padding: '16px' }}
      onClick={(e) => { if (e.target === e.currentTarget) handleClose() }}
    >
      <div style={{ background: '#fff', borderRadius: '16px', width: '100%', maxWidth: '460px', boxShadow: '0 20px 60px rgba(0,0,0,0.18)', overflow: 'hidden' }}>
        {/* Modal header */}
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '20px 24px', borderBottom: '1px solid #e2e8f0' }}>
          <div>
            <p style={{ fontSize: '13px', color: '#94a3b8', margin: 0 }}>Compartir reporte</p>
            <p style={{ fontSize: '17px', fontWeight: 700, color: '#0f172a', margin: 0 }}>{athleteName}</p>
          </div>
          <button onClick={handleClose} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '20px', color: '#94a3b8', lineHeight: 1 }}>✕</button>
        </div>

        <div style={{ padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>

          {/* Preview KPIs */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px' }}>
            {[
              { label: 'Readiness', value: preview?.readiness_score ?? preview?.readiness ?? '—' },
              { label: 'CTL',       value: preview?.ctl ? Math.round(preview.ctl) : '—' },
              { label: 'ACWR',      value: preview?.acwr ?? '—' },
            ].map(({ label, value }) => (
              <div key={label} style={{ background: '#f8fafc', borderRadius: '10px', padding: '12px', textAlign: 'center', border: '1px solid #e2e8f0' }}>
                <p style={{ fontSize: '10px', textTransform: 'uppercase', letterSpacing: '0.08em', color: '#94a3b8', margin: '0 0 4px' }}>{label}</p>
                <p style={{ fontSize: '20px', fontWeight: 800, color: '#0f172a', margin: 0 }}>{value}</p>
              </div>
            ))}
          </div>

          {/* Period selector */}
          {!generated && (
            <>
              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569', display: 'block', marginBottom: '6px' }}>Período</label>
                <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                  {PERIOD_OPTIONS.map(({ label, days }) => (
                    <button
                      key={days}
                      onClick={() => setPeriodDays(days)}
                      style={{
                        padding: '6px 14px', borderRadius: '6px', fontSize: '13px', fontWeight: 500, cursor: 'pointer', border: 'none',
                        background: periodDays === days ? '#f59e0b' : '#f1f5f9',
                        color: periodDays === days ? '#0f172a' : '#475569',
                      }}
                    >
                      {label}
                    </button>
                  ))}
                </div>
              </div>

              <div>
                <label style={{ fontSize: '12px', fontWeight: 600, color: '#475569', display: 'block', marginBottom: '6px' }}>
                  Mensaje para el atleta (opcional)
                </label>
                <textarea
                  value={message}
                  onChange={e => setMessage(e.target.value)}
                  placeholder="Ej: Excelente progresión este mes, seguí así..."
                  rows={3}
                  maxLength={2000}
                  style={{ width: '100%', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '10px 12px', fontSize: '13px', color: '#334155', resize: 'vertical', fontFamily: 'inherit', outline: 'none' }}
                />
              </div>
            </>
          )}

          {/* Error */}
          {error && (
            <p style={{ fontSize: '13px', color: '#b91c1c', background: '#fee2e2', padding: '10px 14px', borderRadius: '8px', margin: 0 }}>{error}</p>
          )}

          {/* PRE-GENERATE: primary action */}
          {!generated && (
            <button
              onClick={handleGenerate}
              disabled={generating}
              style={{ padding: '12px', borderRadius: '10px', background: generating ? '#fbbf24' : '#f59e0b', color: '#0f172a', fontWeight: 700, fontSize: '14px', border: 'none', cursor: generating ? 'not-allowed' : 'pointer' }}
            >
              {generating ? 'Generando reporte...' : 'Generar Reporte'}
            </button>
          )}

          {/* POST-GENERATE: share buttons */}
          {generated && (
            <>
              <div style={{ background: '#f0fdf4', border: '1px solid #bbf7d0', borderRadius: '10px', padding: '12px 14px' }}>
                <p style={{ fontSize: '12px', color: '#15803d', fontWeight: 600, margin: '0 0 2px' }}>Reporte generado</p>
                <p style={{ fontSize: '11px', color: '#166534', margin: 0, wordBreak: 'break-all' }}>{generated.url}</p>
              </div>

              {/* Share buttons */}
              <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                <button
                  onClick={handleWhatsApp}
                  style={{ flex: '1', padding: '10px', borderRadius: '8px', background: '#dcfce7', color: '#15803d', fontWeight: 700, fontSize: '13px', border: 'none', cursor: 'pointer', minWidth: '120px' }}
                >
                  WhatsApp
                </button>
                <button
                  onClick={() => { setEmailMode(!emailMode); setEmailSent(false); setEmailError(null) }}
                  style={{ flex: '1', padding: '10px', borderRadius: '8px', background: emailMode ? '#e0e7ff' : '#f1f5f9', color: emailMode ? '#3730a3' : '#475569', fontWeight: 700, fontSize: '13px', border: 'none', cursor: 'pointer', minWidth: '120px' }}
                >
                  Email
                </button>
                <button
                  onClick={handleCopy}
                  style={{ flex: '1', padding: '10px', borderRadius: '8px', background: copied ? '#e0f2fe' : '#f1f5f9', color: copied ? '#0369a1' : '#475569', fontWeight: 700, fontSize: '13px', border: 'none', cursor: 'pointer', minWidth: '120px' }}
                >
                  {copied ? 'Copiado!' : 'Copiar Link'}
                </button>
              </div>

              {/* Email sub-form */}
              {emailMode && !emailSent && (
                <div style={{ display: 'flex', gap: '8px' }}>
                  <input
                    type="email"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    placeholder="email@atletismo.com"
                    style={{ flex: 1, border: '1px solid #e2e8f0', borderRadius: '8px', padding: '10px 12px', fontSize: '13px', outline: 'none', fontFamily: 'inherit' }}
                  />
                  <button
                    onClick={handleEmail}
                    disabled={emailSending}
                    style={{ padding: '10px 16px', borderRadius: '8px', background: '#3b82f6', color: '#fff', fontWeight: 700, fontSize: '13px', border: 'none', cursor: emailSending ? 'not-allowed' : 'pointer', whiteSpace: 'nowrap' }}
                  >
                    {emailSending ? '...' : 'Enviar'}
                  </button>
                </div>
              )}
              {emailError && (
                <p style={{ fontSize: '12px', color: '#b91c1c', margin: 0 }}>{emailError}</p>
              )}
              {emailSent && (
                <p style={{ fontSize: '13px', color: '#15803d', background: '#f0fdf4', padding: '8px 12px', borderRadius: '8px', margin: 0 }}>
                  Email enviado correctamente.
                </p>
              )}
            </>
          )}

        </div>
      </div>
    </div>
  )
}

export default ShareReportModal
