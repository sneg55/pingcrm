"use client";

import { useState, useRef, useEffect } from "react";
import { Building2, Check, Copy, Pencil, Plus, Wand2 } from "lucide-react";
import Link from "next/link";
import { cn } from "@/lib/utils";
import { InlineListField } from "@/components/inline-list-field";
import { CompanyFavicon } from "@/components/company-favicon";
import { client } from "@/lib/api-client";
import { useAuth } from "@/hooks/use-auth";
import { formatDistanceToNow } from "date-fns";
import type { Contact } from "@/hooks/use-contacts";
import { BccAddressRow } from "./bcc-address-row";

/* ── Copy button ── */

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        void navigator.clipboard.writeText(text);
        setCopied(true);
        setTimeout(() => setCopied(false), 1500);
      }}
      className={cn(
        "p-0.5 rounded transition-opacity",
        copied
          ? "text-emerald-500 opacity-100"
          : "text-stone-300 dark:text-stone-600 hover:text-stone-500 dark:hover:text-stone-400 opacity-0 group-hover/row:opacity-100"
      )}
      title="Copy"
    >
      {copied ? <Check className="w-3 h-3" /> : (
        <svg className="w-3 h-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
          <rect x="9" y="9" width="13" height="13" rx="2" ry="2" />
          <path d="M5 15H4a2 2 0 01-2-2V4a2 2 0 012-2h9a2 2 0 012 2v1" />
        </svg>
      )}
    </button>
  );
}

/* ── Inline field ── */

