import { useState, useEffect } from 'react'
import { api } from '../services/api'

export default function OnboardingGapsModal({ userId, isOpen, onClose, onComplete, inlineGaps, inlineTotalAccounts }) {
  const [gaps, setGaps]     = useState([])
  const [totalAccounts, setTotalAccounts] = useState(0)
  const [values, setValues] = useState({})
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    if (!isOpen || !userId) return
    setLoading(true)
    if (inlineGaps) {
      // Gaps provided inline from sync response (cloud sync off)
      setGaps(inlineGaps);
      setTotalAccounts(inlineTotalAccounts || inlineGaps.length);
      const init = {};
      inlineGaps.forEach((gap, i) => {
        init[i] = {
          new_last4:      (gap.account_last4 && gap.account_last4 !== '0000') ? gap.account_last4 : '',
          anchor_balance: '',
        };
      });
      setValues(init);
      setLoading(false);
    } else {
      // Fetch gaps from API (cloud sync on)
      api.getOnboardingGaps(userId)
        .then(res => {
          const g = res?.gaps || []
          setGaps(g)
          setTotalAccounts(res?.total_accounts || 0)
          const init = {}
          g.forEach((gap, i) => {
            init[i] = {
              new_last4:      (gap.account_last4 && gap.account_last4 !== '0000') ? gap.account_last4 : '',
              anchor_balance: '',
            }
          })
          setValues(init)
        })
        .catch(err => console.error('Failed to fetch gaps:', err))
        .finally(() => setLoading(false))
    }
  }, [isOpen, userId, inlineGaps, inlineTotalAccounts])

  const handleChange = (index, field, value) => {
    setValues(v => ({ ...v, [index]: { ...v[index], [field]: value } }))
  }

  const handleSubmit = async () => {
    setSaving(true)
    try {
      const resolutions = gaps.map((g, i) => {
        const resolution = {
          bank:      g.bank,
          old_last4: g.account_last4,
          new_last4: values[i]?.new_last4 || g.account_last4 || '0000', // Default to 0000 if skipped
        }
        if (g.needs_anchor) {
          resolution.anchor_balance = values[i]?.anchor_balance === '' || values[i]?.anchor_balance == null 
            ? null 
            : parseFloat(values[i].anchor_balance)
        }
        return resolution
      })
      await api.resolveOnboardingGaps(userId, resolutions)
      onComplete()
    } catch (e) {
      console.error('Failed to resolve gaps:', e)
    } finally {
      setSaving(false)
    }
  }

  if (!isOpen) return null

  // Describe what's needed per gap — action-oriented with bank name
  const gapLabel = (gap) => {
    if (gap.needs_account_number && gap.needs_anchor)
      return 'Account number & starting balance needed'
    if (gap.needs_account_number)
      return 'Enter last 4 digits of account number'
    if (gap.needs_anchor)
      return 'Enter starting / anchor balance'
    return ''
  }

  const gapDescription = (gap) => {
    if (gap.needs_account_number && gap.needs_anchor)
      return 'No account number or balance found in email alerts. Please provide the last 4 digits and your starting balance.'
    if (gap.needs_account_number)
      return 'No account number found in email alerts. Provide the last 4 digits — Mirror will track your balance from emails.'
    if (gap.needs_anchor)
      return 'This bank does not include balance in email alerts. Provide your balance at audit start date so Mirror can calculate running totals.'
    return ''
  }

  return (
    <div style={{
      position: 'fixed', inset: 0, zIndex: 1000,
      background: 'rgba(0,0,0,0.85)',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      padding: 24,
    }}>
      <div style={{
        background: '#111', border: '1px solid #222',
        borderRadius: 16, padding: 32,
        width: '100%', maxWidth: 480,
        maxHeight: '80vh', overflowY: 'auto',
      }}>

        {/* Header */}
        <div style={{ marginBottom: 24 }}>
          <h2 style={{ fontSize: 20, fontWeight: 700, marginBottom: 8, color: '#fff' }}>
            Some accounts need configuration
          </h2>
          <p style={{ color: '#666', fontSize: 14, lineHeight: 1.6 }}>
            {gaps.length > 0
              ? `${gaps.length} of ${totalAccounts} account${totalAccounts > 1 ? 's' : ''} need${totalAccounts > 1 ? '' : 's'} configuration.`
              : 'Mirror found some accounts that need a little info to track your money accurately.'}
          </p>
        </div>

        {loading && (
          <p style={{ color: '#555', fontSize: 13, textAlign: 'center', padding: '20px 0' }}>
            Checking your accounts…
          </p>
        )}

        {!loading && gaps.length === 0 && (
          <div style={{ textAlign: 'center', padding: '20px 0' }}>
            <p style={{ color: '#00c853', fontSize: 14, marginBottom: 16 }}>
              ✓ All accounts are set up correctly.
            </p>
            <button onClick={onComplete} style={{
              background: '#00c853', color: '#000',
              border: 'none', borderRadius: 8,
              padding: '12px 24px', fontWeight: 700,
              fontSize: 14, cursor: 'pointer',
            }}>
              Continue
            </button>
          </div>
        )}

        {!loading && gaps.map((gap, i) => (
          <div key={i} style={{
            background: '#1a1a1a', border: '1px solid #222',
            borderRadius: 10, padding: 20, marginBottom: 16,
          }}>
            {/* Bank header */}
            <div style={{
              display: 'flex', justifyContent: 'space-between',
              alignItems: 'flex-start', marginBottom: 12,
            }}>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 700, color: '#fff', marginBottom: 4 }}>
                  {gap.bank}
                </div>
                <div style={{
                  fontSize: 12, fontWeight: 600, color: '#f59e0b',
                  marginBottom: 4,
                }}>
                  → {gapLabel(gap)}
                </div>
                <div style={{ fontSize: 11, color: '#555', lineHeight: 1.5 }}>
                  {gapDescription(gap)}
                </div>
              </div>
              {gap.account_last4 && gap.account_last4 !== '0000' && (
                <span style={{ color: '#444', fontFamily: 'monospace', fontSize: 12, marginTop: 2, whiteSpace: 'nowrap', marginLeft: 12 }}>
                  •••• {gap.account_last4}
                </span>
              )}
            </div>

            {/*
              Case 1: Has balance (from email), missing account number
              -> Show ONLY account number input
            */}
            {gap.needs_account_number && !gap.needs_anchor && (
              <div>
                <label style={{
                  fontSize: 11, color: '#666',
                  display: 'block', marginBottom: 6, letterSpacing: '0.08em',
                }}>
                  YOUR {gap.bank.toUpperCase()} ACCOUNT — last 4 digits
                </label>
                <input
                  type="text"
                  maxLength={4}
                  placeholder="e.g. 1234"
                  value={values[i]?.new_last4 || ''}
                  onChange={e => handleChange(i, 'new_last4', e.target.value.replace(/\D/g, ''))}
                  style={{
                    width: '100%', background: '#111',
                    border: '1px solid #333', borderRadius: 8,
                    padding: '10px 14px', color: '#fff',
                    fontSize: 14, fontFamily: 'monospace',
                    outline: 'none', boxSizing: 'border-box',
                  }}
                />
                <p style={{ fontSize: 11, color: '#444', marginTop: 6 }}>
                  Balance is auto-tracked from your email alerts — no balance entry needed.
                </p>
              </div>
            )}

            {/*
              Case 2: Has account number, email doesn't contain balance
              -> Show ONLY opening balance input
            */}
            {gap.needs_anchor && !gap.needs_account_number && (
              <div>
                <label style={{
                  fontSize: 11, color: '#666',
                  display: 'block', marginBottom: 6, letterSpacing: '0.08em',
                }}>
                  OPENING BALANCE (₦) — as of {' '}
                  <span style={{ color: '#888' }}>your audit start date</span>
                </label>
                <div style={{ position: 'relative' }}>
                  <span style={{
                    position: 'absolute', left: 12,
                    top: '50%', transform: 'translateY(-50%)',
                    color: '#555', fontSize: 14,
                  }}>₦</span>
                  <input
                    type="number"
                    placeholder="0.00"
                    value={values[i]?.anchor_balance || ''}
                    onChange={e => handleChange(i, 'anchor_balance', e.target.value)}
                    style={{
                      width: '100%', background: '#111',
                      border: '1px solid #333', borderRadius: 8,
                      padding: '10px 14px 10px 28px', color: '#fff',
                      fontSize: 14, fontFamily: 'monospace',
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
                <p style={{ fontSize: 11, color: '#444', marginTop: 6 }}>
                  Enter 0 if you had no balance at the start of this period.
                  Mirror will calculate your running balance from there.
                </p>
              </div>
            )}

            {/*
              Case 3: Missing both account number AND opening balance
              -> Show both inputs
            */}
            {gap.needs_account_number && gap.needs_anchor && (
              <>
                <div style={{ marginBottom: 12 }}>
                  <label style={{
                    fontSize: 11, color: '#666',
                    display: 'block', marginBottom: 6, letterSpacing: '0.08em',
                  }}>
                    ACCOUNT NUMBER — last 4 digits
                  </label>
                  <input
                    type="text"
                    maxLength={4}
                    placeholder="e.g. 1234"
                    value={values[i]?.new_last4 || ''}
                    onChange={e => handleChange(i, 'new_last4', e.target.value.replace(/\D/g, ''))}
                    style={{
                      width: '100%', background: '#111',
                      border: '1px solid #333', borderRadius: 8,
                      padding: '10px 14px', color: '#fff',
                      fontSize: 14, fontFamily: 'monospace',
                      outline: 'none', boxSizing: 'border-box',
                    }}
                  />
                </div>
                <div>
                  <label style={{
                    fontSize: 11, color: '#666',
                    display: 'block', marginBottom: 6, letterSpacing: '0.08em',
                  }}>
                    OPENING BALANCE (₦)
                  </label>
                  <div style={{ position: 'relative' }}>
                    <span style={{
                      position: 'absolute', left: 12,
                      top: '50%', transform: 'translateY(-50%)',
                      color: '#555', fontSize: 14,
                    }}>₦</span>
                    <input
                      type="number"
                      placeholder="0.00"
                      value={values[i]?.anchor_balance || ''}
                      onChange={e => handleChange(i, 'anchor_balance', e.target.value)}
                      style={{
                        width: '100%', background: '#111',
                        border: '1px solid #333', borderRadius: 8,
                        padding: '10px 14px 10px 28px', color: '#fff',
                        fontSize: 14, fontFamily: 'monospace',
                        outline: 'none', boxSizing: 'border-box',
                      }}
                    />
                  </div>
                </div>
              </>
            )}
          </div>
        ))}

        {!loading && gaps.length > 0 && (
          <>
            <button
              onClick={handleSubmit}
              disabled={saving}
              style={{
                width: '100%',
                background: saving ? '#333' : '#00c853',
                color: saving ? '#666' : '#000',
                border: 'none', borderRadius: 8,
                padding: '14px', fontWeight: 700, fontSize: 15,
                cursor: saving ? 'not-allowed' : 'pointer',
                marginTop: 8, transition: 'background 0.15s',
              }}
            >
              {saving ? 'Saving…' : 'Confirm & Continue'}
            </button>

            <button
              onClick={handleSubmit}
              style={{
                width: '100%', background: 'transparent',
                color: '#555', border: 'none',
                padding: '12px', fontSize: 13,
                cursor: 'pointer', marginTop: 4,
              }}
            >
              Skip for now
            </button>
          </>
        )}
      </div>
    </div>
  )
}
