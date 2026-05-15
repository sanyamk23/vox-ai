import React, { useState, useEffect, useRef } from 'react';
import { Phone, Mic, MicOff, MessageSquare, Briefcase, User, Send, Play, Square, Activity } from 'lucide-react';

const VoiceChat = () => {
    const [isConnecting, setIsConnecting] = useState(false);
    const [isConnected, setIsConnected] = useState(false);
    const [isAiSpeaking, setIsAiSpeaking] = useState(false);
    const [transcripts, setTranscripts] = useState([]);
    const [recap, setRecap] = useState(null);
    
    // Command Center State
    const [jd, setJd] = useState("We are looking for a Senior Software Engineer proficient in React and Django.");
    const [phone, setPhone] = useState("+1");
    const [name, setName] = useState("");
    const [company, setCompany] = useState("");
    
    const socketRef = useRef(null);
    const audioContextRef = useRef(null);
    const processorRef = useRef(null);
    const streamRef = useRef(null);
    const audioQueue = useRef([]);
    const isPlaying = useRef(false);

    const connectWebSocket = async (type = 'web') => {
        setIsConnecting(true);
        setTranscripts([]);
        setRecap(null);

        if (type === 'phone') {
            try {
                const resp = await fetch('http://localhost:8000/api/call/', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ phone, jd, name, company })
                });
                const res = await resp.json();
                if (res.status === 'success') {
                    setTranscripts([{ role: 'system', text: `Initiating Phone Call to ${name} (${phone})...` }]);
                } else {
                    alert("Error initiating call: " + res.message);
                }
            } catch (e) {
                alert("Backend not reachable for phone calls.");
            }
            setIsConnecting(false);
            return;
        }

        // Web Flow
        const wsUrl = `ws://localhost:8000/ws/voice/?jd=${encodeURIComponent(jd)}&name=${encodeURIComponent(name)}&company=${encodeURIComponent(company)}`;
        socketRef.current = new WebSocket(wsUrl);

        socketRef.current.onopen = async () => {
            setIsConnected(true);
            setIsConnecting(false);
            await startRecording();
        };

        socketRef.current.onmessage = async (e) => {
            if (typeof e.data === 'string') {
                const data = jsonParse(e.data);
                if (data.type === 'transcript') {
                    setTranscripts(prev => [...prev, { role: data.role, text: data.text }]);
                } else if (data.type === 'interrupt') {
                    clearAudioQueue();
                } else if (data.type === 'recap') {
                    setRecap(data.data);
                }
            } else {
                const audioBlob = e.data;
                const arrayBuffer = await audioBlob.arrayBuffer();
                audioQueue.current.push(arrayBuffer);
                if (!isPlaying.current) playNextInQueue();
            }
        };

        socketRef.current.onclose = () => {
            stopRecording();
            setIsConnected(false);
            setIsConnecting(false);
        };
    };

    const jsonParse = (str) => { try { return JSON.parse(str); } catch { return {}; } };

    const startRecording = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            streamRef.current = stream;
            audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)({ sampleRate: 16000 });
            const source = audioContextRef.current.createMediaStreamSource(stream);
            processorRef.current = audioContextRef.current.createScriptProcessor(4096, 1, 1);

            processorRef.current.onaudioprocess = (e) => {
                const inputData = e.inputBuffer.getChannelData(0);
                const pcmData = floatTo16BitPCM(inputData);
                if (socketRef.current?.readyState === WebSocket.OPEN) {
                    socketRef.current.send(pcmData);
                }
            };

            source.connect(processorRef.current);
            processorRef.current.connect(audioContextRef.current.destination);
        } catch (err) {
            console.error("Mic access denied", err);
        }
    };

    const stopRecording = () => {
        if (socketRef.current) socketRef.current.close();
        if (streamRef.current) streamRef.current.getTracks().forEach(track => track.stop());
        if (processorRef.current) processorRef.current.disconnect();
        if (audioContextRef.current) audioContextRef.current.close();
        isPlaying.current = false;
        audioQueue.current = [];
    };

    const floatTo16BitPCM = (output) => {
        const buffer = new ArrayBuffer(output.length * 2);
        const view = new DataView(buffer);
        for (let i = 0; i < output.length; i++) {
            const s = Math.max(-1, Math.min(1, output[i]));
            view.setInt16(i * 2, s < 0 ? s * 0x8000 : s * 0x7FFF, true);
        }
        return buffer;
    };

    const playNextInQueue = async () => {
        if (audioQueue.current.length === 0) {
            isPlaying.current = false;
            setIsAiSpeaking(false);
            return;
        }

        isPlaying.current = true;
        setIsAiSpeaking(true);
        const arrayBuffer = audioQueue.current.shift();
        
        try {
            const audioBuffer = await audioContextRef.current.decodeAudioData(arrayBuffer);
            const source = audioContextRef.current.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioContextRef.current.destination);
            source.onended = playNextInQueue;
            source.start(0);
        } catch (e) {
            playNextInQueue();
        }
    };

    const clearAudioQueue = () => {
        audioQueue.current = [];
        setIsAiSpeaking(false);
    };

    return (
        <div className="max-w-6xl mx-auto p-6 grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* Header */}
            <div className="col-span-12 flex items-center justify-between mb-4 bg-slate-900/50 p-4 rounded-2xl border border-slate-800">
                <div className="flex items-center gap-3">
                    <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center">
                        <Activity className="text-white" size={24} />
                    </div>
                    <div>
                        <h1 className="text-xl font-bold bg-gradient-to-r from-white to-slate-400 bg-clip-text text-transparent">Project Vox</h1>
                        <p className="text-xs text-slate-500">Ultra-Realistic HR Screening</p>
                    </div>
                </div>
                <div className="flex items-center gap-2">
                    <div className={`w-2 h-2 rounded-full ${isConnected ? 'bg-green-500 animate-pulse' : 'bg-slate-700'}`}></div>
                    <span className="text-xs font-medium text-slate-400">{isConnected ? 'Session Live' : 'Disconnected'}</span>
                </div>
            </div>

            {/* Left Column: Command Center */}
            <div className="col-span-12 lg:col-span-4 space-y-6">
                <div className="bg-slate-900/50 rounded-3xl p-6 border border-slate-800 shadow-2xl backdrop-blur-xl">
                    <div className="flex items-center gap-2 mb-6">
                        <Briefcase size={18} className="text-blue-500" />
                        <h2 className="font-semibold text-slate-200">Job Description</h2>
                    </div>
                    <textarea 
                        className="w-full h-40 bg-slate-950/50 border border-slate-800 rounded-2xl p-4 text-sm text-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all resize-none mb-4"
                        placeholder="Paste Job Description here..."
                        value={jd}
                        onChange={(e) => setJd(e.target.value)}
                    />
                    <div className="relative mb-6">
                        <Briefcase size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
                        <input 
                            type="text" 
                            className="w-full bg-slate-950/50 border border-slate-800 rounded-xl py-3 pl-12 pr-4 text-sm text-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
                            placeholder="Company Name (e.g. Acme Corp)"
                            value={company}
                            onChange={(e) => setCompany(e.target.value)}
                        />
                    </div>

                    <div className="flex items-center gap-2 mb-4">
                        <User size={18} className="text-blue-500" />
                        <h2 className="font-semibold text-slate-200">Candidate Details</h2>
                    </div>
                    <div className="space-y-4 mb-6">
                        <div className="relative">
                            <User size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
                            <input 
                                type="text" 
                                className="w-full bg-slate-950/50 border border-slate-800 rounded-xl py-3 pl-12 pr-4 text-sm text-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
                                placeholder="Candidate Name"
                                value={name}
                                onChange={(e) => setName(e.target.value)}
                            />
                        </div>
                        <div className="relative">
                            <Phone size={16} className="absolute left-4 top-1/2 -translate-y-1/2 text-slate-500" />
                            <input 
                                type="text" 
                                className="w-full bg-slate-950/50 border border-slate-800 rounded-xl py-3 pl-12 pr-4 text-sm text-slate-300 focus:ring-2 focus:ring-blue-500 focus:outline-none transition-all"
                                placeholder="Candidate Phone (+1...)"
                                value={phone}
                                onChange={(e) => setPhone(e.target.value)}
                            />
                        </div>
                    </div>

                    <div className="space-y-3">
                        {!isConnected ? (
                            <>
                                <button 
                                    onClick={() => connectWebSocket('web')}
                                    disabled={isConnecting}
                                    className="w-full py-4 bg-white text-slate-950 rounded-2xl font-bold flex items-center justify-center gap-2 hover:bg-slate-200 transition-all shadow-lg active:scale-95 disabled:opacity-50"
                                >
                                    <Mic size={20} />
                                    {isConnecting ? 'Initializing...' : 'Start Web Screening'}
                                </button>
                                <button 
                                    onClick={() => connectWebSocket('phone')}
                                    className="w-full py-4 bg-blue-600 text-white rounded-2xl font-bold flex items-center justify-center gap-2 hover:bg-blue-500 transition-all shadow-lg shadow-blue-900/20 active:scale-95"
                                >
                                    <Send size={20} />
                                    Trigger Outbound Call
                                </button>
                            </>
                        ) : (
                            <button 
                                onClick={stopRecording}
                                className="w-full py-4 bg-red-500/10 text-red-500 border border-red-500/50 rounded-2xl font-bold flex items-center justify-center gap-2 hover:bg-red-500/20 transition-all active:scale-95"
                            >
                                <Square size={20} fill="currentColor" />
                                End Screening Session
                            </button>
                        )}
                    </div>
                </div>
            </div>

            {/* Right Column: Interaction & Recap */}
            <div className="col-span-12 lg:col-span-8 space-y-6">
                {/* Visualizer & Chat */}
                <div className="bg-slate-900/50 rounded-3xl p-6 border border-slate-800 shadow-2xl backdrop-blur-xl h-[600px] flex flex-col">
                    <div className="flex items-center justify-between mb-6">
                        <div className="flex items-center gap-2">
                            <MessageSquare size={18} className="text-blue-500" />
                            <h2 className="font-semibold text-slate-200">Live Screening Log</h2>
                        </div>
                        {isAiSpeaking && (
                            <div className="flex items-center gap-1">
                                <span className="text-[10px] font-bold text-blue-500 uppercase tracking-widest mr-2">Vox Speaking</span>
                                {[1,2,3,4].map(i => (
                                    <div key={i} className={`w-1 bg-blue-500 rounded-full animate-bounce h-${i+1}`}></div>
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="flex-1 overflow-y-auto space-y-4 pr-2 scrollbar-hide">
                        {transcripts.map((t, i) => (
                            <div key={i} className={`flex ${t.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                                <div className={`max-w-[80%] rounded-2xl p-4 ${
                                    t.role === 'user' 
                                        ? 'bg-blue-600 text-white rounded-tr-none' 
                                        : t.role === 'vox'
                                            ? 'bg-slate-800 text-slate-200 rounded-tl-none border border-slate-700'
                                            : 'bg-slate-800/30 text-slate-500 italic text-xs w-full text-center'
                                }`}>
                                    {t.role !== 'system' && (
                                        <div className="text-[10px] font-bold uppercase tracking-wider mb-1 opacity-50">
                                            {t.role === 'user' ? 'Candidate' : 'Vox'}
                                        </div>
                                    )}
                                    <p className="text-sm leading-relaxed">{t.text}</p>
                                </div>
                            </div>
                        ))}
                    </div>
                </div>

                {/* Scorecard Overlay */}
                {recap && (
                    <div className="bg-gradient-to-br from-blue-600 to-indigo-700 rounded-3xl p-8 text-white shadow-2xl border border-white/10 animate-in fade-in slide-in-from-bottom-4">
                        <div className="flex items-center justify-between mb-6">
                            <div>
                                <h3 className="text-2xl font-black">Screening Scorecard</h3>
                                <p className="text-blue-100 opacity-80">AI-Generated Candidate Assessment</p>
                            </div>
                            <div className="bg-white/20 backdrop-blur-md rounded-2xl px-6 py-4 text-center">
                                <div className="text-3xl font-black">{recap.score}</div>
                                <div className="text-[10px] font-bold uppercase">Intent Score</div>
                            </div>
                        </div>
                        <div className="bg-black/20 rounded-2xl p-6 backdrop-blur-sm">
                            <pre className="text-sm font-sans whitespace-pre-wrap leading-relaxed opacity-90">{recap.reason}</pre>
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
};

export default VoiceChat;
