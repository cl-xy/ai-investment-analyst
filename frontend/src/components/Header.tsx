export default function Header() {
  return (
    <header className="bg-gray-900 text-white px-6 py-5 shadow-lg">
      <div className="max-w-6xl mx-auto flex items-center gap-3">
        <span className="text-2xl">📈</span>
        <div>
          <h1 className="text-xl font-bold tracking-tight">Investment Analyst</h1>
          <p className="text-gray-400 text-sm">AI-powered stock analysis based on news, fundamentals & SEC filings</p>
        </div>
      </div>
    </header>
  )
}
