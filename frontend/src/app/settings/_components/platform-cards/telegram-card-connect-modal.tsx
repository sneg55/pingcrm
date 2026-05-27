"use client";

import { X, Check, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import type { SyncState } from "../../_hooks/use-settings-controller";
import type { UseTelegramConnectFlowReturn } from "../../_hooks/use-telegram-connect-flow";

type TelegramConnectModalProps = {
  telegramConnect: SyncState;
  telegramFlow: UseTelegramConnectFlowReturn;
};

function PhoneStep({
  telegramPhone,
  setTelegramPhone,
  telegramConnect,
  closeTelegramModal,
  handleTelegramSendCode,
}: {
  telegramPhone: string;
  setTelegramPhone: (v: string) => void;
  telegramConnect: SyncState;
  closeTelegramModal: () => void;
  handleTelegramSendCode: () => Promise<void>;
}) {
  return (
    <>
      <label
        htmlFor="telegram-phone"
        className="block text-sm font-medium text-stone-700 dark:text-stone-300 mb-1"
      >
        Phone number
      </label>
      <input
        id="telegram-phone"
        type="tel"
        value={telegramPhone}
        onChange={(e) => setTelegramPhone(e.target.value)}
        placeholder="+1234567890"
        className="w-full px-3 py-2 rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-teal-400"
      />
      <div className="flex gap-2">
        <button
          onClick={closeTelegramModal}
          className="flex-1 px-3 py-2 text-sm rounded-lg border border-stone-300 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
        >
          Cancel
        </button>
        <button
          onClick={() => void handleTelegramSendCode()}
          disabled={!telegramPhone.trim() || telegramConnect.status === "loading"}
          className="flex-1 px-3 py-2 text-sm rounded-lg bg-teal-600 text-white font-medium hover:bg-teal-700 disabled:opacity-50"
        >
          {telegramConnect.status === "loading" ? "Sending..." : "Send code"}
        </button>
      </div>
    </>
  );
}

function CodeStep({
  telegramCode,
  setTelegramCode,
  telegramConnect,
  closeTelegramModal,
  handleTelegramVerify,
}: {
  telegramCode: string;
  setTelegramCode: (v: string) => void;
  telegramConnect: SyncState;
  closeTelegramModal: () => void;
  handleTelegramVerify: () => Promise<void>;
}) {
  return (
    <>
      <label
        htmlFor="telegram-code"
        className="block text-sm text-stone-500 dark:text-stone-400 mb-3"
      >
        Enter the code sent to your Telegram app.
      </label>
      <input
        id="telegram-code"
        type="text"
        value={telegramCode}
        onChange={(e) => setTelegramCode(e.target.value)}
        placeholder="12345"
        className="w-full px-3 py-2 rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-teal-400"
      />
      <div className="flex gap-2">
        <button
          onClick={closeTelegramModal}
          className="flex-1 px-3 py-2 text-sm rounded-lg border border-stone-300 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
        >
          Cancel
        </button>
        <button
          onClick={() => void handleTelegramVerify()}
          disabled={!telegramCode.trim() || telegramConnect.status === "loading"}
          className="flex-1 px-3 py-2 text-sm rounded-lg bg-teal-600 text-white font-medium hover:bg-teal-700 disabled:opacity-50"
        >
          {telegramConnect.status === "loading" ? "Verifying..." : "Verify"}
        </button>
      </div>
    </>
  );
}

function PasswordStep({
  telegramPassword,
  setTelegramPassword,
  telegramConnect,
  closeTelegramModal,
  handleTelegram2FA,
}: {
  telegramPassword: string;
  setTelegramPassword: (v: string) => void;
  telegramConnect: SyncState;
  closeTelegramModal: () => void;
  handleTelegram2FA: () => Promise<void>;
}) {
  return (
    <>
      <label
        htmlFor="telegram-password"
        className="block text-sm text-stone-500 dark:text-stone-400 mb-3"
      >
        Your account has two-step verification. Enter your Telegram password.
      </label>
      <input
        id="telegram-password"
        type="password"
        value={telegramPassword}
        onChange={(e) => setTelegramPassword(e.target.value)}
        placeholder="Telegram password"
        className="w-full px-3 py-2 rounded-lg border border-stone-300 dark:border-stone-700 bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100 text-sm mb-4 focus:outline-none focus:ring-2 focus:ring-teal-400"
      />
      <div className="flex gap-2">
        <button
          onClick={closeTelegramModal}
          className="flex-1 px-3 py-2 text-sm rounded-lg border border-stone-300 dark:border-stone-700 text-stone-600 dark:text-stone-300 hover:bg-stone-50 dark:hover:bg-stone-800"
        >
          Cancel
        </button>
        <button
          onClick={() => void handleTelegram2FA()}
          disabled={!telegramPassword.trim() || telegramConnect.status === "loading"}
          className="flex-1 px-3 py-2 text-sm rounded-lg bg-teal-600 text-white font-medium hover:bg-teal-700 disabled:opacity-50"
        >
          {telegramConnect.status === "loading" ? "Verifying..." : "Submit"}
        </button>
      </div>
    </>
  );
}

export function TelegramConnectModal({
  telegramConnect,
  telegramFlow,
}: TelegramConnectModalProps) {
  const {
    telegramStep,
    telegramPhone,
    setTelegramPhone,
    telegramCode,
    setTelegramCode,
    telegramPassword,
    setTelegramPassword,
    closeTelegramModal,
    handleTelegramSendCode,
    handleTelegramVerify,
    handleTelegram2FA,
  } = telegramFlow;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="bg-white dark:bg-stone-900 rounded-xl p-6 w-full max-w-sm shadow-xl">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold text-stone-900 dark:text-stone-100">Connect Telegram</h3>
          <button
            onClick={closeTelegramModal}
            aria-label="Close"
            className="text-stone-400 dark:text-stone-500 hover:text-stone-600 dark:hover:text-stone-300"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {telegramStep === "phone" && (
          <PhoneStep
            telegramPhone={telegramPhone}
            setTelegramPhone={setTelegramPhone}
            telegramConnect={telegramConnect}
            closeTelegramModal={closeTelegramModal}
            handleTelegramSendCode={handleTelegramSendCode}
          />
        )}

        {telegramStep === "code" && (
          <CodeStep
            telegramCode={telegramCode}
            setTelegramCode={setTelegramCode}
            telegramConnect={telegramConnect}
            closeTelegramModal={closeTelegramModal}
            handleTelegramVerify={handleTelegramVerify}
          />
        )}

        {telegramStep === "password" && (
          <PasswordStep
            telegramPassword={telegramPassword}
            setTelegramPassword={setTelegramPassword}
            telegramConnect={telegramConnect}
            closeTelegramModal={closeTelegramModal}
            handleTelegram2FA={handleTelegram2FA}
          />
        )}

        {telegramConnect.message && (
          <p
            className={cn(
              "text-xs mt-3",
              telegramConnect.status === "error" ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
            )}
          >
            {telegramConnect.message}
          </p>
        )}
      </div>
    </div>
  );
}

export function TelegramConnectStatusMessage({
  telegramConnect,
  showTelegramModal,
}: {
  telegramConnect: SyncState;
  showTelegramModal: boolean;
}) {
  if (!telegramConnect.message || showTelegramModal) return null;
  return (
    <p
      className={cn(
        "text-xs mt-3 flex items-center gap-1",
        telegramConnect.status === "error" ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
      )}
    >
      {telegramConnect.status === "error" ? (
        <AlertCircle className="w-3 h-3" />
      ) : (
        <Check className="w-3 h-3" />
      )}
      {telegramConnect.message}
    </p>
  );
}
