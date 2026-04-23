/**
 * Round-trip a message to the PingCRM Chrome extension.
 * Resolves to the response if the extension replies within `timeoutMs`,
 * otherwise resolves to null (extension not installed or not responding).
 */

// eslint-disable-next-line no-restricted-properties -- public env var read at module boundary; required to reach the Chrome extension by ID
const EXTENSION_ID = process.env.NEXT_PUBLIC_EXTENSION_ID ?? '';

type ChromeSendMessage = (
  extensionId: string,
  message: unknown,
  responseCallback: (response: unknown) => void,
) => void;

type ChromeRuntime = {
  sendMessage?: ChromeSendMessage;
  lastError?: unknown;
};

export async function sendToExtension<T = unknown>(
  message: Record<string, unknown>,
  timeoutMs = 500,
): Promise<T | null> {
  if (typeof window === 'undefined') return null;
  const chromeRuntime = (window as unknown as { chrome?: { runtime?: ChromeRuntime } }).chrome
    ?.runtime;
  const sendMessage = chromeRuntime?.sendMessage;
  if (!sendMessage || !EXTENSION_ID) return null;

  return await new Promise<T | null>((resolve) => {
    const timer = window.setTimeout(() => resolve(null), timeoutMs);
    try {
      sendMessage(EXTENSION_ID, message, (resp: unknown) => {
        window.clearTimeout(timer);
        if (chromeRuntime.lastError) {
          resolve(null);
          return;
        }
        resolve((resp as T | undefined) ?? null);
      });
    } catch {
      window.clearTimeout(timer);
      resolve(null);
    }
  });
}
