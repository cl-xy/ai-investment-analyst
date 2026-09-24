import { useState } from 'react'
import { Lock } from 'lucide-react'
import { useAuthStore } from '../stores/authStore'

export default function LoginPage() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const { login, loading, error } = useAuthStore()

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!username || !password) return
    await login(username, password)
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg)] px-4">
      <form
        onSubmit={handleSubmit}
        className="w-full max-w-sm bg-[var(--surface)] border border-[var(--border)] rounded-xl p-6 shadow-sm"
      >
        <div className="flex flex-col items-center gap-2 mb-6">
          <div className="w-10 h-10 rounded-full bg-[var(--accent)]/10 flex items-center justify-center">
            <Lock className="w-5 h-5 text-[var(--accent)]" />
          </div>
          <h1 className="text-lg font-semibold text-[var(--text-primary)]">Sign in</h1>
          <p className="text-sm text-[var(--text-muted)] text-center">
            Investment Analyst is a private demo. Sign in to continue.
          </p>
        </div>

        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1" htmlFor="username">
          Username
        </label>
        <input
          id="username"
          type="text"
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="admin"
          className="w-full mb-4 text-sm border border-[var(--border)] bg-[var(--bg)] rounded-lg px-3 py-2 text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] transition-shadow"
        />

        <label className="block text-sm font-medium text-[var(--text-secondary)] mb-1" htmlFor="password">
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          className="w-full mb-4 text-sm border border-[var(--border)] bg-[var(--bg)] rounded-lg px-3 py-2 text-[var(--text-primary)] placeholder:text-[var(--text-muted)] focus:outline-none focus:ring-2 focus:ring-[var(--ring)] transition-shadow"
        />

        {error && (
          <p className="text-sm text-[var(--danger,#dc2626)] mb-4" role="alert">
            {error}
          </p>
        )}

        <button
          type="submit"
          disabled={loading || !username || !password}
          className="w-full py-2 rounded-lg bg-[var(--accent)] text-white text-sm font-medium disabled:opacity-50 disabled:cursor-not-allowed hover:opacity-90 transition-opacity"
        >
          {loading ? 'Signing in…' : 'Sign in'}
        </button>

        <p className="text-xs text-[var(--text-muted)] text-center mt-4">
          Default credentials: <code>admin</code> / <code>investor2026</code>
        </p>
      </form>
    </div>
  )
}
