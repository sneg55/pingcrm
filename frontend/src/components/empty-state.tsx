import { type LucideIcon } from "lucide-react";

type EmptyStateProps = {
  icon?: LucideIcon;
  title: string;
  description?: string;
  action?: {
    label: string;
    href?: string;
    onClick?: () => void;
  };
}

export function EmptyState({ icon: Icon, title, description, action }: EmptyStateProps) {
  return (
    <div className="flex flex-col items-center justify-center py-16 px-4">
      {Icon && <Icon className="w-12 h-12 text-gray-300 dark:text-gray-600 mb-4" />}
      <h3 className="text-base font-medium text-gray-900 dark:text-stone-100 mb-1">{title}</h3>
      {description && (
        <p className="text-sm text-gray-500 dark:text-stone-400 mb-4 text-center max-w-sm">{description}</p>
      )}
      {action && (
        action.href ? (
          <a
            href={action.href}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          >
            {action.label}
          </a>
        ) : (
          <button
            onClick={action.onClick}
            className="px-4 py-2 text-sm font-medium rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition-colors"
          >
            {action.label}
          </button>
        )
      )}
    </div>
  );
}
