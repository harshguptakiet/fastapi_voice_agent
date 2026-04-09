'use client';

import { useState, useRef, useEffect } from 'react';
import { Button } from "@/components/ui/button";
import { Avatar, AvatarImage, AvatarFallback } from "@/components/ui/avatar";
import { Send, Trash, Loader2, Upload, FileText, X, CheckCircle, AlertCircle } from "lucide-react";
import { Sidebar } from '@/app/components/Sidebar';
import { VoiceOrb } from '@/components/voice-orb';
import { useVoiceChat } from '@/hooks/use-voice-chat';
import { streamRecordedVoiceTurn } from '@/lib/voice-streaming';

export default function Dashboard() {
  const [message, setMessage] = useState('');
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [uploadedFiles, setUploadedFiles] = useState([]);
  const [isDragging, setIsDragging] = useState(false);
  const [isTyping, setIsTyping] = useState(false);
  const [error, setError] = useState(null);
  const [voiceError, setVoiceError] = useState('');
  /** idle | processing | speaking — voice pipeline HUD (not a chat bubble). */
  const [voicePhase, setVoicePhase] = useState('idle');
  const [handsFreeVoiceEnabled, setHandsFreeVoiceEnabled] = useState(false);
  const messagesEndRef = useRef(null);
  const fileInputRef = useRef(null);
  const textareaRef = useRef(null);
  const isLoadingRef = useRef(false);
  const handsFreeEnabledRef = useRef(false);
  const voiceTurnActiveRef = useRef(false);
  /** Shared across typed chat and voice so FastAPI memory (session_id) stays consistent. */
  const voiceSessionIdRef = useRef(`education-session-${Date.now()}`);

  useEffect(() => {
    setMessages([
      { 
        id: 1, 
        content: "👋 Welcome to Eduthum AI! I'm here to help you explore and understand your documents. Upload your PDFs and ask me anything about their content - from summaries to specific questions!", 
        sender: "bot", 
        time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
      },
    ]);
  }, []);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  useEffect(() => {
    isLoadingRef.current = isLoading;
  }, [isLoading]);

  useEffect(() => {
    handsFreeEnabledRef.current = handsFreeVoiceEnabled;
  }, [handsFreeVoiceEnabled]);

  // Auto-resize textarea
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = 'auto';
      textareaRef.current.style.height = Math.min(textareaRef.current.scrollHeight, 120) + 'px';
    }
  }, [message]);

  const sendMessageToAPI = async (userMessage, files = []) => {
    try {
      setIsLoading(true);
      setIsTyping(true);
      setError(null);

      let response;
      let requestUrl;
      let requestOptions;

      if (userMessage === "UPLOAD_FILES") {
        // File Upload Route
        const formData = new FormData();
        formData.append('query', userMessage);

        const allUploadedFiles =
          files.length > 0
            ? files
            : uploadedFiles.filter(f => f.uploaded).map(f => f.file);

        allUploadedFiles.forEach((file, index) => {
          formData.append(`file_${index}`, file);
        });

        requestUrl = "/api/Eduthum";
        requestOptions = {
          method: "POST",
          body: formData,
        };
      } else {
        // Chat Route
        requestUrl = "/api/Eduthum/chat";
        requestOptions = {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: userMessage,
            session_id: voiceSessionIdRef.current,
            student_id: 2,
          }),
        };
      }

      console.log('Sending request to:', requestUrl);
      response = await fetch(requestUrl, requestOptions);

      if (!response.ok) {
        const errorText = await response.text();
        console.error('Server response error:', errorText);
        throw new Error(`Server error: ${response.status} - ${errorText}`);
      }

      const data = await response.json();
      console.log('API Response:', data);

      // Handle different response formats
      let botMessage = data.answer || data.response || "I apologize, but I didn't receive a proper response. Please try again.";

      setIsTyping(false);
      setMessages(prev => [
        ...prev,
        {
          id: Date.now() + Math.random(),
          content: botMessage,
          sender: "bot",
          time: new Date().toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit",
            hour12: true,
          }),
        },
      ]);

      return botMessage;
    } catch (error) {
      console.error("API Error:", error);
      setError(error.message);
      setIsTyping(false);
      setMessages(prev => [
        ...prev,
        {
          id: Date.now() + Math.random(),
          content: `❌ Oops! Something went wrong: ${error.message}. Please check your connection and try again.`,
          sender: "bot",
          time: new Date().toLocaleTimeString("en-US", {
            hour: "2-digit",
            minute: "2-digit",
            hour12: true,
          }),
        },
      ]);
      return "";
    } finally {
      setIsLoading(false);
    }
  };

  const sendVoiceMessage = async (transcript) => {
    const text = (transcript || '').trim();
    if (!text || isLoadingRef.current) return;
    const userMessage = {
      id: Date.now(),
      content: text,
      sender: "user",
      time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
    };
    setMessages(prev => [...prev, userMessage]);
    await sendMessageToAPI(text);
  };

  const playBase64Audio = async (audioB64, mimeType = 'audio/mpeg') => {
    const audio = new Audio(`data:${mimeType};base64,${audioB64}`);
    await new Promise((resolve, reject) => {
      audio.onended = resolve;
      audio.onerror = () => reject(new Error('Audio playback failed.'));
      audio.play().catch(reject);
    });
  };

  const handleVoiceTurn = async ({ audio_b64, sample_rate_hz }) => {
    if (voiceTurnActiveRef.current) return;
    voiceTurnActiveRef.current = true;
    try {
      setIsTyping(false);
      setVoicePhase('processing');
      setVoiceError('');

      const isVoiceStopCommand = (rawText) => {
        const t = String(rawText || "").trim().toLowerCase();
        if (!t) return false;
        if (["no", "nah", "bye", "goodbye", "exit", "quit"].includes(t)) return true;
        if (["no thanks", "no thank you"].includes(t)) return true;
        if (
          t.includes("end chat") ||
          t.includes("end the chat") ||
          t.includes("stop chat") ||
          t.includes("stop the chat") ||
          t.includes("stop talking")
        )
          return true;
        // Common short assistant-followup answers: "no", "no that's all", etc.
        if (t.startsWith("no ")) {
          const wc = t.split(/\s+/).filter(Boolean).length;
          if (wc <= 6) return true;
        }
        return false;
      };

      let didAddBotBubble = false;
      const turnResult = await streamRecordedVoiceTurn({
        session_id: voiceSessionIdRef.current,
        audio_b64,
        sample_rate_hz,
        domain: 'education',
        language: 'en-US',
        stream: true,
        onTranscript: (t) => {
          const text = String(t || '').trim();
          if (!text) return;
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now() + Math.random(),
              content: text,
              sender: 'user',
              time: new Date().toLocaleTimeString('en-US', {
                hour: '2-digit',
                minute: '2-digit',
                hour12: true,
              }),
            },
          ]);

          if (isVoiceStopCommand(text)) {
            // Stop hands-free mic; allow the current assistant audio turn to finish.
            setHandsFreeVoiceEnabled(false);
            handsFreeEnabledRef.current = false;
            stopListening({ finalize: false }).catch(() => {});
          }
        },
        onFinalText: (text) => {
          const reply = String(text || '').trim();
          if (!reply) return;
          didAddBotBubble = true;
          setMessages((prev) => [
            ...prev,
            {
              id: Date.now() + Math.random(),
              content: reply,
              sender: 'bot',
              time: new Date().toLocaleTimeString('en-US', {
                hour: '2-digit',
                minute: '2-digit',
                hour12: true,
              }),
            },
          ]);
        },
        onAudioChunk: async (chunk) => {
          setVoicePhase('speaking');
          await playBase64Audio(chunk.audio_b64, chunk.mime_type || 'audio/mpeg');
        },
      });

      // Fallback: if `final_text` wasn't parsed for any reason, add it once now.
      const fallbackBotText = String(turnResult?.final_text || "").trim();
      if (fallbackBotText && !didAddBotBubble) {
        setMessages((prev) => [
          ...prev,
          {
            id: Date.now() + Math.random(),
            content: fallbackBotText,
            sender: 'bot',
            time: new Date().toLocaleTimeString('en-US', {
              hour: '2-digit',
              minute: '2-digit',
              hour12: true,
            }),
          },
        ]);
      }
    } catch (err) {
      setVoiceError(err?.message || 'Voice conversation failed.');
    } finally {
      voiceTurnActiveRef.current = false;
      setVoicePhase('idle');
    }
  };

  const {
    isListening,
    isTranscribing,
    startListening,
    stopListening,
    supported: voiceSupported,
  } = useVoiceChat({
    // Voice pipeline uses FastAPI SSE (`event: input` + `event: final_text`) for chat bubbles.
    // Avoid wiring STT transcript here to prevent duplicate user messages.
    onTranscript: undefined,
    onAudioCaptured: handleVoiceTurn,
    onError: (msg) => setVoiceError(msg),
    manualMode: false,
  });

  const voiceHudMode = isListening
    ? 'listening'
    : voicePhase === 'speaking'
      ? 'speaking'
      : voicePhase === 'processing'
        ? 'processing'
        : 'idle';

  const validateFiles = (files) => {
    const validFiles = [];
    const errors = [];
    const maxFileSize = 10 * 1024 * 1024; // 10MB

    Array.from(files).forEach(file => {
      if (file.type !== 'application/pdf') {
        errors.push(`${file.name} is not a PDF file`);
        return;
      }

      if (file.size > maxFileSize) {
        errors.push(`${file.name} is too large (max 10MB)`);
        return;
      }

      if (file.size === 0) {
        errors.push(`${file.name} is empty`);
        return;
      }

      if (uploadedFiles.some(existing => existing.name === file.name && existing.size === (file.size / 1024 / 1024).toFixed(2) + ' MB')) {
        errors.push(`${file.name} is already uploaded`);
        return;
      }

      validFiles.push(file);
    });

    return { validFiles, errors };
  };

  const handleFileUpload = async (fileList) => {
    if (!fileList || fileList.length === 0) return;

    const { validFiles, errors } = validateFiles(fileList);

    if (errors.length > 0) {
      setMessages(prev => [...prev, {
        id: Date.now(),
        content: `⚠️ Upload issues:\n${errors.join('\n')}`,
        sender: "system",
        time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
      }]);
      return;
    }

    if (validFiles.length === 0) return;

    const newFiles = validFiles.map(file => ({
      id: Date.now() + Math.random(),
      file: file,
      name: file.name,
      size: (file.size / 1024 / 1024).toFixed(2) + ' MB',
      uploaded: false,
      uploading: false
    }));

    setUploadedFiles(prev => [...prev, ...newFiles]);

    const fileNames = newFiles.map(f => f.name).join(', ');
    setMessages(prev => [...prev, {
      id: Date.now(),
      content: `📚 Processing ${newFiles.length} document${newFiles.length !== 1 ? 's' : ''}: ${fileNames}...`,
      sender: "system",
      time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
    }]);

    // Set uploading status
    setUploadedFiles(prev =>
      prev.map(file =>
        newFiles.find(nf => nf.id === file.id) ? { ...file, uploading: true } : file
      )
    );

    try {
      const filesToSend = newFiles.map(f => f.file);
      await sendMessageToAPI(`UPLOAD_FILES`, filesToSend);

      setUploadedFiles(prev =>
        prev.map(file =>
          newFiles.find(nf => nf.id === file.id) ? { ...file, uploaded: true, uploading: false } : file
        )
      );

    } catch (error) {
      console.error('Upload error:', error);
      setUploadedFiles(prev =>
        prev.map(file =>
          newFiles.find(nf => nf.id === file.id) ? { ...file, uploading: false } : file
        )
      );
    }
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    if (!e.currentTarget.contains(e.relatedTarget)) {
      setIsDragging(false);
    }
  };

  const handleDrop = (e) => {
    e.preventDefault();
    setIsDragging(false);
    handleFileUpload(e.dataTransfer.files);
  };

  const removeFile = (fileId) => {
    setUploadedFiles(prev => prev.filter(file => file.id !== fileId));
  };

  const handleSendMessage = async () => {
    if (!message.trim() || isLoading || voicePhase !== 'idle') return;

    const userMessage = {
      id: Date.now(),
      content: message.trim(),
      sender: "user",
      time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
    };

    setMessages(prev => [...prev, userMessage]);
    const messageToSend = message.trim();
    setMessage('');

    await sendMessageToAPI(messageToSend);
  };

  const handleVoiceOrbPress = async () => {
    try {
      if (handsFreeEnabledRef.current) {
        setHandsFreeVoiceEnabled(false);
        await stopListening();
      } else {
        setHandsFreeVoiceEnabled(true);
        await startListening();
      }
    } catch (err) {
      setVoiceError(err?.message || 'Voice unavailable.');
      setHandsFreeVoiceEnabled(false);
    }
  };

  const voiceOrbDisabled =
    !voiceSupported || isLoading || isTranscribing;

  const handleKeyPress = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const clearChat = () => {
    setHandsFreeVoiceEnabled(false);
    stopListening();
    voiceSessionIdRef.current = `education-session-${Date.now()}`;
    setVoicePhase('idle');
    setVoiceError('');
    setMessages([
      { 
        id: 1, 
        content: "👋 Welcome to Eduthum AI! I'm here to help you explore and understand your documents. Upload your PDFs and ask me anything about their content - from summaries to specific questions!", 
        sender: "bot", 
        time: new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: true })
      },
    ]);
    setUploadedFiles([]);
    setError(null);
  };

  const retryLastMessage = () => {
    const lastUserMessage = messages.filter(msg => msg.sender === 'user').pop();
    if (lastUserMessage) {
      sendMessageToAPI(lastUserMessage.content);
    }
  };

  return (
    <div className="flex h-screen w-full bg-zinc-100">
      <Sidebar />

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200/80 bg-white px-4">
          <div className="flex items-center gap-3">
            <h1 className="text-[15px] font-semibold tracking-tight text-zinc-900">Eduthum AI</h1>
            {error && (
              <span className="flex items-center gap-1.5 text-xs text-red-600">
                <AlertCircle className="h-3.5 w-3.5" />
                Connection issue
              </span>
            )}
          </div>
          <Avatar className="h-8 w-8">
            <AvatarImage src="/avatar.png" alt="" />
            <AvatarFallback className="bg-zinc-200 text-xs text-zinc-700">ED</AvatarFallback>
          </Avatar>
        </header>

        <main className="flex min-h-0 flex-1 overflow-hidden">
          <div className="relative flex min-h-0 min-w-0 flex-1 flex-col bg-white">
            <div className="flex h-14 shrink-0 items-center justify-between border-b border-zinc-200/80 px-5">
              <div className="flex items-center gap-3">
                <Avatar className="h-9 w-9">
                  <AvatarFallback className="bg-zinc-900 text-[11px] font-medium text-white">ED</AvatarFallback>
                </Avatar>
                <div>
                  <h2 className="text-[15px] font-medium text-zinc-900">Assistant</h2>
                  <p className="text-xs text-zinc-500">
                    {voiceHudMode === 'listening'
                      ? 'Listening'
                      : voiceHudMode === 'processing'
                        ? 'Processing'
                        : voiceHudMode === 'speaking'
                          ? 'Playing reply'
                          : isTyping
                            ? 'Typing…'
                            : isLoading
                              ? 'Working…'
                              : `${uploadedFiles.filter((f) => f.uploaded).length} PDF${uploadedFiles.filter((f) => f.uploaded).length !== 1 ? 's' : ''} ready`}
                  </p>
                </div>
              </div>
              <div className="flex items-center gap-1">
                <Button
                  type="button"
                  variant="ghost"
                  size="sm"
                  className="text-zinc-600"
                  onClick={() => fileInputRef.current?.click()}
                  disabled={isLoading || voicePhase !== 'idle'}
                >
                  <Upload className="mr-2 h-4 w-4" />
                  Upload
                </Button>
                {error && (
                  <Button type="button" variant="ghost" size="sm" className="text-amber-700" onClick={retryLastMessage}>
                    Retry
                  </Button>
                )}
                <Button type="button" variant="ghost" size="sm" className="text-zinc-600" onClick={clearChat}>
                  <Trash className="mr-2 h-4 w-4" />
                  Clear
                </Button>
              </div>
            </div>

            {uploadedFiles.length > 0 && (
              <div className="border-b border-zinc-200/80 bg-zinc-50 px-5 py-2.5">
                <div className="mx-auto flex max-w-3xl flex-wrap gap-2">
                  {uploadedFiles.map((file) => (
                    <div
                      key={file.id}
                      className="flex items-center gap-2 rounded-lg border border-zinc-200/80 bg-white px-2.5 py-1.5"
                    >
                      <FileText className="h-3.5 w-3.5 text-zinc-500" />
                      <span className="max-w-[10rem] truncate text-xs font-medium text-zinc-800">{file.name}</span>
                      <span className="text-[10px] text-zinc-400">{file.size}</span>
                      {file.uploading && <Loader2 className="h-3.5 w-3.5 animate-spin text-zinc-400" />}
                      {file.uploaded && <CheckCircle className="h-3.5 w-3.5 text-emerald-600" />}
                      <button
                        type="button"
                        onClick={() => removeFile(file.id)}
                        className="text-zinc-400 hover:text-red-600"
                        disabled={file.uploading}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    </div>
                  ))}
                </div>
              </div>
            )}

            <div className="custom-scrollbar min-h-0 flex-1 overflow-y-auto px-4 py-5">
              <div className="mx-auto max-w-3xl space-y-5">
                {messages.map((msg) => (
                  <div
                    key={msg.id}
                    className={`flex ${
                      msg.sender === 'user' ? 'justify-end' : msg.sender === 'system' ? 'justify-center' : 'justify-start'
                    }`}
                  >
                    <div
                      className={`max-w-[85%] rounded-2xl px-4 py-2.5 ${
                        msg.sender === 'user'
                          ? 'rounded-br-md bg-zinc-800 text-zinc-50'
                          : msg.sender === 'system'
                            ? 'rounded-lg border border-amber-200/80 bg-amber-50 text-amber-950'
                            : 'rounded-bl-md border border-zinc-200/80 bg-zinc-50/80 text-zinc-800 shadow-sm'
                      }`}
                    >
                      <p className="whitespace-pre-wrap text-[15px] leading-relaxed">{msg.content}</p>
                      <p
                        className={`mt-1.5 text-[11px] tabular-nums ${
                          msg.sender === 'user' ? 'text-zinc-400' : msg.sender === 'system' ? 'text-amber-700/80' : 'text-zinc-400'
                        }`}
                      >
                        {msg.time}
                      </p>
                    </div>
                  </div>
                ))}

                {isTyping && (
                  <div className="flex justify-start">
                    <div className="flex items-center gap-2 rounded-2xl rounded-bl-md border border-zinc-200/80 bg-white px-4 py-2.5 text-sm text-zinc-500">
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-zinc-400" />
                      <span>Typing…</span>
                    </div>
                  </div>
                )}

                {isLoading && !isTyping && (
                  <div className="flex justify-start">
                    <div className="flex items-center gap-2 rounded-2xl rounded-bl-md border border-zinc-200/80 bg-white px-4 py-2.5 text-sm text-zinc-500">
                      <Loader2 className="h-4 w-4 shrink-0 animate-spin text-zinc-400" />
                      <span>Working…</span>
                    </div>
                  </div>
                )}

                <div ref={messagesEndRef} />
              </div>
            </div>

            {isDragging && (
              <div
                className="absolute inset-0 z-10 flex items-center justify-center border-4 border-dashed border-zinc-400 bg-zinc-900/10 backdrop-blur-[1px]"
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
              >
                <div className="text-center text-zinc-800">
                  <Upload className="mx-auto mb-2 h-10 w-10 text-zinc-600" />
                  <p className="text-sm font-medium">Drop PDF files here</p>
                </div>
              </div>
            )}

            <div
              className="border-t border-zinc-200/80 bg-zinc-50/90 px-4 py-3"
              onDragOver={handleDragOver}
              onDragLeave={handleDragLeave}
              onDrop={handleDrop}
            >
              <div className="mx-auto max-w-3xl">
                <div className="flex items-end gap-2">
                  <VoiceOrb state={voiceHudMode} disabled={voiceOrbDisabled} onClick={handleVoiceOrbPress} />
                  <div className="min-w-0 flex-1">
                    <textarea
                      ref={textareaRef}
                      value={message}
                      onChange={(e) => setMessage(e.target.value)}
                      onKeyPress={handleKeyPress}
                      placeholder={
                        uploadedFiles.filter((f) => f.uploaded).length > 0
                          ? 'Ask about your documents…'
                          : 'Upload a PDF, then ask questions…'
                      }
                      disabled={isLoading || voicePhase !== 'idle'}
                      rows={1}
                      className="min-h-[48px] w-full resize-none rounded-xl border border-zinc-200 bg-white px-4 py-3 text-[15px] text-zinc-900 placeholder:text-zinc-400 focus:border-zinc-300 focus:outline-none focus:ring-2 focus:ring-zinc-200/80 max-h-[120px] disabled:opacity-50"
                      style={{ minHeight: '48px', maxHeight: '120px' }}
                    />
                  </div>
                  <Button
                    type="button"
                    onClick={handleSendMessage}
                    disabled={!message.trim() || isLoading || voicePhase !== 'idle'}
                    className="h-12 w-12 shrink-0 rounded-xl border border-zinc-200 bg-zinc-900 text-white hover:bg-zinc-800 disabled:opacity-40"
                  >
                    {isLoading ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
                  </Button>
                </div>
                {voiceError && <p className="mt-2 text-xs text-red-600">{voiceError}</p>}
                {!voiceSupported && (
                  <p className="mt-2 text-xs text-zinc-500">Voice input is not available in this browser.</p>
                )}
                {isListening && (
                  <p className="mt-2 text-xs text-zinc-500">Tap the microphone again to stop and send.</p>
                )}
              </div>
            </div>

            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              multiple
              className="hidden"
              onChange={(e) => handleFileUpload(e.target.files)}
            />
          </div>
        </main>
      </div>
    </div>
  );
}