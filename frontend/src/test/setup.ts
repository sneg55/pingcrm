import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
});

// Mock next/navigation
vi.mock("next/navigation", () => ({
  useSearchParams: vi.fn(() => ({
    get: vi.fn(() => null),
  })),
  useRouter: vi.fn(() => ({
    push: vi.fn(),
    replace: vi.fn(),
    back: vi.fn(),
  })),
  usePathname: vi.fn(() => "/dashboard"),
  useParams: vi.fn(() => ({})),
}));

// Mock next/link as a simple anchor
vi.mock("next/link", () => ({
  default: ({ children, href, ...rest }: Record<string, unknown>) => {
    const { createElement } = require("react");
    return createElement("a", { href, ...rest }, children);
  },
}));

// Mock lucide-react icons as simple spans
vi.mock("lucide-react", () => {
  const icon = (name: string) => {
    const Component = (props: Record<string, unknown>) => {
      const { children, ...rest } = props;
      return `<span data-testid="icon-${name}" ${Object.entries(rest).map(([k, v]) => `${k}="${v}"`).join(" ")}>${children || ""}</span>`;
    };
    Component.displayName = name;
    return Component;
  };

  // Return actual React components instead of string-returning functions
  const { createElement } = require("react");
  const makeIcon = (name: string) => {
    const Comp = (props: Record<string, unknown>) =>
      createElement("span", { "data-testid": `icon-${name}`, ...props });
    Comp.displayName = name;
    return Comp;
  };

  return {
    // settings page
    Mail: makeIcon("Mail"),
    MessageCircle: makeIcon("MessageCircle"),
    Twitter: makeIcon("Twitter"),
    RefreshCw: makeIcon("RefreshCw"),
    Check: makeIcon("Check"),
    AlertCircle: makeIcon("AlertCircle"),
    CheckCircle2: makeIcon("CheckCircle2"),
    X: makeIcon("X"),
    Clock: makeIcon("Clock"),
    Calendar: makeIcon("Calendar"),
    // timeline + editable-field
    FileText: makeIcon("FileText"),
    Plus: makeIcon("Plus"),
    Pencil: makeIcon("Pencil"),
    // nav
    Menu: makeIcon("Menu"),
    LayoutDashboard: makeIcon("LayoutDashboard"),
    Users: makeIcon("Users"),
    Sparkles: makeIcon("Sparkles"),
    GitMerge: makeIcon("GitMerge"),
    Settings: makeIcon("Settings"),
    Bell: makeIcon("Bell"),
    LogOut: makeIcon("LogOut"),
    ChevronDown: makeIcon("ChevronDown"),
    // contacts pages
    Search: makeIcon("Search"),
    UserCircle: makeIcon("UserCircle"),
    ArrowLeft: makeIcon("ArrowLeft"),
    User: makeIcon("User"),
    Phone: makeIcon("Phone"),
    Building2: makeIcon("Building2"),
    Briefcase: makeIcon("Briefcase"),
    Tag: makeIcon("Tag"),
    AtSign: makeIcon("AtSign"),
    // other
    AlertTriangle: makeIcon("AlertTriangle"),
    Upload: makeIcon("Upload"),
    CheckCircle: makeIcon("CheckCircle"),
    Send: makeIcon("Send"),
    TrendingUp: makeIcon("TrendingUp"),
    Activity: makeIcon("Activity"),
    CheckCheck: makeIcon("CheckCheck"),
    ScanSearch: makeIcon("ScanSearch"),
    Filter: makeIcon("Filter"),
    ArrowDown: makeIcon("ArrowDown"),
    ArrowUp: makeIcon("ArrowUp"),
    Archive: makeIcon("Archive"),
    CheckSquare: makeIcon("CheckSquare"),
    ChevronRight: makeIcon("ChevronRight"),
    ChevronUp: makeIcon("ChevronUp"),
    Globe: makeIcon("Globe"),
    MapPin: makeIcon("MapPin"),
    Cake: makeIcon("Cake"),
    MoreVertical: makeIcon("MoreVertical"),
    UserPlus: makeIcon("UserPlus"),
    Trash2: makeIcon("Trash2"),
    ExternalLink: makeIcon("ExternalLink"),
    Link2: makeIcon("Link2"),
    Linkedin: makeIcon("Linkedin"),
    // contacts/archive
    ArchiveRestore: makeIcon("ArchiveRestore"),
    ChevronLeft: makeIcon("ChevronLeft"),
    // contacts/page
    SlidersHorizontal: makeIcon("SlidersHorizontal"),
    ArrowUpDown: makeIcon("ArrowUpDown"),
    SearchX: makeIcon("SearchX"),
    // dashboard
    HeartPulse: makeIcon("HeartPulse"),
    Plug: makeIcon("Plug"),
    FileDown: makeIcon("FileDown"),
    // identity
    HelpCircle: makeIcon("HelpCircle"),
    BarChart2: makeIcon("BarChart2"),
    Zap: makeIcon("Zap"),
    // notifications
    ArrowRight: makeIcon("ArrowRight"),
    // suggestions
    Timer: makeIcon("Timer"),
    TimerOff: makeIcon("TimerOff"),
    CalendarClock: makeIcon("CalendarClock"),
    // contacts/[id] + settings
    Save: makeIcon("Save"),
    Key: makeIcon("Key"),
    History: makeIcon("History"),
    Unplug: makeIcon("Unplug"),
    Download: makeIcon("Download"),
    Camera: makeIcon("Camera"),
    // tag-taxonomy-panel
    Loader2: makeIcon("Loader2"),
    Wand2: makeIcon("Wand2"),
    RotateCcw: makeIcon("RotateCcw"),
    // organizations page
    BarChart3: makeIcon("BarChart3"),
    MessageSquare: makeIcon("MessageSquare"),
    // contacts/[id] detail (multi-select icons)
    Minus: makeIcon("Minus"),
    Copy: makeIcon("Copy"),
    StickyNote: makeIcon("StickyNote"),
  };
});
