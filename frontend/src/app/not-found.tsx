export default function NotFound() {
  return (
    <div className="min-h-screen flex items-center justify-center">
      <div className="text-center">
        <h2 className="text-2xl font-bold mb-4">Page Not Found</h2>
        <p className="text-gray-600 mb-4">Could not find the requested page.</p>
        <a
          href="/"
          className="px-4 py-2 bg-blue-600 text-white rounded hover:bg-blue-700 inline-block"
        >
          Go Home
        </a>
      </div>
    </div>
  )
}
