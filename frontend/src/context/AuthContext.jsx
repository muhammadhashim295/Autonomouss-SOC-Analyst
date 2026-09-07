import { createContext, useContext, useState, useEffect, useCallback } from 'react'
import {
  login as apiLogin,
  getMe as apiGetMe,
  getOrganizations as apiGetOrganizations,
  setAuthSession,
  clearAuthSession,
  getAuthToken,
} from '../utils/api'

const AuthContext = createContext(null)

export const PRESET_ACCOUNTS = [
  {
    key: 'client',
    name: '1-Click Test Client',
    email: 'client@soc.local',
    password: 'Client@SOC2026!',
    role: 'client',
    orgCode: 'UBL',
    sector: 'FINANCIAL SECTOR',
    badge: 'Test Client Analyst | UBL Enclave',
    color: 'emerald',
  },
  {
    key: 'admin',
    name: '1-Click SOC Admin',
    email: 'admin@soc.local',
    password: 'Admin@SOC2026!',
    role: 'admin',
    badge: 'Cross-Org Super Admin (Global)',
    color: 'purple',
  },
  {
    key: 'ubl',
    name: 'UBL Digital Bank',
    email: 'ubl-analyst@ubl.com.pk',
    password: 'UBL@Analyst2026!',
    role: 'client',
    orgCode: 'UBL',
    sector: 'FINANCIAL SECTOR',
    badge: 'UBL Digital Bank | Financial Sector',
    color: 'emerald',
  },
  {
    key: 'indus',
    name: 'Indus Health Network',
    email: 'indus-analyst@indus.health',
    password: 'Indus@Analyst2026!',
    role: 'client',
    orgCode: 'INDUS',
    sector: 'HEALTHCARE SECTOR',
    badge: 'Indus Health Network | Healthcare Sector',
    color: 'cyan',
  },
  {
    key: 'smiu',
    name: 'Sindh Madressatul Islam Univ.',
    email: 'smiu-analyst@smiu.edu.pk',
    password: 'SMIU@Analyst2026!',
    role: 'client',
    orgCode: 'SMIU',
    sector: 'EDUCATION SECTOR',
    badge: 'Sindh Madressatul Islam | Education Sector',
    color: 'amber',
  },
]

export function AuthProvider({ children }) {
  const [currentUser, setCurrentUser] = useState(null)
  const [organizations, setOrganizations] = useState([])
  const [selectedOrgId, setSelectedOrgId] = useState('ALL')
  const [isLoginModalOpen, setIsLoginModalOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  // Fetch organizations list on mount
  useEffect(() => {
    async function loadOrgs() {
      try {
        const orgs = await apiGetOrganizations()
        setOrganizations(orgs || [])
      } catch (err) {
        console.warn('Could not load organizations list:', err)
      }
    }
    loadOrgs()
  }, [])

  // Restore session from token on mount
  useEffect(() => {
    async function restoreSession() {
      const token = getAuthToken()
      if (!token) {
        setLoading(false)
        return
      }
      try {
        const me = await apiGetMe()
        const userCtx = {
          ...me,
          is_admin: me.role === 'admin' || me.is_admin === true,
          is_client: me.role === 'client' || me.is_client === true,
        }
        setCurrentUser(userCtx)
        if (userCtx.is_client && userCtx.org_id) {
          setSelectedOrgId(userCtx.org_id)
        }
      } catch (err) {
        console.warn('Session expired or invalid, clearing:', err)
        clearAuthSession()
        setCurrentUser(null)
      } finally {
        setLoading(false)
      }
    }
    restoreSession()
  }, [])

  const handleLogin = useCallback(async (email, password) => {
    setError(null)
    setLoading(true)
    try {
      const res = await apiLogin(email, password)
      const { access_token, user, profile, organization } = res
      setAuthSession(access_token, user, profile, organization)

      const userCtx = {
        id: user.id,
        email: user.email,
        role: profile.role,
        is_admin: profile.role === 'admin',
        is_client: profile.role === 'client',
        org_id: profile.org_id,
        org_code: organization?.code || user?.user_metadata?.org_code,
        org_name: organization?.name,
        sector: organization?.sector,
      }

      setCurrentUser(userCtx)
      if (userCtx.role === 'client' && userCtx.org_id) {
        setSelectedOrgId(userCtx.org_id)
      } else {
        setSelectedOrgId('ALL')
      }
      setIsLoginModalOpen(false)
      return userCtx
    } catch (err) {
      setError(err.message || 'Login failed')
      throw err
    } finally {
      setLoading(false)
    }
  }, [])

  const handleLogout = useCallback(() => {
    clearAuthSession()
    setCurrentUser(null)
    setSelectedOrgId('ALL')
  }, [])

  const quickSwitch = useCallback(
    async (roleKey) => {
      const target = PRESET_ACCOUNTS.find((a) => a.key === roleKey)
      if (!target) return
      return handleLogin(target.email, target.password)
    },
    [handleLogin]
  )

  const value = {
    currentUser,
    organizations,
    selectedOrgId,
    setSelectedOrgId,
    isLoginModalOpen,
    setIsLoginModalOpen,
    login: handleLogin,
    logout: handleLogout,
    quickSwitch,
    loading,
    error,
    setError,
  }

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