function InlineField({
  label,
  value,
  displayValue,
  onSave,
  copyable,
  isLink,
  linkPrefix,
  internalHref,
}: {
  label: string;
  value: string | null | undefined;
  displayValue?: string;
  onSave: (v: string) => void;
  copyable?: boolean;
  isLink?: boolean;
  linkPrefix?: string;
  internalHref?: string;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  const save = () => {
    if (draft !== (value ?? "")) onSave(draft);
    setEditing(false);
  };

  const cancel = () => {
    setDraft(value ?? "");
    setEditing(false);
  };

  const startEdit = () => {
    setDraft(value ?? "");
    setEditing(true);
  };

  return (
    <div className="group/row flex items-start justify-between gap-4 py-1.5">
      <span className="text-xs text-stone-500 dark:text-stone-400 shrink-0 mt-0.5">{label}</span>
      {editing ? (
        <div className="flex flex-col items-end gap-1.5 min-w-0 flex-1">
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
              if (e.key === "Escape") cancel();
            }}
            className="w-full text-xs border border-stone-300 dark:border-stone-700 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-teal-400 bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100"
          />
          <div className="flex items-center gap-2">
            <button
              onClick={cancel}
              className="px-2.5 py-1 text-xs font-medium rounded-md text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 border border-stone-200 dark:border-stone-700"
            >
              Cancel
            </button>
            <button
              onClick={save}
              className="px-2.5 py-1 text-xs font-medium rounded-md bg-emerald-600 text-white hover:bg-emerald-700"
            >
              Save
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 min-w-0">
          {value ? (
            internalHref ? (
              <Link
                href={internalHref}
                className="text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300 truncate"
              >
                {displayValue ?? value}
              </Link>
            ) : isLink && linkPrefix !== undefined ? (
              <a
                href={`${linkPrefix}${value}`}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300 cursor-pointer truncate"
                onClick={(e) => e.stopPropagation()}
              >
                {displayValue ?? value}
              </a>
            ) : (
              <span className="text-xs font-medium text-stone-900 dark:text-stone-100 truncate">
                {displayValue ?? value}
              </span>
            )
          ) : (
            <span className="text-xs text-stone-400 dark:text-stone-500">—</span>
          )}
          {copyable && value && <CopyButton text={value} />}
          <button
            onClick={startEdit}
            className="p-0.5 rounded text-stone-300 dark:text-stone-600 hover:text-stone-500 dark:hover:text-stone-400 opacity-0 group-hover/row:opacity-100 transition-opacity shrink-0"
          >
            <Pencil className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}

/* ── Company autocomplete field ── */

type OrgOption = {
  id: string;
  name: string;
}

function CompanyAutocompleteField({
  value,
  organizationId,
  emails,
  onSave,
  onLinkOrg,
}: {
  value: string | null | undefined;
  organizationId: string | null | undefined;
  emails?: string[] | null;
  onSave: (v: string) => void;
  onLinkOrg: (orgId: string, orgName: string) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(value ?? "");
  const [options, setOptions] = useState<OrgOption[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (editing) inputRef.current?.focus();
  }, [editing]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowDropdown(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  const fetchOptions = (query: string) => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    if (!query.trim()) {
      setOptions([]);
      setShowDropdown(false);
      return;
    }
    debounceRef.current = setTimeout(() => {
      void (async () => {
        try {
          const res = await client.GET("/api/v1/organizations", {
            params: { query: { search: query, page_size: 8 } },
          });
          const orgs = (res.data?.data ?? []) as OrgOption[];
          setOptions(orgs);
          setShowDropdown(orgs.length > 0 || query.trim().length > 0);
        } catch {
          setOptions([]);
        }
      })();
    }, 200);
  };

  const save = () => {
    if (draft !== (value ?? "")) onSave(draft);
    setEditing(false);
    setShowDropdown(false);
  };

  const cancel = () => {
    setDraft(value ?? "");
    setEditing(false);
    setShowDropdown(false);
  };

  const selectOrg = (org: OrgOption) => {
    onLinkOrg(org.id, org.name);
    setEditing(false);
    setShowDropdown(false);
  };

  const startEdit = () => {
    setDraft(value ?? "");
    setEditing(true);
  };

  return (
    <div className="group/row flex items-start justify-between gap-4 py-1.5" ref={wrapperRef}>
      <span className="text-xs text-stone-500 dark:text-stone-400 shrink-0 mt-0.5">Company</span>
      {editing ? (
        <div className="flex flex-col items-end gap-1.5 min-w-0 flex-1 relative">
          <input
            ref={inputRef}
            value={draft}
            onChange={(e) => {
              setDraft(e.target.value);
              fetchOptions(e.target.value);
            }}
            onKeyDown={(e) => {
              if (e.key === "Enter") save();
              if (e.key === "Escape") cancel();
            }}
            className="w-full text-xs border border-stone-300 dark:border-stone-700 rounded-md px-2.5 py-1.5 focus:outline-none focus:ring-2 focus:ring-teal-400 focus:border-teal-400 bg-white dark:bg-stone-800 text-stone-900 dark:text-stone-100"
            autoComplete="off"
          />
          {showDropdown && (
            <div className="absolute top-full left-0 right-0 mt-1 bg-white dark:bg-stone-900 border border-stone-200 dark:border-stone-700 rounded-lg shadow-lg z-50 max-h-48 overflow-y-auto">
              {options.map((org) => (
                <button
                  key={org.id}
                  onClick={() => selectOrg(org)}
                  className="w-full text-left px-3 py-2 text-xs hover:bg-teal-50 dark:hover:bg-teal-950 flex items-center gap-2 transition-colors"
                >
                  <Building2 className="w-3 h-3 text-stone-400 dark:text-stone-500 shrink-0" />
                  <span className="text-stone-900 dark:text-stone-100 truncate">{org.name}</span>
                </button>
              ))}
              {draft.trim() &&
                !options.some((o) => o.name.toLowerCase() === draft.toLowerCase()) && (
                  <button
                    onClick={save}
                    className="w-full text-left px-3 py-2 text-xs hover:bg-emerald-50 dark:hover:bg-emerald-950 flex items-center gap-2 border-t border-stone-100 dark:border-stone-800 transition-colors"
                  >
                    <Plus className="w-3 h-3 text-emerald-500 shrink-0" />
                    <span className="text-emerald-700 dark:text-emerald-400">Set as &quot;{draft.trim()}&quot;</span>
                  </button>
                )}
            </div>
          )}
          <div className="flex items-center gap-2">
            <button
              onClick={cancel}
              className="px-2.5 py-1 text-xs font-medium rounded-md text-stone-600 dark:text-stone-300 hover:bg-stone-100 dark:hover:bg-stone-800 border border-stone-200 dark:border-stone-700"
            >
              Cancel
            </button>
            <button
              onClick={save}
              className="px-2.5 py-1 text-xs font-medium rounded-md bg-emerald-600 text-white hover:bg-emerald-700"
            >
              Save
            </button>
          </div>
        </div>
      ) : (
        <div className="flex items-center gap-1.5 min-w-0">
          {value ? (
            <>
              <CompanyFavicon emails={emails} size="w-3.5 h-3.5" />
              {organizationId ? (
                <Link
                  href={`/organizations/${organizationId}`}
                  className="text-xs font-medium text-teal-600 dark:text-teal-400 hover:text-teal-700 dark:hover:text-teal-300 truncate"
                >
                  {value}
                </Link>
              ) : (
                <span className="text-xs font-medium text-stone-900 dark:text-stone-100 truncate">{value}</span>
              )}
            </>
          ) : (
            <span className="text-xs text-stone-400 dark:text-stone-500">—</span>
          )}
          <button
            onClick={startEdit}
            className="p-0.5 rounded text-stone-300 dark:text-stone-600 hover:text-stone-500 dark:hover:text-stone-400 opacity-0 group-hover/row:opacity-100 transition-opacity shrink-0"
          >
            <Pencil className="w-3 h-3" />
          </button>
        </div>
      )}
    </div>
  );
}


/* ── Details Panel ── */

export function DetailsPanel({
  contact,
  onSaveField,
  onLinkOrg,
  onExtractBio,
  isExtracting,
}: {
  contact: Contact;
  onSaveField: (field: string, value: string | string[]) => void;
  onLinkOrg: (orgId: string, orgName: string) => void;
  onExtractBio?: () => void;
  isExtracting?: boolean;
}) {
  const { user } = useAuth();
  const hasBios = Boolean(
    contact.twitter_bio || contact.telegram_bio || contact.full_name
  );

  // Construct BCC address: user's email with +hash suffix
  const bccAddress = (() => {
    if (!contact.bcc_hash || !user?.email) return null;
    const [local, domain] = user.email.split("@");
    if (!local || !domain) return null;
    return `${local}+${contact.bcc_hash}@${domain}`;
  })();

  return (
    <div className="bg-white dark:bg-stone-900 rounded-xl border border-stone-200 dark:border-stone-700 p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-sm font-semibold text-stone-900 dark:text-stone-100">Contact Details</h3>
        {hasBios && onExtractBio && (
          <button
            onClick={onExtractBio}
            disabled={isExtracting}
            title="Extract details from bios"
            className={cn(
              "p-1.5 rounded-lg transition-all",
              isExtracting
                ? "text-amber-500 animate-pulse"
                : "text-stone-400 dark:text-stone-500 hover:text-amber-500 dark:hover:text-amber-400 hover:bg-amber-50 dark:hover:bg-amber-950"
            )}
          >
            <Wand2 className="w-4 h-4" />
          </button>
        )}
      </div>
      <div className="space-y-0.5">
        <InlineField
          label="First name"
          value={contact.given_name}
          onSave={(v) => onSaveField("given_name", v)}
        />
        <InlineField
          label="Last name"
          value={contact.family_name}
          onSave={(v) => onSaveField("family_name", v)}
        />
        <InlineField
          label="Title"
          value={contact.title}
          onSave={(v) => onSaveField("title", v)}
        />
        <CompanyAutocompleteField
          value={contact.company}
          organizationId={contact.organization_id}
          emails={contact.emails}
          onSave={(v) => onSaveField("company", v)}
          onLinkOrg={onLinkOrg}
        />
        <InlineField
          label="Location"
          value={contact.location}
          onSave={(v) => onSaveField("location", v)}
          internalHref={
            contact.latitude != null && contact.longitude != null
              ? `/map?focus=${contact.id}`
              : undefined
          }
        />
        <InlineField
          label="Birthday"
          value={contact.birthday}
          onSave={(v) => onSaveField("birthday", v)}
        />

        <div className="my-2 h-px bg-stone-100 dark:bg-stone-800" />

        <InlineListField
          label="Email"
          values={contact.emails ?? []}
          onSave={(v) => onSaveField("emails", v)}
          copyable
          isLink
          linkPrefix="mailto:"
        />
        {bccAddress && <BccAddressRow address={bccAddress} />}
        <InlineField
          label="Telegram"
          value={contact.telegram_username}
          onSave={(v) => onSaveField("telegram_username", v)}
          copyable
          isLink
          linkPrefix="https://t.me/"
        />
        {contact.telegram_last_seen_at && (
          <div className="flex items-center justify-between py-1.5 px-1 text-xs text-stone-400 dark:text-stone-500 -mt-1">
            <span>Last seen</span>
            <span>{formatDistanceToNow(new Date(contact.telegram_last_seen_at), { addSuffix: true })}</span>
          </div>
        )}
        <InlineField
          label="Twitter"
          value={contact.twitter_handle}
          onSave={(v) => onSaveField("twitter_handle", v)}
          copyable
          isLink
          linkPrefix="https://x.com/"
        />
        <InlineField
          label="LinkedIn"
          value={contact.linkedin_url}
          displayValue={contact.linkedin_url
            ?.replace(/^https?:\/\/(www\.)?linkedin\.com\/in\//, "")
            ?.replace(/\/$/, "")}
          onSave={(v) => onSaveField("linkedin_url", v)}
          isLink
          linkPrefix=""
          copyable
        />
        <InlineField
          label="Facebook"
          value={contact.facebook_id}
          displayValue={contact.facebook_name ?? contact.facebook_id ?? undefined}
          onSave={(v) => onSaveField("facebook_id", v)}
          isLink
          linkPrefix="https://facebook.com/"
          copyable
        />
        <InlineField
          label="Instagram"
          value={contact.instagram_username}
          displayValue={contact.instagram_username ? `@${contact.instagram_username}` : undefined}
          onSave={(v) => onSaveField("instagram_username", v)}
          isLink
          linkPrefix="https://instagram.com/"
          copyable
        />
        <InlineListField
          label="Phone"
          values={contact.phones ?? []}
          onSave={(v) => onSaveField("phones", v)}
          copyable
          isLink
          linkPrefix="tel:"
          valueIcon={(phone) => {
            if (!contact.whatsapp_phone) return null;
            // Match if phone is a suffix of the WhatsApp number (country code mismatch)
            const waDigits = contact.whatsapp_phone.replace(/\D/g, "");
            const phoneDigits = phone.replace(/\D/g, "");
            if (!waDigits.endsWith(phoneDigits) && !phoneDigits.endsWith(waDigits)) return null;
            return (
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" className="shrink-0" aria-label="WhatsApp">
                <path d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.298-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347z" fill="#25D366"/>
                <path d="M12 2C6.477 2 2 6.477 2 12c0 1.89.525 3.66 1.438 5.168L2 22l4.832-1.438A9.955 9.955 0 0012 22c5.523 0 10-4.477 10-10S17.523 2 12 2z" stroke="#25D366" strokeWidth="2" fill="none"/>
              </svg>
            );
          }}
        />
      </div>
    </div>
  );
}
