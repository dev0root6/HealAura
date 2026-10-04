import { useEffect, useState } from 'react'
import { fetchMe, getToken, logout } from './api'
import type { User } from './api'
import BootScreen from './components/BootScreen'
import Landing from './components/Landing'
import Login from './components/Login'
import Signup from './components/Signup'
import AppShell from './components/AppShell'

type View = 'landing' | 'login' | 'signup' | 'app'

// Read once per page load (not per render, and not twice under StrictMode):
// the full loading screen plays on the first visit of a browser session.
const FIRST_VISIT = (() => {
  try {
    const seen = sessionStorage.getItem('healaura:splash') === '1'
    sessionStorage.setItem('healaura:splash', '1')
    return !seen
  } catch {
    return true
  }
})()

export default function App() {
  const [user, setUser] = useState<User | null>(null)
  const [view, setView] = useState<View>('landing')
  const [booting, setBooting] = useState(true)
  // The loading screen gets a moment to breathe on the first visit of a
  // session, and a quick fade after that. It then plays its exit.
  const [minShown, setMinShown] = useState(false)
  const [splashGone, setSplashGone] = useState(false)

  useEffect(() => {
    const id = setTimeout(() => setMinShown(true), FIRST_VISIT ? 2600 : 700)
    return () => clearTimeout(id)
  }, [])

  const ready = !booting && minShown
  useEffect(() => {
    if (!ready) return
    const id = setTimeout(() => setSplashGone(true), 600)
    return () => clearTimeout(id)
  }, [ready])

  // Resume an existing session on load.
  useEffect(() => {
    if (!getToken()) {
      setBooting(false)
      return
    }
    fetchMe()
      .then((u) => {
        setUser(u)
        setView('app')
      })
      .catch(() => {
        /* stale/invalid token — fall back to landing */
      })
      .finally(() => setBooting(false))
  }, [])

  function handleLoggedIn(u: User) {
    setUser(u)
    setView('app')
  }

  async function handleLogout() {
    await logout()
    setUser(null)
    setView('landing')
  }

  let content
  if (view === 'app' && user) {
    content = <AppShell user={user} onLogout={handleLogout} />
  } else if (view === 'login') {
    content = (
      <Login
        onLoggedIn={handleLoggedIn}
        onBack={() => setView('landing')}
        onSignUp={() => setView('signup')}
      />
    )
  } else if (view === 'signup') {
    content = (
      <Signup
        onSignedUp={handleLoggedIn}
        onBack={() => setView('landing')}
        onSignIn={() => setView('login')}
      />
    )
  } else {
    content = <Landing onSignIn={() => setView('login')} onSignUp={() => setView('signup')} />
  }

  if (!ready) return <BootScreen />
  return (
    <>
      {!splashGone && <BootScreen leaving />}
      {content}
    </>
  )
}
