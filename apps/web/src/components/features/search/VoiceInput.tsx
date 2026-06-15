"use client";

import React, { useState, useRef } from "react";
import { Mic, Square, Loader2, AlertCircle } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useSession } from "next-auth/react";
import { env } from "@/env";

// Define SpeechRecognition types to avoid TypeScript compilation errors
const SpeechRecognitionAPI =
  typeof window !== "undefined"
    ? (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
    : null;

interface VoiceInputProps {
  onTranscript: (text: string) => void;
  disabled?: boolean;
}

export default function VoiceInput({ onTranscript, disabled }: VoiceInputProps) {
  const { data: session } = useSession();
  const [isRecording, setIsRecording] = useState(false);
  const [isTranscribing, setIsTranscribing] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const audioChunksRef = useRef<Blob[]>([]);
  const recognitionRef = useRef<any>(null);

  const startRecording = async () => {
    setError(null);
    audioChunksRef.current = [];

    try {
      // Request microphone stream first to trigger permission dialog and ensure device availability
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });

      if (SpeechRecognitionAPI) {
        try {
          const recognition = new SpeechRecognitionAPI();
          recognition.continuous = false;
          recognition.interimResults = false;
          recognition.lang = "en-US";

          recognition.onstart = () => {
            setIsRecording(true);
          };

          recognition.onresult = (event: any) => {
            const text = event.results[0][0].transcript;
            if (text) {
              onTranscript(text);
            }
          };

          recognition.onerror = async (event: any) => {
            console.warn("Speech recognition error, falling back to MediaRecorder...", event.error);
            // On speech recognition failure (e.g. Chrome cloud service blocked), fall back to recording & Whisper API
            recognition.onend = null; // Prevent double handling
            recognitionRef.current = null;
            await startMediaRecorderWithStream(stream);
          };

          recognition.onend = () => {
            setIsRecording(false);
            recognitionRef.current = null;
            stream.getTracks().forEach((track) => track.stop());
          };

          recognitionRef.current = recognition;
          recognition.start();
        } catch (err) {
          console.error("Failed to start SpeechRecognition, falling back...", err);
          await startMediaRecorderWithStream(stream);
        }
      } else {
        // Fallback to MediaRecorder & Backend Transcription API
        await startMediaRecorderWithStream(stream);
      }
    } catch (err) {
      console.error("Failed to get microphone stream", err);
      setError("Microphone access denied or unsupported.");
    }
  };

  const startMediaRecorderWithStream = async (stream: MediaStream) => {
    try {
      const mediaRecorder = new MediaRecorder(stream, { mimeType: "audio/webm" });
      mediaRecorderRef.current = mediaRecorder;
      
      mediaRecorder.ondataavailable = (event) => {
        if (event.data.size > 0) {
          audioChunksRef.current.push(event.data);
        }
      };

      mediaRecorder.onstop = async () => {
        const audioBlob = new Blob(audioChunksRef.current, { type: "audio/webm" });
        await uploadAndTranscribe(audioBlob);
        
        // Stop all tracks to release microphone
        stream.getTracks().forEach((track) => track.stop());
      };

      mediaRecorder.start(200);
      setIsRecording(true);
      setError(null); // Clear any transient speech recognition errors
    } catch (err) {
      console.error("Failed to initialize MediaRecorder", err);
      setError("Audio recording failed.");
      stream.getTracks().forEach((track) => track.stop());
    }
  };

  const stopRecording = () => {
    if (recognitionRef.current) {
      recognitionRef.current.stop();
      setIsRecording(false);
    } else if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
    }
  };

  const uploadAndTranscribe = async (audioBlob: Blob) => {
    setIsTranscribing(true);
    setError(null);

    try {
      const formData = new FormData();
      formData.append("file", audioBlob, "recording.webm");

      // Pass mock-token or session token for auth
      const token = session?.accessToken || "mock-token";
      
      const response = await fetch(
        `${env.NEXT_PUBLIC_API_URL}/api/v1/chat/transcribe?token=${token}`,
        {
          method: "POST",
          headers: {
            "X-Tenant-ID": "22222222-2222-2222-2222-222222222222",
          },
          body: formData,
        }
      );

      if (!response.ok) {
        throw new Error(`Server returned status ${response.status}`);
      }

      const data = await response.json();
      if (data.text) {
        onTranscript(data.text);
      }
    } catch (err) {
      console.error("Transcription failed", err);
      setError("Failed to transcribe audio.");
    } finally {
      setIsTranscribing(false);
    }
  };


  return (
    <div className="flex items-center gap-2 shrink-0">
      {isRecording ? (
        <Button
          type="button"
          variant="destructive"
          size="icon"
          className="h-9 w-9 shrink-0 animate-pulse rounded-xl shadow-[0_0_15px_rgba(239,68,68,0.4)] cursor-pointer"
          onClick={stopRecording}
          disabled={disabled}
        >
          <Square className="h-3.5 w-3.5" />
        </Button>
      ) : isTranscribing ? (
        <Button
          type="button"
          variant="secondary"
          size="icon"
          className="h-9 w-9 shrink-0 rounded-xl cursor-not-allowed"
          disabled
        >
          <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
        </Button>
      ) : (
        <Button
          type="button"
          variant="outline"
          size="icon"
          className="h-9 w-9 shrink-0 rounded-xl border-border hover:border-primary/50 text-muted-foreground hover:text-primary transition-all cursor-pointer"
          onClick={startRecording}
          disabled={disabled || isTranscribing}
        >
          <Mic className="h-3.5 w-3.5" />
        </Button>
      )}

      {/* Visual active waves */}
      {isRecording && (
        <div className="flex items-center gap-0.5 px-2">
          <span className="h-3 w-0.5 bg-destructive animate-bounce" style={{ animationDelay: "0ms" }} />
          <span className="h-4.5 w-0.5 bg-destructive animate-bounce" style={{ animationDelay: "150ms" }} />
          <span className="h-3.5 w-0.5 bg-destructive animate-bounce" style={{ animationDelay: "300ms" }} />
          <span className="h-5 w-0.5 bg-destructive animate-bounce" style={{ animationDelay: "450ms" }} />
          <span className="h-3 w-0.5 bg-destructive animate-bounce" style={{ animationDelay: "600ms" }} />
          <span className="text-[10px] text-destructive font-bold ml-1 uppercase tracking-widest">Rec</span>
        </div>
      )}

      {error && (
        <div className="flex items-center gap-1 text-[10px] text-destructive font-semibold">
          <AlertCircle className="h-3.5 w-3.5" />
          <span>{error}</span>
        </div>
      )}
    </div>
  );
}
