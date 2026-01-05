import React, { useState, useRef, useEffect, useCallback } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Mic, MicOff, Volume2, AlertCircle, Send, Plus } from "lucide-react";
import { usePluginCapability } from "@/context/PluginRegistryContext";
import { useDiagramTeaching } from "@/context/DiagramTeachingContext";

const API_URL = process.env.REACT_APP_BACKEND_URL;

// Context-specific initial messages - these appear IN THE CHAT STREAM
const INITIAL_MESSAGES = {
  VOICE_SYMPTOM_DIAGNOSTICS: {
    role: "alexis",
    content: "ALEXIS DIAGNOSTIC AUTHORITY — ONLINE\n\nState the symptom. Include:\n• Vehicle year, make, model, engine\n• Exact symptom description\n• When it occurs",
    timestamp: new Date().toISOString()
  },
  VISUAL_DIAGNOSTICS: {
    role: "alexis", 
    content: "ALEXIS VISUAL INSPECTION — ONLINE\n\nShow the component. State what requires verification.",
    timestamp: new Date().toISOString()
  },
  WIRING_DIAGRAM_INTERPRETATION: {
    role: "alexis",
    content: "ALEXIS DIAGRAM ASSISTANCE — ONLINE\n\nUpload a wiring diagram using the + button below, then ask about any circuit or component.",
    timestamp: new Date().toISOString()
  }
};

// Map context to backend context strings
const CONTEXT_MAP = {
  VOICE_SYMPTOM_DIAGNOSTICS: "symptom_audio_diagnostics",
  VISUAL_DIAGNOSTICS: "visual_inspection", 
  WIRING_DIAGRAM_INTERPRETATION: "diagram_assistance"
};

// Status labels per context
const STATUS_LABELS = {
  VOICE_SYMPTOM_DIAGNOSTICS: "LIVE",
  VISUAL_DIAGNOSTICS: "LIVE",
  WIRING_DIAGRAM_INTERPRETATION: "LIVE"
};

