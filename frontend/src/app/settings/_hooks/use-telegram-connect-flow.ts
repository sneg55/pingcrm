"use client";

import { useState } from "react";
import { client } from "@/lib/api-client";
import type { SyncState } from "./use-settings-controller";

/* ═══════════════════════════════════════════════════════════ */
/*  Types                                                       */
/* ═══════════════════════════════════════════════════════════ */

export type TelegramStep = "phone" | "code" | "password" | "done";

export type UseTelegramConnectFlowProps = {
  telegramConnect: SyncState;
  setTelegramConnect: (s: SyncState) => void;
  showTelegramModal: boolean;
  setShowTelegramModal: (v: boolean) => void;
  onSuccess: (username?: string | null) => Promise<void>;
}

export type UseTelegramConnectFlowReturn = {
  // State
  telegramStep: TelegramStep;
  telegramPhone: string;
  setTelegramPhone: (v: string) => void;
  telegramCode: string;
  setTelegramCode: (v: string) => void;
  telegramPassword: string;
  setTelegramPassword: (v: string) => void;

  // Actions
  handleTelegramConnect: () => void;
  closeTelegramModal: () => void;
  handleTelegramSendCode: () => Promise<void>;
  handleTelegramVerify: () => Promise<void>;
  handleTelegram2FA: () => Promise<void>;
}

export function useTelegramConnectFlow({
  telegramConnect: _telegramConnect,
  setTelegramConnect,
  setShowTelegramModal,
  onSuccess,
}: UseTelegramConnectFlowProps): UseTelegramConnectFlowReturn {
  const [telegramPhone, setTelegramPhone] = useState("");
  const [telegramCode, setTelegramCode] = useState("");
  const [telegramPhoneCodeHash, setTelegramPhoneCodeHash] = useState("");
  const [telegramPassword, setTelegramPassword] = useState("");
  const [telegramStep, setTelegramStep] = useState<TelegramStep>("phone");

  const closeTelegramModal = () => {
    setShowTelegramModal(false);
    setTelegramStep("phone");
    setTelegramPhone("");
    setTelegramCode("");
    setTelegramPassword("");
    setTelegramPhoneCodeHash("");
    setTelegramConnect({ status: "idle", message: "" });
  };

  const handleTelegramConnect = () => {
    setShowTelegramModal(true);
    setTelegramStep("phone");
    setTelegramConnect({ status: "idle", message: "" });
  };

  const handleTelegramSendCode = async () => {
    setTelegramConnect({ status: "loading", message: "" });
    const { data, error } = await client.POST("/api/v1/auth/telegram/connect", {
      body: { phone: telegramPhone },
    });
    if (error) {
      setTelegramConnect({
        status: "error",
        message: (error as { detail?: string })?.detail ?? "Failed to send code.",
      });
    } else {
      setTelegramPhoneCodeHash(
        (data?.data as { phone_code_hash?: string })?.phone_code_hash ?? ""
      );
      setTelegramStep("code");
      setTelegramConnect({ status: "idle", message: "Code sent to your Telegram app" });
    }
  };

  const handleTelegramVerify = async () => {
    setTelegramConnect({ status: "loading", message: "" });
    const { data, error } = await client.POST("/api/v1/auth/telegram/verify", {
      body: {
        phone: telegramPhone,
        code: telegramCode,
        phone_code_hash: telegramPhoneCodeHash,
      },
    });
    if (error) {
      setTelegramConnect({
        status: "error",
        message: (error as { detail?: string })?.detail ?? "Invalid code.",
      });
      return;
    }
    const respData = data?.data as { requires_2fa?: boolean; username?: string } | undefined;
    if (respData?.requires_2fa) {
      setTelegramStep("password");
      setTelegramConnect({
        status: "idle",
        message: "Two-step verification is enabled. Enter your Telegram password.",
      });
      return;
    }
    setTelegramStep("done");
    setTelegramCode("");
    closeTelegramModal();
    setTelegramConnect({ status: "success", message: "" });
    await onSuccess(respData?.username);
  };

  const handleTelegram2FA = async () => {
    setTelegramConnect({ status: "loading", message: "" });
    const { data, error } = await client.POST("/api/v1/auth/telegram/verify-2fa", {
      body: { password: telegramPassword },
    });
    if (error) {
      setTelegramPassword("");
      setTelegramConnect({
        status: "error",
        message: (error as { detail?: string })?.detail ?? "Incorrect password.",
      });
      return;
    }
    setTelegramStep("done");
    setTelegramPassword("");
    closeTelegramModal();
    setTelegramConnect({ status: "success", message: "" });
    await onSuccess((data?.data as { username?: string })?.username);
  };

  return {
    telegramStep,
    telegramPhone,
    setTelegramPhone,
    telegramCode,
    setTelegramCode,
    telegramPassword,
    setTelegramPassword,
    handleTelegramConnect,
    closeTelegramModal,
    handleTelegramSendCode,
    handleTelegramVerify,
    handleTelegram2FA,
  };
}
