"use client";

import { useState, useEffect } from "react";
import { RefreshCw, Save, AlertCircle, Check } from "lucide-react";
import { cn } from "@/lib/utils";
import { client } from "@/lib/api-client";
import { Toggle } from "./shared";

interface PrioritySettings {
  high: number;
  medium: number;
  low: number;
}

export function FollowUpRulesTab() {
  const [settings, setSettings] = useState<PrioritySettings>({ high: 7, medium: 30, low: 90 });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [feedback, setFeedback] = useState<{
    type: "success" | "error";
    message: string;
  } | null>(null);

  // Suggestion preferences — persisted via /api/v1/settings/suggestions
  const [maxBatch, setMaxBatch] = useState("10");
  const [dormantRevival, setDormantRevival] = useState(true);
  const [birthdayReminders, setBirthdayReminders] = useState(true);
  const [preferredChannel, setPreferredChannel] = useState("auto");

  // Load suggestion prefs
  useEffect(() => {
    (async () => {
      try {
        const { data } = await client.GET("/api/v1/settings/suggestions", {});
        const prefs = (data as any)?.data;
        if (prefs) {
          setMaxBatch(String(prefs.max_suggestions ?? 10));
          setDormantRevival(prefs.include_dormant ?? true);
          setBirthdayReminders(prefs.birthday_reminders ?? true);
          setPreferredChannel(prefs.preferred_channel ?? "auto");
        }
      } catch {}
    })();
  }, []);

  const saveSuggestionPref = async (updates: Record<string, unknown>) => {
    try {
      await client.PUT("/api/v1/settings/suggestions", { body: updates });
    } catch {}
  };

  useEffect(() => {
    (async () => {
      try {
        const { data } = await client.GET("/api/v1/settings/priority", {});
        const ps = (data as any)?.data;
        if (ps) setSettings({ high: ps.high, medium: ps.medium, low: ps.low });
      } catch {
        // use defaults
      } finally {
        setIsLoading(false);
      }
    })();
  }, []);

  const handleSave = async () => {
    setIsSaving(true);
    setFeedback(null);
    try {
      const { data, error } = await client.PUT("/api/v1/settings/priority", {
        body: settings,
      });
      if (error) {
        setFeedback({
          type: "error",
          message: (error as any)?.detail ?? "Failed to save",
        });
      } else {
        const ps = (data as any)?.data;
        if (ps) setSettings({ high: ps.high, medium: ps.medium, low: ps.low });
        setFeedback({ type: "success", message: "Priority settings saved" });
      }
    } catch {
      setFeedback({ type: "error", message: "Failed to save" });
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex items-center gap-2 text-sm text-stone-400 dark:text-stone-500 mt-8 justify-center">
        <RefreshCw className="w-4 h-4 animate-spin" />
        Loading settings...
      </div>
    );
  }

  const THRESHOLD_MIN = 7;
  const THRESHOLD_MAX = 365;

  const validationErrors: Partial<Record<keyof PrioritySettings, string>> = {};
  for (const key of ["high", "medium", "low"] as const) {
    if (settings[key] < THRESHOLD_MIN) {
      validationErrors[key] = "Minimum 7 days";
    }
  }
  const hasValidationErrors = Object.keys(validationErrors).length > 0;

  const levels: {
    key: keyof PrioritySettings;
    label: string;
    color: string;
    min: number;
    max: number;
  }[] = [
    { key: "high", label: "High priority", color: "bg-red-500", min: THRESHOLD_MIN, max: 30 },
    { key: "medium", label: "Medium priority", color: "bg-amber-500", min: THRESHOLD_MIN, max: 90 },
    { key: "low", label: "Low priority", color: "bg-blue-500", min: THRESHOLD_MIN, max: THRESHOLD_MAX },
  ];

  return (
    <div className="space-y-6">
      {/* Priority thresholds */}
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5">
        <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 mb-1">Priority Thresholds</h3>
        <p className="text-xs text-stone-500 dark:text-stone-400 mb-5">
          How many days of silence before a follow-up is suggested, based on priority level.
        </p>

        <div className="space-y-6">
          {levels.map(({ key, label, color, min, max }) => (
            <div key={key}>
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className={cn("w-2.5 h-2.5 rounded-full", color)} />
                  <span className="text-sm font-medium text-stone-700 dark:text-stone-300">{label}</span>
                </div>
                <div className="flex items-center gap-1.5">
                  <span className="font-mono text-sm font-medium text-stone-900 dark:text-stone-100 bg-stone-100 dark:bg-stone-800 px-2 py-0.5 rounded">
                    {settings[key]}
                  </span>
                  <span className="text-xs text-stone-400 dark:text-stone-500">days</span>
                </div>
              </div>
              <input
                type="range"
                min={min}
                max={max}
                value={settings[key]}
                onChange={(e) =>
                  setSettings((s) => ({ ...s, [key]: Number(e.target.value) }))
                }
                className="w-full accent-teal-600"
              />
              <div className="flex justify-between mt-1">
                <span className="text-[10px] text-stone-300 dark:text-stone-600">
                  {min} day{min > 1 ? "s" : ""}
                </span>
                <span className="text-[10px] text-stone-300 dark:text-stone-600">{max} days</span>
              </div>
              {validationErrors[key] && (
                <p className="text-[11px] text-red-500 flex items-center gap-1 mt-0.5">
                  <AlertCircle className="w-3 h-3" />
                  {validationErrors[key]}
                </p>
              )}
            </div>
          ))}
        </div>

        <div className="mt-5 pt-4 border-t border-stone-100 dark:border-stone-800 flex items-center justify-end gap-3">
          {feedback && (
            <p
              className={cn(
                "text-xs flex items-center gap-1",
                feedback.type === "error" ? "text-red-500" : "text-emerald-600 dark:text-emerald-400"
              )}
            >
              {feedback.type === "error" ? (
                <AlertCircle className="w-3 h-3" />
              ) : (
                <Check className="w-3 h-3" />
              )}
              {feedback.message}
            </p>
          )}
          <button
            onClick={() => void handleSave()}
            disabled={isSaving || hasValidationErrors}
            className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-medium rounded-lg bg-teal-600 text-white hover:bg-teal-700 transition-colors shadow-sm disabled:opacity-50"
          >
            {isSaving ? (
              <RefreshCw className="w-3.5 h-3.5 animate-spin" />
            ) : (
              <Save className="w-3.5 h-3.5" />
            )}
            Save thresholds
          </button>
        </div>
      </div>

      {/* Suggestion preferences */}
      <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5">
        <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100 mb-1">Suggestion Preferences</h3>
        <p className="text-xs text-stone-500 dark:text-stone-400 mb-5">
          Control how and when follow-up suggestions are generated.
        </p>

        <div className="space-y-4">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm text-stone-700 dark:text-stone-300">Max suggestions per batch</p>
              <p className="text-xs text-stone-400 dark:text-stone-500">How many suggestions to generate at once</p>
            </div>
            <select
              value={maxBatch}
              onChange={(e) => { setMaxBatch(e.target.value); void saveSuggestionPref({ max_suggestions: parseInt(e.target.value) }); }}
              className="w-full sm:w-auto text-sm border border-stone-200 dark:border-stone-700 rounded-lg px-3 py-1.5 text-stone-700 dark:text-stone-300 bg-white dark:bg-stone-900 focus:outline-none focus:ring-2 focus:ring-teal-400"
            >
              <option value="5">5</option>
              <option value="10">10</option>
              <option value="15">15</option>
              <option value="20">20</option>
            </select>
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-stone-700 dark:text-stone-300">Include dormant revival (Pool B)</p>
              <p className="text-xs text-stone-400 dark:text-stone-500">
                Suggest re-engaging contacts you haven&apos;t spoken to in a while
              </p>
            </div>
            <Toggle checked={dormantRevival} onChange={(v) => { setDormantRevival(v); void saveSuggestionPref({ include_dormant: v }); }} />
          </div>

          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm text-stone-700 dark:text-stone-300">Birthday reminders</p>
              <p className="text-xs text-stone-400 dark:text-stone-500">
                Generate suggestions for upcoming birthdays
              </p>
            </div>
            <Toggle checked={birthdayReminders} onChange={(v) => { setBirthdayReminders(v); void saveSuggestionPref({ birthday_reminders: v }); }} />
          </div>

          <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
            <div>
              <p className="text-sm text-stone-700 dark:text-stone-300">Preferred channel</p>
              <p className="text-xs text-stone-400 dark:text-stone-500">Default channel for new suggestions</p>
            </div>
            <select
              value={preferredChannel}
              onChange={(e) => { setPreferredChannel(e.target.value); void saveSuggestionPref({ preferred_channel: e.target.value }); }}
              className="w-full sm:w-auto text-sm border border-stone-200 dark:border-stone-700 rounded-lg px-3 py-1.5 text-stone-700 dark:text-stone-300 bg-white dark:bg-stone-900 focus:outline-none focus:ring-2 focus:ring-teal-400"
            >
              <option value="auto">Auto-detect</option>
              <option value="email">Email</option>
              <option value="telegram">Telegram</option>
              <option value="twitter">Twitter</option>
            </select>
          </div>
        </div>
      </div>
    </div>
  );
}
