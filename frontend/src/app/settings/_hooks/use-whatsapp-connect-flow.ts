"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { client } from "@/lib/api-client";
import type { SyncState } from "./use-settings-controller";

export type WhatsAppStep = "idle" | "qr_pending" | "connected" | "error";

export interface UseWhatsAppConnectFlowProps {
  whatsappConnect: SyncState;
  setWhatsappConnect: (s: SyncState) => void;
  onSuccess: () => Promise<void>;
}

export interface UseWhatsAppConnectFlowReturn {
  step: WhatsAppStep;
  qrData: string | null;
  error: string | null;
  startConnect: () => Promise<void>;
  cancel: () => void;
}

export function useWhatsAppConnectFlow({
  whatsappConnect,
  setWhatsappConnect,
  onSuccess,
}: UseWhatsAppConnectFlowProps): UseWhatsAppConnectFlowReturn {
  const [step, setStep] = useState<WhatsAppStep>("idle");
  const [qrData, setQrData] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const startConnect = useCallback(async () => {
    setStep("qr_pending");
    setError(null);
    setWhatsappConnect({ status: "loading", message: "Starting WhatsApp session..." });

    const { data, error: err } = await client.POST("/api/v1/auth/whatsapp/connect", {});
    if (err) {
      setStep("error");
      const detail = (err as { detail?: string })?.detail;
      setError(detail || "Failed to start WhatsApp session. The service may not be available yet.");
      setWhatsappConnect({ status: "error", message: "Connection failed" });
      return;
    }

    const result = data?.data;
    if (result?.qr) {
      setQrData(result.qr);
    }
    setWhatsappConnect({ status: "idle", message: "Scan QR code with your phone" });

    pollRef.current = setInterval(async () => {
      const { data: statusData } = await client.GET("/api/v1/auth/whatsapp/qr", {});
      const s = statusData?.data;
      if (s?.qr) setQrData(s.qr);
      if (s?.status === "connected") {
        stopPolling();
        setStep("connected");
        setWhatsappConnect({ status: "success", message: "WhatsApp connected!" });
        await onSuccess();
      }
    }, 3000);
  }, [setWhatsappConnect, onSuccess, stopPolling]);

  const cancel = useCallback(() => {
    stopPolling();
    setStep("idle");
    setQrData(null);
    setError(null);
    setWhatsappConnect({ status: "idle", message: "" });
  }, [stopPolling, setWhatsappConnect]);

  useEffect(() => () => stopPolling(), [stopPolling]);

  // suppress unused variable warning — whatsappConnect is a prop kept for API symmetry
  void whatsappConnect;

  return { step, qrData, error, startConnect, cancel };
}
