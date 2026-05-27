"use client";

import { format } from "date-fns";
import {
  Calendar,
  Phone,
  Sparkles,
  Video,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  dateSeparatorLabel,
  needsSeparator,
  platformLabel,
} from "../_lib/formatters";
import type { InteractionResponse } from "../_hooks/use-contact-detail-controller";
import { CollapsibleText, NoteItem, platformIconMap } from "./chat-timeline";

// ---------------------------------------------------------------------------
// Per-kind badge components
// ---------------------------------------------------------------------------

function MeetingBadge({ item }: { item: InteractionResponse }) {
  return (
    <div className="flex justify-center py-1">
      <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-stone-50 dark:bg-stone-800 border border-stone-100 dark:border-stone-700">
        <Calendar className="w-3.5 h-3.5 text-teal-500" />
        <span className="text-[11px] text-stone-500 dark:text-stone-400">
          Meeting{item.content_preview ? ` · ${item.content_preview}` : ""}
        </span>
      </div>
    </div>
  );
}

function CallBadge({ item }: { item: InteractionResponse }) {
  const isVideoCall = item.content_preview?.startsWith("Video call") === true;
  const preview = item.content_preview ?? "";
  const label = isVideoCall ? "Video Call" : "Call";
  // Extract duration if present, e.g. "Phone call · 12 min"
  const afterPrefix = isVideoCall
    ? preview.slice("Video call".length)
    : preview.slice("Phone call".length);
  const duration = afterPrefix.replace(/^[\s·\-:]+/, "").trim();
  const displayLabel = duration ? `${label} · ${duration}` : label;

  return (
    <div className="flex justify-center py-1">
      <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-stone-50 dark:bg-stone-800 border border-stone-100 dark:border-stone-700">
        {isVideoCall ? (
          <Video className="w-3.5 h-3.5 text-teal-500" />
        ) : (
          <Phone className="w-3.5 h-3.5 text-teal-500" />
        )}
        <span className="text-[11px] text-stone-500 dark:text-stone-400">
          {displayLabel}
        </span>
      </div>
    </div>
  );
}

function EventBadge({ item }: { item: InteractionResponse }) {
  return (
    <div className="flex justify-center py-1">
      <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full bg-violet-50 border border-violet-100">
        {platformIconMap[item.platform] ?? (
          <Sparkles className="w-3.5 h-3.5 text-violet-500" />
        )}
        <span className="text-[11px] text-violet-600">
          {item.content_preview || "Profile updated"}
        </span>
        <span className="text-[10px] text-stone-400 dark:text-stone-500">
          &middot; {format(new Date(item.occurred_at), "MMM d")}
        </span>
      </div>
    </div>
  );
}

function MessageBubble({
  item,
  isOutbound,
  contactAvatarCls,
  initials,
}: {
  item: InteractionResponse;
  isOutbound: boolean;
  contactAvatarCls: string;
  initials: string;
}) {
  const time = format(new Date(item.occurred_at), "h:mm a");

  if (isOutbound) {
    return (
      <div className="flex items-end gap-2 max-w-[85%] ml-auto flex-row-reverse">
        <div className="w-6 h-6 rounded-full bg-teal-100 dark:bg-teal-900 text-teal-700 dark:text-teal-300 flex items-center justify-center text-[10px] font-semibold shrink-0">
          You
        </div>
        <div>
          <div className="bg-teal-600 text-white rounded-2xl rounded-br-md px-3.5 py-2.5">
            {item.content_preview && (
              <p className="text-[13px] leading-relaxed">
                <CollapsibleText
                  text={item.content_preview}
                  linkClassName="text-teal-100 hover:text-white"
                />
              </p>
            )}
          </div>
          <div className="flex items-center gap-1.5 mt-1 mr-1 justify-end">
            {/* Read receipt indicator — only for outbound telegram messages */}
            {item.platform === "telegram" && item.is_read_by_recipient != null && (
              <span
                className={cn(
                  "text-[10px]",
                  item.is_read_by_recipient
                    ? "text-teal-400 dark:text-teal-500"
                    : "text-stone-300 dark:text-stone-600"
                )}
                aria-label={item.is_read_by_recipient ? "Read by recipient" : "Delivered, not yet read"}
                title={item.is_read_by_recipient ? "Read" : "Delivered"}
              >
                {item.is_read_by_recipient ? "✓✓" : "✓"}
              </span>
            )}
            <span className="text-[10px] text-stone-400 dark:text-stone-500">
              {time} &middot; {platformLabel(item.platform)}
            </span>
            {platformIconMap[item.platform]}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex items-end gap-2 max-w-[85%]">
      <div
        className={cn(
          "w-6 h-6 rounded-full flex items-center justify-center text-[10px] font-semibold shrink-0",
          contactAvatarCls
        )}
      >
        {initials}
      </div>
      <div>
        <div className="bg-stone-100 dark:bg-stone-800 rounded-2xl rounded-bl-md px-3.5 py-2.5">
          {item.content_preview && (
            <p className="text-[13px] text-stone-800 dark:text-stone-200 leading-relaxed">
              <CollapsibleText
                text={item.content_preview}
                linkClassName="text-teal-600 dark:text-teal-400 hover:text-teal-800 dark:hover:text-teal-300"
              />
            </p>
          )}
        </div>
        <div className="flex items-center gap-1.5 mt-1 ml-1">
          {platformIconMap[item.platform]}
          <span className="text-[10px] text-stone-400 dark:text-stone-500">
            {platformLabel(item.platform)} &middot; {time}
          </span>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// TimelineItem — renders one interaction entry (separator + content)
// ---------------------------------------------------------------------------

export function TimelineItem({
  item,
  prevOccurredAt,
  contactId,
  contactAvatarCls,
  initials,
}: {
  item: InteractionResponse;
  prevOccurredAt: string | null;
  contactId: string;
  contactAvatarCls: string;
  initials: string;
}) {
  const showSeparator = needsSeparator(item.occurred_at, prevOccurredAt);
  const isManual = item.platform === "manual";
  const isMeeting = item.platform === "meeting";
  const isCall =
    item.content_preview?.startsWith("Phone call") === true ||
    item.content_preview?.startsWith("Video call") === true;
  const isEvent = item.direction === "event";
  const isOutbound = item.direction === "outbound";

  return (
    <div>
      {/* Date separator */}
      {showSeparator && (
        <div className="flex items-center gap-3 py-2 mt-1">
          <div className="flex-1 h-px bg-stone-100 dark:bg-stone-800" />
          <span className="text-[10px] font-medium text-stone-400 dark:text-stone-500 uppercase tracking-wider">
            {dateSeparatorLabel(item.occurred_at)}
          </span>
          <div className="flex-1 h-px bg-stone-100 dark:bg-stone-800" />
        </div>
      )}

      {/* Note */}
      {isManual && <NoteItem item={item} contactId={contactId} />}

      {/* Meeting event */}
      {isMeeting && <MeetingBadge item={item} />}

      {/* Call event */}
      {isCall && !isMeeting && !isEvent && <CallBadge item={item} />}

      {/* Event (bio change, etc.) */}
      {isEvent && <EventBadge item={item} />}

      {/* Regular message */}
      {!isManual && !isMeeting && !isCall && !isEvent && (
        <MessageBubble
          item={item}
          isOutbound={isOutbound}
          contactAvatarCls={contactAvatarCls}
          initials={initials}
        />
      )}
    </div>
  );
}
