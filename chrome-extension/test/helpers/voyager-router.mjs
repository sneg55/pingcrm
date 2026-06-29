/**
 * Maps an executeScript Voyager call to a canned fixture, mimicking what the
 * in-page fetch would have returned. This is the seam that lets the whole sync
 * pipeline run without a browser or a real LinkedIn session.
 *
 * The default fixtures live in test/fixtures/voyager/. Capture real ones from a
 * live session with `node test/capture-and-e2e.mjs --capture` (see README).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const FIX = path.resolve(HERE, "../fixtures/voyager");

const read = (name) => JSON.parse(fs.readFileSync(path.join(FIX, name), "utf8"));

export function loadFixtures() {
  return {
    me: read("me.json"),
    conversations: read("conversations.page1.json"),
    conversationsEmpty: { data: { messengerConversationsBySyncToken: { elements: [] } } },
    messagesConv1: read("messages.conv1.json"),
    messagesConv2: read("messages.conv2.json"),
    profile: read("profile.json"),
  };
}

const ok = (data) => ({ ok: true, status: 200, data });

/**
 * Build an executeScript router over a fixture set.
 * @param {ReturnType<typeof loadFixtures>} [fixtures]
 */
export function makeVoyagerRouter(fixtures = loadFixtures()) {
  return async (args) => {
    // Image fetch path: func(imgUrl, maxBytes) — args[1] is a number.
    if (args.length === 2 && typeof args[1] === "number") {
      return { ok: true, dataUrl: "data:image/jpeg;base64,/9j/stub", via: "stub" };
    }

    const url = String(args[0] ?? "");

    if (url.includes("/voyager/api/me")) return ok(fixtures.me);

    if (url.includes("voyagerMessagingGraphQL")) {
      const rawVars = url.split("variables=")[1] ?? "";
      const variables = decodeURIComponent(rawVars);

      if (url.includes("messengerConversations")) {
        return ok(variables.includes("lastUpdatedBefore") ? fixtures.conversationsEmpty : fixtures.conversations);
      }
      if (url.includes("messengerMessages")) {
        const convUrn = variables.match(/conversationUrn:([^,)]+)/)?.[1] ?? "";
        if (convUrn.includes("CONV1")) return ok(fixtures.messagesConv1);
        if (convUrn.includes("CONV2")) return ok(fixtures.messagesConv2);
        return ok({ data: { messengerMessagesByConversation: { elements: [] } } });
      }
    }

    if (url.includes("/identity/dash/profiles")) return ok(fixtures.profile);

    return { ok: false, status: 404, body: "NO_FIXTURE: " + url };
  };
}
