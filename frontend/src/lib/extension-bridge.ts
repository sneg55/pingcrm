/**
 * Round-trip a message to the PingCRM Chrome extension.
 * Resolves to the response if the extension replies within `timeoutMs`,
 * otherwise resolves to null (extension not installed or not responding).
 */

const EXTENSION_ID = process.env.NEXT_PUBLIC_EXTENSION_ID ?? '';

export async function sendToExtension<T = unknown>(
  message: Record<string, unknown>,
  timeoutMs = 500,
): Promise<T | null> {
  if (typeof window === 'undefined') return null;
  const chromeRuntime = (
    window as unknown as { chrome?: { runtime?: { sendMessage?: Function; lastError?: unknown } } }
  ).chrome?.runtime;
  if (!chromeRuntime?.sendMessage || !EXTENSION_ID) return null;

  return new Promise<T | null>((resolve) => {
    const timer = window.setTimeout(() => resolve(null), timeoutMs);
    try {
      chromeRuntime.sendMessage!(EXTENSION_ID, message, (resp: T) => {
        window.clearTimeout(timer);
        if (chromeRuntime.lastError) {
          resolve(null);
          return;
        }
        resolve(resp ?? null);
      });
    } catch {
      window.clearTimeout(timer);
      resolve(null);
    }
  });
}
