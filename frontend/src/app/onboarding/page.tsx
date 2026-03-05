"use client";

import { useState } from "react";
import Link from "next/link";
import { CsvImport } from "@/components/csv-import";
import { api } from "@/lib/api";

const TOTAL_STEPS = 4;

export default function OnboardingPage() {
  const [step, setStep] = useState(1);
  const [googleSyncing, setGoogleSyncing] = useState(false);
  const [googleResult, setGoogleResult] = useState<{ created: number; updated: number } | null>(null);
  const [syncError, setSyncError] = useState<string | null>(null);

  const goNext = () => setStep((s) => Math.min(s + 1, TOTAL_STEPS));
  const goBack = () => setStep((s) => Math.max(s - 1, 1));

  const handleConnectGoogle = async () => {
    try {
      const { data } = await api.get("/auth/google/url");
      if (data?.data?.url) {
        window.location.href = data.data.url;
      }
    } catch {
      // If no Google OAuth URL endpoint, open the callback flow
      setSyncError("Google OAuth not configured yet. Add GOOGLE_CLIENT_ID to .env");
    }
  };

  const handleGoogleSync = async () => {
    setGoogleSyncing(true);
    setSyncError(null);
    try {
      const { data } = await api.post("/contacts/sync/google");
      setGoogleResult(data?.data ?? null);
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Failed to sync Google Contacts";
      setSyncError(msg);
    } finally {
      setGoogleSyncing(false);
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <div className="w-full max-w-lg">
        {/* Progress dots */}
        <div className="flex items-center justify-center gap-2 mb-8">
          {Array.from({ length: TOTAL_STEPS }, (_, i) => (
            <span
              key={i}
              className={`h-2 rounded-full transition-all duration-300 ${
                i + 1 === step
                  ? "w-6 bg-blue-600"
                  : i + 1 < step
                  ? "w-2 bg-blue-300"
                  : "w-2 bg-gray-300"
              }`}
            />
          ))}
        </div>

        <div className="bg-white rounded-xl border border-gray-200 p-8 shadow-sm min-h-[320px] flex flex-col">
          {step === 1 && (
            <div className="flex flex-col items-center text-center flex-1 justify-center">
              <div className="text-5xl mb-4">👋</div>
              <h1 className="text-2xl font-bold text-gray-900 mb-2">
                Welcome to Ping!
              </h1>
              <p className="text-gray-500 text-sm mb-6 max-w-sm">
                Ping helps you keep track of your professional relationships,
                follow-ups, and interactions — all in one place.
              </p>
              <p className="text-sm text-gray-400 mb-8">
                Let&apos;s take a couple of minutes to set up your account.
              </p>
              <button
                onClick={goNext}
                className="px-6 py-2.5 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
              >
                Get started
              </button>
            </div>
          )}

          {step === 2 && (
            <div className="flex flex-col flex-1">
              <h2 className="text-xl font-bold text-gray-900 mb-1">
                Connect your accounts
              </h2>
              <p className="text-sm text-gray-500 mb-6">
                Connect Google to automatically import your contacts and sync
                interactions.
              </p>

              <button
                onClick={handleConnectGoogle}
                className="flex items-center gap-3 w-full px-4 py-3 rounded-lg border border-gray-300 hover:border-blue-400 hover:bg-blue-50 transition-colors mb-3"
              >
                <svg
                  xmlns="http://www.w3.org/2000/svg"
                  viewBox="0 0 48 48"
                  className="w-5 h-5 flex-shrink-0"
                >
                  <path fill="#4285F4" d="M46.5 24.5c0-1.6-.1-3.1-.4-4.5H24v8.5h12.7c-.6 3-2.3 5.5-4.9 7.2v6h7.9c4.6-4.3 7.8-10.6 7.8-17.2z" />
                  <path fill="#34A853" d="M24 48c6.5 0 11.9-2.1 15.9-5.8l-7.9-6c-2.1 1.4-4.8 2.3-8 2.3-6.1 0-11.3-4.1-13.1-9.7H2.7v6.2C6.7 43.1 14.8 48 24 48z" />
                  <path fill="#FBBC05" d="M10.9 28.8c-.5-1.4-.7-2.9-.7-4.8s.3-3.3.7-4.8v-6.2H2.7C1 16.4 0 20.1 0 24s1 7.6 2.7 11z" />
                  <path fill="#EA4335" d="M24 9.5c3.4 0 6.5 1.2 8.9 3.5l6.6-6.6C35.9 2.4 30.4 0 24 0 14.8 0 6.7 4.9 2.7 13l8.2 6.2C12.7 13.6 17.9 9.5 24 9.5z" />
                </svg>
                <span className="text-sm font-medium text-gray-700">
                  Connect Google account
                </span>
              </button>

              {syncError && (
                <p className="text-xs text-red-500 mb-2">{syncError}</p>
              )}

              <p className="text-xs text-gray-400 mb-auto">
                You can skip this step and connect later from Settings.
              </p>

              <div className="flex justify-between mt-6">
                <button
                  onClick={goBack}
                  className="text-sm text-gray-500 hover:text-gray-700"
                >
                  Back
                </button>
                <button
                  onClick={goNext}
                  className="px-5 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
                >
                  {syncError ? "Skip for now" : "Next"}
                </button>
              </div>
            </div>
          )}

          {step === 3 && (
            <div className="flex flex-col flex-1">
              <h2 className="text-xl font-bold text-gray-900 mb-1">
                Import your contacts
              </h2>
              <p className="text-sm text-gray-500 mb-6">
                Upload a CSV file or sync from Google Contacts to bring your
                existing network into Ping.
              </p>

              <div className="space-y-3 mb-6">
                <CsvImport />

                <div className="text-center text-xs text-gray-400">or</div>

                <button
                  onClick={handleGoogleSync}
                  disabled={googleSyncing}
                  className="w-full flex items-center justify-center gap-2 px-4 py-3 rounded-lg border border-gray-300 text-sm text-gray-600 hover:border-blue-400 hover:bg-blue-50 transition-colors disabled:opacity-50"
                >
                  {googleSyncing ? "Syncing..." : "Sync from Google Contacts"}
                </button>

                {googleResult && (
                  <p className="text-xs text-green-600 text-center">
                    Imported {googleResult.created} new, updated {googleResult.updated} existing contacts.
                  </p>
                )}
                {syncError && (
                  <p className="text-xs text-red-500 text-center">{syncError}</p>
                )}
              </div>

              <div className="flex justify-between mt-auto">
                <button
                  onClick={goBack}
                  className="text-sm text-gray-500 hover:text-gray-700"
                >
                  Back
                </button>
                <button
                  onClick={goNext}
                  className="px-5 py-2 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
                >
                  {googleResult ? "Next" : "Skip for now"}
                </button>
              </div>
            </div>
          )}

          {step === 4 && (
            <div className="flex flex-col items-center text-center flex-1 justify-center">
              <div className="text-5xl mb-4">🎉</div>
              <h2 className="text-2xl font-bold text-gray-900 mb-2">
                You&apos;re all set!
              </h2>
              <p className="text-gray-500 text-sm mb-8 max-w-sm">
                Your Ping account is ready. Head to your dashboard to see your
                contacts and follow-up suggestions.
              </p>
              <Link
                href="/dashboard"
                className="px-6 py-2.5 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 transition-colors"
              >
                Go to Dashboard
              </Link>
            </div>
          )}
        </div>

        <p className="text-center text-xs text-gray-400 mt-4">
          Step {step} of {TOTAL_STEPS}
        </p>
      </div>
    </div>
  );
}
