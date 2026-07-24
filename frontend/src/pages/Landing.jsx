// Landing.jsx — The first page users see. Shows a hero section with login
// options (Google OAuth, Yahoo Mail, Gmail App Password) and info panels.
import React, { useState, useEffect, useRef } from 'react'
import { Shield, Zap, Github, Mail, Database, Lock, Clock, AlertCircle, Eye, EyeOff } from 'lucide-react'
import { api } from '../services/api'

export function Landing({ onLogin, onEasterEggClick, user, onStartSync }) {
  // ── UI state ──────────────────────────────────────────────────────────
  const [isLoading, setIsLoading] = useState(false)        // true while login is in progress
  const [showEmailForm, setShowEmailForm] = useState(false) // show the inline email/password form?
  const [emailFormProvider, setEmailFormProvider] = useState('yahoo') // 'yahoo' or 'gmail'
  const [email, setEmail] = useState('')                    // email address typed by user
  const [password, setPassword] = useState('')              // app password typed by user
  const [error, setError] = useState('')                    // error message to display
  const [showPassword, setShowPassword] = useState(false)   // toggle password visibility
  const [subSlide, setSubSlide] = useState(0)               // which info panel (0 or 1) is showing
  const [isIntroActive, setIsIntroActive] = useState(true)  // true during the initial 4s zoomed-in intro

  // On mount: hide the intro layout after 4 seconds, then cycle info panels every 10 seconds
  useEffect(() => {
    const layoutTimer = setTimeout(() => {
      setIsIntroActive(false)
    }, 4000)

    const slideTimer = setInterval(() => {
      setSubSlide(prev => (prev === 0 ? 1 : 0))
    }, 10000)

    return () => {
      clearTimeout(layoutTimer)
      clearInterval(slideTimer)
    }
  }, [])

  const formTimer = useRef(null)
  const globalTimer = useRef(null)
  const vibrateTimer = useRef(null)
  const visualTimer = useRef(null)
  const purpleActive = useRef(false)
  const gmailCount = useRef(0)
  const lastGmailTime = useRef(0)
  const firstLogoTime = useRef(0)
  const stepRef = useRef(0)

  const [step, setStep] = useState(0)
  const [logoShake, setLogoShake] = useState(false)
  const [pageGlow, setPageGlow] = useState(null)
  const [gmailShimmer, setGmailShimmer] = useState(false)

  useEffect(() => { stepRef.current = step }, [step])

  const resetState = () => {
    setStep(0)
    gmailCount.current = 0
    firstLogoTime.current = 0
    setGmailShimmer(false)
    setLogoShake(false)
    clearTimeout(globalTimer.current)
    clearTimeout(vibrateTimer.current)
    clearTimeout(visualTimer.current)
  }

  const handleLogoClick = () => {
    const now = Date.now()
    if (step === 0) {
      setStep(1)
      firstLogoTime.current = now
      globalTimer.current = setTimeout(() => {
        setPageGlow('red')
        setTimeout(() => setPageGlow(null), 1000)
        resetState()
      }, 15000)
      vibrateTimer.current = setTimeout(() => {
        if (stepRef.current === 1) {
          setLogoShake(true)
          setTimeout(() => setLogoShake(false), 400)
        }
      }, 3000)
      visualTimer.current = setTimeout(() => {
        firstLogoTime.current = 0
      }, 3000)
    } else if (step === 1) {
      if (firstLogoTime.current > 0 && (now - firstLogoTime.current) < 3000) {
        if (!purpleActive.current) {
          purpleActive.current = true
          setPageGlow('purple')
          setTimeout(() => {
            setGmailShimmer(true)
            setTimeout(() => setGmailShimmer(false), 1500)
          }, 1000)
          setTimeout(() => {
            purpleActive.current = false
          }, 5000)
        }
      }
    } else if (step === 2) {
      setPageGlow('green')
      setStep(3)
    }
  }

  const handleGmailClick = () => {
    setEmailFormProvider('gmail')
    setError('')
    if (formTimer.current) clearTimeout(formTimer.current)
    formTimer.current = setTimeout(() => {
      setShowEmailForm(true)
    }, 1200)

    if (step !== 1) return
    const now = Date.now()
    if (gmailCount.current === 0) {
      gmailCount.current = 1
      lastGmailTime.current = now
    } else if (now - lastGmailTime.current < 1000) {
      gmailCount.current = 2
      setStep(2)
    } else {
      gmailCount.current = 1
      lastGmailTime.current = now
    }
  }

  useEffect(() => {
    if (step !== 3) return
    const handleDocClick = (e) => {
      if (e.target.closest('button') || e.target.closest('a') || e.target.closest('input')) return
      clearTimeout(globalTimer.current)
      onEasterEggClick()
    }
    document.addEventListener('click', handleDocClick)
    return () => document.removeEventListener('click', handleDocClick)
  }, [step, onEasterEggClick])

  useEffect(() => {
    return () => {
      if (formTimer.current) clearTimeout(formTimer.current)
      clearTimeout(globalTimer.current)
      clearTimeout(vibrateTimer.current)
      clearTimeout(visualTimer.current)
    }
  }, [])

  // Called when the user clicks "Connect" on the email form.
  // Sends the email/password to the backend, then calls onLogin() if successful.
  const handleEmailLogin = async () => {
    if (!email || !password) return
    setIsLoading(true)
    setError('')
    try {
      const res = await fetch('/api/auth/email-login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, provider: emailFormProvider })
      })
      const data = await res.json()
      if (data.success) {
        onLogin(data.user, {}, password)
      } else {
        setError(data.error || 'Login failed')
      }
    } catch (e) {
      setError('Connection failed. Is the backend running?')
    } finally {
      setIsLoading(false)
    }
  }

  // ── Authenticated but no data: show "Welcome Back" instead of login ──
  if (user && user.user_id) {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 via-purple-900 to-slate-900 flex items-center justify-center p-6">
        <div className="max-w-md w-full space-y-8 text-center">
          <div className="space-y-4">
            <h1 className="text-5xl font-bold text-white">mirror.ng</h1>
            <p className="text-xl text-purple-300">Your Financial Mirror</p>
          </div>
          <div className="bg-white/5 backdrop-blur-sm border border-white/10 rounded-2xl p-8 space-y-6">
            <div className="space-y-2">
              <h2 className="text-2xl font-bold text-white">Welcome Back!</h2>
              <p className="text-slate-400">
                You&apos;re logged in but haven&apos;t synced any transactions yet.
              </p>
            </div>
            <button
              onClick={onStartSync}
              className="w-full py-4 bg-gradient-to-r from-purple-500 to-pink-500 hover:from-purple-600 hover:to-pink-600 text-white font-bold rounded-xl transition-all transform hover:scale-105"
            >
              Get Started &rarr;
            </button>
            <button
              onClick={async () => {
                await api.logout();
                window.location.reload();
              }}
              className="w-full py-2 text-slate-400 hover:text-white text-sm transition-colors"
            >
              Not you? Logout
            </button>
          </div>
        </div>
      </div>
    )
  }

  // ── Render ───────────────────────────────────────────────────────────
  return (
    <div className={`h-screen bg-[#050608] overflow-hidden flex flex-col text-white font-sans ${pageGlow === 'purple' ? 'animate-page-purple' : pageGlow === 'green' ? 'animate-page-green' : pageGlow === 'red' ? 'animate-page-red' : ''}`}>
      
      {/* ── HEADER: logo + GitHub link ────────────────────────────────── */}
      <header className="h-14 sm:h-16 border-b border-white/[0.03] bg-[#050608]/80 backdrop-blur-xl px-4 sm:px-10 flex items-center justify-between z-20 shrink-0">
        <div className="flex flex-col">
          <h1
            onClick={handleLogoClick}
            className={`font-black tracking-tighter text-lg sm:text-xl leading-tight cursor-default select-none transition-all duration-300 ${
              logoShake ? 'animate-shake' : ''
            }`}
          >
            mirror<span className="text-indigo-500">.ng</span>
          </h1>
          <span className="text-[8px] sm:text-[9px] text-slate-400 font-black uppercase tracking-[0.15em]">
            A financial project by Tobiii
          </span>
        </div>

        <a href="https://github.com/mirror-ng/mirror-ng" target="_blank" rel="noopener noreferrer"
          className="inline-flex items-center gap-2 text-slate-400 hover:text-white transition-all text-[10px] sm:text-[11px] bg-white/[0.03] px-3 sm:px-5 py-2 sm:py-2.5 rounded-xl border border-white/[0.05] font-bold">
          <Github size={12} /> View on GitHub
        </a>
      </header>

      {/* ── MAIN CONTENT: hero + login buttons + info panels ──────────── */}
      <main className="flex-1 relative max-w-7xl mx-auto w-full px-4 sm:px-10 flex items-center min-h-0">
        
        <div className="grid grid-cols-1 md:grid-cols-12 w-full items-center gap-12 transition-all [transition-duration:1200ms] [transition-timing-function:cubic-bezier(0.16,1,0.3,1)]">
          
          {/* LEFT COLUMN */}
          <div className={`flex flex-col items-center text-center mx-auto w-full transition-all [transition-duration:1200ms] [transition-timing-function:cubic-bezier(0.16,1,0.3,1)]
            ${isIntroActive ? 'md:col-span-12 max-w-2xl' : 'md:col-span-7 max-w-xl'}`}>
            
            {/* Badge */}
            <div className="inline-flex items-center gap-2 bg-indigo-500/10 rounded-full px-5 py-2.5 border border-indigo-500/20 mb-4 scale-100">
              <Shield size={14} className="text-indigo-400" />
              <span className="text-[10px] font-black text-indigo-400 uppercase tracking-wider">Open Source · Privacy First</span>
            </div>

            {/* Brand */}
            <h2
              onClick={handleLogoClick}
              className={`font-black tracking-tighter leading-none mb-4 transition-all [transition-duration:1200ms] [transition-timing-function:cubic-bezier(0.16,1,0.3,1)] cursor-default select-none
              ${isIntroActive ? 'text-5xl sm:text-8xl md:text-[7rem]' : 'text-4xl sm:text-6xl md:text-7xl'} ${logoShake ? 'animate-shake' : ''}`}
            >
              mirror<span className="text-indigo-500">.ng</span>
            </h2>
            
            {/* Subtitle */}
             <p className={`text-slate-400 leading-relaxed mb-2 transition-all [transition-duration:1200ms] [transition-timing-function:cubic-bezier(0.16,1,0.3,1)] mx-auto
              ${isIntroActive ? 'text-base sm:text-xl max-w-xl' : showEmailForm ? 'text-xs sm:text-sm max-w-sm' : 'text-sm sm:text-lg max-w-md'}`}>
              Your financial mirror across all Nigerian banks. No API needed.
            </p>
             <p className={`text-white font-black tracking-tight mb-8 transition-all [transition-duration:1200ms] [transition-timing-function:cubic-bezier(0.16,1,0.3,1)]
              ${showEmailForm ? 'text-sm sm:text-lg' : 'text-xl sm:text-2xl'}`}>
              Just your email alerts.
            </p>

            {/* Trust indicators */}
            <div className={`flex items-center justify-center text-slate-600 w-full flex-wrap transition-all [transition-duration:1200ms] [transition-timing-function:cubic-bezier(0.16,1,0.3,1)]
              ${showEmailForm ? 'gap-1 sm:gap-3 mb-3 sm:mb-4' : 'gap-2 sm:gap-6 mb-6 sm:mb-8'}`}>
              <div className="flex items-center gap-1 sm:gap-2">
                <Lock size={showEmailForm ? 8 : 10} className="sm:size-[12px]" />
                <span className="text-[7px] sm:text-[10px] font-bold uppercase tracking-wider">Non-Custodial</span>
              </div>
              <div className="w-[1px] h-3 sm:h-4 bg-white/10" />
              <div className="flex items-center gap-1 sm:gap-2">
                <Zap size={showEmailForm ? 8 : 10} className="sm:size-[12px]" />
                <span className="text-[7px] sm:text-[10px] font-bold uppercase tracking-wider">Instant Sync</span>
              </div>
              <div className="w-[1px] h-3 sm:h-4 bg-white/10" />
              <div className="flex items-center gap-1 sm:gap-2">
                <Database size={showEmailForm ? 8 : 10} className="sm:size-[12px]" />
                <span className="text-[7px] sm:text-[10px] font-bold uppercase tracking-wider">Local Only</span>
              </div>
            </div>

            {/* Auth buttons: Google OAuth, Yahoo, or Gmail App Password */}
            <div className="w-full max-w-md flex flex-col gap-4 items-center mx-auto">
              {!showEmailForm ? (
                <>
                  <a
                    href="/api/auth/google/login"
                    className="w-full bg-white/[0.02] border border-white/[0.05] hover:border-white/10 text-slate-400 hover:text-white h-10 sm:h-12 rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-2 transition-all cursor-pointer"
                  >
                    <svg viewBox="0 0 24 24" className="w-4 h-4 sm:w-5 sm:h-5" aria-hidden="true">
                      <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92a5.06 5.06 0 0 1-2.2 3.32v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.1z"/>
                      <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
                      <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l2.85-2.22.81-.62z"/>
                      <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
                    </svg>
                    <span className="hidden sm:inline">Continue with Google </span>
                  </a>
                  <div className="flex items-center gap-3 w-full">
                    <div className="flex-1 h-px bg-white/5" />
                    <span className="text-[9px] text-slate-600 font-bold uppercase tracking-widest shrink-0">or</span>
                    <div className="flex-1 h-px bg-white/5" />
                  </div>
                  <div className="flex gap-2 sm:gap-3 w-full">
                    <button 
                      onClick={() => { setEmailFormProvider('yahoo'); setShowEmailForm(true); setError(''); }}
                      className="flex-1 bg-[#0f0a1c] border border-indigo-500/20 hover:border-indigo-500/40 text-indigo-300 hover:text-white h-10 sm:h-12 rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-1 sm:gap-2 transition-all shadow-lg cursor-pointer"
                    >
                      <span className="font-black italic text-xs sm:text-sm tracking-tighter text-indigo-400">y!</span>
                      Yahoo
                    </button>
                    <button
              onClick={handleGmailClick}
              className={`flex-1 rounded-xl font-bold text-xs sm:text-sm flex items-center justify-center gap-1 sm:gap-2 transition-all cursor-pointer h-10 sm:h-12 bg-white/[0.02] border border-white/[0.05] hover:border-white/10 text-slate-400 hover:text-white ${
                gmailShimmer ? 'animate-gmail-shimmer' : ''
              }`}
            >
              <Mail size={12} className="sm:size-[14px]" />
              Gmail App
            </button>
                  </div>
                </>
              ) : (
                <div className="w-full bg-[#0a0c10] border border-white/10 rounded-2xl sm:rounded-[2rem] p-2.5 sm:p-3 space-y-1.5 sm:space-y-2 animate-in fade-in zoom-in-95 duration-300 text-left">
                   <div className="flex justify-between items-center">
                     <span className="text-[8px] sm:text-[10px] font-black uppercase text-indigo-400 tracking-widest">{emailFormProvider === 'yahoo' ? 'Yahoo Mail' : 'Gmail App Password'}</span>
                     <button onClick={() => { setShowEmailForm(false); setError(''); }} className="text-[10px] sm:text-xs text-slate-500 hover:text-white font-bold cursor-pointer">Cancel</button>
                   </div>
                   {emailFormProvider === 'gmail' ? (
                     <p className="text-[8px] sm:text-[9px] text-slate-500 leading-relaxed">Generate an App Password from your <a href="https://myaccount.google.com/apppasswords" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300 underline">Google Account settings</a>. Use it below.</p>
                   ) : (
                     <p className="text-[8px] sm:text-[9px] text-slate-500 leading-relaxed">Generate an App Password from your <a href="https://login.yahoo.com/account/security" target="_blank" rel="noopener noreferrer" className="text-indigo-400 hover:text-indigo-300 underline">Yahoo Account Security settings</a>. Use it below.</p>
                   )}
                   <input type="email" value={email} onChange={e => setEmail(e.target.value)} placeholder={emailFormProvider === 'yahoo' ? 'Yahoo Email Address' : 'Gmail Address'} className="w-full bg-black/50 border border-white/5 rounded-xl px-3 sm:px-4 py-2 sm:py-2.5 text-[10px] sm:text-xs outline-none focus:border-indigo-500 transition-all" />
                   <div className="relative">
                     <input type={showPassword ? 'text' : 'password'} value={password} onChange={e => setPassword(e.target.value)} placeholder={emailFormProvider === 'yahoo' ? 'Yahoo App Password' : 'Gmail App Password'} className="w-full bg-black/50 border border-white/5 rounded-xl px-3 sm:px-4 py-2 sm:py-2.5 pr-9 sm:pr-10 text-[10px] sm:text-xs outline-none focus:border-indigo-500 transition-all" />
                     <button type="button" onClick={() => setShowPassword(!showPassword)} className="absolute right-2.5 sm:right-3 top-1/2 -translate-y-1/2 text-slate-500 hover:text-white transition-colors p-0.5">
                       {showPassword ? <EyeOff size={14} className="sm:size-[16px]" /> : <Eye size={14} className="sm:size-[16px]" />}
                     </button>
                   </div>
                   {error && (
                     <div className="flex items-start gap-2 text-red-400 text-[9px] sm:text-[10px]">
                       <AlertCircle size={10} className="sm:size-[12px] shrink-0 mt-0.5" />
                       <span>{error}</span>
                     </div>
                   )}
                   <button onClick={handleEmailLogin} disabled={isLoading} className="w-full bg-indigo-600 py-2 sm:py-2.5 rounded-xl font-black text-[10px] sm:text-xs uppercase tracking-widest hover:bg-indigo-700 transition-all disabled:opacity-50 cursor-pointer flex items-center justify-center gap-2">
                     {isLoading ? <div className="w-3 h-3 sm:w-4 sm:h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" /> : null}
                     {isLoading ? 'Connecting...' : 'Connect'}
                   </button>
                </div>
              )}
            </div>
            
            {!isIntroActive && (
              <p className={`text-[10px] text-slate-700 font-bold uppercase tracking-[0.2em] flex items-center gap-2 justify-center w-full mx-auto transition-all [transition-duration:1200ms] [transition-timing-function:cubic-bezier(0.16,1,0.3,1)]
                ${showEmailForm ? 'mt-2' : 'mt-6'}`}>
                <Lock size={12} className="text-slate-800 shrink-0" /> Credentials never leave your browser.
              </p>
            )}
          </div>

          {/* RIGHT COLUMN — 5/12 — Dynamic sliding panels */}
          <div className={`md:col-span-5 relative h-[520px] bg-[#0b0a14]/60 border border-indigo-500/[0.06] rounded-[2.5rem] p-8 flex flex-col justify-between shadow-2xl backdrop-blur-md transition-all [transition-duration:1200ms] [transition-timing-function:cubic-bezier(0.16,1,0.3,1)]
            ${isIntroActive ? 'opacity-0 translate-x-16 scale-95 pointer-events-none hidden md:none' : 'opacity-100 translate-x-0 scale-100 hidden md:flex'}`}>
            
            <div className="flex items-center justify-between border-b border-indigo-500/[0.06] pb-4">
              <span className="text-[11px] font-black text-indigo-300/60 uppercase tracking-[0.25em]">
                {subSlide === 0 ? '01 // Isolation' : '02 // Pipeline'}
              </span>
              
              <div className="flex gap-1.5">
                <button onClick={() => setSubSlide(0)} className={`h-1 rounded-full transition-all duration-500 cursor-pointer ${subSlide === 0 ? 'w-8 bg-indigo-500' : 'w-2 bg-slate-800'}`} />
                <button onClick={() => setSubSlide(1)} className={`h-1 rounded-full transition-all duration-500 cursor-pointer ${subSlide === 1 ? 'w-8 bg-indigo-500' : 'w-2 bg-slate-800'}`} />
              </div>
            </div>

            <div className="relative flex-1 mt-6">
              
              {/* SLIDE 0 */}
              <div className={`absolute inset-0 transition-all duration-700 flex flex-col gap-5 ${subSlide === 0 ? 'opacity-100 scale-100' : 'opacity-0 scale-95 pointer-events-none'}`}>
                <div className="bg-indigo-500/[0.06] border border-indigo-500/[0.08] rounded-2xl p-6 flex items-start gap-4">
                   <div className="w-12 h-12 bg-indigo-500/10 border border-indigo-500/20 rounded-xl flex items-center justify-center shrink-0"><Shield size={22} className="text-indigo-400"/></div>
                   <div className="text-left"><h4 className="text-white font-black text-xs uppercase mb-1 tracking-widest">Security Audit</h4><p className="text-indigo-200/50 text-[11px] leading-relaxed">Mirror is sandboxed open-source software. You can compile your own localized package or review our codebase manually.</p></div>
                </div>
                <div className="grid grid-cols-2 gap-4 flex-1 text-left">
                  <div className="bg-indigo-500/[0.03] border border-indigo-500/[0.06] rounded-2xl p-5 flex flex-col justify-between"><Zap className="text-indigo-400" size={24} /><div><h4 className="font-black text-[10px] uppercase mb-1 tracking-widest text-white">Instant Sync</h4><p className="text-indigo-200/40 text-[10px] leading-snug">Local triggers clear raw inputs natively post-parse.</p></div></div>
                  <div className="bg-indigo-500/[0.03] border border-indigo-500/[0.06] rounded-2xl p-5 flex flex-col justify-between"><Database className="text-indigo-400" size={24} /><div><h4 className="font-black text-[10px] uppercase mb-1 tracking-widest text-white">Zero Cloud</h4><p className="text-indigo-200/40 text-[10px] leading-snug">No data parsing caches or intermediate database engines used.</p></div></div>
                </div>
              </div>


              {/* SLIDE 1 — STAGGERED PIPELINE LAYOUT */}
              <div className={`absolute inset-0 transition-all duration-700 flex flex-col justify-between -mt-2 py-1 ${subSlide === 1 ? 'opacity-100 scale-100' : 'opacity-0 scale-95 pointer-events-none'}`}>
                
                {/* Step 1 - Left Aligned */}
                <div className="flex items-center gap-4 self-start w-[72%] bg-white/[0.02] border border-white/[0.03] rounded-2xl p-3.5 text-left backdrop-blur-sm shadow-xl">
                  <div className="w-11 h-11 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center font-black text-sm text-indigo-400 shrink-0 shadow-inner">
                    1
                  </div>
                  <div>
                    <h5 className="font-black text-white uppercase tracking-wider text-[11px] leading-tight">Connect Email</h5>
                    <p className="text-slate-400 text-[10px] mt-0.5 leading-tight">Sign in securely — we read only your bank alerts</p>
                  </div>
                </div>

                {/* Step 2 - Right Aligned */}
                <div className="flex items-center gap-4 self-end w-[72%] bg-white/[0.02] border border-white/[0.03] rounded-2xl p-3.5 text-left backdrop-blur-sm shadow-xl">
                  <div className="order-2 w-11 h-11 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center font-black text-sm text-indigo-400 shrink-0 shadow-inner">
                    2
                  </div>
                  <div className="order-1 text-right flex-1">
                    <h5 className="font-black text-white uppercase tracking-wider text-[11px] leading-tight">Set Balances</h5>
                    <p className="text-slate-400 text-[10px] mt-0.5 leading-tight">Input initial points to calculate ongoing shifts</p>
                  </div>
                </div>

                {/* Step 3 - Left Aligned */}
                <div className="flex items-center gap-4 self-start w-[72%] bg-white/[0.02] border border-white/[0.03] rounded-2xl p-3.5 text-left backdrop-blur-sm shadow-xl">
                  <div className="w-11 h-11 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center font-black text-sm text-indigo-400 shrink-0 shadow-inner">
                    3
                  </div>
                  <div>
                    <h5 className="font-black text-white uppercase tracking-wider text-[11px] leading-tight">Sync Alerts</h5>
                    <p className="text-slate-400 text-[10px] mt-0.5 leading-tight">Isolated micro-scans run natively on device</p>
                  </div>
                </div>

                {/* Step 4 - Right Aligned */}
                <div className="flex items-center gap-4 self-end w-[72%] bg-white/[0.02] border border-white/[0.03] rounded-2xl p-3.5 text-left backdrop-blur-sm shadow-xl">
                  <div className="order-2 w-11 h-11 rounded-xl bg-indigo-600/20 border border-indigo-500/30 flex items-center justify-center font-black text-sm text-indigo-400 shrink-0 shadow-inner">
                    4
                  </div>
                  <div className="order-1 text-right flex-1">
                    <h5 className="font-black text-white uppercase tracking-wider text-[11px] leading-tight">Track Dashboard</h5>
                    <p className="text-slate-400 text-[10px] mt-0.5 leading-tight">Unified transaction metrics updated in real-time</p>
                  </div>
                </div>

                {/* Vector Path Connection */}
                <svg className="absolute inset-0 w-full h-full -z-10 opacity-[0.03]" viewBox="0 0 300 300" preserveAspectRatio="none">
                  <path d="M 55 45 L 245 45 L 55 255 L 245 255" fill="none" stroke="#818cf8" strokeWidth="2" strokeDasharray="120 120" />
                </svg>

              </div>

            </div>

            <div className="border-t border-indigo-500/[0.06] pt-3 flex items-center gap-2 text-indigo-300/40">
              <Clock size={12} className="text-indigo-400/40 animate-pulse" />
              <span className="text-[9px] font-black uppercase tracking-[0.25em]">Automated lifecycle sync interval — 10s cycle</span>
            </div>

          </div>

        </div>
      </main>

      {/* ── FOOTER ────────────────────────────────────────────────────── */}
      <footer className="h-10 border-t border-white/[0.03] bg-[#050608] flex items-center justify-center shrink-0">
        <p className="text-[8px] text-slate-700 font-black uppercase tracking-[0.4em]">
          Financially Transparent · mirror.ng · By Tobiii
        </p>
      </footer>
    </div>
  )
}
