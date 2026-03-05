import Link from "next/link";

export default function HomePage() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center bg-gray-50 px-4">
      <div className="text-center max-w-2xl">
        <h1 className="text-5xl font-bold text-gray-900 mb-4">Ping CRM</h1>
        <p className="text-xl text-gray-600 mb-10">
          Your AI-powered networking assistant
        </p>
        <div className="flex gap-4 justify-center">
          <Link
            href="/contacts"
            className="inline-flex items-center px-6 py-3 rounded-lg bg-blue-600 text-white font-medium hover:bg-blue-700 transition-colors"
          >
            View Contacts
          </Link>
          <Link
            href="/dashboard"
            className="inline-flex items-center px-6 py-3 rounded-lg bg-white text-gray-800 font-medium border border-gray-300 hover:bg-gray-100 transition-colors"
          >
            Dashboard
          </Link>
        </div>
      </div>
    </main>
  );
}
