'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';

export default function LoginPage() {
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const router = useRouter();
  
  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError('');
    setLoading(true);
    
    const res = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password }),
    });
    
    if (res.ok) {
      router.push('/');
      router.refresh();
    } else {
      setError('Invalid password');
      setLoading(false);
    }
  }
  
  return (
    <div className="min-h-screen flex items-center justify-center px-4">
      <form onSubmit={handleSubmit} className="bg-white rounded-lg shadow-lg p-8 w-full max-w-md">
        <h1 className="text-2xl font-bold mb-1" style={{ color: 'var(--usdm-blue)' }}>
          Vault-Glean Admin
        </h1>
        <p className="text-sm text-gray-600 mb-6">USDM Quality Vault integration console</p>
        
        <label className="block">
          <span className="text-sm font-medium text-gray-700">Admin Password</span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 shadow-sm focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
            autoFocus
          />
        </label>
        
        {error && <p className="text-red-600 text-sm mt-3">{error}</p>}
        
        <button
          type="submit"
          disabled={loading}
          className="mt-6 w-full rounded-md py-2 px-4 text-white font-medium disabled:opacity-50"
          style={{ backgroundColor: 'var(--usdm-blue)' }}
        >
          {loading ? 'Signing in...' : 'Sign in'}
        </button>
      </form>
    </div>
  );
}
