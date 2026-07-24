import { useState, useEffect, useRef } from 'react';

export default function SecretImap({ onClose }) {
  const [status, setStatus] = useState('loading');
  const [code, setCode] = useState('');
  const [claiming, setClaiming] = useState(false);
  const [message, setMessage] = useState('');
  const [showVideo, setShowVideo] = useState(true);
  const [videoPlayCount, setVideoPlayCount] = useState(0);
  const [canClaim, setCanClaim] = useState(false);
  const playerRef = useRef(null);
  const videoCountRef = useRef(0);

  useEffect(() => {
    fetch('/api/easter-egg/status')
      .then(res => res.json())
      .then(data => {
        if (!data.is_active) {
          setStatus('inactive');
          setShowVideo(false);
          return;
        }
        if (data.is_claimed) {
          setStatus('claimed');
          setShowVideo(false);
          return;
        }
        return fetch('/api/easter-egg/code', { credentials: 'include' })
          .then(res => res.json())
          .then(data => {
            if (data.code) {
              setCode(data.code);
              setStatus('active');
            } else {
              setStatus(data.status);
              setShowVideo(false);
            }
          });
      });
  }, []);

  const handleVideoStateChange = (event) => {
    if (event.data === 0) {
      videoCountRef.current += 1;
      setVideoPlayCount(videoCountRef.current);

      if (videoCountRef.current < 3) {
        setTimeout(() => {
          if (playerRef.current && playerRef.current.playVideo) {
            playerRef.current.playVideo();
          }
        }, 500);
      } else {
        setShowVideo(false);
        setCanClaim(true);
      }
    }
  };

  useEffect(() => {
    if (!showVideo) return;

    const initPlayer = () => {
      if (!window.YT || !window.YT.Player) return;
      playerRef.current = new window.YT.Player('youtube-player', {
        height: '100%',
        width: '100%',
        videoId: 'l60MnDJklnM',
        playerVars: {
          autoplay: 1,
          controls: 0,
          rel: 0,
          modestbranding: 1,
          playsinline: 1,
        },
        events: {
          onStateChange: handleVideoStateChange,
          onReady: (event) => event.target.playVideo(),
        },
      });
    };

    window.onYouTubeIframeAPIReady = initPlayer;
    if (window.YT && window.YT.Player) {
      initPlayer();
    } else {
      const tag = document.createElement('script');
      tag.src = 'https://www.youtube.com/iframe_api';
      document.head.appendChild(tag);
    }

    return () => {
      if (playerRef.current && playerRef.current.destroy) {
        playerRef.current.destroy();
      }
    };
  }, [showVideo]);

  const handleClaim = async () => {
    setClaiming(true);
    try {
      const res = await fetch('/api/easter-egg/claim', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ code }),
      });
      const data = await res.json();
      if (data.success) {
        setStatus('claimed');
        setMessage(data.message);
      } else {
        setMessage(data.detail || 'Claim failed');
      }
    } catch (e) {
      setMessage('Network error');
    }
    setClaiming(false);
  };

  if (showVideo && status === 'active') {
    return (
      <div className="min-h-screen bg-black flex flex-col items-center justify-center p-4">
        <div id="youtube-player" className="w-full max-w-4xl aspect-video"></div>
        <div className="mt-4 text-white text-sm font-mono">
          Watching... {videoPlayCount + 1} of 3
        </div>
      </div>
    );
  }

  if (status === 'loading') {
    return (
      <div className="min-h-screen bg-slate-900 flex items-center justify-center text-white">
        Loading...
      </div>
    );
  }

  if (status === 'inactive') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 to-purple-900 flex items-center justify-center p-6">
        <div className="text-center text-white">
          <div className="text-6xl mb-4">&#x1f512;</div>
          <h1 className="text-2xl font-bold mb-2">The vault is closed</h1>
          <p className="text-slate-400">Check back later for the next treasure hunt.</p>
          <button onClick={onClose} className="mt-6 px-6 py-2 bg-white/10 rounded-lg hover:bg-white/20 transition-colors">
            &larr; Go Back
          </button>
        </div>
      </div>
    );
  }

  if (status === 'claimed') {
    return (
      <div className="min-h-screen bg-gradient-to-br from-slate-900 to-purple-900 flex items-center justify-center p-6">
        <div className="text-center text-white">
          <div className="text-6xl mb-4">&#x1f3c6;</div>
          <h1 className="text-2xl font-bold mb-2">Treasure Already Claimed!</h1>
          <p className="text-slate-400">
            {message || 'Someone beat you to it. Better luck next time!'}
          </p>
          <button onClick={onClose} className="mt-6 px-6 py-2 bg-white/10 rounded-lg hover:bg-white/20 transition-colors">
            &larr; Go Back
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-gradient-to-br from-purple-900 via-indigo-900 to-slate-900 flex items-center justify-center p-6">
      <div className="max-w-md w-full text-center space-y-6">
        <div className="text-6xl">&#x1f389;</div>
        <h1 className="text-3xl font-bold text-white">You Found It!</h1>
        <p className="text-purple-300">First person to claim wins &#x20a6;10,000</p>

        <div className="bg-white/5 border border-white/10 rounded-xl p-6 space-y-4">
          <p className="text-xs text-slate-400 uppercase tracking-wide">Your Code</p>
          <div className="font-mono text-2xl text-yellow-400 break-all">{code}</div>

          <button
            onClick={handleClaim}
            disabled={claiming || !canClaim}
            className="w-full py-3 bg-gradient-to-r from-yellow-500 to-orange-500 hover:from-yellow-600 hover:to-orange-600 text-black font-bold rounded-lg transition-all disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {claiming ? 'Claiming...' : !canClaim ? 'Watch the video first...' : 'Claim &#x20a6;10,000 Now'}
          </button>

          {message && <p className="text-sm text-red-400">{message}</p>}
        </div>

        <button onClick={onClose} className="text-slate-400 hover:text-white text-sm transition-colors">
          &larr; Go Back
        </button>
      </div>
    </div>
  );
}