const ALEXISConversationPanel = ({ 
  context = "VOICE_SYMPTOM_DIAGNOSTICS",
  onAttachment = null,
  onOverlayCommands = null,
  onUploadClick = null,
  // For wiring diagrams: inline PDF preview in chat
  inlineContent = null,
}) => {
  const [conversation, setConversation] = useState([]);
  const [inputText, setInputText] = useState("");
  const [sessionId, setSessionId] = useState(null);
  const [isProcessing, setIsProcessing] = useState(false);
  const [status, setStatus] = useState("Initializing...");
  const [error, setError] = useState(null);
  const [micReady, setMicReady] = useState(false);

  // ═══════════════════════════════════════════════════════════════════════
  // VOICE STATE MACHINE - CRITICAL FOR TURN-TAKING
  // States: IDLE | USER_SPEAKING | ALEXIS_SPEAKING
  // ═══════════════════════════════════════════════════════════════════════
  const [voiceState, setVoiceState] = useState("IDLE"); // IDLE | USER_SPEAKING | ALEXIS_SPEAKING
  const audioRef = useRef(null); // Reference to current ALEXIS audio
  const utteranceRef = useRef(null); // Reference to browser speech utterance

  // Get diagram context for ALEXIS awareness
  const { diagramMetadata } = useDiagramTeaching();

  // Plugin-based capability checks
  const { canUseLive, canUseAuthority, blockReason } = usePluginCapability([
    context === "VOICE_SYMPTOM_DIAGNOSTICS" ? "voice_diagnostics_engine" : null,
    context === "WIRING_DIAGRAM_INTERPRETATION" ? "visual_wiring_interpretation" : null,
  ].filter(Boolean));
  const [responseMode, setResponseMode] = useState(
    context === "WIRING_DIAGRAM_INTERPRETATION" ? "EXPLANATION" : "EXPLANATION"
  ); // reserved for future modes
  const [authorityScope, setAuthorityScope] = useState(null); // null | "ONE_RESPONSE"

  const messagesEndRef = useRef(null);
  const recognitionRef = useRef(null);

  // Auto-scroll to bottom of messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [conversation]);

  // Pre-load browser voices
  useEffect(() => {
    const loadVoices = () => window.speechSynthesis.getVoices();
    loadVoices();
    window.speechSynthesis.onvoiceschanged = loadVoices;
  }, []);

  // Initialize session
  useEffect(() => {
    initSession();
    armMicrophone();
  }, [context]);

  const armMicrophone = async () => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach(t => t.stop());
      setMicReady(true);
    } catch (err) {
      setMicReady(false);
    }
  };

  const initSession = async () => {
    try {
      setStatus("Connecting...");
      const loginRes = await fetch(`${API_URL}/api/auth/login`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: "Technician", email: "tech@alexis.local" })
      });
      const loginData = await loginRes.json();

      const sessionRes = await fetch(`${API_URL}/api/session/start`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ technician_id: loginData.technician_id })
      });
      const sessionData = await sessionRes.json();

      if (sessionData.live) {
        setSessionId(sessionData.session_id);
        setStatus(STATUS_LABELS[context] || "LIVE");
        setConversation([INITIAL_MESSAGES[context] || INITIAL_MESSAGES.VOICE_SYMPTOM_DIAGNOSTICS]);
      } else {
        setStatus("Offline");
      }
    } catch (err) {
      console.error("Session init error:", err);
      setStatus("Connection Failed");
    }
  };

  // Browser-based speech recognition
  const startBrowserRecognition = () => {
    const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition) {
      setError("Browser speech recognition not supported. Please type your message.");
      return;
    }

    const recognition = new SpeechRecognition();
    recognition.continuous = false;
    recognition.interimResults = false;
    recognition.lang = 'en-US';

    recognition.onstart = () => {
      setIsRecording(true);
      setStatus("Listening...");
    };

    recognition.onresult = async (event) => {
      const transcript = event.results[0][0].transcript;
      setIsRecording(false);
      if (transcript && transcript.trim()) {
        setInputText(transcript);
        await sendMessage(transcript);
      } else {
        setError("No speech detected. Please try again.");
        setStatus(STATUS_LABELS[context] || "LIVE");
      }
    };

    recognition.onerror = (event) => {
      setIsRecording(false);
      if (event.error === 'no-speech') {
        setError("No speech detected. Please try again.");
      } else if (event.error === 'not-allowed') {
        setError("Microphone access denied.");
        setMicReady(false);
      } else {
        setError(`Speech error: ${event.error}`);
      }
      setStatus(STATUS_LABELS[context] || "LIVE");
    };

    recognition.onend = () => {
      setIsRecording(false);
    };

    recognitionRef.current = recognition;
    recognition.start();
  };

  const stopBrowserRecognition = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      setIsRecording(false);
    }
  };

  const toggleMic = () => {
    if (isRecording) {
      stopBrowserRecognition();
    } else {
      if (!sessionId) {
        setError("Session not ready.");
        return;
      }
      if (!canUseLive) {
        setError(blockReason || "Live diagnostics capability is disabled by plugin state.");
        return;
      }
      setError(null);
      startBrowserRecognition();
    }
  };

  // Send message to ALEXIS
  const sendMessage = async (text) => {
    const modeForThisMessage = responseMode;
    const messageText = text || inputText;
    if (!messageText.trim() || !sessionId) return;
    
    setIsProcessing(true);
    setError(null);
    setInputText("");

    const techMessage = {
      role: "technician",
      content: messageText.trim(),
      timestamp: new Date().toISOString()
    };
    setConversation(prev => [...prev, techMessage]);

    try {
      if (!canUseLive) {
        setError(blockReason || "Live diagnostics capability is disabled by plugin state.");
        return;
      }

      setStatus("ALEXIS is thinking...");
      
      const tapContext =
        context === "WIRING_DIAGRAM_INTERPRETATION"
          ? window.__ALEXIS_DIAGRAM_TAP_CONTEXT__ || null
          : null;

      // Build diagram context for ALEXIS awareness (CRITICAL for diagram binding)
      const diagramContext = 
        context === "WIRING_DIAGRAM_INTERPRETATION" && diagramMetadata?.loaded
          ? {
              loaded: true,
              filename: diagramMetadata.filename,
              totalPages: diagramMetadata.totalPages,
              currentPage: diagramMetadata.currentPage,
              loadedAt: diagramMetadata.loadedAt,
            }
          : null;

      const chatRes = await fetch(`${API_URL}/api/diagnostic/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          // If a required plugin is inactive/locked, force Explanation mode on backend
          response_mode: canUseAuthority ? modeForThisMessage : "EXPLANATION",
          session_id: sessionId, 
          transcript: messageText.trim(),
          context: CONTEXT_MAP[context] || "symptom_audio_diagnostics",
          tap_context: tapContext,
          diagram_context: diagramContext, // NEW: Pass diagram metadata to backend
        })
      });

      if (!chatRes.ok) throw new Error("Chat request failed");
      const chatData = await chatRes.json();

      const alexisMessage = {
        role: "alexis",
        content: chatData.response,
        timestamp: new Date().toISOString(),
        overlayCommands: chatData.overlayCommands || null,
      };

      // REMOVED: Client-side override that was forcing fallback message
      // The backend now handles this properly with diagram context awareness

      setConversation(prev => [...prev, alexisMessage]);

      // If diagram assistance, push overlayCommands into DiagramOverlayCanvas
      if (context === "WIRING_DIAGRAM_INTERPRETATION" && chatData.overlayCommands && onOverlayCommands) {
        onOverlayCommands(chatData.overlayCommands);
      }

      setStatus("ALEXIS is speaking...");

      // If Authority was scoped to one response, revert back after this
      if (authorityScope === "ONE_RESPONSE") {
        setResponseMode("EXPLANATION");
        setAuthorityScope(null);
      }
      
      await speakResponse(chatData.response);
      
    } catch (err) {
      console.error("Chat error:", err);
      const errorMessage = {
        role: "alexis",
        content: "I apologize, but I encountered an error. Please try again.",
        timestamp: new Date().toISOString()
      };
      setConversation(prev => [...prev, errorMessage]);
      setStatus(STATUS_LABELS[context] || "LIVE");
    } finally {
      setIsProcessing(false);
    }
  };

  // Add system message
  const addSystemMessage = useCallback((content, attachments = []) => {
    const systemMessage = {
      role: "system",
      content,
      attachments,
      timestamp: new Date().toISOString()
    };
    setConversation(prev => [...prev, systemMessage]);
  }, []);

  useEffect(() => {
    if (onAttachment) {
      onAttachment(addSystemMessage);
    }
  }, [onAttachment, addSystemMessage]);

  // TTS
  const speakResponse = async (text) => {
    setIsSpeaking(true);
    const cleanText = text.replace(/\*\*/g, '').replace(/\*/g, '').replace(/#/g, '');
    
    try {
      const ttsRes = await fetch(`${API_URL}/api/tts`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId, text })
      });

      if (ttsRes.ok) {
        const audioBlob = await ttsRes.blob();
        if (audioBlob.size > 100) {
          const audioUrl = URL.createObjectURL(audioBlob);
          const audio = new Audio(audioUrl);
          audio.onended = () => { 
            setIsSpeaking(false); 
            setStatus(STATUS_LABELS[context] || "LIVE");
            URL.revokeObjectURL(audioUrl); 
          };
          audio.onerror = () => browserSpeak(cleanText);
          await audio.play();
          return;
        }
      }
      browserSpeak(cleanText);
    } catch {
      browserSpeak(cleanText);
    }
  };

  const browserSpeak = (text) => {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 0.95;
    utterance.pitch = 1.0;
    utterance.lang = 'en-US';
    
    const voices = window.speechSynthesis.getVoices();
    let selectedVoice = voices.find(v => v.name.includes('Microsoft Ava Online'));
    if (!selectedVoice) selectedVoice = voices.find(v => v.name.includes('Microsoft Ava'));
    if (!selectedVoice) selectedVoice = voices.find(v => v.name.toLowerCase().includes('ava'));
    if (!selectedVoice) selectedVoice = voices.find(v => v.name.includes('Microsoft') && v.lang.startsWith('en'));
    if (selectedVoice) utterance.voice = selectedVoice;
    
    utterance.onend = () => { setIsSpeaking(false); setStatus(STATUS_LABELS[context] || "LIVE"); };
    utterance.onerror = () => { setIsSpeaking(false); setStatus(STATUS_LABELS[context] || "LIVE"); };
    window.speechSynthesis.speak(utterance);
  };

  const handleSend = () => sendMessage();

  const handleKeyDown = (e) => {
    if (e.key === 'Enter' && e.ctrlKey) {
      // Ctrl+Enter → Authority for one response
      e.preventDefault();
      setResponseMode("AUTHORITY");
      setAuthorityScope("ONE_RESPONSE");
      sendMessage();
    } else if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  /* ════════════════════════════════════════════════════════════════════════
     CHATGPT-STYLE UNIFIED LAYOUT
     ═════════════════════════════════════════════════════════════════════════
     Structure:
     1. ONE scrollable conversation area (flex-1, grows upward)
     2. Fixed input bar at bottom (never scrolls)
     3. ALL messages render in the same stream - no separate panels
     ═════════════════════════════════════════════════════════════════════════ */

  return (
    <div className="flex flex-col h-full bg-slate-950">
      {/* ═══════════════════════════════════════════════════════════════════
          SCROLLABLE CONVERSATION STREAM - THE ONLY SCROLLABLE AREA
          ═══════════════════════════════════════════════════════════════════ */}
      <div 
        className="flex-1 overflow-y-auto"
        data-testid="conversation-stream"
      >
        {/* Inner container with max-width for readability */}
        <div className="max-w-3xl mx-auto px-4 py-6 space-y-4">
          {/* Status indicator at top of conversation */}
          <div className="flex items-center justify-center gap-3 py-2">
            <span className={`px-3 py-1 rounded-full text-[11px] font-semibold uppercase tracking-wider ${
              sessionId 
                ? 'bg-emerald-500/15 text-emerald-400 border border-emerald-500/30' 
                : 'bg-amber-500/15 text-amber-400 border border-amber-500/30'
            }`}>
              {status}
            </span>
            {isSpeaking && (
              <span className="flex items-center gap-1.5 text-cyan-400 text-[11px]">
                <Volume2 className="h-3.5 w-3.5 animate-pulse" /> Speaking
              </span>
            )}
            {isRecording && (
              <span className="flex items-center gap-1.5 text-red-400 text-[11px] animate-pulse">
                <span className="w-2 h-2 bg-red-500 rounded-full"></span> Recording
              </span>
            )}
          </div>

          {/* Error Banner - renders IN the conversation stream */}
          {error && (
            <div className="mx-auto max-w-xl px-4 py-3 bg-red-900/20 border border-red-800/40 rounded-lg flex items-center gap-3">
              <AlertCircle className="h-4 w-4 text-red-400 flex-shrink-0" />
              <span className="text-sm text-red-300 flex-1">{error}</span>
              <button onClick={() => setError(null)} className="text-red-400 hover:text-red-300 text-sm font-medium">Dismiss</button>
            </div>
          )}

          {/* Inline content (e.g., PDF preview for wiring diagrams) - renders IN the conversation stream */}
          {inlineContent && (
            <div className="rounded-lg border border-slate-700/50 bg-slate-900/50 overflow-hidden">
              {inlineContent}
            </div>
          )}

          {/* Messages */}
          {conversation.map((msg, idx) => (
            <div 
              key={idx} 
              className={`flex ${msg.role === "technician" ? 'justify-end' : 'justify-start'}`}
            >
              <div 
                className={`max-w-[85%] rounded-2xl px-4 py-3 ${
                  msg.role === "technician" 
                    ? 'bg-cyan-600/90 text-white' 
                    : msg.role === "system"
                      ? 'bg-slate-800/60 border border-slate-700/50 text-slate-300'
                      : 'bg-slate-800/80 border border-slate-700/50 text-slate-100'
                }`}
              >
                {/* Role label for ALEXIS messages */}
                {msg.role === "alexis" && (
                  <p className="text-[10px] uppercase tracking-wider font-semibold text-cyan-400 mb-1.5">
                    ALEXIS
                  </p>
                )}
                {msg.role === "system" && (
                  <p className="text-[10px] uppercase tracking-wider font-semibold text-slate-500 mb-1.5">
                    System
                  </p>
                )}
                <p className="text-sm whitespace-pre-wrap leading-relaxed">{msg.content}</p>
                {msg.attachments && msg.attachments.length > 0 && (
                  <div className="mt-2 flex gap-2 flex-wrap">
                    {msg.attachments.map((att, i) => (
                      <span key={i} className="text-[10px] bg-slate-700/80 text-slate-300 px-2 py-1 rounded-full">
                        {att.name || 'Attachment'}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            </div>
          ))}
          
          {/* Scroll anchor */}
          <div ref={messagesEndRef} />
        </div>
      </div>

      {/* ═══════════════════════════════════════════════════════════════════
          FIXED INPUT BAR - PINNED TO BOTTOM, NEVER SCROLLS
          ═══════════════════════════════════════════════════════════════════ */}
      <div className="flex-shrink-0 border-t border-slate-800 bg-slate-900/95 backdrop-blur-sm">
        <div className="max-w-3xl mx-auto px-4 py-3">
          <div className="flex items-end gap-2">
            {/* Upload (+) Button */}
            {onUploadClick && (
              <Button
                type="button"
                variant="ghost"
                onClick={onUploadClick}
                disabled={isProcessing}
                data-testid="upload-plus-button"
                className="h-10 w-10 rounded-full p-0 flex-shrink-0 text-slate-400 hover:text-slate-200 hover:bg-slate-800"
              >
                <Plus className="h-5 w-5" />
              </Button>
            )}

            {/* Mic Button */}
            <Button
              variant="ghost"
              onClick={toggleMic}
              disabled={isProcessing || !sessionId}
              data-testid="mic-button"
              className={`h-10 w-10 rounded-full p-0 flex-shrink-0 transition-all ${
                isRecording 
                  ? 'bg-red-600 text-white animate-pulse' 
                  : micReady
                    ? 'text-emerald-400 hover:bg-slate-800'
                    : 'text-slate-500 hover:bg-slate-800'
              }`}
            >
              {isRecording ? <MicOff className="h-5 w-5" /> : <Mic className="h-5 w-5" />}
            </Button>

            {/* Text Input */}
            <Textarea
              value={inputText}
              onChange={(e) => setInputText(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder={isRecording ? "Listening..." : "Message ALEXIS..."}
              className="flex-1 min-h-[40px] max-h-[120px] resize-none bg-slate-800/80 border-slate-700 rounded-2xl text-sm text-slate-100 placeholder:text-slate-500 px-4 py-2.5"
              data-testid="message-input"
              disabled={isProcessing}
            />

            {/* Send Button */}
            <Button
              onClick={handleSend}
              disabled={isProcessing || !inputText.trim() || !sessionId}
              className="h-10 w-10 p-0 bg-cyan-600 hover:bg-cyan-500 text-white disabled:opacity-40 rounded-full flex-shrink-0"
              data-testid="send-button"
            >
              {isProcessing ? (
                <span className="text-xs">...</span>
              ) : (
                <Send className="h-4 w-4" />
              )}
            </Button>
          </div>
          
          {/* Subtle hint text */}
          <p className="text-[10px] text-slate-600 text-center mt-2">
            Press Enter to send • Ctrl+Enter for Authority mode
          </p>
        </div>
      </div>
    </div>
  );
};

export default ALEXISConversationPanel;
