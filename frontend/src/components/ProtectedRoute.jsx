import React from 'react'
import { Navigate, useLocation, useParams } from 'react-router-dom'
import { useAuth } from '../context/AuthContext'

/**
 * ProtectedRoute — Strict Zero-Trust Enclave Guard
 *
 * Rules:
 * 1. Unauthenticated users cannot view ANY command center or dashboard -> Redirect to /login
 * 2. Client vendors can ONLY view their own designated command center:
 *    - Visiting /dashboard (admin-only) -> Redirect to /orchestration/:org_code
 *    - Visiting un-scoped /orchestration -> Redirect to /orchestration/:org_code
 *    - Visiting /orchestration/:client of ANOTHER vendor -> Redirect to /orchestration/:org_code
 * 3. Super Admins (role: 'admin') can access /dashboard and oversee enclaves
 */
export default function ProtectedRoute({ children, requireAdmin = false }) {
  const { currentUser, loading } = useAuth()
  const location = useLocation()
  const { client } = useParams()

  // 1. Session verification in progress
  if (loading) {
    return (
      <div className="min-h-screen bg-[#02050b] flex flex-col items-center justify-center text-slate-100 font-mono space-y-4">
        <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-emerald-500 to-teal-700 flex items-center justify-center shadow-[0_0_20px_rgba(16,185,129,0.4)] animate-pulse">
          <span className="font-bold text-white text-sm">PS</span>
        </div>
        <div className="flex items-center gap-2 text-xs text-emerald-400">
          <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping" />
          <span>VERIFYING SESSION...</span>
        </div>
      </div>
    )
  }

  // 2. Unauthenticated: Strictly no public access to any command center
  if (!currentUser) {
    return <Navigate to="/login" replace state={{ from: location }} />
  }

  const isClient = currentUser.role === 'client' || currentUser.is_client
  const isAdmin = currentUser.role === 'admin' || currentUser.is_admin
  const userOrgCode = (currentUser.org_code || '').toLowerCase()

  // 3. Admin-only Route Check (e.g. /dashboard)
  if (requireAdmin && !isAdmin) {
    // Authorized vendor trying to access cross-tenant dashboard: force to their own enclave
    const fallbackPath = userOrgCode ? `/orchestration/${userOrgCode}` : '/login'
    return <Navigate to={fallbackPath} replace />
  }

  // 4. Client Vendor Isolation Check for Orchestration routes
  if (isClient && userOrgCode) {
    // If on /orchestration without :client parameter, force to their own enclave
    if (!client) {
      return <Navigate to={`/orchestration/${userOrgCode}`} replace />
    }

    // If client attempts to view another vendor's enclave URL
    const urlClient = client.toLowerCase()
    const isSelfEnclave =
      urlClient === userOrgCode ||
      (userOrgCode === 'ubl' && urlClient.includes('ubl')) ||
      (userOrgCode === 'indus' && urlClient.includes('indus')) ||
      (userOrgCode === 'smiu' && urlClient.includes('smiu'))

    if (!isSelfEnclave) {
      // Strictly prevent cross-vendor command center snooping
      return <Navigate to={`/orchestration/${userOrgCode}`} replace />
    }
  }

  // 5. Authorized
  return children
}
